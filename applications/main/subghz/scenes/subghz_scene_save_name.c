#include "../subghz_i.h"
#include "subghz/types.h"
#include "../helpers/subghz_custom_event.h"
#include <lib/subghz/protocols/raw.h>
#include <gui/modules/validators.h>
#include <dolphin/dolphin.h>
#include <toolbox/name_generator.h>

void subghz_scene_save_name_text_input_callback(void* context) {
    furi_assert(context);
    SubGhz* subghz = context;
    view_dispatcher_send_custom_event(subghz->view_dispatcher, SubGhzCustomEventSceneSaveName);
}

void subghz_scene_save_name_on_enter(void* context) {
    SubGhz* subghz = context;

    // Setup view
    TextInput* text_input = subghz->text_input;
    bool dev_name_empty = false;

    FuriString* file_name = furi_string_alloc();
    FuriString* dir_name = furi_string_alloc();
    FuriString* current_name = furi_string_alloc();

    char file_name_buf[SUBGHZ_MAX_LEN_NAME] = {0};
    DateTime* datetime = subghz->save_datetime_set ? &subghz->save_datetime : NULL;
    subghz->save_datetime_set = false;
#ifdef SUBGHZ_ADD_MANUALLY
    name_generator_make_auto_datetime(
        file_name_buf, SUBGHZ_MAX_LEN_NAME, SUBGHZ_APP_FILENAME_PREFIX, datetime);
    furi_string_set(file_name, file_name_buf);
    furi_string_set(subghz->file_path, SUBGHZ_APP_FOLDER);
    dev_name_empty = true;
#else
    if(!subghz_path_is_file(subghz->file_path)) {
        furi_string_reset(subghz->file_path_tmp);
        SubGhzProtocolDecoderBase* decoder_result = subghz_txrx_get_decoder(subghz->txrx);
        if(subghz->last_settings->protocol_file_names && decoder_result != NULL &&
           strlen(decoder_result->protocol->name) != 0) {
            name_generator_make_auto_datetime(
                file_name_buf, SUBGHZ_MAX_LEN_NAME, decoder_result->protocol->name, datetime);
        } else {
            name_generator_make_auto_datetime(
                file_name_buf, SUBGHZ_MAX_LEN_NAME, SUBGHZ_APP_FILENAME_PREFIX, datetime);
        }
        furi_string_set(file_name, file_name_buf);
        furi_string_set(subghz->file_path, SUBGHZ_APP_FOLDER);
        //highlighting the entire filename by default
        dev_name_empty = true;
    } else {
        furi_string_reset(subghz->file_path_tmp);
        furi_string_set(subghz->file_path_tmp, subghz->file_path);
        path_extract_dirname(furi_string_get_cstr(subghz->file_path), dir_name);
        path_extract_filename(subghz->file_path, file_name, true);
        furi_string_set(current_name, file_name);
        if(scene_manager_get_scene_state(subghz->scene_manager, SubGhzSceneReadRAW) !=
           SubGhzCustomEventManagerNoSet) {
            if(scene_manager_get_scene_state(subghz->scene_manager, SubGhzSceneReadRAW) ==
               SubGhzCustomEventManagerSetRAW) {
                dev_name_empty = true;
                if(subghz->last_settings->protocol_file_names) {
                    name_generator_make_auto_datetime(
                        file_name_buf, SUBGHZ_MAX_LEN_NAME, "RAW", datetime);
                } else {
                    name_generator_make_auto_datetime(
                        file_name_buf, SUBGHZ_MAX_LEN_NAME, SUBGHZ_APP_FILENAME_PREFIX, datetime);
                }
                furi_string_set(file_name, file_name_buf);
            }
        }
        furi_string_set(subghz->file_path, dir_name);
    }
#endif

    strlcpy(subghz->file_name_tmp, furi_string_get_cstr(file_name), SUBGHZ_MAX_LEN_NAME);
    text_input_set_header_text(text_input, "Name signal");
    text_input_set_result_callback(
        text_input,
        subghz_scene_save_name_text_input_callback,
        subghz,
        subghz->file_name_tmp,
        SUBGHZ_MAX_LEN_NAME,
        dev_name_empty);

    ValidatorIsFile* validator_is_file = validator_is_file_alloc_init(
        furi_string_get_cstr(subghz->file_path),
        SUBGHZ_APP_FILENAME_EXTENSION,
        furi_string_get_cstr(current_name));
    text_input_set_validator(text_input, validator_is_file_callback, validator_is_file);

    furi_string_free(file_name);
    furi_string_free(dir_name);
    furi_string_free(current_name);

    view_dispatcher_switch_to_view(subghz->view_dispatcher, SubGhzViewIdTextInput);
}

