#pragma once
#include <gui/view.h>

typedef enum {
    LfRfidReadAsk,
    LfRfidReadPsk,
    LfRfidReadAskOnly,
    LfRfidReadPskOnly
} LfRfidReadViewMode;

typedef enum {
    LfRfidReadSearching,
    LfRfidReadSignal,
    LfRfidReadChecking,
} LfRfidReadViewStatus;

typedef struct LfRfidReadView LfRfidReadView;

LfRfidReadView* lfrfid_view_read_alloc(void);

void lfrfid_view_read_free(LfRfidReadView* read_view);

View* lfrfid_view_read_get_view(LfRfidReadView* read_view);

void lfrfid_view_read_set_read_mode(LfRfidReadView* read_view, LfRfidReadViewMode mode);

void lfrfid_view_read_set_status(LfRfidReadView* read_view, LfRfidReadViewStatus status);
