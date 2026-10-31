#include "../../echo/echo_dashboard.h"
#include "../nfc_app_i.h"
#include <dolphin/dolphin.h>

enum SubmenuIndex {
    SubmenuIndexRead,
    SubmenuIndexDetectReader,
    SubmenuIndexSaved,
    SubmenuIndexExtraAction,
    SubmenuIndexAddManually,
    SubmenuIndexDebug,
};

void nfc_scene_start_submenu_callback(void* context, uint32_t index) {
    NfcApp* nfc = context;

    view_dispatcher_send_custom_event(nfc->view_dispatcher, index);
}

void nfc_scene_start_on_enter(void* context) {
    NfcApp* nfc = context;

    // Clear file name and device contents
    furi_string_reset(nfc->file_name);
    nfc_device_clear(nfc->nfc_device);
    iso14443_3a_reset(nfc->iso14443_3a_edit_data);
    // Reset detected protocols list
    nfc_detected_protocols_reset(nfc->detected_protocols);

    static EchoDashboardItem items[] = {
        {"Read card", "Identify a nearby tag", SubmenuIndexRead, EchoDashRead, false},
        {"Saved cards", "Open stored NFC files", SubmenuIndexSaved, EchoDashFiles, false},
        {"Extra tools", "Card-specific tools", SubmenuIndexExtraAction, EchoDashTools, false},
        {"Add manually", "Create a card record", SubmenuIndexAddManually, EchoDashRead, false},
        {"Extract MFC keys", "Reader-assisted keys", SubmenuIndexDetectReader, EchoDashLink, false},
        {"Debug", "Enable system debug", SubmenuIndexDebug, EchoDashTools, true},
    };
    items[5].locked = !furi_hal_rtc_is_flag_set(FuriHalRtcFlagDebug);
    items[5].description = items[5].locked ? "Enable system debug" : "NFC developer tools";
    echo_dashboard_configure(
        nfc->dashboard,
        "NFC",
        storage_sd_status(nfc->storage) == FSE_OK ? "SD ready" : "No SD",
        EchoDashRead,
        items,
        COUNT_OF(items),
        scene_manager_get_scene_state(nfc->scene_manager, NfcSceneStart),
        nfc_scene_start_submenu_callback,
        nfc);
    view_dispatcher_switch_to_view(nfc->view_dispatcher, NfcViewDashboard);
}

bool nfc_scene_start_on_event(void* context, SceneManagerEvent event) {
    NfcApp* nfc = context;
    bool consumed = false;

    if(event.type == SceneManagerEventTypeCustom) {
        consumed = true;
        if(event.event == SubmenuIndexRead) {
            scene_manager_next_scene(nfc->scene_manager, NfcSceneDetect);
            dolphin_deed(DolphinDeedNfcRead);
        } else if(event.event == SubmenuIndexDetectReader) {
            scene_manager_next_scene(nfc->scene_manager, NfcSceneMfClassicDetectReader);
        } else if(event.event == SubmenuIndexSaved) {
            scene_manager_next_scene(nfc->scene_manager, NfcSceneFileSelect);
        } else if(event.event == SubmenuIndexExtraAction) {
            scene_manager_next_scene(nfc->scene_manager, NfcSceneExtraActions);
        } else if(event.event == SubmenuIndexAddManually) {
            scene_manager_next_scene(nfc->scene_manager, NfcSceneSetType);
        } else if(event.event == SubmenuIndexDebug) {
            scene_manager_next_scene(nfc->scene_manager, NfcSceneDebug);
        } else {
            consumed = false;
        }
        if(consumed) {
            scene_manager_set_scene_state(nfc->scene_manager, NfcSceneStart, event.event);
        }
    }
    return consumed;
}

void nfc_scene_start_on_exit(void* context) {
    NfcApp* nfc = context;

    submenu_reset(nfc->submenu);
}
