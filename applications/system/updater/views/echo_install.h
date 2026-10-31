#pragma once

/* Echo's private, code-drawn installer artwork; shared with the visual preview. */
#include <gui/canvas.h>
#include <gui/elements.h>
#include <furi.h>
#include <stdio.h>
#include <string.h>

static inline void
    echo_install_text(Canvas* canvas, int x, int y, size_t width, const char* text) {
    FuriString* line = furi_string_alloc_set(text);
    elements_string_fit_width(canvas, line, width);
    canvas_draw_str(canvas, x, y, furi_string_get_cstr(line));
    furi_string_free(line);
}

static inline void echo_install_wordmark(Canvas* canvas) {
    static const uint8_t letters[4][7] = {
        {31, 16, 16, 30, 16, 16, 31},
        {15, 16, 16, 16, 16, 16, 15},
        {17, 17, 17, 31, 17, 17, 17},
        {14, 17, 17, 17, 17, 17, 14},
    };
    for(size_t letter = 0; letter < 4; ++letter) {
        for(size_t row = 0; row < 7; ++row) {
            for(size_t col = 0; col < 5; ++col) {
                if(letters[letter][row] & (1u << (4 - col)))
                    canvas_draw_box(canvas, 43 + letter * 19 + col * 3, 14 + row * 3, 3, 3);
            }
        }
    }
    /* Open pulse rings echo the desktop animation. */
    canvas_draw_circle(canvas, 23, 23, 11);
    canvas_draw_circle(canvas, 23, 23, 6);
    canvas_set_color(canvas, ColorWhite);
    canvas_draw_box(canvas, 24, 11, 12, 25);
    canvas_set_color(canvas, ColorBlack);
    canvas_draw_box(canvas, 23, 22, 3, 3);
}

static inline void
    echo_install_draw(Canvas* canvas, const char* status, uint8_t progress, bool failed) {
    canvas_clear(canvas);
    canvas_set_color(canvas, ColorBlack);
    if(failed) {
        canvas_set_font(canvas, FontPrimary);
        echo_install_text(canvas, 4, 10, 120, "Echo update failed");
        canvas_draw_line(canvas, 4, 13, 123, 13);
        canvas_set_font(canvas, FontSecondary);
        /* Keep the original diagnostic text and stage/error code available. */
        elements_text_box(canvas, 5, 17, 118, 27, AlignLeft, AlignTop, status, false);
        canvas_draw_line(canvas, 4, 46, 123, 46);
        canvas_draw_str(canvas, 5, 54, "OK: retry");
        canvas_draw_str(canvas, 5, 63, "Hold Back: exit");
        return;
    }

    bool complete = strncmp(status, "Restarting", 10) == 0;
    unsigned percent = complete ? 100 : (progress > 100 ? 100 : progress);
    canvas_set_font(canvas, FontSecondary);
    canvas_draw_str(canvas, 6, 9, complete ? "Restarting Echo" : "Installing Echo");
    char number[6];
    snprintf(number, sizeof(number), "%u%%", percent);
    canvas_draw_str_aligned(canvas, 122, 9, AlignRight, AlignBottom, number);
    echo_install_wordmark(canvas);
    canvas_draw_rframe(canvas, 6, 37, 116, 8, 2);
    if(percent) canvas_draw_box(canvas, 8, 39, (112 * percent + 99) / 100, 4);

    char stage[64];
    snprintf(stage, sizeof(stage), "%s", status);
    /* The worker retains per-stage progress; show its overall progress only once. */
    char* suffix = strrchr(stage, ' ');
    if(suffix) {
        size_t digits = strspn(suffix + 1, "0123456789");
        if(digits && suffix[digits + 1] == '%' && suffix[digits + 2] == '\0') *suffix = '\0';
    }
    echo_install_text(canvas, 6, 55, 116, stage);
    canvas_set_font(canvas, FontKeyboard);
    echo_install_text(canvas, 6, 63, 116, complete ? "Please wait" : "Keep powered on");
}
