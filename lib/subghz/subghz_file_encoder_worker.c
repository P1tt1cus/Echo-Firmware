#include "subghz_file_encoder_worker.h"

#include <toolbox/stream/stream.h>
#include <flipper_format/flipper_format.h>
#include <flipper_format/flipper_format_i.h>
#include <lib/subghz/devices/devices.h>
#include <string.h>

#define TAG "SubGhzFileEncoderWorker"

#define SUBGHZ_FILE_ENCODER_LOAD     512
#define SUBGHZ_FILE_ENCODER_MAX_LINE 6144

struct SubGhzFileEncoderWorker {
    FuriThread* thread;
    FuriStreamBuffer* stream;

    Storage* storage;
    FlipperFormat* flipper_format;

    volatile bool worker_running;
    volatile bool worker_stopping;
    volatile bool is_storage_slow;
    volatile bool producer_done;
    volatile bool read_error;
    volatile size_t read_offset;
    size_t file_size;
    FuriString* str_data;
    FuriString* file_path;
    const SubGhzDevice* device;

    SubGhzFileEncoderWorkerCallbackEnd callback_end;
    void* context_end;
};

void subghz_file_encoder_worker_callback_end(
    SubGhzFileEncoderWorker* instance,
    SubGhzFileEncoderWorkerCallbackEnd callback_end,
    void* context_end) {
    furi_assert(instance);
    furi_assert(callback_end);
    instance->callback_end = callback_end;
    instance->context_end = context_end;
}

static bool subghz_file_encoder_worker_add_level_duration(
    SubGhzFileEncoderWorker* instance,
    int32_t duration) {
    while(instance->worker_running) {
        if(furi_stream_buffer_send(instance->stream, &duration, sizeof(duration), 10) ==
           sizeof(duration))
            return true;
    }
    return false;
}

// Validate the entire record before enqueueing any pulse from it. Native RAW
// recordings contain at most 512 non-zero durations per record, under 1 second.
static bool subghz_file_encoder_worker_parse_record(
    SubGhzFileEncoderWorker* instance,
    const char* line,
    bool emit) {
    if(strncmp(line, "RAW_Data:", 9) != 0) return false;
    const char* cursor = line + 9;
    size_t count = 0;
    while(true) {
        while(*cursor == ' ' || *cursor == '\t' || *cursor == '\r')
            cursor++;
        if(!*cursor) return count != 0;
        bool negative = *cursor == '-';
        if(*cursor == '-' || *cursor == '+') cursor++;
        if(*cursor < '0' || *cursor > '9') return false;
        uint32_t magnitude = 0;
        do {
            unsigned digit = *cursor++ - '0';
            if(magnitude > (1000000U - digit) / 10U) return false;
            magnitude = magnitude * 10U + digit;
        } while(*cursor >= '0' && *cursor <= '9');
        if(!magnitude || ++count > SUBGHZ_FILE_ENCODER_LOAD) return false;
        if(*cursor && *cursor != ',' && *cursor != ' ' && *cursor != '\t' && *cursor != '\r')
            return false;
        if(emit && !subghz_file_encoder_worker_add_level_duration(
                       instance, negative ? -(int32_t)magnitude : (int32_t)magnitude))
            return false;
        while(*cursor == ' ' || *cursor == '\t' || *cursor == '\r')
            cursor++;
        if(*cursor == ',') cursor++;
    }
}

bool subghz_file_encoder_worker_data_parse(SubGhzFileEncoderWorker* instance, const char* line) {
    return subghz_file_encoder_worker_parse_record(instance, line, false) &&
           subghz_file_encoder_worker_parse_record(instance, line, true);
}

typedef enum {
    RawLineError,
    RawLineEnd,
    RawLineReady
} RawLineResult;

static RawLineResult subghz_file_encoder_worker_read_line(SubGhzFileEncoderWorker* instance) {
    Stream* stream = flipper_format_get_raw_stream(instance->flipper_format);
    furi_string_reset(instance->str_data);
    uint8_t byte;
    while(instance->worker_running) {
        if(stream_read(stream, &byte, 1) != 1) {
            instance->read_offset = stream_tell(stream);
            if(instance->read_offset < instance->file_size) return RawLineError;
            return furi_string_empty(instance->str_data) ? RawLineEnd : RawLineReady;
        }
        if(byte == '\n') {
            instance->read_offset = stream_tell(stream);
            return RawLineReady;
        }
        if(byte == 0 || furi_string_size(instance->str_data) >= SUBGHZ_FILE_ENCODER_MAX_LINE)
            return RawLineError;
        furi_string_push_back(instance->str_data, byte);
    }
    return RawLineError;
}