bool subghz_scene_save_name_on_event(void* context, SceneManagerEvent event) {
    SubGhz* subghz = context;
    if(event.type == SceneManagerEventTypeBack) {
        // Set file path to default
        furi_string_set(subghz->file_path, SUBGHZ_APP_FOLDER);
        //
#ifndef SUBGHZ_ADD_MANUALLY
        if(subghz_path_is_file(subghz->file_path_tmp)) {
            if(!scene_manager_has_previous_scene(subghz->scene_manager, SubGhzSceneDecodeRAW)) {
                furi_string_set(subghz->file_path, subghz->file_path_tmp);
            }
        }
#endif

        scene_manager_previous_scene(subghz->scene_manager);

        return true;
    } else if(event.type == SceneManagerEventTypeCustom) {
        if(event.event == SubGhzCustomEventSceneSaveName) {
            if(strcmp(subghz->file_name_tmp, "") != 0) {
                FuriString* destination = furi_string_alloc_printf(
                    "%s/%s%s",
                    furi_string_get_cstr(subghz->file_path),
                    subghz->file_name_tmp,
                    SUBGHZ_APP_FILENAME_EXTENSION);
                bool saved;
                if(subghz_path_is_file(subghz->file_path_tmp)) {
                    saved = subghz_rename_file(subghz, furi_string_get_cstr(destination));
                } else {
#ifdef SUBGHZ_ADD_MANUALLY
                    FlipperFormat* data = subghz_txrx_get_fff_data(subghz->txrx);
#else
                    FlipperFormat* data =
                        subghz_history_get_raw_data(subghz->history, subghz->idx_menu_chosen);
#endif
                    saved = subghz_save_protocol_to_file(
                        subghz, data, furi_string_get_cstr(destination), SubGhzSaveNew);
                }
                if(saved) furi_string_set(subghz->file_path, destination);
                furi_string_free(destination);
                if(!saved) return true;

#ifdef SUBGHZ_ADD_MANUALLY
                subghz_file_name_clear(subghz);
#else
                if(scene_manager_get_scene_state(subghz->scene_manager, SubGhzSceneReadRAW) !=
                   SubGhzCustomEventManagerNoSet) {
                    subghz_protocol_raw_gen_fff_data(
                        subghz_txrx_get_fff_data(subghz->txrx),
                        furi_string_get_cstr(subghz->file_path),
                        subghz_txrx_radio_device_get_name(subghz->txrx));
                    scene_manager_set_scene_state(
                        subghz->scene_manager, SubGhzSceneReadRAW, SubGhzCustomEventManagerNoSet);
                }
                furi_string_reset(subghz->file_path_tmp);
#endif

                scene_manager_next_scene(subghz->scene_manager, SubGhzSceneSaveSuccess);
#ifdef SUBGHZ_ADD_MANUALLY
                dolphin_deed(DolphinDeedSubGhzAddManually);
#else
                if(scene_manager_has_previous_scene(subghz->scene_manager, SubGhzSceneSavedMenu)) {
                    // Nothing, do not count editing as saving
                } else if(scene_manager_has_previous_scene(
                              subghz->scene_manager, SubGhzSceneMoreRAW)) {
                    // Ditto, for RAW signals
                } else {
                    dolphin_deed(DolphinDeedSubGhzSave);
                }
#endif
                return true;
            } else {
                dialog_message_show_storage_error(subghz->dialogs, "Enter a name\nfor the signal");
                return true;
            }
        }
    }
    return false;
}

void subghz_scene_save_name_on_exit(void* context) {
    SubGhz* subghz = context;

    // Clear validator
    void* validator_context = text_input_get_validator_callback_context(subghz->text_input);
    text_input_set_validator(subghz->text_input, NULL, NULL);
    validator_is_file_free(validator_context);

    // Clear view
    text_input_reset(subghz->text_input);
}
