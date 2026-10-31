#include "subghz_i.h"

void subghz_scene_replay_bench_on_enter(void* context);
bool subghz_scene_replay_bench_on_event(void* context, SceneManagerEvent event);
void subghz_scene_replay_bench_on_exit(void* context);

static void (*const enter_handlers[])(void*) = {subghz_scene_replay_bench_on_enter};
static bool (*const event_handlers[])(void*, SceneManagerEvent) = {
    subghz_scene_replay_bench_on_event};
static void (*const exit_handlers[])(void*) = {subghz_scene_replay_bench_on_exit};
static const SceneManagerHandlers handlers = {
    .on_enter_handlers = enter_handlers,
    .on_event_handlers = event_handlers,
    .on_exit_handlers = exit_handlers,
    .scene_num = 1,
};

static bool replay_custom(void* context, uint32_t event) {
    SubGhz* app = context;
    return scene_manager_handle_custom_event(app->scene_manager, event);
}

static bool replay_back(void* context) {
    SubGhz* app = context;
    return scene_manager_handle_back_event(app->scene_manager);
}

static void replay_tick(void* context) {
    SubGhz* app = context;
    scene_manager_handle_tick_event(app->scene_manager);
}

int32_t echo_replay_app(void* context) {
    UNUSED(context);
    // Load only the bench UI, not the receiver, analyser, history and editing views.
    SubGhz* app = calloc(1, sizeof(SubGhz));
    app->gui = furi_record_open(RECORD_GUI);
    app->dialogs = furi_record_open(RECORD_DIALOGS);
    app->view_dispatcher = view_dispatcher_alloc();
    app->scene_manager = scene_manager_alloc(&handlers, app);
    app->submenu = submenu_alloc();
    app->widget = widget_alloc();
    app->txrx = subghz_txrx_alloc();
    view_dispatcher_add_view(
        app->view_dispatcher, SubGhzViewIdMenu, submenu_get_view(app->submenu));
    view_dispatcher_add_view(
        app->view_dispatcher, SubGhzViewIdWidget, widget_get_view(app->widget));
    view_dispatcher_set_event_callback_context(app->view_dispatcher, app);
    view_dispatcher_set_custom_event_callback(app->view_dispatcher, replay_custom);
    view_dispatcher_set_navigation_event_callback(app->view_dispatcher, replay_back);
    view_dispatcher_set_tick_event_callback(app->view_dispatcher, replay_tick, 100);
    view_dispatcher_attach_to_gui(app->view_dispatcher, app->gui, ViewDispatcherTypeFullscreen);
    furi_hal_power_suppress_charge_enter();
    scene_manager_next_scene(app->scene_manager, 0);
    view_dispatcher_run(app->view_dispatcher);
    subghz_replay_bench_free(app);
    subghz_txrx_stop(app->txrx);
    subghz_txrx_sleep(app->txrx);
    subghz_txrx_free(app->txrx);
    view_dispatcher_remove_view(app->view_dispatcher, SubGhzViewIdMenu);
    view_dispatcher_remove_view(app->view_dispatcher, SubGhzViewIdWidget);
    submenu_free(app->submenu);
    widget_free(app->widget);
    scene_manager_free(app->scene_manager);
    view_dispatcher_free(app->view_dispatcher);
    furi_hal_power_suppress_charge_exit();
    furi_record_close(RECORD_DIALOGS);
    furi_record_close(RECORD_GUI);
    free(app);
    return 0;
}
