#include "infrared_remote.h"
#include "../echo/echo_file_save.h"

#include <m-array.h>

#include <toolbox/m_cstr_dup.h>
#include <toolbox/path.h>
#include <storage/storage.h>

#define TAG "InfraredRemote"

#define INFRARED_FILE_HEADER    "IR signals file"
#define INFRARED_LIBRARY_HEADER "IR library file"
#define INFRARED_FILE_VERSION   (1)

ARRAY_DEF(StringArray, const char*, M_CSTR_DUP_OPLIST); //-V575

struct InfraredRemote {
    StringArray_t signal_names;
    FuriString* name;
    FuriString* path;
    FuriString* recovery_path;
};

typedef struct {
    InfraredRemote* remote;
    FlipperFormat* ff_in;
    FlipperFormat* ff_out;
    FuriString* signal_name;
    InfraredSignal* signal;
    size_t signal_index;
} InfraredBatch;

typedef struct {
    size_t signal_index;
    size_t source_index;
    const char* signal_name;
    const InfraredSignal* signal;
} InfraredBatchTarget;

typedef InfraredErrorCode (
    *InfraredBatchCallback)(const InfraredBatch* batch, const InfraredBatchTarget* target);

InfraredRemote* infrared_remote_alloc(void) {
    InfraredRemote* remote = malloc(sizeof(InfraredRemote));
    StringArray_init(remote->signal_names);
    remote->name = furi_string_alloc();
    remote->path = furi_string_alloc();
    remote->recovery_path = furi_string_alloc();
    return remote;
}

void infrared_remote_free(InfraredRemote* remote) {
    StringArray_clear(remote->signal_names);
    furi_string_free(remote->recovery_path);
    furi_string_free(remote->path);
    furi_string_free(remote->name);
    free(remote);
}

void infrared_remote_reset(InfraredRemote* remote) {
    StringArray_reset(remote->signal_names);
    furi_string_reset(remote->name);
    furi_string_reset(remote->path);
}

const char* infrared_remote_get_name(const InfraredRemote* remote) {
    return furi_string_get_cstr(remote->name);
}

static void infrared_remote_set_path(InfraredRemote* remote, const char* path) {
    furi_string_set(remote->path, path);
    path_extract_filename(remote->path, remote->name, true);
}

const char* infrared_remote_get_path(const InfraredRemote* remote) {
    return furi_string_get_cstr(remote->path);
}

size_t infrared_remote_get_signal_count(const InfraredRemote* remote) {
    return StringArray_size(remote->signal_names);
}

const char* infrared_remote_get_signal_name(const InfraredRemote* remote, size_t index) {
    furi_assert(index < infrared_remote_get_signal_count(remote));
    return *StringArray_cget(remote->signal_names, index);
}

InfraredErrorCode infrared_remote_load_signal(
    const InfraredRemote* remote,
    InfraredSignal* signal,
    size_t index) {
    furi_assert(index < infrared_remote_get_signal_count(remote));

    Storage* storage = furi_record_open(RECORD_STORAGE);
    FlipperFormat* ff = flipper_format_buffered_file_alloc(storage);

    InfraredErrorCode error = InfraredErrorCodeNone;

    do {
        const char* path = furi_string_get_cstr(remote->path);
        if(!flipper_format_buffered_file_open_existing(ff, path)) {
            error = InfraredErrorCodeFileOperationFailed;
            break;
        }

        error = infrared_signal_search_by_index_and_read(signal, ff, index);
        if(INFRARED_ERROR_PRESENT(error)) {
            const char* signal_name = infrared_remote_get_signal_name(remote, index);
            FURI_LOG_E(TAG, "Failed to load signal '%s' from file '%s'", signal_name, path);
            break;
        }
    } while(false);

    flipper_format_free(ff);
    furi_record_close(RECORD_STORAGE);

    return error;
}