static RawLineResult subghz_file_encoder_worker_read_record(SubGhzFileEncoderWorker* instance) {
    RawLineResult result;
    do {
        result = subghz_file_encoder_worker_read_line(instance);
        if(result != RawLineReady) return result;
        furi_string_trim(instance->str_data);
    } while(furi_string_empty(instance->str_data) ||
            furi_string_get_char(instance->str_data, 0) == '#');
    return RawLineReady;
}

// Bound metadata as well as pulse lines. No unbounded FlipperFormat key search
// is needed before the first record. Custom preset metadata is skipped intact.
static bool subghz_file_encoder_worker_read_header(SubGhzFileEncoderWorker* instance) {
    bool filetype = false, version = false, protocol = false;
    while(subghz_file_encoder_worker_read_line(instance) == RawLineReady) {
        if(instance->read_offset > 16384) return false;
        furi_string_trim(instance->str_data);
        if(furi_string_empty(instance->str_data) ||
           furi_string_get_char(instance->str_data, 0) == '#')
            continue;
        const char* line = furi_string_get_cstr(instance->str_data);
        if(strncmp(line, "RAW_Data:", 9) == 0) return filetype && version && protocol;
        const char* colon = strchr(line, ':');
        if(!colon) return false;
        const char* value = colon + 1;
        while(*value == ' ' || *value == '\t')
            value++;
        size_t key_size = colon - line;
        if(key_size == 8 && strncmp(line, "Filetype", 8) == 0) {
            if(filetype || strcmp(value, "Flipper SubGhz RAW File")) return false;
            filetype = true;
        } else if(key_size == 7 && strncmp(line, "Version", 7) == 0) {
            if(version || strcmp(value, "1")) return false;
            version = true;
        } else if(key_size == 8 && strncmp(line, "Protocol", 8) == 0) {
            if(protocol || strcmp(value, "RAW")) return false;
            protocol = true;
        }
    }
    return false;
}

void subghz_file_encoder_worker_get_text_progress(
    SubGhzFileEncoderWorker* instance,
    FuriString* output) {
    if(instance->read_error) {
        furi_string_set(output, "File error");
        return;
    }
    // Report input read progress, not guessed playback progress: buffered binary
    // samples and bytes in the text file do not have interchangeable units.
    size_t offset = MIN(instance->read_offset, instance->file_size);
    unsigned percent = instance->file_size ? (uint64_t)offset * 100U / instance->file_size : 0;
    furi_string_printf(output, "Read %03u%%", percent);
}

LevelDuration subghz_file_encoder_worker_get_level_duration(void* context) {
    furi_assert(context);
    SubGhzFileEncoderWorker* instance = context;
    if(instance->read_error) {
        instance->worker_stopping = true;
        return level_duration_reset();
    }
    int32_t duration;
    int ret = furi_stream_buffer_receive(instance->stream, &duration, sizeof(int32_t), 0);
    bool producer_done = instance->producer_done;
    if(ret != sizeof(int32_t) && producer_done) {
        // Completion can be published just after an empty receive. Check once
        // more after observing it so the last queued pulse cannot be skipped.
        ret = furi_stream_buffer_receive(instance->stream, &duration, sizeof(int32_t), 0);
    }
    if(ret == sizeof(int32_t)) {
        LevelDuration level_duration = {.level = LEVEL_DURATION_RESET};
        if(duration < 0) {
            level_duration = level_duration_make(false, -duration);
        } else if(duration > 0) {
            level_duration = level_duration_make(true, duration);
        } else if(duration == 0) { //-V547
            level_duration = level_duration_reset();
            FURI_LOG_I(TAG, "Stop transmission");
            instance->worker_stopping = true;
        }
        return level_duration;
    } else {
        if(producer_done) {
            instance->worker_stopping = true;
            return level_duration_reset();
        }
        instance->is_storage_slow = true;
        return level_duration_wait();
    }
}

/** Worker thread
 * 
 * @param context 
 * @return exit code 
 */
