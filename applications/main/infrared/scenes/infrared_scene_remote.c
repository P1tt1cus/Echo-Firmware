#include "../infrared_app_i.h"

static void
    infrared_scene_remote_callback(void* context, InfraredRemoteViewEvent event, int32_t index) {
    InfraredApp* infrared = context;
    uint16_t type = InfraredCustomEventTypeRemoteSelection;
    if(event == InfraredRemoteViewPress)
        type = InfraredCustomEventTypeTransmitStarted;
    else if(event == InfraredRemoteViewRelease)
        type = InfraredCustomEventTypeTransmitStopped;
    else if(event == InfraredRemoteViewControl)
        type = InfraredCustomEventTypeMenuSelected;
    view_dispatcher_send_custom_event(
        infrared->view_dispatcher, infrared_custom_event_pack(type, index));
}

static bool infrared_scene_remote_detail(InfraredApp* infrared, int32_t index) {
    if(index < 0) {
        infrared_remote_view_status(infrared->remote_view, index, "Remote actions", false);
        return false;
    }
    if((size_t)index >= infrared_remote_get_signal_count(infrared->remote)) return false;
    if(infrared->remote_loaded_index != index || !infrared->remote_signal_valid) {
        infrared->remote_loaded_index = index;
        infrared->remote_signal_valid = !INFRARED_ERROR_PRESENT(
            infrared_remote_load_signal(infrared->remote, infrared->current_signal, index));
    }
    if(!infrared->remote_signal_valid) {
        infrared_remote_view_status(infrared->remote_view, index, "Cannot read signal", false);
        return false;
    }
    char detail[48];
    const bool active = infrared->app_state.is_transmitting;
    if(infrared_signal_is_raw(infrared->current_signal)) {
        const InfraredRawSignal* raw = infrared_signal_get_raw_signal(infrared->current_signal);
        snprintf(
            detail,
            sizeof(detail),
            "%sRAW %lu kHz %zu samples",
            active ? "TX " : "",
            (unsigned long)(raw->frequency / 1000),
            raw->timings_size);
    } else {
        const InfraredMessage* message = infrared_signal_get_message(infrared->current_signal);
        snprintf(
            detail,
            sizeof(detail),
            "%s %s",
            active ? "TX" : "Parsed",
            infrared_get_protocol_name(message->protocol));
    }
    infrared_remote_view_status(infrared->remote_view, index, detail, active);
    return true;
}

void infrared_scene_remote_on_enter(void* context) {
    InfraredApp* infrared = context;
    infrared->remote_loaded_index = -1;
    infrared->remote_signal_valid = false;
    infrared_remote_view_configure(
        infrared->remote_view,
        infrared->remote,
        (int32_t)scene_manager_get_scene_state(infrared->scene_manager, InfraredSceneRemote),
        infrared_scene_remote_callback,
        infrared);
    view_dispatcher_switch_to_view(infrared->view_dispatcher, InfraredViewRemote);
    infrared_scene_remote_detail(infrared, infrared_remote_view_selected(infrared->remote_view));
}

bool infrared_scene_remote_on_event(void* context, SceneManagerEvent event) {
    InfraredApp* infrared = context;
    SceneManager* scene_manager = infrared->scene_manager;
    int32_t selected = infrared_remote_view_selected(infrared->remote_view);
    if(event.type == SceneManagerEventTypeBack) {
        bool was_transmitting = infrared->app_state.is_transmitting;
        infrared_remote_view_cancel(infrared->remote_view);
        infrared_tx_stop(infrared);
        if(was_transmitting) {
            infrared_scene_remote_detail(infrared, selected);
            return true;
        }
        const uint32_t possible_scenes[] = {InfraredSceneRemoteList, InfraredSceneStart};
        return scene_manager_search_and_switch_to_previous_scene_one_of(
            scene_manager, possible_scenes, COUNT_OF(possible_scenes));
    }
    if(event.type != SceneManagerEventTypeCustom) return false;
    uint16_t type = infrared_custom_event_get_type(event.event);
    if(type == InfraredCustomEventTypeRemoteSelection) {
        if(!infrared->app_state.is_transmitting) infrared_scene_remote_detail(infrared, selected);
    } else if(type == InfraredCustomEventTypeTransmitStarted) {
        if(infrared->app_state.is_transmitting) return true;
        if(!infrared_remote_view_can_send(infrared->remote_view, selected)) return true;
        if(infrared_scene_remote_detail(infrared, selected) &&
           infrared_remote_view_can_send(infrared->remote_view, selected)) {
            infrared_tx_start(infrared);
            infrared_scene_remote_detail(infrared, selected);
            if(!infrared->app_state.is_transmitting) {
                infrared_remote_view_status(
                    infrared->remote_view, selected, "Wait, then press OK", false);
            }
        }
    } else if(type == InfraredCustomEventTypeTransmitStopped) {
        infrared_tx_stop(infrared);
        infrared_scene_remote_detail(infrared, selected);
    } else if(type == InfraredCustomEventTypeMenuSelected && !infrared->app_state.is_transmitting) {
        if(selected == -2) {
            infrared->app_state.is_learning_new_remote = false;
            scene_manager_next_scene(scene_manager, InfraredSceneLearn);
        } else if(selected == -1) {
            scene_manager_next_scene(scene_manager, InfraredSceneEdit);
        }
    } else {
        return false;
    }
    return true;
}

void infrared_scene_remote_on_exit(void* context) {
    InfraredApp* infrared = context;
    scene_manager_set_scene_state(
        infrared->scene_manager,
        InfraredSceneRemote,
        (uint32_t)infrared_remote_view_selected(infrared->remote_view));
    infrared_remote_view_cancel(infrared->remote_view);
    infrared_tx_stop(infrared);
    infrared->remote_signal_valid = false;
}
