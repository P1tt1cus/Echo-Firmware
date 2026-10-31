"""Exercise production RAW input/repeat cancellation and TX start cleanup without RF."""

import ast
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "applications/main/subghz"
tree = ast.parse((ROOT / "scripts/echo_shared_menu_test.py").read_text())
STUB = next(
    ast.literal_eval(n.value)
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets)
)


def function(source, name, result=r"void|bool|SubGhzTxRxStartTxState"):
    match = re.search(
        r"^(?:static )?(?:" + result + r")\s+" + name + r"\([^;]*?\) \{", source, re.M
    )
    assert match, name
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start() : end] + "\n"


RAW_ADAPTER = r"""
#include <stdarg.h>
#define FURI_LOG_W(...) ((void)0)
static void furi_string_printf(FuriString* s,const char* fmt,...) {char b[256];va_list v;va_start(v,fmt);vsnprintf(b,sizeof(b),fmt,v);va_end(v);furi_string_set_str(s,b);}
typedef enum {SubGhzRadioDeviceTypeInternal,SubGhzRadioDeviceTypeExternalCC1101} SubGhzRadioDeviceType;
"""
RAW_TEST = r"""
static unsigned calls;static SubGhzCustomEvent posted;
static void callback(SubGhzCustomEvent e,void* context) {
 SubGhzReadRAW* raw=context;assert(!raw->view->locked);posted=e;calls++;
 // Dispatcher consumers can safely acquire the model lock from this callback.
 (void)subghz_read_raw_is_tx_requested(raw);
}
static void key(SubGhzReadRAW* r,InputKey k,InputType t) {InputEvent e={k,t};subghz_read_raw_input(&e,r);}
int main(void) {
 SubGhzReadRAW raw={.callback=callback};raw.context=&raw;raw.view=view_alloc();view_allocate_model(raw.view,0,sizeof(SubGhzReadRAWModel));
 SubGhzReadRAWModel* m=raw.view->model;m->sample_write=alloc_text("");m->file_name=alloc_text("test");
 for(int loaded=0;loaded<2;loaded++) {
  SubGhzReadRAWStatus idle=loaded?SubGhzReadRAWStatusLoadKeyIDLE:SubGhzReadRAWStatusIDLE;
  m->status=idle;calls=0;key(&raw,InputKeyOk,InputTypePress);
  assert(calls==1&&posted==SubGhzCustomEventViewReadRAWSendStart&&subghz_read_raw_is_tx_requested(&raw)&&!m->tx_active);
  key(&raw,InputKeyOk,InputTypePress);assert(calls==1); // duplicate press cannot start twice
  subghz_read_raw_set_tx_active(&raw,true);assert(m->tx_active);
  subghz_read_raw_stop_send(&raw);assert(calls==2&&!m->tx_active); // held => repeat
  key(&raw,InputKeyBack,InputTypeShort);assert(posted==SubGhzCustomEventViewReadRAWTXRXStop&&m->status==idle);
  assert(!subghz_read_raw_is_tx_requested(&raw)); // queued repeat must be rejected by scene
  unsigned stopped=calls;subghz_read_raw_stop_send(&raw);assert(calls==stopped&&!subghz_read_raw_is_tx_requested(&raw));
  m->status=idle;key(&raw,InputKeyOk,InputTypePress);key(&raw,InputKeyOk,InputTypeRelease);
  stopped=calls;subghz_read_raw_stop_send(&raw);assert(calls==stopped&&m->status==idle); // one pass
  key(&raw,InputKeyOk,InputTypePress);subghz_read_raw_cancel_send(&raw);assert(m->status==idle&&!m->tx_active);
  subghz_read_raw_start_send(&raw);assert(subghz_read_raw_is_tx_requested(&raw));
  stopped=calls;subghz_read_raw_stop_send(&raw);assert(calls==stopped&&m->status==idle); // favorite one pass
 }
 m->status=SubGhzReadRAWStatusStart;key(&raw,InputKeyOk,InputTypeShort);assert(m->status==SubGhzReadRAWStatusREC&&posted==SubGhzCustomEventViewReadRAWREC);
 key(&raw,InputKeyBack,InputTypeShort);assert(m->status==SubGhzReadRAWStatusIDLE&&posted==SubGhzCustomEventViewReadRAWIDLE);
 key(&raw,InputKeyLeft,InputTypeShort);assert(m->status==SubGhzReadRAWStatusStart&&posted==SubGhzCustomEventViewReadRAWErase);
 key(&raw,InputKeyLeft,InputTypeShort);assert(posted==SubGhzCustomEventViewReadRAWConfig);
 m->status=SubGhzReadRAWStatusLoadKeyIDLE;key(&raw,InputKeyRight,InputTypeShort);assert(posted==SubGhzCustomEventViewReadRAWMore);
 m->raw_send_only=true;unsigned before=calls;key(&raw,InputKeyLeft,InputTypeShort);key(&raw,InputKeyRight,InputTypeShort);assert(calls==before);
 furi_string_free(m->sample_write);furi_string_free(m->file_name);view_free(raw.view);
 puts("PASS: RAW unlocked callbacks, hold/release/repeat, Back cancels held and one-pass TX, failed-start state and stale-repeat intent");
}
"""
TX_ADAPTER = r"""
#define FURI_LOG_E(...) ((void)0)
enum {SubGhzProtocolStatusOk,SubGhzProtocolStatusError,SubGhzTxRxStateSleep,SubGhzTxRxStateIDLE,SubGhzTxRxStateTx,SubGhzProtocolTypeDynamic,SubGhzProtocolTypeStatic};
typedef struct {bool stopped;} Transmitter;
typedef struct {int type;} Protocol;
typedef struct {Protocol* protocol;} Decoder;
typedef struct {FuriString* name;uint32_t frequency;} SubGhzRadioPreset;
typedef struct {SubGhzRadioPreset* preset;Transmitter* transmitter;void* environment;void* radio_device;void* setting;int txrx_state;Decoder* decoder_result;void(*need_save_callback)(void*);void* need_save_context;} SubGhzTxRx;
typedef int FlipperFormat;
static bool rewind_ok=true,protocol_ok=true,encoder_ok=true,deserialize_ok=true,radio_ok=true,async_ok=true,preset_ok=true;
static unsigned allocations,frees,stops,async_starts,async_stops,saves;static bool speaker,complete;
static bool subghz_devices_is_async_complete_tx(void* radio) {(void)radio;return complete;}
static void subghz_txrx_tx_stop(SubGhzTxRx* t);
static void subghz_txrx_stop(SubGhzTxRx* t) {if(t->txrx_state==SubGhzTxRxStateTx)subghz_txrx_tx_stop(t);}
static bool flipper_format_rewind(FlipperFormat* f) {(void)f;return rewind_ok;}
static bool flipper_format_read_string(FlipperFormat* f,const char* key,FuriString* str) {(void)f;(void)key;furi_string_set_str(str,"RAW");return protocol_ok;}
static Transmitter* subghz_transmitter_alloc_init(void* env,const char* name) {(void)env;(void)name;if(!encoder_ok)return NULL;allocations++;return calloc(1,sizeof(Transmitter));}
static int subghz_transmitter_deserialize(Transmitter* t,FlipperFormat* f) {(void)t;(void)f;return deserialize_ok?SubGhzProtocolStatusOk:SubGhzProtocolStatusError;}
static void* subghz_setting_get_preset_data_by_name(void* settings,const char* name) {(void)settings;assert(*name);return preset_ok?(void*)1:NULL;}
static void subghz_txrx_begin(SubGhzTxRx* t,void* data) {assert(data);t->txrx_state=SubGhzTxRxStateIDLE;}
static bool subghz_txrx_tx(SubGhzTxRx* t,uint32_t freq) {assert(freq);if(radio_ok){t->txrx_state=SubGhzTxRxStateTx;speaker=true;}return radio_ok;}
static void subghz_transmitter_yield(void) {}
static bool subghz_devices_start_async_tx(void* radio,void(*yield)(void),Transmitter* t) {(void)radio;(void)yield;assert(t);async_starts++;return async_ok;}
static void subghz_transmitter_stop(Transmitter* t) {assert(t);t->stopped=true;stops++;}
static void subghz_transmitter_free(Transmitter* t) {assert(t&&t->stopped);frees++;free(t);}
static void subghz_txrx_idle(SubGhzTxRx* t) {t->txrx_state=SubGhzTxRxStateIDLE;speaker=false;}
static void subghz_devices_stop_async_tx(void* radio) {(void)radio;async_stops++;}
static void subghz_txrx_speaker_off(SubGhzTxRx* t) {(void)t;speaker=false;}
static void save(void* context) {(void)context;saves++;}
"""
TX_TEST = r"""
int main(void) {
 SubGhzRadioPreset preset={alloc_text("AM650"),433920000};SubGhzTxRx t={.preset=&preset,.txrx_state=SubGhzTxRxStateIDLE,.need_save_callback=save};FlipperFormat f=0;
 rewind_ok=false;assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorParserOthers&&!allocations);rewind_ok=true;
 protocol_ok=false;assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorParserOthers&&!allocations);protocol_ok=true;
 encoder_ok=false;assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorEncoderUnavailable&&!t.transmitter);encoder_ok=true;
 deserialize_ok=false;assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorParserOthers&&!t.transmitter);deserialize_ok=true;
 radio_ok=false;assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorOnlyRx&&!t.transmitter&&!speaker);radio_ok=true;
 async_ok=false;assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorRadio&&!t.transmitter&&!speaker&&t.txrx_state==SubGhzTxRxStateIDLE);async_ok=true;
 preset.frequency=0;assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorParserOthers&&!t.transmitter);preset.frequency=433920000;
 furi_string_set_str(preset.name,"");assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorParserOthers&&!t.transmitter);furi_string_set_str(preset.name,"AM650");
 preset_ok=false;assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateErrorParserOthers&&!t.transmitter);preset_ok=true;
 assert(allocations==frees&&stops==frees);
 assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateOk&&t.transmitter&&speaker);
 assert(!subghz_txrx_is_tx_complete(&t));complete=true;assert(subghz_txrx_is_tx_complete(&t));
 subghz_txrx_tx_stop(&t);assert(!subghz_txrx_is_tx_complete(&t));assert(!t.transmitter&&!speaker&&allocations==frees&&!saves); // decoder can be absent
 Protocol p={SubGhzProtocolTypeDynamic};Decoder d={&p};t.decoder_result=&d;
 assert(subghz_txrx_tx_start(&t,&f)==SubGhzTxRxStartTxStateOk);subghz_txrx_tx_stop(&t);assert(saves==1&&allocations==frees);
 furi_string_free(preset.name);puts("PASS: real TX start/stop parser/encoder/radio/async failures, balanced ownership, no stale transmitter, dynamic-save callback and absent decoder");
}
"""
raw = (APP / "views/subghz_read_raw.c").read_text()
header = re.sub(
    r"^\s*#(?:include|pragma).*$",
    "",
    (APP / "views/subghz_read_raw.h").read_text(),
    flags=re.M,
)
events = (APP / "helpers/subghz_custom_event.h").read_text()
events = events[
    events.index("typedef enum {") : events.index("} SubGhzCustomEvent;")
    + len("} SubGhzCustomEvent;")
]
raw_types = raw[
    raw.index("struct SubGhzReadRAW {") : raw.index("void subghz_read_raw_start_send")
]
raw_funcs = "".join(
    function(raw, n)
    for n in (
        "subghz_read_raw_start_send",
        "subghz_read_raw_set_tx_active",
        "subghz_read_raw_is_tx_requested",
        "subghz_read_raw_cancel_send",
        "subghz_read_raw_stop_send",
        "subghz_read_raw_input",
    )
)
tx = (APP / "helpers/subghz_txrx.c").read_text()
tx_header = (APP / "helpers/subghz_txrx.h").read_text()
tx_enum = tx_header[
    tx_header.index("typedef enum {") : tx_header.index("} SubGhzTxRxStartTxState;")
    + len("} SubGhzTxRxStartTxState;")
]
with tempfile.TemporaryDirectory() as folder:
    for name, code in {
        "raw": STUB + RAW_ADAPTER + events + header + raw_types + raw_funcs + RAW_TEST,
        "tx": STUB
        + tx_enum
        + TX_ADAPTER
        + function(tx, "subghz_txrx_tx_start")
        + function(tx, "subghz_txrx_tx_stop")
        + function(tx, "subghz_txrx_is_tx_complete")
        + TX_TEST,
    }.items():
        path = Path(folder) / (name + ".c")
        path.write_text(code)
        binary = Path(folder) / name
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
