#include "infrared_remote_view.h"
#include <furi.h>
#include <gui/elements.h>

#define REMOTE_ROWS 3

struct InfraredRemoteView {
    View* view;
    InfraredRemoteViewCallback callback;
    void* context;
};

typedef struct {
    const InfraredRemote* remote;
    size_t count;
    size_t selected;
    bool pressed;
    bool cancelled;
    bool transmitting;
    int32_t requested;
    char detail[48];
} InfraredRemoteViewModel;

static int32_t infrared_remote_view_index(const InfraredRemoteViewModel* model) {
    if(model->selected < model->count) return model->selected;
    return model->selected == model->count ? -2 : -1;
}

static void infrared_remote_view_draw(Canvas* canvas, void* context) {
    InfraredRemoteViewModel* model = context;
    canvas_set_font(canvas, FontSecondary);
    FuriString* text = furi_string_alloc_printf("%zu/%zu", model->selected + 1, model->count + 2);
    size_t counter_width = canvas_string_width(canvas, furi_string_get_cstr(text));
    canvas_draw_str_aligned(canvas, 127, 9, AlignRight, AlignBottom, furi_string_get_cstr(text));
    furi_string_set(text, infrared_remote_get_name(model->remote));
    elements_string_fit_width(canvas, text, counter_width < 120 ? 120 - counter_width : 0);
    canvas_draw_str(canvas, 2, 9, furi_string_get_cstr(text));
    canvas_draw_line(canvas, 0, 12, 127, 12);
    size_t first = (model->selected / REMOTE_ROWS) * REMOTE_ROWS;
    for(size_t row = 0; row < REMOTE_ROWS && first + row < model->count + 2; row++) {
        size_t index = first + row;
        bool selected = index == model->selected;
        if(selected) {
            canvas_draw_box(canvas, 0, 14 + row * 10, 128, 10);
            canvas_set_color(canvas, ColorWhite);
        }
        const char* label = index < model->count ?
                                infrared_remote_get_signal_name(model->remote, index) :
                            index == model->count ? "+ Learn button" :
                                                    "Edit remote";
        furi_string_set(text, label);
        elements_string_fit_width(canvas, text, 120);
        canvas_draw_str(canvas, 4, 22 + row * 10, furi_string_get_cstr(text));
        canvas_set_color(canvas, ColorBlack);
    }
    canvas_draw_line(canvas, 0, 45, 127, 45);
    furi_string_set(text, model->detail);
    elements_string_fit_width(canvas, text, 124);
    canvas_draw_str(canvas, 2, 53, furi_string_get_cstr(text));
    canvas_draw_str(
        canvas,
        2,
        63,
        model->transmitting            ? "Release / Back stops" :
        model->selected < model->count ? "Hold OK: send" :
                                         "OK opens  Back exits");
    furi_string_free(text);
}

