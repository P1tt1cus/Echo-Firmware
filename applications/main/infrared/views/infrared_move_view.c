#include "infrared_move_view.h"

#include <m-array.h>

#include <gui/canvas.h>
#include <gui/elements.h>

#include <toolbox/m_cstr_dup.h>

#define LIST_ITEMS    3U
#define LIST_LINE_H   13U
#define HEADER_H      12U
#define MOVE_X_OFFSET 5U

struct InfraredMoveView {
    View* view;
    InfraredMoveCallback callback;
    void* callback_context;
};

ARRAY_DEF(InfraredMoveViewItemArray, const char*, M_CSTR_DUP_OPLIST); //-V575

typedef struct {
    InfraredMoveViewItemArray_t labels;
    int32_t list_offset;
    int32_t current_idx;
    int32_t start_idx;
    bool is_moving;
} InfraredMoveViewModel;

static void infrared_move_view_draw_callback(Canvas* canvas, void* _model) {
    InfraredMoveViewModel* model = _model;
    const size_t count = InfraredMoveViewItemArray_size(model->labels);
    canvas_set_color(canvas, ColorBlack);
    canvas_set_font(canvas, FontSecondary);
    char header[32];
    snprintf(
        header,
        sizeof(header),
        "Reorder  %lu/%lu",
        count ? (unsigned long)model->current_idx + 1 : 0,
        (unsigned long)count);
    canvas_draw_str(canvas, 2, 9, header);
    canvas_draw_line(canvas, 0, 11, 127, 11);
    for(size_t row = 0; row < LIST_ITEMS && row + model->list_offset < count; row++) {
        size_t index = row + model->list_offset;
        uint8_t x = model->is_moving && model->current_idx == (int32_t)index ? MOVE_X_OFFSET : 0;
        uint8_t y = HEADER_H + row * LIST_LINE_H;
        canvas_set_color(canvas, ColorBlack);
        if(model->current_idx == (int32_t)index) {
            canvas_draw_box(canvas, x, y, 123 - x, LIST_LINE_H);
            canvas_set_color(canvas, ColorWhite);
        }
        char label[128];
        strlcpy(label, *InfraredMoveViewItemArray_cget(model->labels, index), sizeof(label));
        size_t length = strlen(label);
        while(length && canvas_string_width(canvas, label) > 119 - x)
            label[--length] = 0;
        canvas_draw_str(canvas, x + 2, y + 10, label);
    }
    canvas_set_color(canvas, ColorBlack);
    if(!count) canvas_draw_str(canvas, 2, 30, "No buttons");
    if(count > LIST_ITEMS) {
        elements_scrollbar_pos(
            canvas, 128, HEADER_H, LIST_ITEMS * LIST_LINE_H, model->current_idx, count);
    }
    canvas_draw_line(canvas, 0, 53, 127, 53);
    canvas_draw_str(
        canvas, 2, 63, model->is_moving ? "OK save  Back cancel" : "OK pick  Back exit");
}

static void update_list_offset(InfraredMoveViewModel* model) {
    if(model->current_idx < model->list_offset) model->list_offset = model->current_idx;
    if(model->current_idx >= model->list_offset + (int32_t)LIST_ITEMS) {
        model->list_offset = model->current_idx - LIST_ITEMS + 1;
    }
}

static void infrared_move_view_reorder(InfraredMoveViewModel* model, int32_t from, int32_t to) {
    // Adjacent swaps also preserve insertion order when moving across the list
    // boundary; swapping the endpoints alone would display a different result.
    while(from < to) {
        InfraredMoveViewItemArray_swap_at(model->labels, from, from + 1);
        from++;
    }
    while(from > to) {
        InfraredMoveViewItemArray_swap_at(model->labels, from, from - 1);
        from--;
    }
}

static bool infrared_move_view_input_callback(InputEvent* event, void* context) {
    InfraredMoveView* move_view = context;
    bool consumed = false;
    bool commit = false;
    uint32_t from = 0, to = 0;
    with_view_model(
        move_view->view,
        InfraredMoveViewModel * model,
        {
            const int32_t count = InfraredMoveViewItemArray_size(model->labels);
            if((event->type == InputTypeShort || event->type == InputTypeRepeat) &&
               (event->key == InputKeyUp || event->key == InputKeyDown)) {
                consumed = true;
                if(count) {
                    int32_t previous = model->current_idx;
                    model->current_idx =
                        (previous + (event->key == InputKeyUp ? count - 1 : 1)) % count;
                    if(model->is_moving)
                        infrared_move_view_reorder(model, previous, model->current_idx);
                    update_list_offset(model);
                }
            } else if(event->key == InputKeyOk && event->type == InputTypeShort) {
                consumed = true;
                if(count) {
                    if(model->is_moving) {
                        from = model->start_idx;
                        to = model->current_idx;
                        commit = from != to;
                    } else {
                        model->start_idx = model->current_idx;
                    }
                    model->is_moving = !model->is_moving;
                }
            } else if(event->key == InputKeyBack && model->is_moving) {
                consumed = true;
                if(event->type == InputTypeShort) {
                    infrared_move_view_reorder(model, model->current_idx, model->start_idx);
                    model->current_idx = model->start_idx;
                    model->is_moving = false;
                    update_list_offset(model);
                }
            }
        },
        consumed);
    // Posting a task while holding the model lock can block drawing or teardown.
    if(commit && move_view->callback) move_view->callback(from, to, move_view->callback_context);
    return consumed;
}

void infrared_move_view_set_callback(
    InfraredMoveView* move_view,
    InfraredMoveCallback callback,
    void* context) {
    furi_assert(move_view);
    move_view->callback = callback;
    move_view->callback_context = context;
}

void infrared_move_view_add_item(InfraredMoveView* move_view, const char* label) {
    with_view_model(
        move_view->view,
        InfraredMoveViewModel * model,
        { InfraredMoveViewItemArray_push_back(model->labels, label); },
        true);
}

void infrared_move_view_reset(InfraredMoveView* move_view) {
    with_view_model(
        move_view->view,
        InfraredMoveViewModel * model,
        {
            InfraredMoveViewItemArray_reset(model->labels);
            model->list_offset = 0;
            model->start_idx = 0;
            model->current_idx = 0;
            model->is_moving = false;
        },
        false);
    move_view->callback = NULL;
    move_view->callback_context = NULL;
}

InfraredMoveView* infrared_move_view_alloc(void) {
    InfraredMoveView* move_view = calloc(1, sizeof(InfraredMoveView));

    move_view->view = view_alloc();
    view_allocate_model(move_view->view, ViewModelTypeLocking, sizeof(InfraredMoveViewModel));
    view_set_draw_callback(move_view->view, infrared_move_view_draw_callback);
    view_set_input_callback(move_view->view, infrared_move_view_input_callback);
    view_set_context(move_view->view, move_view);

    with_view_model(
        move_view->view,
        InfraredMoveViewModel * model,
        { InfraredMoveViewItemArray_init(model->labels); },
        true);

    return move_view;
}

void infrared_move_view_free(InfraredMoveView* move_view) {
    with_view_model(
        move_view->view,
        InfraredMoveViewModel * model,
        { InfraredMoveViewItemArray_clear(model->labels); },
        true);

    view_free(move_view->view);
    free(move_view);
}

View* infrared_move_view_get_view(InfraredMoveView* move_view) {
    return move_view->view;
}
