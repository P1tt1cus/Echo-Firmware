#pragma once

#include <storage/storage.h>

// Private to the native apps: preserves API87.1. The writer must finish and close
// its file, returning false for write/flush/close errors. All paths stay on the
// same filesystem. This protects normal I/O failure, not power-loss atomicity.
typedef bool (*EchoFileWriter)(const char* path, void* context);

static inline bool echo_file_save(
    Storage* storage,
    const char* destination,
    bool replace,
    EchoFileWriter writer,
    void* context,
    FuriString* recovery_path) {
    furi_string_reset(recovery_path);
    FileInfo info;
    FS_Error status = storage_common_stat(storage, destination, &info);
    bool existed = status == FSE_OK;
    if((existed && (!replace || (info.flags & FSF_DIRECTORY))) ||
       (!existed && status != FSE_NOT_EXIST))
        return false;

    bool saved = false;
    bool staged = false;
    bool moved_original = false;
    FuriString* temporary = furi_string_alloc();
    FuriString* original = furi_string_alloc();
    File* reservation = storage_file_alloc(storage);
    do {
        // Exclusive creation never truncates another save's staging file or an
        // artifact retained after an interrupted operation.
        for(unsigned slot = 0; slot < 32; slot++) {
            furi_string_printf(temporary, "%s.echo-new-%u", destination, slot);
            staged = storage_file_open(
                reservation, furi_string_get_cstr(temporary), FSAM_WRITE, FSOM_CREATE_NEW);
            FS_Error error = storage_file_get_error(reservation);
            bool closed = storage_file_close(reservation);
            if(staged) {
                if(!closed) break;
                if(!writer(furi_string_get_cstr(temporary), context)) break;
                saved = true; // Staging complete; not committed yet.
                break;
            }
            if(error != FSE_EXIST) break;
        }
        if(!saved) break;
        saved = false;

        if(existed) {
            for(unsigned slot = 0; slot < 32; slot++) {
                furi_string_printf(original, "%s.echo-old-%u", destination, slot);
                status = storage_common_rename_safe(
                    storage, destination, furi_string_get_cstr(original));
                if(status == FSE_OK) {
                    moved_original = true;
                    break;
                }
                if(status != FSE_EXIST) break;
            }
            if(!moved_original) break;
        }

        status = storage_common_rename_safe(storage, furi_string_get_cstr(temporary), destination);
        if(status == FSE_OK) {
            saved = true;
            staged = false;
            if(moved_original &&
               storage_common_remove(storage, furi_string_get_cstr(original)) != FSE_OK) {
                furi_string_set(recovery_path, original);
            }
        } else if(moved_original) {
            // A failed rollback must never delete the only remaining original.
            if(storage_common_rename_safe(storage, furi_string_get_cstr(original), destination) !=
               FSE_OK) {
                furi_string_set(recovery_path, original);
            }
        }
    } while(false);

    if(staged) storage_common_remove(storage, furi_string_get_cstr(temporary));
    storage_file_free(reservation);
    furi_string_free(temporary);
    furi_string_free(original);
    return saved;
}