static int32_t subghz_file_encoder_worker_thread(void* context) {
    SubGhzFileEncoderWorker* instance = context;
    FURI_LOG_I(TAG, "Worker start");
    while(instance->worker_running) {
        size_t free_bytes = furi_stream_buffer_spaces_available(instance->stream);
        if(free_bytes / sizeof(int32_t) < SUBGHZ_FILE_ENCODER_LOAD) {
            furi_delay_ms(1);
            continue;
        }
        RawLineResult result = subghz_file_encoder_worker_read_record(instance);
        if(result == RawLineEnd) break;
        if(result == RawLineError || !subghz_file_encoder_worker_data_parse(
                                         instance, furi_string_get_cstr(instance->str_data))) {
            if(instance->worker_running) {
                instance->read_error = true;
                FURI_LOG_E(TAG, "Invalid RAW record or storage read failure");
            }
            break;
        }
    }
    instance->producer_done = true;
    //waiting for the end of the transfer
    if(instance->is_storage_slow) {
        FURI_LOG_E(TAG, "Storage is slow");
    }

    FURI_LOG_I(TAG, "End read file");
    while(instance->device && !subghz_devices_is_async_complete_tx(instance->device) &&
          instance->worker_running) {
        furi_delay_ms(5);
    }

    FURI_LOG_I(TAG, "End transmission");
    bool notified = false;
    while(instance->worker_running) {
        if(instance->worker_stopping && instance->callback_end && !notified) {
            notified = true;
            instance->callback_end(instance->context_end);
        }
        furi_delay_ms(50);
    }
    flipper_format_buffered_file_close(instance->flipper_format);

    FURI_LOG_I(TAG, "Worker stop");
    return 0;
}

SubGhzFileEncoderWorker* subghz_file_encoder_worker_alloc(void) {
    SubGhzFileEncoderWorker* instance = calloc(1, sizeof(SubGhzFileEncoderWorker));

    instance->thread =
        furi_thread_alloc_ex("SubGhzFEWorker", 2048, subghz_file_encoder_worker_thread, instance);
    instance->stream = furi_stream_buffer_alloc(sizeof(int32_t) * 2048, sizeof(int32_t));

    instance->storage = furi_record_open(RECORD_STORAGE);
    instance->flipper_format = flipper_format_buffered_file_alloc(instance->storage);

    instance->str_data = furi_string_alloc();
    instance->file_path = furi_string_alloc();
    instance->worker_stopping = true;

    return instance;
}

void subghz_file_encoder_worker_free(SubGhzFileEncoderWorker* instance) {
    furi_assert(instance);

    furi_assert(!instance->worker_running);
    furi_stream_buffer_free(instance->stream);
    furi_thread_free(instance->thread);

    furi_string_free(instance->str_data);
    furi_string_free(instance->file_path);

    flipper_format_free(instance->flipper_format);
    furi_record_close(RECORD_STORAGE);

    free(instance);
}

bool subghz_file_encoder_worker_start(
    SubGhzFileEncoderWorker* instance,
    const char* file_path,
    const char* radio_device_name) {
    furi_assert(instance);
    furi_assert(!instance->worker_running);

    furi_stream_buffer_reset(instance->stream);
    furi_string_set(instance->file_path, file_path);
    instance->device = radio_device_name ? subghz_devices_get_by_name(radio_device_name) : NULL;
    instance->producer_done = instance->read_error = instance->is_storage_slow = false;
    instance->worker_stopping = false;
    instance->file_size = instance->read_offset = 0;
    if(!flipper_format_buffered_file_open_existing(instance->flipper_format, file_path)) {
        instance->producer_done = instance->read_error = true;
        return false;
    }
    instance->file_size = stream_size(flipper_format_get_raw_stream(instance->flipper_format));
    instance->worker_running = true;
    bool valid =
        subghz_file_encoder_worker_read_header(instance) &&
        subghz_file_encoder_worker_data_parse(instance, furi_string_get_cstr(instance->str_data));
    if(!valid) {
        instance->worker_running = false;
        instance->producer_done = instance->read_error = true;
        furi_stream_buffer_reset(instance->stream);
        flipper_format_buffered_file_close(instance->flipper_format);
        return false;
    }
    // The header and first record are valid and buffered before the caller can TX.
    furi_thread_start(instance->thread);
    return true;
}

void subghz_file_encoder_worker_stop(SubGhzFileEncoderWorker* instance) {
    furi_assert(instance);
    furi_assert(instance->worker_running);

    instance->worker_running = false;
    furi_thread_join(instance->thread);
}

bool subghz_file_encoder_worker_is_running(SubGhzFileEncoderWorker* instance) {
    furi_assert(instance);
    return instance->worker_running;
}