bool infrared_remote_get_signal_index(
    const InfraredRemote* remote,
    const char* name,
    size_t* index) {
    uint32_t i = 0;
    StringArray_it_t it;

    for(StringArray_it(it, remote->signal_names); !StringArray_end_p(it);
        StringArray_next(it), ++i) {
        if(strcmp(*StringArray_cref(it), name) == 0) {
            *index = i;
            return true;
        }
    }

    return false;
}

void infrared_remote_take_recovery_path(InfraredRemote* remote, FuriString* path) {
    furi_string_set(path, remote->recovery_path);
    furi_string_reset(remote->recovery_path);
}

typedef struct {
    InfraredBatch batch;
    InfraredBatchCallback callback;
    const InfraredBatchTarget* target;
    InfraredErrorCode error;
} InfraredBatchWrite;

static bool infrared_remote_batch_write(const char* path, void* context) {
    InfraredBatchWrite* write = context;
    InfraredBatch* batch = &write->batch;
    const InfraredBatchTarget* target = write->target;
    write->error = InfraredErrorCodeFileOperationFailed;
    do {
        // echo_file_save reserved an empty file; never truncate an unrelated file.
        if(!flipper_format_buffered_file_open_existing(
               batch->ff_in, infrared_remote_get_path(batch->remote)) ||
           !flipper_format_buffered_file_open_existing(batch->ff_out, path))
            break;
        uint32_t version;
        if(!flipper_format_read_header(batch->ff_in, batch->signal_name, &version) ||
           !furi_string_equal(batch->signal_name, INFRARED_FILE_HEADER) ||
           version != INFRARED_FILE_VERSION ||
           !flipper_format_write_header_cstr(
               batch->ff_out, INFRARED_FILE_HEADER, INFRARED_FILE_VERSION))
            break;
        const size_t count = infrared_remote_get_signal_count(batch->remote);
        write->error = InfraredErrorCodeNone;
        for(; batch->signal_index < count; ++batch->signal_index) {
            write->error = infrared_signal_read(batch->signal, batch->ff_in, batch->signal_name);
            if(!INFRARED_ERROR_PRESENT(write->error)) {
                write->error = write->callback(batch, target);
            }
            if(INFRARED_ERROR_PRESENT(write->error)) {
                INFRARED_ERROR_SET_INDEX(write->error, batch->signal_index);
                break;
            }
        }
        // Inserting at count appends in this same staged transaction, including
        // the first signal in an empty remote.
        if(!INFRARED_ERROR_PRESENT(write->error) && target->signal &&
           target->signal_index == count) {
            write->error =
                infrared_signal_save(target->signal, batch->ff_out, target->signal_name);
            if(!INFRARED_ERROR_PRESENT(write->error)) {
                StringArray_push_back(batch->remote->signal_names, target->signal_name);
            }
        }
    } while(false);
    // Close both handles even when the first close fails. A buffered flush error
    // must prevent the staged file from replacing the original.
    bool output_closed = flipper_format_buffered_file_close(batch->ff_out);
    bool input_closed = flipper_format_buffered_file_close(batch->ff_in);
    if(!output_closed || !input_closed) write->error = InfraredErrorCodeFileOperationFailed;
    // Buffered close can fail before closing its underlying file. Release both
    // streams before the staging helper attempts cleanup or rename.
    flipper_format_free(batch->ff_out);
    flipper_format_free(batch->ff_in);
    batch->ff_out = NULL;
    batch->ff_in = NULL;
    return !INFRARED_ERROR_PRESENT(write->error);
}

