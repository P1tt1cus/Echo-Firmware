#include "validators.h"
#include <storage/storage.h>
#include <furi.h>

struct ValidatorIsFile {
    char* app_path_folder;
    const char* app_extension;
    char* current_name;
};

bool validator_is_file_callback(const char* text, FuriString* error, void* context) {
    furi_check(context);
    ValidatorIsFile* instance = context;

    size_t length = strlen(text);
    if(length == 0 || strcmp(text, ".") == 0 || strcmp(text, "..") == 0) {
        furi_string_set(error, "Enter a file name.");
        return false;
    }
    if(text[length - 1] == ' ' || text[length - 1] == '.') {
        furi_string_set(error, "Name cannot end\nwith a dot or space.");
        return false;
    }
    for(const unsigned char* c = (const unsigned char*)text; *c; c++) {
        if(*c < 0x20 || *c == 0x7f || strchr("/\\:*?\"<>|", *c)) {
            furi_string_set(error, "Name contains\nan invalid\ncharacter.");
            return false;
        }
    }

    if(instance->current_name != NULL) {
        if(strcmp(instance->current_name, text) == 0) {
            return true;
        }
    }

    FuriString* path = furi_string_alloc_printf(
        "%s/%s%s", instance->app_path_folder, text, instance->app_extension);
    Storage* storage = furi_record_open(RECORD_STORAGE);
    FS_Error status = storage_common_stat(storage, furi_string_get_cstr(path), NULL);
    const bool ret = status == FSE_NOT_EXIST;
    if(status == FSE_OK || status == FSE_EXIST) {
        furi_string_set(error, "This name\nexists!\nChoose\nanother one.");
    } else if(!ret) {
        furi_string_set(error, "Cannot check name.\nCheck the SD card.");
    }
    furi_string_free(path);
    furi_record_close(RECORD_STORAGE);

    return ret;
}

ValidatorIsFile* validator_is_file_alloc_init(
    const char* app_path_folder,
    const char* app_extension,
    const char* current_name) {
    ValidatorIsFile* instance = calloc(1, sizeof(ValidatorIsFile));

    instance->app_path_folder = strdup(app_path_folder);
    instance->app_extension = app_extension;
    if(current_name != NULL) {
        instance->current_name = strdup(current_name);
    }

    return instance;
}

void validator_is_file_free(ValidatorIsFile* instance) {
    furi_check(instance);
    free(instance->app_path_folder);
    free(instance->current_name);
    free(instance);
}
