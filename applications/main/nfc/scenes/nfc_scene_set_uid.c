#include "../nfc_app_i.h"

#include "../helpers/protocol_support/nfc_protocol_support_gui_common.h"

void nfc_scene_set_uid_on_enter(void* context) {
    NfcApp* instance = context;

    size_t uid_len;
    const uint8_t* uid = nfc_device_get_uid(instance->nfc_device, &uid_len);
    memcpy(instance->byte_input_store, uid, uid_len);

    // Setup view
    ByteInput* byte_input = instance->byte_input;
    byte_input_set_header_text(byte_input, "Enter UID in hex");
    byte_input_set_result_callback(
        byte_input,
        nfc_protocol_support_common_byte_input_done_callback,
        NULL,
        instance,
        instance->byte_input_store,
        uid_len);

    view_dispatcher_switch_to_view(instance->view_dispatcher, NfcViewByteInput);
}

bool nfc_scene_set_uid_on_event(void* context, SceneManagerEvent event) {
    NfcApp* instance = context;
    bool consumed = false;

    if(event.type == SceneManagerEventTypeCustom) {
        if(event.event == NfcCustomEventByteInputDone) {
            size_t uid_len = 0;
            const uint8_t* uid = nfc_device_get_uid(instance->nfc_device, &uid_len);
            uint8_t original_uid[NFC_BYTE_INPUT_STORE_SIZE];
            furi_check(uid_len <= sizeof(original_uid));
            memcpy(original_uid, uid, uid_len);
            if(!nfc_device_set_uid(instance->nfc_device, instance->byte_input_store, uid_len)) {
                dialog_message_show_storage_error(instance->dialogs, "Cannot change UID");
                return true;
            }
            if(scene_manager_has_previous_scene(instance->scene_manager, NfcSceneSavedMenu)) {
                if(nfc_save_shadow_file(instance)) {
                    scene_manager_next_scene(instance->scene_manager, NfcSceneSaveSuccess);
                } else {
                    nfc_device_set_uid(instance->nfc_device, original_uid, uid_len);
                }
                consumed = true;
            } else if(scene_manager_has_previous_scene(instance->scene_manager, NfcSceneReadMenu)) {
                scene_manager_search_and_switch_to_previous_scene(
                    instance->scene_manager, NfcSceneReadMenu);
                consumed = true;
            } else {
                scene_manager_next_scene(instance->scene_manager, NfcSceneSaveName);
                consumed = true;
            }
        }
    }

    return consumed;
}

void nfc_scene_set_uid_on_exit(void* context) {
    NfcApp* instance = context;

    // Clear view
    byte_input_set_result_callback(instance->byte_input, NULL, NULL, NULL, NULL, 0);
    byte_input_set_header_text(instance->byte_input, "");
}