static InfraredErrorCode infrared_remote_batch_start(
    InfraredRemote* remote,
    InfraredBatchCallback callback,
    const InfraredBatchTarget* target) {
    Storage* storage = furi_record_open(RECORD_STORAGE);
    InfraredBatchWrite write = {
        .batch =
            {
                .remote = remote,
                .ff_in = flipper_format_buffered_file_alloc(storage),
                .ff_out = flipper_format_buffered_file_alloc(storage),
                .signal_name = furi_string_alloc(),
                .signal = infrared_signal_alloc(),
            },
        .callback = callback,
        .target = target,
        .error = InfraredErrorCodeNone,
    };
    StringArray_t prior_names;
    StringArray_init_set(prior_names, remote->signal_names);
    bool saved = echo_file_save(
        storage,
        infrared_remote_get_path(remote),
        true,
        infrared_remote_batch_write,
        &write,
        remote->recovery_path);
    if(!saved) {
        StringArray_set(remote->signal_names, prior_names);
        if(!INFRARED_ERROR_PRESENT(write.error))
            write.error = InfraredErrorCodeFileOperationFailed;
    }
    StringArray_clear(prior_names);
    infrared_signal_free(write.batch.signal);
    furi_string_free(write.batch.signal_name);
    if(write.batch.ff_out) flipper_format_free(write.batch.ff_out);
    if(write.batch.ff_in) flipper_format_free(write.batch.ff_in);
    furi_record_close(RECORD_STORAGE);
    return write.error;
}

InfraredErrorCode infrared_remote_append_signal(
    InfraredRemote* remote,
    const InfraredSignal* signal,
    const char* name) {
    return infrared_remote_insert_signal(
        remote, signal, name, infrared_remote_get_signal_count(remote));
}

static InfraredErrorCode infrared_remote_insert_signal_callback(
    const InfraredBatch* batch,
    const InfraredBatchTarget* target) {
    // Insert a signal under the specified index
    if(batch->signal_index == target->signal_index) {
        InfraredErrorCode error =
            infrared_signal_save(target->signal, batch->ff_out, target->signal_name);
        if(INFRARED_ERROR_PRESENT(error)) return error;

        StringArray_push_at(
            batch->remote->signal_names, target->signal_index, target->signal_name);
    }

    // Write the rest normally
    return infrared_signal_save(
        batch->signal, batch->ff_out, furi_string_get_cstr(batch->signal_name));
}

InfraredErrorCode infrared_remote_insert_signal(
    InfraredRemote* remote,
    const InfraredSignal* signal,
    const char* name,
    size_t index) {
    index = MIN(index, infrared_remote_get_signal_count(remote));

    const InfraredBatchTarget insert_target = {
        .signal_index = index,
        .signal_name = name,
        .signal = signal,
    };

    return infrared_remote_batch_start(
        remote, infrared_remote_insert_signal_callback, &insert_target);
}

static InfraredErrorCode infrared_remote_rename_signal_callback(
    const InfraredBatch* batch,
    const InfraredBatchTarget* target) {
    const char* signal_name;

    if(batch->signal_index == target->signal_index) {
        // Rename the signal at requested index
        signal_name = target->signal_name;
        StringArray_set_at(batch->remote->signal_names, batch->signal_index, signal_name);
    } else {
        // Use the original name otherwise
        signal_name = furi_string_get_cstr(batch->signal_name);
    }

    return infrared_signal_save(batch->signal, batch->ff_out, signal_name);
}

InfraredErrorCode
    infrared_remote_rename_signal(InfraredRemote* remote, size_t index, const char* new_name) {
    furi_assert(index < infrared_remote_get_signal_count(remote));

    const InfraredBatchTarget rename_target = {
        .signal_index = index,
        .signal_name = new_name,
        .signal = NULL,
    };

    return infrared_remote_batch_start(
        remote, infrared_remote_rename_signal_callback, &rename_target);
}

static InfraredErrorCode infrared_remote_delete_signal_callback(
    const InfraredBatch* batch,
    const InfraredBatchTarget* target) {
    if(batch->signal_index == target->signal_index) {
        // Do not save the signal to be deleted, remove it from the signal name list instead
        StringArray_remove_v(
            batch->remote->signal_names, batch->signal_index, batch->signal_index + 1);
    } else {
        // Pass other signals through
        return infrared_signal_save(
            batch->signal, batch->ff_out, furi_string_get_cstr(batch->signal_name));
    }

    return InfraredErrorCodeNone;
}