static bool infrared_remote_view_input(InputEvent* event, void* context) {
    InfraredRemoteView* instance = context;
    bool consumed = false;
    int posted = -1;
    int32_t selected = -1;
    with_view_model(
        instance->view,
        InfraredRemoteViewModel * model,
        {
            if(event->key == InputKeyBack && event->type == InputTypeShort) {
                // Cancel immediately, including while the app is loading a signal.
                model->cancelled = true;
                model->pressed = false;
            } else if(event->key == InputKeyOk) {
                consumed = true;
                selected = infrared_remote_view_index(model);
                if(selected >= 0 && event->type == InputTypePress && !model->pressed) {
                    model->pressed = true;
                    model->cancelled = false;
                    model->requested = selected;
                    posted = InfraredRemoteViewPress;
                } else if(event->type == InputTypeRelease && model->pressed) {
                    model->pressed = false;
                    posted = InfraredRemoteViewRelease;
                } else if(selected < 0 && event->type == InputTypeShort) {
                    posted = InfraredRemoteViewControl;
                }
            } else if(
                !model->pressed && !model->transmitting &&
                (event->type == InputTypeShort || event->type == InputTypeRepeat)) {
                size_t total = model->count + 2;
                size_t previous = model->selected;
                if(event->key == InputKeyUp) {
                    model->selected = (model->selected + total - 1) % total;
                    consumed = true;
                } else if(event->key == InputKeyDown) {
                    model->selected = (model->selected + 1) % total;
                    consumed = true;
                } else if(event->key == InputKeyLeft) {
                    model->selected =
                        model->selected >= REMOTE_ROWS ? model->selected - REMOTE_ROWS : 0;
                    consumed = true;
                } else if(event->key == InputKeyRight) {
                    model->selected = MIN(model->selected + REMOTE_ROWS, total - 1);
                    consumed = true;
                }
                if(model->selected != previous) {
                    model->cancelled = true;
                    selected = infrared_remote_view_index(model);
                    strlcpy(
                        model->detail,
                        selected >= 0 ? "Loading signal..." : "Remote actions",
                        sizeof(model->detail));
                    posted = InfraredRemoteViewSelect;
                }
            }
        },
        true);
    // A dispatcher callback must not run under the view-model lock.
    if(posted >= 0 && instance->callback) instance->callback(instance->context, posted, selected);
    return consumed;
}

InfraredRemoteView* infrared_remote_view_alloc(void) {
    InfraredRemoteView* instance = calloc(1, sizeof(InfraredRemoteView));
    instance->view = view_alloc();
    view_allocate_model(instance->view, ViewModelTypeLocking, sizeof(InfraredRemoteViewModel));
    view_set_context(instance->view, instance);
    view_set_draw_callback(instance->view, infrared_remote_view_draw);
    view_set_input_callback(instance->view, infrared_remote_view_input);
    return instance;
}

void infrared_remote_view_free(InfraredRemoteView* instance) {
    view_free(instance->view);
    free(instance);
}

View* infrared_remote_view_get_view(InfraredRemoteView* instance) {
    return instance->view;
}

void infrared_remote_view_configure(
    InfraredRemoteView* instance,
    const InfraredRemote* remote,
    int32_t selected,
    InfraredRemoteViewCallback callback,
    void* context) {
    instance->callback = callback;
    instance->context = context;
    with_view_model(
        instance->view,
        InfraredRemoteViewModel * model,
        {
            model->remote = remote;
            model->count = infrared_remote_get_signal_count(remote);
            model->selected = selected == -2                                   ? model->count :
                              selected == -1                                   ? model->count + 1 :
                              selected >= 0 && (size_t)selected < model->count ? (size_t)selected :
                                                                                 0;
            model->pressed = model->transmitting = false;
            model->cancelled = true;
            model->requested = -1;
            strlcpy(model->detail, "Loading signal...", sizeof(model->detail));
        },
        true);
}

int32_t infrared_remote_view_selected(InfraredRemoteView* instance) {
    int32_t selected;
    with_view_model(
        instance->view,
        InfraredRemoteViewModel * model,
        { selected = infrared_remote_view_index(model); },
        false);
    return selected;
}

bool infrared_remote_view_can_send(InfraredRemoteView* instance, int32_t index) {
    bool allowed;
    with_view_model(
        instance->view,
        InfraredRemoteViewModel * model,
        {
            allowed = !model->cancelled && model->requested == index &&
                      infrared_remote_view_index(model) == index;
        },
        false);
    return allowed;
}

void infrared_remote_view_cancel(InfraredRemoteView* instance) {
    with_view_model(
        instance->view,
        InfraredRemoteViewModel * model,
        {
            model->cancelled = true;
            model->pressed = model->transmitting = false;
        },
        true);
}

void infrared_remote_view_status(
    InfraredRemoteView* instance,
    int32_t index,
    const char* detail,
    bool transmitting) {
    with_view_model(
        instance->view,
        InfraredRemoteViewModel * model,
        {
            if(infrared_remote_view_index(model) == index) {
                strlcpy(model->detail, detail, sizeof(model->detail));
                model->transmitting = transmitting;
            }
        },
        true);
}
