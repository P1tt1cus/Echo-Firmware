"""Exercise production replay control flow with a mocked radio and storage failures.

No radio is used. The actual prepare/send/finish/event functions are compiled.
"""

from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "applications/main/subghz/scenes/subghz_scene_replay_bench.c"
source = SOURCE.read_text()


def function(name):
    match = re.search(
        r"^(?:static )?(?:void|bool) " + name + r"\([^;]*?\) \{", source, re.M
    )
    assert match, name
    start = match.start()
    pos = match.end()
    depth = 1
    while depth:
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
        pos += 1
    return source[start:pos] + "\n"


TYPES = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "subghz_replay_data.h"
typedef struct {char data[8192];} FuriString;
static const char* furi_string_get_cstr(const FuriString* s){return s->data;}
static bool furi_string_empty(const FuriString* s){return !s->data[0];}
static size_t furi_string_size(const FuriString* s){return strlen(s->data);}
static void furi_string_set(FuriString* s,const char* t){snprintf(s->data,sizeof(s->data),"%s",t);}
static void furi_string_cat(FuriString* s,const char* t){assert(strlen(s->data)+strlen(t)<sizeof(s->data));strcat(s->data,t);}
static void furi_string_printf(FuriString* s,const char* f,...){va_list a;va_start(a,f);vsnprintf(s->data,sizeof(s->data),f,a);va_end(a);}
static FuriString* furi_string_alloc(void){return calloc(1,sizeof(FuriString));}
static FuriString* furi_string_alloc_printf(const char* f,...){FuriString* s=furi_string_alloc();va_list a;va_start(a,f);vsnprintf(s->data,sizeof(s->data),f,a);va_end(a);return s;}
static void furi_string_free(FuriString* s){free(s);}
typedef void Storage;typedef void File;
typedef int SubGhzRadioDeviceType;
typedef enum {GuiButtonTypeLeft,GuiButtonTypeCenter,GuiButtonTypeRight} GuiButtonType;
typedef enum {InputTypeShort,InputTypeLong} InputType;
typedef struct {int type;} Protocol;
typedef struct {Protocol* protocol;} SubGhzProtocolDecoderBase;
typedef struct {void* radio_device;} TxRx;
typedef struct SubGhzReplayBench SubGhzReplayBench;
typedef struct {SubGhzReplayBench* replay_bench;TxRx* txrx;void* view_dispatcher;void* widget;void* submenu;void* scene_manager;int state_notifications;} SubGhz;
typedef enum {SceneManagerEventTypeCustom,SceneManagerEventTypeBack,SceneManagerEventTypeTick} EventType;
typedef struct {EventType type;uint32_t event;} SceneManagerEvent;
enum {SubGhzProtocolTypeStatic,SubGhzProtocolTypeDynamic,SubGhzNotificationStateIDLE,SubGhzNotificationStateTx,SubGhzTxRxStartTxStateOk,SubGhzTxRxStartTxStateErrorParserOthers,SubGhzViewIdMenu};
typedef int SubGhzTxRxStartTxState;
static struct {bool endless_tx;} subghz_block_generic_global;
static uint32_t tick,repeat_value,posted;
static int starts,stops,loads,observed_menu;
static bool load_ok=true,sendable=true,format_ok=true,report_ok=true,reserve_ok=true,complete;
static int start_result=SubGhzTxRxStartTxStateOk;
static Protocol protocol={SubGhzProtocolTypeStatic};
static SubGhzProtocolDecoderBase decoder={&protocol};
static uint32_t furi_get_tick(void){return tick;}
static uint32_t furi_kernel_get_tick_frequency(void){return 1000;}
static void subghz_custom_btns_reset(void){}
static bool subghz_key_load(SubGhz* s,const char* p,bool d){(void)s;(void)p;(void)d;loads++;return load_ok;}
static SubGhzProtocolDecoderBase* subghz_txrx_get_decoder(TxRx* t){(void)t;return &decoder;}
static bool subghz_txrx_protocol_is_transmittable(TxRx* t,bool c){(void)t;(void)c;return sendable;}
static void* subghz_txrx_get_fff_data(TxRx* t){return t;}
static bool flipper_format_insert_or_update_uint32(void* f,const char* k,uint32_t* v,int n){(void)f;(void)k;(void)n;repeat_value=*v;return format_ok;}
static int subghz_txrx_tx_start(TxRx* t,void* f){(void)t;(void)f;assert(!subghz_block_generic_global.endless_tx);starts++;return start_result;}
static void subghz_txrx_stop(TxRx* t){(void)t;stops++;}
static bool subghz_devices_is_async_complete_tx(void* d){(void)d;return complete;}
static void view_dispatcher_send_custom_event(void* v,uint32_t e){(void)v;posted=e;}
static void view_dispatcher_switch_to_view(void* v,int i){(void)v;(void)i;}
static void scene_manager_previous_scene(void* s){(void)s;}
static void submenu_reset(void* s){(void)s;}
static void submenu_set_header(void* s,const char* h){(void)s;(void)h;observed_menu++;}
static void submenu_add_item(void* s,const char* l,uint32_t e,void(*cb)(void*,uint32_t),void* c){(void)s;(void)l;(void)e;(void)cb;(void)c;}
static void storage_file_free(File* f){(void)f;}
static size_t storage_file_write(File* f,const void* b,size_t n){(void)f;(void)b;return n;}
static bool storage_file_sync(File* f){(void)f;return true;}
"""

STUBS = r"""
static void bench_menu(SubGhz* s){s->replay_bench->mode=BenchMenu;}
static void bench_page(SubGhz* s,const char* t,BenchMode m,const char* a){(void)t;(void)a;s->replay_bench->mode=m;}
static bool bench_begin_report(SubGhzReplayBench* b){if(reserve_ok)furi_string_set(b->report_base,"Report");return reserve_ok;}
static bool bench_write_report(SubGhzReplayBench* b){b->report_saved=report_ok;return report_ok;}
static void bench_show_result(SubGhz* s){s->replay_bench->mode=BenchPage;}
static void bench_load_tick(SubGhz* s){(void)s;}
static void bench_close_files(SubGhzReplayBench* b){(void)b;}
static void bench_remove_snapshot(SubGhzReplayBench* b,unsigned i){b->loaded[i]=false;}
static void bench_callback(void* c,uint32_t e){(void)c;(void)e;}
static void bench_select(SubGhz* s,unsigned i){(void)s;(void)i;}
static FuriString* bench_comparison(SubGhzReplayBench* b){(void)b;return furi_string_alloc();}
static File* bench_new_file(SubGhzReplayBench* b,FuriString* p,const char* s){(void)b;(void)p;(void)s;return NULL;}
"""

TEST = r"""
static void event(SubGhz* s,EventType type,uint32_t e){SceneManagerEvent v={type,e};assert(subghz_scene_replay_bench_on_event(s,v));}
int main(void){
 SubGhzReplayBench b={0};TxRx radio={0};SubGhz s={.replay_bench=&b,.txrx=&radio};
 b.report_base=furi_string_alloc();b.report_path=furi_string_alloc();b.test_status=furi_string_alloc();b.snapshot[0]=furi_string_alloc();
 b.observation="Unknown";b.loaded[0]=true;b.capture[0].bytes=200;b.capture[0].frequency=433920000;strcpy(b.capture[0].protocol,"Princeton");
 bench_prepare(&s);assert(b.mode==BenchPrepared&&starts==0&&repeat_value==1);
 bench_button(GuiButtonTypeCenter,InputTypeLong,&s);assert(posted==0&&starts==0);
 bench_button(GuiButtonTypeCenter,InputTypeShort,&s);assert(posted==BenchSend&&starts==0);
 tick=100;event(&s,SceneManagerEventTypeCustom,posted);assert(starts==1&&b.mode==BenchSending);
 event(&s,SceneManagerEventTypeCustom,BenchSend);assert(starts==1); // Queued duplicate must not replay.
 tick=10100;event(&s,SceneManagerEventTypeTick,0);assert(stops==1&&b.mode==BenchPage&&b.elapsed_ms==10000);
 assert(strstr(b.test_status->data,"time limit")&&!strstr(b.test_status->data,"completed"));
 bench_prepare(&s);tick=UINT32_MAX-50;bench_send(&s);tick=75;complete=true;
 event(&s,SceneManagerEventTypeTick,0);assert(b.elapsed_ms==126&&strstr(b.test_status->data,"receiver response unverified"));
 complete=false;bench_prepare(&s);bench_send(&s);event(&s,SceneManagerEventTypeBack,0);assert(strstr(b.test_status->data,"Stopped by user"));
 int before=starts;protocol.type=SubGhzProtocolTypeDynamic;bench_prepare(&s);assert(b.mode==BenchPage&&starts==before);bench_send(&s);assert(starts==before);
 protocol.type=SubGhzProtocolTypeStatic;load_ok=false;bench_prepare(&s);assert(b.mode==BenchPage&&starts==before);load_ok=true;
 b.capture[0].raw=true;b.capture[0].duration_us=10000001;bench_prepare(&s);assert(b.mode==BenchPage&&starts==before);
 b.capture[0].raw=false;b.capture[0].bytes=8193;bench_prepare(&s);assert(b.mode==BenchPage);b.capture[0].bytes=200;
 format_ok=false;bench_prepare(&s);assert(b.mode==BenchPage);format_ok=true;
 bench_prepare(&s);reserve_ok=false;bench_send(&s);assert(starts==before);reserve_ok=true;
 bench_prepare(&s);report_ok=false;bench_send(&s);assert(starts==before&&strstr(b.test_status->data,"Not started"));report_ok=true;
 bench_prepare(&s);start_result=SubGhzTxRxStartTxStateErrorParserOthers;bench_send(&s);assert(starts==before+1&&strstr(b.test_status->data,"Start failed"));
 event(&s,SceneManagerEventTypeCustom,BenchObserve);assert(b.mode==BenchObservation);
 event(&s,SceneManagerEventTypeCustom,BenchAccepted);assert(strcmp(b.observation,"Expected response")==0&&b.report_saved);
 furi_string_free(b.report_base);furi_string_free(b.report_path);furi_string_free(b.test_status);furi_string_free(b.snapshot[0]);
 puts("PASS: production replay prepare/send guards, no auto TX, duplicate events, cancellation, deadline, clock wrap, storage/start failures and manual observation");
}
"""

types_start = source.index("typedef enum {")
types_end = source.index("static void bench_menu(")
code = TYPES + source[types_start:types_end] + STUBS
for name in [
    "bench_button",
    "bench_prepare",
    "bench_send",
    "bench_finish",
    "subghz_scene_replay_bench_on_event",
]:
    code += function(name)
code += TEST
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    path = folder / "control.c"
    path.write_text(code)
    binary = folder / "control"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-function",
            "-Wno-format",
            "-fsanitize=address,undefined",
            "-I",
            str(ROOT / "applications/main/subghz/helpers"),
            str(path),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
