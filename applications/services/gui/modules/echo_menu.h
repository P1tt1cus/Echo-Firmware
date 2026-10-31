#pragma once

/* Private Echo styling for the shared GUI controls. No exported API changes. */
#include <gui/canvas.h>
#include <gui/elements.h>
#include <furi.h>
#include <stdio.h>
#include <string.h>

static inline FuriString* echo_menu_title(void) {
    const char* name = furi_thread_get_name(furi_thread_get_current_id());
    return furi_string_alloc_set(name && *name ? name : "Echo");
}

static inline void echo_menu_fit(Canvas* canvas, int x, int y, size_t width, const char* text) {
    FuriString* fitted = furi_string_alloc_set(text);
    elements_string_fit_width(canvas, fitted, width);
    canvas_draw_str(canvas, x, y, furi_string_get_cstr(fitted));
    furi_string_free(fitted);
}

static inline void echo_menu_icon(Canvas* canvas, int x, int y, const char* label) {
    if(strstr(label, "Saved") || strstr(label, "File") || strstr(label, "Log")) {
        canvas_draw_frame(canvas, x, y + 2, 8, 6);
        canvas_draw_line(canvas, x, y, x + 3, y);
        canvas_draw_line(canvas, x, y, x, y + 2);
    } else if(strstr(label, "Setting") || strstr(label, "Config")) {
        for(int i = 0; i < 3; ++i) {
            canvas_draw_line(canvas, x, y + 1 + i * 3, x + 7, y + 1 + i * 3);
            canvas_draw_box(canvas, x + 1 + (i % 2) * 4, y + i * 3, 2, 3);
        }
    } else if(strstr(label, "Read") || strstr(label, "Scan")) {
        canvas_draw_frame(canvas, x + 1, y, 6, 8);
        canvas_draw_line(canvas, x + 3, y + 3, x + 4, y + 3);
        canvas_draw_line(canvas, x + 3, y + 5, x + 4, y + 5);
    } else if(strstr(label, "Add") || strstr(label, "New")) {
        canvas_draw_line(canvas, x + 3, y + 1, x + 3, y + 7);
        canvas_draw_line(canvas, x, y + 4, x + 6, y + 4);
    } else {
        canvas_draw_line(canvas, x + 2, y + 1, x + 5, y + 4);
        canvas_draw_line(canvas, x + 5, y + 4, x + 2, y + 7);
    }
}

static inline const char* echo_menu_hint(const char* label) {
    if(strcmp(label, "Read") == 0) return "Start reading";
    if(strcmp(label, "Saved") == 0) return "Open saved items";
    if(strcmp(label, "Add Manually") == 0) return "Create a new item";
    if(strcmp(label, "Extra Actions") == 0) return "Additional tools";
    if(strcmp(label, "USB-UART Bridge") == 0) return "Serial bridge setup";
    if(strcmp(label, "GPIO Manual Control") == 0) return "Control GPIO pins";
    if(strcmp(label, "I2C-Scanner") == 0) return "Find I2C devices";
    return "OK: select  Back: up";
}

static inline void
    echo_menu_header(Canvas* canvas, const char* title, size_t position, size_t count) {
    int width = canvas_width(canvas);
    char counter[24];
    snprintf(counter, sizeof(counter), "%zu/%zu", count ? position + 1 : 0, count);
    canvas_set_color(canvas, ColorBlack);
    canvas_set_font(canvas, FontSecondary);
    size_t counter_width = canvas_string_width(canvas, counter);
    canvas_draw_str_aligned(canvas, width - 2, 10, AlignRight, AlignBottom, counter);
    canvas_set_font(canvas, FontPrimary);
    /* Narrow/portrait layouts use the entire title area without an icon. */
    echo_menu_fit(
        canvas, 2, 10, width > (int)counter_width + 8 ? width - counter_width - 8 : 1, title);
    canvas_draw_line(canvas, 1, 12, width - 2, 12);
    canvas_set_font(canvas, FontSecondary);
}

static inline void echo_menu_footer(Canvas* canvas, const char* hint) {
    int width = canvas_width(canvas);
    int height = canvas_height(canvas);
    canvas_set_color(canvas, ColorBlack);
    canvas_draw_line(canvas, 1, height - 9, width - 2, height - 9);
    canvas_set_font(canvas, FontKeyboard);
    echo_menu_fit(canvas, 2, height - 1, width - 4, hint);
}

static inline void
    echo_menu_scrollbar(Canvas* canvas, size_t position, size_t count, size_t rows) {
    if(count <= rows) return;
    int x = canvas_width(canvas) - 2;
    int bottom = canvas_height(canvas) - 12;
    canvas_set_color(canvas, ColorBlack);
    canvas_draw_line(canvas, x, 15, x, bottom);
    canvas_draw_box(canvas, x - 1, 15 + position * (bottom - 20) / (count - 1), 3, 6);
}
