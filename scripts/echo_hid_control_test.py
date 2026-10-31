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
        r"^(?:static )?(?:uint32_t|int32_t|bool) " + name + r"\([^;]*?\) \{",
        source,
        re.M,
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
#define HID_KEYBOARD_NONE 0
#define HID_KEYBOARD_RETURN 40
#define BADUSB_ASCII_TO_KEY(script,x) ((script)->layout[(uint8_t)(x)])
typedef int File;
typedef int FuriThread;
typedef int BadUsbHidInterface;
typedef int BadUsbHidConfig;
typedef struct {
 bool (*kb_press)(void*,uint16_t);
 bool (*kb_release)(void*,uint16_t);
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
static bool connected,file_open=true;static uint32_t queued_flags,interrupt_flag;static unsigned presses,key_releases,interrupt_after;static BadUsbScript* current;static int next_command;
static bool is_connected(void* p) {(void)p;return connected;}
static bool release_all(void* p) {(void)p;release_count++;return true;}
static void set_callback(void* p,void* cb,void* ctx) {(void)p;assert(!cb&&!ctx);unregistered++;}
static void deinit(void* p) {(void)p;assert(unregistered&&release_count);deinitialized++;}
static bool press(void* p,uint16_t key) {(void)p;(void)key;if(++presses==interrupt_after)queued_flags=interrupt_flag;return true;}
static bool release(void* p,uint16_t key) {(void)p;(void)key;key_releases++;return true;}
static bool ducky_altchar(BadUsbScript* s,const char* value) {(void)value;return press(s->hid_inst,1)&&release(s->hid_inst,1);}
static const BadUsbHidApi hid={press,release,is_connected,release_all,set_callback,deinit};
static uint32_t furi_get_tick(void) {static uint32_t tick;return ++tick;}
static void* furi_record_open(const char* name) {(void)name;return NULL;}
static File* storage_file_alloc(void* p) {(void)p;return calloc(1,sizeof(File));}
static bool storage_file_open(File* f,const char* path,int a,int b) {(void)f;(void)path;(void)a;(void)b;return file_open;}
static bool storage_file_seek(File* f,unsigned off,bool a) {(void)f;(void)off;(void)a;return true;}
static void storage_file_close(File* f) {(void)f;}
static void storage_file_free(File* f) {free(f);}
static bool ducky_script_preload(BadUsbScript* s,File* f) {(void)f;s->hid=&hid;s->hid_initialized=true;s->st.line_nb=2;return true;}
static int32_t ducky_script_execute_next(BadUsbScript* s,File* f) {(void)f;s->st.line_cur++;executed++;return next_command;}
static bool ducky_string_next(BadUsbScript* s) {(void)s;executed++;return false;}
static void dolphin_deed(int n) {(void)n;}
static uint32_t furi_thread_flags_get(void) {return queued_flags;}
static uint32_t furi_thread_flags_clear(uint32_t flags) {(void)flags;return 0;}
static uint32_t furi_thread_flags_wait(uint32_t mask,uint32_t options,uint32_t timeout) {
 (void)options;(void)timeout;assert(step<nsteps);Step s=steps[step++];
 if(current->st.state!=s.state)fprintf(stderr,"step %u: state %d expected %d\n",step,current->st.state,s.state);
 assert(current->st.state==s.state);assert((s.flags&FuriFlagError)||(s.flags&mask));connected=s.connected;return s.flags;
}
"""
TEST = r"""
static bool run(Step* plan,unsigned count,bool initially,int command,unsigned expect_executed) {
 steps=plan;nsteps=count;step=release_count=executed=unregistered=deinitialized=0;connected=initially;next_command=command;
 BadUsbScript s={0};current=&s;s.file_path=alloc_text("synthetic.txt");bad_usb_worker(&s);
 assert(step==nsteps&&executed==expect_executed);
 if(file_open)assert(release_count&&unregistered==1&&deinitialized==1);
 else assert(!release_count&&!unregistered&&!deinitialized);
 furi_string_free(s.file_path);return s.st.interrupted;
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
 assert(RUN(running,true,0,0));
 Step coalesced[]={
  {BadUsbStateIdle,WorkerEvtStartStop,true},
  {BadUsbStateRunning,WorkerEvtDisconnect|WorkerEvtConnect|WorkerEvtStartStop,true},
  {BadUsbStateIdle,WorkerEvtEnd,true}};
 assert(RUN(coalesced,true,0,0));
 Step armed[]={
  {BadUsbStateNotConnected,WorkerEvtStartStop,false},
  {BadUsbStateWillRun,WorkerEvtConnect,true},
  {BadUsbStateWillRun,WorkerEvtDisconnect|WorkerEvtStartStop,false},
  {BadUsbStateNotConnected,WorkerEvtConnect,true},
  {BadUsbStateIdle,WorkerEvtEnd,true}};
 assert(RUN(armed,false,0,0));
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
 Step file_error[]={{BadUsbStateFileError,WorkerEvtEnd,false}};
 file_open=false;RUN(file_error,false,0,0);file_open=true;
 BadUsbScript text_script={.hid=&hid};
 for(unsigned i=0;i<128;i++)text_script.layout[i]=i;
 const uint32_t controls[]={WorkerEvtEnd,WorkerEvtDisconnect,WorkerEvtStartStop};
 for(unsigned i=0;i<COUNT_OF(controls);i++) {
  for(unsigned alt=0;alt<2;alt++) {
   queued_flags=0;presses=key_releases=0;interrupt_after=3;interrupt_flag=controls[i];
   assert(alt?ducky_altstring(&text_script,"abcdefghi"):ducky_string(&text_script,"ab\ncdefghi"));
   assert(presses==3&&key_releases==3&&queued_flags==controls[i]);
  }
 }
 queued_flags=0;presses=key_releases=0;interrupt_after=0;
 assert(ducky_string(&text_script,"abc"));assert(presses==3&&key_releases==3);
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
            for n in (
                "bad_usb_script_interrupted",
                "ducky_altstring",
                "ducky_string",
                "bad_usb_control_flags",
                "bad_usb_flags_get",
                "bad_usb_worker",
            )
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