InfraredErrorCode infrared_remote_delete_signal(InfraredRemote* remote, size_t index) {
    furi_assert(index < infrared_remote_get_signal_count(remote));

    const InfraredBatchTarget delete_target = {
        .signal_index = index,
        .signal_name = NULL,
        .signal = NULL,
    };

    return infrared_remote_batch_start(
        remote, infrared_remote_delete_signal_callback, &delete_target);
}

static InfraredErrorCode infrared_remote_move_signal_callback(
    const InfraredBatch* batch,
    const InfraredBatchTarget* target) {
    InfraredErrorCode error = InfraredErrorCodeNone;
    if(batch->signal_index == target->signal_index &&
       target->source_index > target->signal_index) {
        error = infrared_signal_save(target->signal, batch->ff_out, target->signal_name);
    }
    if(!INFRARED_ERROR_PRESENT(error) && batch->signal_index != target->source_index) {
        error = infrared_signal_save(
            batch->signal, batch->ff_out, furi_string_get_cstr(batch->signal_name));
    }
    if(!INFRARED_ERROR_PRESENT(error) && batch->signal_index == target->signal_index &&
       target->source_index < target->signal_index) {
        error = infrared_signal_save(target->signal, batch->ff_out, target->signal_name);
    }
    return error;
}

InfraredErrorCode
    infrared_remote_move_signal(InfraredRemote* remote, size_t index, size_t new_index) {
    const size_t count = infrared_remote_get_signal_count(remote);
    furi_assert(index < count && new_index < count);
    furi_string_reset(remote->recovery_path);
    if(index == new_index) return InfraredErrorCodeNone;
    InfraredSignal* signal = infrared_signal_alloc();
    char* name = strdup(infrared_remote_get_signal_name(remote, index));
    InfraredErrorCode error = infrared_remote_load_signal(remote, signal, index);
    if(!INFRARED_ERROR_PRESENT(error)) {
        const InfraredBatchTarget target = {
            .signal_index = new_index,
            .source_index = index,
            .signal_name = name,
            .signal = signal,
        };
        error = infrared_remote_batch_start(remote, infrared_remote_move_signal_callback, &target);
        if(!INFRARED_ERROR_PRESENT(error)) {
            StringArray_remove_v(remote->signal_names, index, index + 1);
            StringArray_push_at(remote->signal_names, new_index, name);
        }
    }
    free(name);
    infrared_signal_free(signal);
    return error;
}

typedef struct {
    Storage* storage;
    const InfraredSignal* signal;
    const char* name;
    InfraredErrorCode error;
} InfraredCreate;

static bool infrared_remote_create_write(const char* path, void* context) {
    InfraredCreate* create = context;
    FlipperFormat* ff = flipper_format_buffered_file_alloc(create->storage);
    create->error = InfraredErrorCodeFileOperationFailed;
    do {
        if(!flipper_format_buffered_file_open_existing(ff, path) ||
           !flipper_format_write_header_cstr(ff, INFRARED_FILE_HEADER, INFRARED_FILE_VERSION))
            break;
        create->error = create->signal ? infrared_signal_save(create->signal, ff, create->name) :
                                         InfraredErrorCodeNone;
    } while(false);
    if(!flipper_format_buffered_file_close(ff))
        create->error = InfraredErrorCodeFileOperationFailed;
    flipper_format_free(ff);
    return !INFRARED_ERROR_PRESENT(create->error);
}

