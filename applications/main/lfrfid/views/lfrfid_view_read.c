#include "lfrfid_view_read.h"
#include <gui/elements.h>
#include <assets_icons.h>

#define TEMP_STR_LEN 128

struct LfRfidReadView {
    View* view;
};

typedef struct {
    IconAnimation* icon;
    LfRfidReadViewMode read_mode;
    LfRfidReadViewStatus status;
} LfRfidReadViewModel;

static void lfrfid_view_read_draw_callback(Canvas* canvas, void* _model) {
    LfRfidReadViewModel* model = _model;
    canvas_set_color(canvas, ColorBlack);

    canvas_set_font(canvas, FontPrimary);
    canvas_draw_str(canvas, 2, 11, "125 kHz RFID");
    canvas_draw_icon_animation(canvas, 116, 2, model->icon);
    canvas_set_font(canvas, FontSecondary);
    const char* mode = "PSK only";
    if(model->read_mode == LfRfidReadAsk) mode = "Auto: ASK (1/2)";
    if(model->read_mode == LfRfidReadPsk) mode = "Auto: PSK (2/2)";
    if(model->read_mode == LfRfidReadAskOnly) mode = "ASK only";
    canvas_draw_str(canvas, 2, 25, mode);
    const char* status = "Searching...";
    if(model->status == LfRfidReadSignal) status = "Signal detected";
    if(model->status == LfRfidReadChecking) status = "Checking data...";
    canvas_draw_str(canvas, 2, 38, status);
    canvas_draw_str(
        canvas,
        2,
        50,
        model->status == LfRfidReadSearching ? "Hold tag at back" : "Keep tag still");
    canvas_draw_str(canvas, 2, 62, "Back stops");
}

void lfrfid_view_read_enter(void* context) {
    LfRfidReadView* read_view = context;
    with_view_model(
        read_view->view, LfRfidReadViewModel * model, { icon_animation_start(model->icon); }, true);
}

void lfrfid_view_read_exit(void* context) {
    LfRfidReadView* read_view = context;
    with_view_model(
        read_view->view, LfRfidReadViewModel * model, { icon_animation_stop(model->icon); }, false);
}

LfRfidReadView* lfrfid_view_read_alloc(void) {
    LfRfidReadView* read_view = malloc(sizeof(LfRfidReadView));
    read_view->view = view_alloc();
    view_set_context(read_view->view, read_view);
    view_allocate_model(read_view->view, ViewModelTypeLocking, sizeof(LfRfidReadViewModel));

    with_view_model(
        read_view->view,
        LfRfidReadViewModel * model,
        {
            model->icon = icon_animation_alloc(&A_Round_loader_8x8);
            view_tie_icon_animation(read_view->view, model->icon);
        },
        false);

    view_set_draw_callback(read_view->view, lfrfid_view_read_draw_callback);
    view_set_enter_callback(read_view->view, lfrfid_view_read_enter);
    view_set_exit_callback(read_view->view, lfrfid_view_read_exit);

    return read_view;
}

void lfrfid_view_read_free(LfRfidReadView* read_view) {
    with_view_model(
        read_view->view, LfRfidReadViewModel * model, { icon_animation_free(model->icon); }, false);

    view_free(read_view->view);
    free(read_view);
}

View* lfrfid_view_read_get_view(LfRfidReadView* read_view) {
    return read_view->view;
}

void lfrfid_view_read_set_read_mode(LfRfidReadView* read_view, LfRfidReadViewMode mode) {
    with_view_model(
        read_view->view,
        LfRfidReadViewModel * model,
        {
            icon_animation_stop(model->icon);
            icon_animation_start(model->icon);
            model->read_mode = mode;
            model->status = LfRfidReadSearching;
        },
        true);
}

void lfrfid_view_read_set_status(LfRfidReadView* read_view, LfRfidReadViewStatus status) {
    with_view_model(
        read_view->view, LfRfidReadViewModel * model, { model->status = status; }, true);
}
