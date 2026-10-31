#pragma once

#include <gui/view.h>
#include "../infrared_remote.h"

typedef struct InfraredRemoteView InfraredRemoteView;
typedef enum {
    InfraredRemoteViewSelect,
    InfraredRemoteViewPress,
    InfraredRemoteViewRelease,
    InfraredRemoteViewControl,
} InfraredRemoteViewEvent;
typedef void (*InfraredRemoteViewCallback)(void*, InfraredRemoteViewEvent, int32_t);

InfraredRemoteView* infrared_remote_view_alloc(void);
void infrared_remote_view_free(InfraredRemoteView* instance);
View* infrared_remote_view_get_view(InfraredRemoteView* instance);
void infrared_remote_view_configure(
    InfraredRemoteView* instance,
    const InfraredRemote* remote,
    int32_t selected,
    InfraredRemoteViewCallback callback,
    void* context);
int32_t infrared_remote_view_selected(InfraredRemoteView* instance);
bool infrared_remote_view_can_send(InfraredRemoteView* instance, int32_t index);
void infrared_remote_view_cancel(InfraredRemoteView* instance);
void infrared_remote_view_status(
    InfraredRemoteView* instance,
    int32_t index,
    const char* detail,
    bool transmitting);
