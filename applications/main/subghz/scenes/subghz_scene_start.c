#include "../../echo/echo_dashboard.h"
#include "../subghz_i.h"
#include "subghz_scene_start.h"
#include <dolphin/dolphin.h>
#include <loader/loader.h>

#include <lib/subghz/protocols/raw.h>

void subghz_scene_start_submenu_callback(void* context, uint32_t index) {
    SubGhz* subghz = context;
    view_dispatcher_send_custom_event(subghz->view_dispatcher, index);
}

void subghz_scene_start_on_enter(void* context) {
    SubGhz* subghz = context;
    if(subghz->state_notifications == SubGhzNotificationStateStarting) {
        subghz->state_notifications = SubGhzNotificationStateIDLE;
    }

    static const EchoDashboardItem items[] = {
        {"Read signals", "Receive and identify", SubmenuIndexRead, EchoDashRadio, false},
        {"Saved signals", "Open saved recordings", SubmenuIndexSaved, EchoDashFiles, false},
        {"Freq. analyser",
         "Find a signal band",
         SubmenuIndexFrequencyAnalyzer,
         EchoDashRead,
         false},
        {"Radio settings", "Module and defaults", SubmenuIndexExtSettings, EchoDashSettings, false},
        {"Read RAW", "Record raw timings", SubmenuIndexReadRAW, EchoDashRadio, false},
        {"Add manually", "Create a signal file", SubmenuIndexAddManually, EchoDashTools, false},
        {"Advanced create",
         "Detailed signal setup",
         SubmenuIndexAddManuallyAdvanced,
         EchoDashTools,
         false},
    };
    Storage* storage = furi_record_open(RECORD_STORAGE);
    bool sd_ready = storage_sd_status(storage) == FSE_OK;
    furi_record_close(RECORD_STORAGE);
    echo_dashboard_configure(
        subghz->dashboard,
        "Sub-GHz",
        sd_ready ? "SD ready" : "No SD",
        EchoDashRadio,
        items,
        COUNT_OF(items),
        scene_manager_get_scene_state(subghz->scene_manager, SubGhzSceneStart),
        subghz_scene_start_submenu_callback,
        subghz);
    view_dispatcher_switch_to_view(subghz->view_dispatcher, SubGhzViewIdDashboard);
}

bool subghz_scene_start_on_event(void* context, SceneManagerEvent event) {
    SubGhz* subghz = context;
    if(event.type == SceneManagerEventTypeBack) {
        //exit app
        scene_manager_stop(subghz->scene_manager);
        view_dispatcher_stop(subghz->view_dispatcher);
        return true;
    } else if(event.type == SceneManagerEventTypeCustom) {
        scene_manager_set_scene_state(subghz->scene_manager, SubGhzSceneStart, event.event);
        if(event.event == SubmenuIndexReadRAW) {
            subghz_rx_key_state_set(subghz, SubGhzRxKeyStateIDLE);
            scene_manager_next_scene(subghz->scene_manager, SubGhzSceneReadRAW);
            return true;
        } else if(event.event == SubmenuIndexRead) {
            subghz_rx_key_state_set(subghz, SubGhzRxKeyStateIDLE);
            scene_manager_next_scene(subghz->scene_manager, SubGhzSceneReceiver);
            return true;
        } else if(event.event == SubmenuIndexSaved) {
            scene_manager_next_scene(subghz->scene_manager, SubGhzSceneSaved);
            return true;
        } else if(
            event.event == SubmenuIndexAddManually ||
            event.event == SubmenuIndexAddManuallyAdvanced) {
            const char* arg = (event.event == SubmenuIndexAddManuallyAdvanced) ?
                                  "AddManuallyAdvanced" :
                                  "AddManually";
            FuriString* self_path = furi_string_alloc();
            Loader* loader = furi_record_open(RECORD_LOADER);
            furi_check(loader_get_application_launch_path(loader, self_path));
            loader_enqueue_launch(
                loader,
                EXT_PATH("apps/assets/subghz_add_manually.fap"),
                arg,
                LoaderDeferredLaunchFlagGui);
            loader_enqueue_launch(
                loader, furi_string_get_cstr(self_path), arg, LoaderDeferredLaunchFlagGui);
            furi_record_close(RECORD_LOADER);
            furi_string_free(self_path);
            while(scene_manager_previous_scene(subghz->scene_manager))
                ;
            scene_manager_stop(subghz->scene_manager);
            view_dispatcher_stop(subghz->view_dispatcher);
            return true;
        } else if(event.event == SubmenuIndexFrequencyAnalyzer) {
            scene_manager_next_scene(subghz->scene_manager, SubGhzSceneFrequencyAnalyzer);
            dolphin_deed(DolphinDeedSubGhzFrequencyAnalyzer);
            return true;
        } else if(event.event == SubmenuIndexExtSettings) {
            scene_manager_next_scene(subghz->scene_manager, SubGhzSceneExtModuleSettings);
            return true;
        }
    }
    return false;
}

void subghz_scene_start_on_exit(void* context) {
    SubGhz* subghz = context;
    submenu_reset(subghz->submenu);
}
