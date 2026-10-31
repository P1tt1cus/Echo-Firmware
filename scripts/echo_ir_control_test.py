"""Run actual IR remote and TX lifecycle code with worker/storage adapters."""

import ast
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def constant(path, name):
    tree = ast.parse(path.read_text())
    return next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
    )


STUB = constant(ROOT / "scripts/echo_shared_menu_test.py", "STUB")
ADAPTER = constant(ROOT / "scripts/echo_ir_view_test.py", "ADAPTER")
clean = lambda s: re.sub(r"^#(?:include|pragma).*$", "", s, flags=re.M)
VIEW = ROOT / "applications/main/infrared/views"
view = clean((VIEW / "infrared_remote_view.h").read_text()) + clean(
    (VIEW / "infrared_remote_view.c").read_text()
)


def function(source, name):
    m = re.search(
        r"^(?:static )?(?:void|bool|InfraredErrorCode)\s+" + name + r"\([^;]*?\) \{",
        source,
        re.M,
    )
    assert m, name
    depth, end = 1, m.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[m.start() : end] + "\n"


RUNTIME = r"""
#define INFRARED_TX_MIN_INTERVAL_MS 50U
#define INFRARED_ERROR_PRESENT(e) ((e)!=0)
typedef int InfraredErrorCode;
enum {InfraredErrorCodeNone,InfraredErrorCodeFileOperationFailed};
typedef struct {uint32_t frequency;size_t timings_size;uint32_t timings[4];float duty_cycle;} InfraredRawSignal;
typedef struct {int protocol;} InfraredMessage;
typedef struct {bool raw;InfraredRawSignal raw_data;InfraredMessage message;} InfraredSignal;
typedef struct {bool is_transmitting,is_learning_new_remote;uint32_t last_transmit_time;} InfraredAppState;
typedef struct {uint32_t selected;int next;} SceneManager;
typedef enum {SceneManagerEventTypeCustom,SceneManagerEventTypeBack,SceneManagerEventTypeTick} SceneManagerEventType;
typedef struct {SceneManagerEventType type;uint32_t event;} SceneManagerEvent;
enum {InfraredSceneRemote,InfraredSceneRemoteList,InfraredSceneStart,InfraredSceneLearn,InfraredSceneEdit,InfraredSceneAskBack,InfraredSceneAskRetry,InfraredSceneLearnEnterName,InfraredViewRemote};
enum {DolphinDeedIrSend,InfraredNotificationMessageBlinkStartSend,InfraredNotificationMessageBlinkStop,InfraredNotificationMessageGreenOn,InfraredNotificationMessageGreenOff};
enum {DialogExResultLeft,DialogExResultRight,DialogExPressCenter,DialogExReleaseCenter};
typedef struct {SceneManager* scene_manager;void* view_dispatcher;void* dialog_ex;void* worker;InfraredRemote* remote;InfraredSignal* current_signal;InfraredAppState app_state;InfraredRemoteView* remote_view;int32_t remote_loaded_index;bool remote_signal_valid;} InfraredApp;
static InfraredApp* current;static uint32_t tick=1000;static bool load_ok=true,cancel_load,raw_signal;static unsigned loads,starts,stops,raw_sets,decoded_sets,callbacks_removed,navigations,dialog_resets;static uint32_t pending[32];static unsigned pending_count;
static uint32_t furi_get_tick(void) {return tick;}
static uint32_t scene_manager_get_scene_state(SceneManager* s,int scene) {(void)scene;return s->selected;}
static void scene_manager_set_scene_state(SceneManager* s,int scene,uint32_t selected) {(void)scene;s->selected=selected;}
static void scene_manager_next_scene(SceneManager* s,int scene) {s->next=scene;}
static bool scene_manager_search_and_switch_to_previous_scene_one_of(SceneManager* s,const uint32_t* scenes,size_t n) {(void)s;(void)scenes;(void)n;navigations++;return true;}
static void view_dispatcher_switch_to_view(void* p,int view) {(void)p;(void)view;}
static void view_dispatcher_send_custom_event(void* p,uint32_t e) {(void)p;assert(pending_count<32);pending[pending_count++]=e;}
static InfraredErrorCode infrared_remote_load_signal(InfraredRemote* r,InfraredSignal* signal,size_t index) {assert(index<r->count);loads++;signal->raw=raw_signal;signal->raw_data.frequency=38000;signal->raw_data.timings_size=4;signal->raw_data.duty_cycle=.33;if(cancel_load)infrared_remote_view_cancel(current->remote_view);return load_ok?0:1;}
static bool infrared_signal_is_raw(InfraredSignal* s) {return s->raw;}
static const InfraredRawSignal* infrared_signal_get_raw_signal(InfraredSignal* s) {return &s->raw_data;}
static const InfraredMessage* infrared_signal_get_message(InfraredSignal* s) {return &s->message;}
static const char* infrared_get_protocol_name(int protocol) {(void)protocol;return "NEC";}
static void infrared_worker_set_raw_signal(void* w,const uint32_t* data,size_t n,uint32_t f,float duty) {(void)w;(void)data;assert(n==4&&f==38000&&duty>0);raw_sets++;}
static void infrared_worker_set_decoded_signal(void* w,const InfraredMessage* m) {(void)w;(void)m;decoded_sets++;}
static void infrared_worker_tx_get_signal_steady_callback(void) {}
static void infrared_worker_tx_set_get_signal_callback(void* w,void(*cb)(void),void* ctx) {(void)w;(void)ctx;if(!cb)callbacks_removed++;}
static void infrared_worker_tx_start(void* w) {(void)w;starts++;}
static void infrared_worker_tx_stop(void* w) {(void)w;stops++;}
static void infrared_play_notification_message(InfraredApp* app,int n) {(void)app;(void)n;}
static void dolphin_deed(int n) {(void)n;}
static void dialog_ex_reset(void* d) {(void)d;dialog_resets++;}
"""
TEST = r"""
static void pump(InfraredApp* a) {while(pending_count){uint32_t e=pending[0];memmove(pending,pending+1,--pending_count*sizeof(*pending));assert(infrared_scene_remote_on_event(a,(SceneManagerEvent){SceneManagerEventTypeCustom,e}));}}
static void key(InfraredApp* a,InputKey k,InputType t) {InputEvent e={k,t};infrared_remote_view_input(&e,a->remote_view);}
static void back(InfraredApp* a) {key(a,InputKeyBack,InputTypeShort);assert(infrared_scene_remote_on_event(a,(SceneManagerEvent){SceneManagerEventTypeBack,0}));}
int main(void) {
 InfraredRemote r={"Synthetic",3};InfraredSignal signal={0};SceneManager manager={0};InfraredApp a={.scene_manager=&manager,.remote=&r,.current_signal=&signal,.remote_view=infrared_remote_view_alloc()};current=&a;
 infrared_scene_remote_on_enter(&a);assert(loads==1&&!starts&&a.remote_signal_valid);
 InfraredRemoteViewModel* m=a.remote_view->view->model;assert(!strcmp(m->detail,"Parsed NEC"));
 key(&a,InputKeyOk,InputTypePress);pump(&a);assert(starts==1&&decoded_sets==1&&loads==1&&m->transmitting);
 unsigned old_loads=loads;assert(infrared_tx_start_button_index(&a,1)==0&&loads==old_loads); // duplicate cannot mutate active signal
 back(&a);assert(stops==1&&!a.app_state.is_transmitting&&!navigations&&!m->transmitting);
 key(&a,InputKeyOk,InputTypeRelease);pump(&a);assert(stops==1);
 tick+=100;key(&a,InputKeyOk,InputTypePress);key(&a,InputKeyOk,InputTypeRelease);pump(&a);assert(starts==2&&stops==2&&!a.app_state.is_transmitting); // queued short tap
 tick+=1;key(&a,InputKeyOk,InputTypePress);pump(&a);assert(starts==2&&!strcmp(m->detail,"Wait, then press OK"));key(&a,InputKeyOk,InputTypeRelease);pump(&a);
 raw_signal=true;key(&a,InputKeyDown,InputTypeShort);pump(&a);assert(loads==2&&!strcmp(m->detail,"RAW 38 kHz 4 samples"));
 tick+=100;key(&a,InputKeyOk,InputTypePress);pump(&a);assert(raw_sets==1&&starts==3);
 infrared_scene_remote_on_exit(&a);assert(stops==3&&manager.selected==1&&!a.app_state.is_transmitting&&!infrared_remote_view_can_send(a.remote_view,1));
 infrared_scene_remote_on_enter(&a);assert(infrared_remote_view_selected(a.remote_view)==1);
 // A queued start cannot run after Back, even if SD loading delayed the app.
 tick+=100;key(&a,InputKeyOk,InputTypePress);back(&a);pump(&a);assert(starts==3&&navigations==1);
 // Cancel inside a storage read; the second intent check must prevent TX.
 a.remote_signal_valid=false;cancel_load=true;key(&a,InputKeyOk,InputTypePress);pump(&a);assert(starts==3);cancel_load=false;
 load_ok=false;a.remote_signal_valid=false;key(&a,InputKeyOk,InputTypePress);pump(&a);assert(starts==3&&!strcmp(m->detail,"Cannot read signal"));key(&a,InputKeyOk,InputTypeRelease);pump(&a);load_ok=true;
 // Learn-result Back stops active TX before a later Back asks to discard.
 a.app_state.is_transmitting=true;assert(infrared_scene_learn_success_on_event(&a,(SceneManagerEvent){SceneManagerEventTypeBack,0}));assert(stops==4&&!a.app_state.is_transmitting);
 infrared_scene_learn_success_on_event(&a,(SceneManagerEvent){SceneManagerEventTypeBack,0});assert(manager.next==InfraredSceneAskBack);
 a.app_state.is_transmitting=true;infrared_scene_learn_success_on_exit(&a);assert(stops==5&&dialog_resets==1&&callbacks_removed==5);
 infrared_remote_view_free(a.remote_view);
 puts("PASS: actual IR selection cache, parsed/RAW setup, single/held start-stop, rate-limit feedback, duplicate starts, Back/loading cancellation, error handling, selection restoration and learn-screen exit cleanup");
}
"""
app = (ROOT / "applications/main/infrared/infrared_app.c").read_text()
scene = clean(
    (ROOT / "applications/main/infrared/scenes/infrared_scene_remote.c").read_text()
)
learn = (
    ROOT / "applications/main/infrared/scenes/infrared_scene_learn_success.c"
).read_text()
events = clean(
    (ROOT / "applications/main/infrared/infrared_custom_event.h").read_text()
)
with tempfile.TemporaryDirectory(prefix="echo-ir-control-") as d:
    p = Path(d) / "test.c"
    exe = Path(d) / "test"
    p.write_text(
        STUB
        + ADAPTER
        + view
        + events
        + RUNTIME
        + "".join(
            function(app, n)
            for n in (
                "infrared_tx_start",
                "infrared_tx_start_button_index",
                "infrared_tx_stop",
            )
        )
        + scene
        + "".join(
            function(learn, n)
            for n in (
                "infrared_scene_learn_success_on_event",
                "infrared_scene_learn_success_on_exit",
            )
        )
        + TEST
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-g",
            "-fsanitize=address,undefined",
            "-I",
            str(ROOT / "lib/mlib"),
            str(p),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)
