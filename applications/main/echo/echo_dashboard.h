#pragma once

/* Echo app-local dashboard. No firmware exports or protocol changes. */
#include <furi.h>
#include <gui/view.h>
#include <stdio.h>
#include <string.h>

typedef enum {
    EchoDashRadio,
    EchoDashFiles,
    EchoDashRead,
    EchoDashTools,
    EchoDashSettings,
    EchoDashLink,
} EchoDashIcon;

typedef struct {
    const char* label;
    const char* description;
    uint32_t id;
    EchoDashIcon icon;
    bool locked;
} EchoDashboardItem;

typedef struct {
    const char* title;
    char status[9];
    const EchoDashboardItem* items;
    size_t count;
    size_t selected;
    EchoDashIcon icon;
} EchoDashboardModel;

typedef struct EchoDashboard {
    View* view;
    void (*callback)(void*, uint32_t);
    void* context;
} EchoDashboard;

static void echo_dashboard_icon(Canvas* canvas, uint8_t x, uint8_t y, EchoDashIcon icon) {
    switch(icon) {
    case EchoDashFiles:
        canvas_draw_frame(canvas, x, y + 2, 8, 6);
        canvas_draw_line(canvas, x, y, x + 3, y);
        canvas_draw_line(canvas, x, y, x, y + 2);
        break;
    case EchoDashSettings:
        for(uint8_t i = 0; i < 3; ++i) {
            canvas_draw_line(canvas, x, y + 1 + i * 3, x + 7, y + 1 + i * 3);
            canvas_draw_box(canvas, x + 1 + (i % 2) * 4, y + i * 3, 2, 3);
        }
        break;
    case EchoDashRead:
        canvas_draw_frame(canvas, x + 1, y, 6, 8);
        canvas_draw_line(canvas, x + 3, y + 3, x + 4, y + 3);
        canvas_draw_line(canvas, x + 3, y + 5, x + 4, y + 5);
        break;
    case EchoDashTools:
        canvas_draw_line(canvas, x, y, x + 7, y + 7);
        canvas_draw_line(canvas, x + 7, y, x, y + 7);
        canvas_draw_frame(canvas, x, y, 3, 3);
        break;
    case EchoDashLink:
        canvas_draw_frame(canvas, x, y + 1, 5, 4);
        canvas_draw_frame(canvas, x + 3, y + 4, 5, 4);
        break;
    default:
        canvas_draw_line(canvas, x, y + 2, x + 3, y);
        canvas_draw_line(canvas, x + 3, y, x + 7, y + 2);
        canvas_draw_line(canvas, x + 2, y + 4, x + 5, y + 4);
        canvas_draw_box(canvas, x + 3, y + 6, 2, 2);
        break;
    }
}

static void echo_dashboard_draw(Canvas* canvas, void* context) {
    const EchoDashboardModel* model = context;
    canvas_clear(canvas);
    canvas_set_color(canvas, ColorBlack);
    if(!model->count) return;
    echo_dashboard_icon(canvas, 2, 2, model->icon);
    canvas_set_font(canvas, FontPrimary);
    canvas_draw_str(canvas, 14, 10, model->title);
    canvas_set_font(canvas, FontSecondary);
    canvas_draw_str_aligned(canvas, 126, 10, AlignRight, AlignBottom, model->status);
    canvas_draw_line(canvas, 1, 12, 126, 12);
    size_t first = model->selected < 4 ? 0 : model->selected - 3;
    for(size_t row = 0; row < 4 && first + row < model->count; ++row) {
        size_t i = first + row;
        uint8_t y = 14 + row * 10;
        if(i == model->selected) {
            canvas_draw_rbox(canvas, 1, y, 122, 10, 2);
            canvas_set_color(canvas, ColorWhite);
        }
        echo_dashboard_icon(canvas, 4, y + 1, model->items[i].icon);
        canvas_draw_str(canvas, 16, y + 8, model->items[i].label);
        if(model->items[i].locked) {
            canvas_draw_frame(canvas, 114, y + 4, 5, 4);
            canvas_draw_frame(canvas, 115, y + 2, 3, 3);
        }
        canvas_set_color(canvas, ColorBlack);
    }
    if(model->count > 4) {
        canvas_draw_line(canvas, 126, 15, 126, 52);
        canvas_draw_box(canvas, 125, 15 + model->selected * 32 / (model->count - 1), 3, 6);
    }
    canvas_draw_line(canvas, 1, 55, 126, 55);
    canvas_set_font(canvas, FontKeyboard);
    canvas_draw_str(canvas, 2, 63, model->items[model->selected].description);
}

static bool echo_dashboard_input(InputEvent* event, void* context) {
    EchoDashboard* dashboard = context;
    if(event->key == InputKeyBack) return false;
    if(event->type != InputTypeShort && event->type != InputTypeRepeat) return true;
    uint32_t selected = 0;
    bool activate = false;
    with_view_model(
        dashboard->view,
        EchoDashboardModel * model,
        {
            if(model->count) {
                if(event->key == InputKeyUp)
                    model->selected = (model->selected + model->count - 1) % model->count;
                if(event->key == InputKeyDown)
                    model->selected = (model->selected + 1) % model->count;
                if(event->key == InputKeyLeft) model->selected = 0;
                if(event->key == InputKeyRight) model->selected = model->count - 1;
                selected = model->items[model->selected].id;
                activate = event->key == InputKeyOk && event->type == InputTypeShort &&
                           !model->items[model->selected].locked;
            }
        },
        true);
    /* Scene transitions must be queued after releasing the GUI model. */
    if(activate && dashboard->callback) dashboard->callback(dashboard->context, selected);
    return true;
}

static inline EchoDashboard* echo_dashboard_alloc(void) {
    EchoDashboard* dashboard = calloc(1, sizeof(EchoDashboard));
    dashboard->view = view_alloc();
    view_allocate_model(dashboard->view, ViewModelTypeLocking, sizeof(EchoDashboardModel));
    view_set_context(dashboard->view, dashboard);
    view_set_draw_callback(dashboard->view, echo_dashboard_draw);
    view_set_input_callback(dashboard->view, echo_dashboard_input);
    return dashboard;
}

static inline void echo_dashboard_free(EchoDashboard* dashboard) {
    view_free(dashboard->view);
    free(dashboard);
}

static inline void echo_dashboard_configure(
    EchoDashboard* dashboard,
    const char* title,
    const char* status,
    EchoDashIcon icon,
    const EchoDashboardItem* items,
    size_t count,
    uint32_t selected,
    void (*callback)(void*, uint32_t),
    void* context) {
    furi_check(items && count);
    dashboard->callback = callback;
    dashboard->context = context;
    with_view_model(
        dashboard->view,
        EchoDashboardModel * model,
        {
            model->title = title;
            snprintf(model->status, sizeof(model->status), "%.8s", status);
            model->icon = icon;
            model->items = items;
            model->count = count;
            model->selected = 0;
            for(size_t i = 0; i < count; ++i) {
                if(items[i].id == selected) model->selected = i;
            }
        },
        true);
}

static inline void echo_dashboard_status(EchoDashboard* dashboard, const char* status) {
    with_view_model(
        dashboard->view,
        EchoDashboardModel * model,
        { snprintf(model->status, sizeof(model->status), "%.8s", status); },
        true);
}
