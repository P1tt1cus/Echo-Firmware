"""Exercise production IR entry/exit routing, including pre-GUI file-load errors."""

from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "applications/main/infrared/infrared_app.c").read_text()
helper_start = source.index("void infrared_show_remote_load_error(")
helper_end = source.index("\n}", helper_start) + 2
source = (
    source[helper_start:helper_end]
    + "\n"
    + source[source.index("int32_t infrared_app(void* p) {") :]
)
ADAPTER = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef int InfraredErrorCode;
enum {InfraredErrorCodeNone,InfraredErrorCodeWrongFileType,InfraredErrorCodeFileOperationFailed,InfraredErrorCodeWrongFileVersion};
#define INFRARED_ERROR_PRESENT(e) ((e)!=0)
#define INFRARED_ERROR_CHECK(e,t) ((e)==(t))
enum {FuriHalInfraredTxPinInternal,ViewDispatcherTypeDesktop,ViewDispatcherTypeFullscreen,InfraredSceneRpc,InfraredSceneRemote,InfraredSceneStart};
typedef struct {void* remote;void* rpc_ctx;void* scene_manager;void* view_dispatcher;void* gui;char file_path[128];bool active,otg;} InfraredApp;
static InfraredApp* current;static unsigned allocated,freed,stopped,runs,errors,attached,started;static int load_error,next_scene;static bool transmit_during_run;
static InfraredApp* infrared_alloc(void) {allocated++;current=calloc(1,sizeof(*current));return current;}
static void infrared_load_settings(InfraredApp* a) {a->otg=true;}
static void infrared_make_app_folder(InfraredApp* a) {(void)a;}
static void infrared_rpc_command_callback(void) {}
static void rpc_system_app_set_callback(void* ctx,void(*cb)(void),InfraredApp* a) {assert(ctx&&cb&&a);}
static void rpc_system_app_send_started(void* ctx) {assert(ctx);started++;}
static InfraredErrorCode infrared_remote_load(void* r,const char* path) {(void)r;assert(path);return load_error;}
static char error_text[128];
static void infrared_show_error_message(const InfraredApp* a,const char* format,const char* path) {(void)a;assert(format&&path);strcpy(error_text,path);errors++;}
static void furi_string_set(char* destination,const char* source) {strcpy(destination,source);}
static void view_dispatcher_attach_to_gui(void* vd,void* gui,int mode) {(void)vd;(void)gui;(void)mode;attached++;}
static void scene_manager_next_scene(void* sm,int scene) {(void)sm;next_scene=scene;}
static void view_dispatcher_run(void* vd) {(void)vd;runs++;current->active=transmit_during_run;}
static void infrared_tx_stop(InfraredApp* a) {a->active=false;stopped++;}
static void infrared_set_tx_pin(InfraredApp* a,int pin) {assert(stopped&&!a->active&&pin==FuriHalInfraredTxPinInternal);}
static void infrared_enable_otg(InfraredApp* a,bool enabled) {a->otg=enabled;}
static void infrared_free(InfraredApp* a) {assert(!a->otg&&!a->active);freed++;free(a);}
"""
TEST = r"""
static void reset(int error,bool active) {allocated=freed=stopped=runs=errors=attached=started=0;next_scene=-1;load_error=error;transmit_during_run=active;}
int main(void) {
 for(unsigned i=0;i<100;i++) {
  reset(InfraredErrorCodeFileOperationFailed,false);assert(infrared_app("missing.ir")==-1);assert(allocated==1&&freed==1&&stopped==1&&errors==1&&!runs&&!attached);
  reset(InfraredErrorCodeWrongFileType,false);assert(infrared_app("library.ir")==-1);assert(freed==1&&errors==1&&!runs&&!strcmp(error_text,"Not an IR\nremote file."));
 }
 reset(InfraredErrorCodeWrongFileVersion,false);assert(infrared_app("future.ir")==-1);assert(!strcmp(error_text,"Unsupported\nfile version.")&&freed==1);
 reset(0,true);assert(infrared_app("valid.ir")==0);assert(freed==1&&stopped==1&&runs==1&&attached==1&&next_scene==InfraredSceneRemote);
 reset(0,false);assert(infrared_app(NULL)==0);assert(freed==1&&runs==1&&next_scene==InfraredSceneStart);
 reset(0,true);assert(infrared_app("RPC 1234")==0);assert(freed==1&&stopped==1&&started==1&&next_scene==InfraredSceneRpc);
 puts("PASS: IR missing/wrong-type direct loads release app, normal/menu/RPC exits stop before output reset and restore GPIO power");
}
"""
with tempfile.TemporaryDirectory(prefix="echo-ir-exit-") as d:
    p = Path(d) / "test.c"
    exe = Path(d) / "test"
    p.write_text(ADAPTER + source + TEST)
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-g",
            "-fsanitize=address,undefined",
            str(p),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)
