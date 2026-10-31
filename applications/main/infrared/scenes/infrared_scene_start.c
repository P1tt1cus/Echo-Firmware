#include "../../echo/echo_dashboard.h"
#include "../infrared_app_i.h"

enum SubmenuIndex {
    SubmenuIndexSavedRemotes,
    SubmenuIndexUniversalRemotes,
    SubmenuIndexLearnNewRemote,
    SubmenuIndexGpioSettings,
    SubmenuIndexDebug
};

static void infrared_scene_start_submenu_callback(void* context, uint32_t index) {
    InfraredApp* infrared = context;
    view_dispatcher_send_custom_event(infrared->view_dispatcher, index);
}

void infrared_scene_start_on_enter(void* context) {
    InfraredApp* infrared = context;
    SceneManager* scene_manager = infrared->scene_manager;

    static EchoDashboardItem items[] = {
        {"Saved remotes", "Open a saved remote", SubmenuIndexSavedRemotes, EchoDashFiles, false},
        {"Learn remote", "Record remote buttons", SubmenuIndexLearnNewRemote, EchoDashRead, false},
        {"Universal remotes",
         "Choose a device type",
         SubmenuIndexUniversalRemotes,
         EchoDashRadio,
         false},
        {"GPIO settings", "IR output and power", SubmenuIndexGpioSettings, EchoDashSettings, false},
        {"Debug RX", "Enable system debug", SubmenuIndexDebug, EchoDashTools, true},
    };
    items[4].locked = !infrared->app_state.is_debug_enabled;
    items[4].description = items[4].locked ? "Enable system debug" : "Inspect received IR";
    echo_dashboard_configure(
        infrared->dashboard,
        "Remotes",
        storage_sd_status(infrared->storage) == FSE_OK ? "SD ready" : "No SD",
        EchoDashRead,
        items,
        COUNT_OF(items),
        scene_manager_get_scene_state(scene_manager, InfraredSceneStart),
        infrared_scene_start_submenu_callback,
        infrared);
    view_dispatcher_switch_to_view(infrared->view_dispatcher, InfraredViewDashboard);
}

bool infrared_scene_start_on_event(void* context, SceneManagerEvent event) {
    InfraredApp* infrared = context;
    SceneManager* scene_manager = infrared->scene_manager;

    bool consumed = false;

    if(event.type == SceneManagerEventTypeCustom) {
        const uint32_t submenu_index = event.event;
        scene_manager_set_scene_state(scene_manager, InfraredSceneStart, submenu_index);
        if(submenu_index == SubmenuIndexUniversalRemotes) {
            // Set file_path only once here so repeated usages of
            // "Load from Library File" have file browser focused on
            // last selected file, feels more intuitive
            furi_string_set(infrared->file_path, INFRARED_APP_FOLDER);
            scene_manager_next_scene(scene_manager, InfraredSceneUniversal);
        } else if(submenu_index == SubmenuIndexLearnNewRemote) {
            infrared->app_state.is_learning_new_remote = true;
            infrared->app_state.current_button_index = 0; // Reset index when starting new remote
            scene_manager_next_scene(scene_manager, InfraredSceneLearn);
        } else if(submenu_index == SubmenuIndexSavedRemotes) {
            furi_string_set(infrared->file_path, INFRARED_APP_FOLDER);
            scene_manager_next_scene(scene_manager, InfraredSceneRemoteList);
        } else if(submenu_index == SubmenuIndexGpioSettings) {
            scene_manager_next_scene(scene_manager, InfraredSceneGpioSettings);
        } else if(submenu_index == SubmenuIndexDebug) {
            scene_manager_next_scene(scene_manager, InfraredSceneDebug);
        }

        consumed = true;
    }

    return consumed;
}

void infrared_scene_start_on_exit(void* context) {
    InfraredApp* infrared = context;
    submenu_reset(infrared->submenu);
}
