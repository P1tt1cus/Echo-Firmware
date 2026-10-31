"""Run the production HID worker through disconnect/cancel races without a host."""

import ast
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "applications/main/bad_usb/helpers"
tree = ast.parse((ROOT / "scripts/echo_shared_menu_test.py").read_text())
STUB = next(
    ast.literal_eval(n.value)
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets)
)


def function(source, name):
    m = re.search(
        r"^static (?:uint32_t|int32_t) " + name + r"\([^;]*?\) \{", source, re.M
    )
    assert m, name
    depth, end = 1, m.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[m.start() : end] + "\n"


source = (APP / "ducky_script.c").read_text()
flags = source[
    source.index("typedef enum {") : source.index("} WorkerEvtFlags;")
    + len("} WorkerEvtFlags;")
]
header = (APP / "ducky_script.h").read_text()
types = header[
    header.index("typedef enum {") : header.index("typedef struct BadUsbScript")
]
struct = (APP / "ducky_script_i.h").read_text()
struct = struct[
    struct.index("struct BadUsbScript {") : struct.index("uint16_t ducky_get_keycode")
]
ADAPTER = r"""
#define FURI_LOG_I(...) ((void)0)
#define FURI_LOG_D(...) ((void)0)
#define FURI_LOG_E(...) ((void)0)
#define RECORD_STORAGE "storage"
#define FILE_BUFFER_LEN 16
#define SCRIPT_STATE_ERROR (-1)
#define SCRIPT_STATE_END (-2)
#define SCRIPT_STATE_STRING_START (-5)
#define SCRIPT_STATE_WAIT_FOR_BTN (-6)
#define FuriFlagError 0x80000000U
#define FuriFlagErrorTimeout 0xfffffffeU
#define FuriFlagErrorResource 0xfffffffdU
#define FuriWaitForever 0xffffffffU
#define FuriFlagWaitAny 0
#define FuriFlagNoClear 1
#define FSAM_READ 0
#define FSOM_OPEN_EXISTING 0
#define DolphinDeedBadUsbPlayScript 0
typedef int File;
typedef int FuriThread;
typedef int BadUsbHidInterface;
typedef int BadUsbHidConfig;
typedef struct {
 bool (*is_connected)(void*);
 bool (*release_all)(void*);
 void (*set_state_callback)(void*,void*,void*);
 void (*deinit)(void*);
} BadUsbHidApi;
typedef struct BadUsbScript BadUsbScript;
"""
RUNTIME = r"""
typedef struct {BadUsbWorkerState state;uint32_t flags;bool connected;} Step;
static Step* steps;static unsigned nsteps,step,release_count,executed,unregistered,deinitialized;
static bool connected,initial_connected;static BadUsbScript* current;static int next_command;
static bool is_connected(void* p) {(void)p;return connected;}
static bool release_all(void* p) {(void)p;release_count++;return true;}
static void set_callback(void* p,void* cb,void* ctx) {(void)p;assert(!cb&&!ctx);unregistered++;}
static void deinit(void* p) {(void)p;assert(unregistered&&release_count);deinitialized++;}
static const BadUsbHidApi hid={is_connected,release_all,set_callback,deinit};
static uint32_t furi_get_tick(void) {static uint32_t tick;return ++tick;}
static void* furi_record_open(const char* name) {(void)name;return NULL;}
static File* storage_file_alloc(void* p) {(void)p;return calloc(1,sizeof(File));}
static bool storage_file_open(File* f,const char* path,int a,int b) {(void)f;(void)path;(void)a;(void)b;return true;}
static bool storage_file_seek(File* f,unsigned off,bool a) {(void)f;(void)off;(void)a;return true;}
static void storage_file_close(File* f) {(void)f;}
static void storage_file_free(File* f) {free(f);}
static bool ducky_script_preload(BadUsbScript* s,File* f) {(void)f;s->hid=&hid;s->st.line_nb=2;return true;}
static int32_t ducky_script_execute_next(BadUsbScript* s,File* f) {(void)f;s->st.line_cur++;executed++;return next_command;}
static bool ducky_string_next(BadUsbScript* s) {(void)s;executed++;return false;}
static void dolphin_deed(int n) {(void)n;}
static uint32_t furi_thread_flags_get(void) {return 0;}
static uint32_t furi_thread_flags_clear(uint32_t flags) {(void)flags;return 0;}
static uint32_t furi_thread_flags_wait(uint32_t mask,uint32_t options,uint32_t timeout) {
 (void)options;(void)timeout;assert(step<nsteps);Step s=steps[step++];
 if(current->st.state!=s.state)fprintf(stderr,"step %u: state %d expected %d\n",step,current->st.state,s.state);
 assert(current->st.state==s.state);assert((s.flags&FuriFlagError)||(s.flags&mask));connected=s.connected;return s.flags;
}
"""
TEST = r"""
static void run(Step* plan,unsigned count,bool initially,int command,unsigned expect_executed) {
 steps=plan;nsteps=count;step=release_count=executed=unregistered=deinitialized=0;connected=initially;next_command=command;
 BadUsbScript s={0};current=&s;s.file_path=alloc_text("synthetic.txt");bad_usb_worker(&s);
 assert(step==nsteps&&executed==expect_executed&&release_count&&unregistered==1&&deinitialized==1);furi_string_free(s.file_path);
}
#define RUN(p,initial,command,executed) run(p,COUNT_OF(p),initial,command,executed)
int main(void) {
 for(uint32_t flags=0;flags<32;flags++) {
  uint32_t out=bad_usb_control_flags(flags);
  assert((out&WorkerEvtEnd)==(flags&WorkerEvtEnd));
  if(flags&WorkerEvtDisconnect)assert((out&(WorkerEvtStartStop|WorkerEvtPauseResume|WorkerEvtConnect))==0);
  else assert(out==flags);
 }
 assert(bad_usb_control_flags(FuriFlagErrorTimeout)==FuriFlagErrorTimeout);
 Step running[]={
  {BadUsbStateIdle,WorkerEvtStartStop,true},
  {BadUsbStateRunning,WorkerEvtDisconnect|WorkerEvtStartStop|WorkerEvtPauseResume,false},
  {BadUsbStateNotConnected,WorkerEvtConnect,true},
  {BadUsbStateIdle,WorkerEvtEnd,true}};
 RUN(running,true,0,0);
 Step coalesced[]={
  {BadUsbStateIdle,WorkerEvtStartStop,true},
  {BadUsbStateRunning,WorkerEvtDisconnect|WorkerEvtConnect|WorkerEvtStartStop,true},
  {BadUsbStateIdle,WorkerEvtEnd,true}};
 RUN(coalesced,true,0,0);
 Step armed[]={
  {BadUsbStateNotConnected,WorkerEvtStartStop,false},
  {BadUsbStateWillRun,WorkerEvtConnect,true},
  {BadUsbStateWillRun,WorkerEvtDisconnect|WorkerEvtStartStop,false},
  {BadUsbStateNotConnected,WorkerEvtConnect,true},
  {BadUsbStateIdle,WorkerEvtEnd,true}};
 RUN(armed,false,0,0);
 Step arm_disconnect[]={
  {BadUsbStateNotConnected,WorkerEvtStartStop,false},
  {BadUsbStateWillRun,WorkerEvtDisconnect,false},
  {BadUsbStateNotConnected,WorkerEvtEnd,false}};
 RUN(arm_disconnect,false,0,0);
 Step arm_exit[]={
  {BadUsbStateNotConnected,WorkerEvtStartStop,false},
  {BadUsbStateWillRun,WorkerEvtConnect,true},
  {BadUsbStateWillRun,WorkerEvtEnd,true}};
 RUN(arm_exit,false,0,0);
 Step cancel_connect[]={
  {BadUsbStateNotConnected,WorkerEvtStartStop,false},
  {BadUsbStateWillRun,WorkerEvtConnect|WorkerEvtStartStop,true},
  {BadUsbStateIdle,WorkerEvtEnd,true}};
 RUN(cancel_connect,false,0,0);
 Step normal_arm[]={
  {BadUsbStateNotConnected,WorkerEvtStartStop,false},
  {BadUsbStateWillRun,WorkerEvtConnect,true},
  {BadUsbStateWillRun,FuriFlagErrorTimeout,true},
  {BadUsbStateRunning,WorkerEvtEnd,true}};
 RUN(normal_arm,false,0,0);
 Step normal_done[]={
  {BadUsbStateIdle,WorkerEvtStartStop,true},
  {BadUsbStateRunning,FuriFlagErrorTimeout,true},
  {BadUsbStateDone,WorkerEvtEnd,true}};
 RUN(normal_done,true,SCRIPT_STATE_END,1);
 Step paused[]={
  {BadUsbStateIdle,WorkerEvtStartStop,true},
  {BadUsbStateRunning,WorkerEvtPauseResume,true},
  {BadUsbStatePaused,WorkerEvtDisconnect|WorkerEvtPauseResume,false},
  {BadUsbStateNotConnected,WorkerEvtEnd,false}};
 RUN(paused,true,0,0);
 Step waitbutton[]={
  {BadUsbStateIdle,WorkerEvtStartStop,true},
  {BadUsbStateRunning,FuriFlagErrorTimeout,true},
  {BadUsbStateWaitForBtn,WorkerEvtDisconnect|WorkerEvtStartStop,false},
  {BadUsbStateNotConnected,WorkerEvtEnd,false}};
 RUN(waitbutton,true,SCRIPT_STATE_WAIT_FOR_BTN,1);
 Step stringdelay[]={
  {BadUsbStateIdle,WorkerEvtStartStop,true},
  {BadUsbStateRunning,FuriFlagErrorTimeout,true},
  {BadUsbStateRunning,WorkerEvtDisconnect|WorkerEvtPauseResume,false},
  {BadUsbStateNotConnected,WorkerEvtEnd,false}};
 RUN(stringdelay,true,SCRIPT_STATE_STRING_START,1);
 Step stopped_before_start[]={
  {BadUsbStateIdle,WorkerEvtStartStop,false},
  {BadUsbStateNotConnected,WorkerEvtEnd,false}};
 RUN(stopped_before_start,true,0,0);
 puts("PASS: production HID worker disconnect priority, pending-run cancellation, reconnect to idle, paused/button/string waits, lost-link start guard and release on exit");
}
"""
with tempfile.TemporaryDirectory(prefix="echo-hid-") as d:
    path = Path(d) / "worker.c"
    path.write_text(
        STUB
        + types
        + flags
        + ADAPTER
        + struct
        + RUNTIME
        + "".join(
            function(source, n)
            for n in ("bad_usb_control_flags", "bad_usb_flags_get", "bad_usb_worker")
        )
        + TEST
    )
    exe = Path(d) / "worker"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-g",
            "-fsanitize=address,undefined",
            "-I",
            str(ROOT / "lib/mlib"),
            str(path),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)
