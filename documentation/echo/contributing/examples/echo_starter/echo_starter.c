#include <furi.h>
#include <gui/gui.h>
#include <gui/modules/submenu.h>
#include <gui/modules/widget.h>
#include <gui/view_dispatcher.h>
#include <stdlib.h>

typedef enum {
    EchoStarterMenu,
    EchoStarterAbout
} EchoStarterView;
typedef enum {
    EchoStarterShowAbout = 1,
    EchoStarterExit
} EchoStarterEvent;

typedef struct {
    ViewDispatcher* dispatcher;
    Submenu* menu;
    Widget* about;
    bool showing_about;
} EchoStarter;

static void echo_starter_select(void* context, uint32_t event) {
    EchoStarter* app = context;
    // Queue work instead of changing views inside a menu callback.
    view_dispatcher_send_custom_event(app->dispatcher, event);
}

static bool echo_starter_event(void* context, uint32_t event) {
    EchoStarter* app = context;
    if(event == EchoStarterShowAbout) {
        app->showing_about = true;
        view_dispatcher_switch_to_view(app->dispatcher, EchoStarterAbout);
        return true;
    }
    if(event == EchoStarterExit) {
        view_dispatcher_stop(app->dispatcher);
        return true;
    }
    return false;
}

static bool echo_starter_back(void* context) {
    EchoStarter* app = context;
    if(app->showing_about) {
        app->showing_about = false;
        view_dispatcher_switch_to_view(app->dispatcher, EchoStarterMenu);
    } else {
        view_dispatcher_stop(app->dispatcher);
    }
    return true;
}

int32_t echo_starter_app(void* context) {
    UNUSED(context);
    EchoStarter* app = calloc(1, sizeof(EchoStarter));
    Gui* gui = furi_record_open(RECORD_GUI);
    app->dispatcher = view_dispatcher_alloc();
    app->menu = submenu_alloc();
    app->about = widget_alloc();
    submenu_set_header(app->menu, "Echo Starter");
    submenu_add_item(app->menu, "About", EchoStarterShowAbout, echo_starter_select, app);
    submenu_add_item(app->menu, "Exit", EchoStarterExit, echo_starter_select, app);
    widget_add_string_multiline_element(
        app->about, 64, 28, AlignCenter, AlignCenter, FontSecondary, "Hello from Echo\nBack: menu");
    view_dispatcher_set_event_callback_context(app->dispatcher, app);
    view_dispatcher_set_custom_event_callback(app->dispatcher, echo_starter_event);
    view_dispatcher_set_navigation_event_callback(app->dispatcher, echo_starter_back);
    view_dispatcher_add_view(app->dispatcher, EchoStarterMenu, submenu_get_view(app->menu));
    view_dispatcher_add_view(app->dispatcher, EchoStarterAbout, widget_get_view(app->about));
    view_dispatcher_attach_to_gui(app->dispatcher, gui, ViewDispatcherTypeFullscreen);
    view_dispatcher_switch_to_view(app->dispatcher, EchoStarterMenu);
    view_dispatcher_run(app->dispatcher);

    // Stop/join any future worker before removing its views or freeing its context.
    view_dispatcher_remove_view(app->dispatcher, EchoStarterAbout);
    view_dispatcher_remove_view(app->dispatcher, EchoStarterMenu);
    view_dispatcher_free(app->dispatcher);
    widget_free(app->about);
    submenu_free(app->menu);
    furi_record_close(RECORD_GUI);
    free(app);
    return 0;
}