InfraredErrorCode infrared_remote_create_with_signal(
    InfraredRemote* remote,
    const char* path,
    const InfraredSignal* signal,
    const char* name) {
    Storage* storage = furi_record_open(RECORD_STORAGE);
    InfraredCreate create = {.storage = storage, .signal = signal, .name = name};
    bool saved = echo_file_save(
        storage, path, false, infrared_remote_create_write, &create, remote->recovery_path);
    if(saved) {
        infrared_remote_reset(remote);
        infrared_remote_set_path(remote, path);
        if(signal) StringArray_push_back(remote->signal_names, name);
    } else if(!INFRARED_ERROR_PRESENT(create.error)) {
        create.error = InfraredErrorCodeFileOperationFailed;
    }
    furi_record_close(RECORD_STORAGE);
    return create.error;
}

InfraredErrorCode infrared_remote_create(InfraredRemote* remote, const char* path) {
    return infrared_remote_create_with_signal(remote, path, NULL, NULL);
}

InfraredErrorCode infrared_remote_load(InfraredRemote* remote, const char* path) {
    FURI_LOG_I(TAG, "Loading file: '%s'", path);

    Storage* storage = furi_record_open(RECORD_STORAGE);
    FlipperFormat* ff = flipper_format_buffered_file_alloc(storage);

    FuriString* tmp = furi_string_alloc();
    InfraredErrorCode error = InfraredErrorCodeNone;

    do {
        if(!flipper_format_buffered_file_open_existing(ff, path)) {
            error = InfraredErrorCodeFileOperationFailed;
            break;
        }

        uint32_t version;
        if(!flipper_format_read_header(ff, tmp, &version)) {
            error = InfraredErrorCodeFileOperationFailed;
            break;
        }

        if(furi_string_equal(tmp, INFRARED_LIBRARY_HEADER)) {
            FURI_LOG_E(TAG, "Library file can't be loaded in this context");
            error = InfraredErrorCodeWrongFileType;
            break;
        }

        if(!furi_string_equal(tmp, INFRARED_FILE_HEADER)) {
            error = InfraredErrorCodeWrongFileType;
            FURI_LOG_E(TAG, "Filetype unknown");
            break;
        }

        if(version != INFRARED_FILE_VERSION) {
            error = InfraredErrorCodeWrongFileVersion;
            FURI_LOG_E(TAG, "Wrong file version");
            break;
        }

        infrared_remote_set_path(remote, path);
        StringArray_reset(remote->signal_names);

        while(infrared_signal_read_name(ff, tmp) == InfraredErrorCodeNone) {
            StringArray_push_back(remote->signal_names, furi_string_get_cstr(tmp));
        }
    } while(false);

    furi_string_free(tmp);
    flipper_format_free(ff);
    furi_record_close(RECORD_STORAGE);

    return error;
}

InfraredErrorCode infrared_remote_rename(InfraredRemote* remote, const char* new_path) {
    const char* old_path = infrared_remote_get_path(remote);

    Storage* storage = furi_record_open(RECORD_STORAGE);
    furi_string_reset(remote->recovery_path);
    bool success;
    if(storage_common_equivalent_path(storage, old_path, new_path)) {
        FileInfo info;
        success = storage_common_stat(storage, old_path, &info) == FSE_OK &&
                  !(info.flags & FSF_DIRECTORY);
    } else {
        success = storage_common_rename_safe(storage, old_path, new_path) == FSE_OK;
    }
    furi_record_close(RECORD_STORAGE);

    if(success) {
        infrared_remote_set_path(remote, new_path);
    }

    return success ? InfraredErrorCodeNone : InfraredErrorCodeFileOperationFailed;
}

InfraredErrorCode infrared_remote_remove(InfraredRemote* remote) {
    Storage* storage = furi_record_open(RECORD_STORAGE);
    const FS_Error status = storage_common_remove(storage, infrared_remote_get_path(remote));
    furi_record_close(RECORD_STORAGE);

    const bool success = (status == FSE_OK || status == FSE_NOT_EXIST);

    if(success) {
        infrared_remote_reset(remote);
    }

    return success ? InfraredErrorCodeNone : InfraredErrorCodeFileOperationFailed;
}
