"""Test production RFID read feedback and scene transitions with host GUI/worker adapters."""

import ast
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "applications/main/lfrfid"
tree = ast.parse((ROOT / "scripts/echo_shared_menu_test.py").read_text())
STUB = next(
    ast.literal_eval(n.value)
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets)
)
EXTRA = r"""
typedef struct {bool active;} IconAnimation;
static const Icon A_Round_loader_8x8={8,8};
static IconAnimation* icon_animation_alloc(const Icon* i) {(void)i;return calloc(1,sizeof(IconAnimation));}
static void icon_animation_free(IconAnimation* i) {free(i);}
static void icon_animation_start(IconAnimation* i) {i->active=true;}
static void icon_animation_stop(IconAnimation* i) {i->active=false;}
static void view_tie_icon_animation(View* v,IconAnimation* i) {(void)v;(void)i;}
static void view_set_enter_callback(View* v,void(*cb)(void*)) {(void)v;(void)cb;}
static void view_set_exit_callback(View* v,void(*cb)(void*)) {(void)v;(void)cb;}
static void canvas_draw_icon_animation(Canvas* c,int x,int y,IconAnimation* i) {(void)i;canvas_draw_icon(c,x,y,&A_Round_loader_8x8);}
"""
SCENE_STUB = r"""
typedef int ProtocolId;
typedef const int* NotificationSequence[2];
static const int message_blink_set_color_yellow,message_blink_set_color_green,message_blink_set_color_cyan;
static const NotificationSequence sequence_blink_start_cyan={NULL},sequence_success={NULL},sequence_blink_stop={NULL};
enum {LFRFIDWorkerReadSenseStart,LFRFIDWorkerReadSenseEnd,LFRFIDWorkerReadSenseCardStart,LFRFIDWorkerReadSenseCardEnd,LFRFIDWorkerReadDone,LFRFIDWorkerReadStartASK,LFRFIDWorkerReadStartPSK};
typedef int LFRFIDWorkerReadResult;
enum {LFRFIDWorkerReadTypeAuto,LFRFIDWorkerReadTypeASKOnly,LFRFIDWorkerReadTypePSKOnly};
enum {LfRfidEventReadSenseStart=100,LfRfidEventReadSenseEnd,LfRfidEventReadSenseCardStart,LfRfidEventReadSenseCardEnd,LfRfidEventReadDone,LfRfidEventReadStartASK,LfRfidEventReadStartPSK};
enum {SceneManagerEventTypeCustom,SceneManagerEventTypeBack};
enum {LfRfidViewRead=20,LfRfidSceneReadSuccess=30,DolphinDeedRfidReadSuccess=40};
typedef struct {int type;uint32_t event;} SceneManagerEvent;
typedef struct {LfRfidReadView* read_view;int read_type;void* lfworker;void* notifications;void* view_dispatcher;void* scene_manager;void* popup;FuriString* file_name;ProtocolId protocol_id,protocol_id_next;} LfRfid;
static int next_scene,starts,stops,thread_stops,successes;static uint32_t queued;
static void view_dispatcher_send_custom_event(void* d,uint32_t e) {(void)d;queued=e;}
static void lfrfid_worker_start_thread(void* w) {(void)w;starts++;}
static void lfrfid_worker_read_start(void* w,int t,void(*cb)(LFRFIDWorkerReadResult,ProtocolId,void*),void* ctx) {(void)w;(void)t;(void)cb;(void)ctx;}
static void notification_message(void* n,const NotificationSequence* s) {(void)n;if(s==&sequence_success)successes++;}
static void view_dispatcher_switch_to_view(void* d,int v) {(void)d;assert(v==LfRfidViewRead);}
static void scene_manager_next_scene(void* s,int n) {(void)s;next_scene=n;}
static void dolphin_deed(int d) {assert(d==DolphinDeedRfidReadSuccess);}
static void popup_reset(void* p) {(void)p;}
static void lfrfid_worker_stop(void* w) {(void)w;stops++;}
static void lfrfid_worker_stop_thread(void* w) {(void)w;thread_stops++;}
"""
TEST = r"""
static void reply(LfRfid* app,int result,int protocol) {lfrfid_read_callback(result,protocol,app);SceneManagerEvent e={SceneManagerEventTypeCustom,queued};assert(lfrfid_scene_read_on_event(app,e));}
int main(void) {
 LfRfid app={0};app.read_view=lfrfid_view_read_alloc();app.file_name=alloc_text("previous");
 LfRfidReadViewModel* model=app.read_view->view->model;
 const char* modes[]={"Auto: ASK (1/2)","Auto: PSK (2/2)","ASK only","PSK only"};
 const char* statuses[]={"Searching...","Signal detected","Checking data..."};
 for(int mode=0;mode<4;mode++)for(int state=0;state<3;state++) {
  lfrfid_view_read_set_read_mode(app.read_view,mode);lfrfid_view_read_set_status(app.read_view,state);
  Canvas c={.w=128,.h=64};lfrfid_view_read_draw_callback(&c,model);
  assert(drawn(&c,modes[mode])&&drawn(&c,statuses[state])&&drawn(&c,"Back stops"));
 }
 app.read_type=LFRFIDWorkerReadTypeAuto;lfrfid_scene_read_on_enter(&app);
 assert(model->read_mode==LfRfidReadAsk&&model->status==LfRfidReadSearching);
 reply(&app,LFRFIDWorkerReadSenseStart,-1);assert(model->status==LfRfidReadSignal&&!successes&&!next_scene);
 reply(&app,LFRFIDWorkerReadSenseCardStart,7);assert(model->status==LfRfidReadChecking&&!successes&&!next_scene);
 reply(&app,LFRFIDWorkerReadSenseCardEnd,-1);assert(model->status==LfRfidReadSearching);
 reply(&app,LFRFIDWorkerReadStartPSK,-1);assert(model->read_mode==LfRfidReadPsk);
 reply(&app,LFRFIDWorkerReadDone,7);assert(successes==1&&next_scene==LfRfidSceneReadSuccess&&app.protocol_id==7&&furi_string_empty(app.file_name));
 lfrfid_scene_read_on_exit(&app);assert(stops==1&&thread_stops==1);
 for(int type=LFRFIDWorkerReadTypeASKOnly;type<=LFRFIDWorkerReadTypePSKOnly;type++) {
  app.read_type=type;lfrfid_scene_read_on_enter(&app);int mode=model->read_mode;
  reply(&app,LFRFIDWorkerReadStartPSK,-1);reply(&app,LFRFIDWorkerReadStartASK,-1);assert(model->read_mode==mode);
  lfrfid_scene_read_on_exit(&app);
 }
 assert(starts==3&&stops==3&&thread_stops==3);
 lfrfid_view_read_free(app.read_view);furi_string_free(app.file_name);
 puts("PASS: RFID 12 read layouts, sense vs confirmed decode, auto/fixed modes, re-entry reset and worker stop on exit");
}
"""


def source(path):
    return re.sub(r"^\s*#(?:include|pragma).*$", "", path.read_text(), flags=re.M)


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "rfid.c"
    path.write_text(
        STUB
        + EXTRA
        + source(APP / "views/lfrfid_view_read.h")
        + source(APP / "views/lfrfid_view_read.c")
        + SCENE_STUB
        + source(APP / "scenes/lfrfid_scene_read.c")
        + TEST
    )
    binary = Path(directory) / "rfid"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-function",
            "-Wno-unused-variable",
            "-Wno-sign-compare",
            "-fsanitize=address,undefined",
            "-I",
            str(ROOT / "lib/mlib"),
            str(path),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
