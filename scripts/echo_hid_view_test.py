"""Validate production HID status rendering with host canvas adapters."""

import ast
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / "scripts/echo_shared_menu_test.py").read_text())
STUB = next(
    ast.literal_eval(n.value)
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets)
)
STUB = STUB.replace(
    "AlignCenter,ViewModelTypeLocking",
    "AlignCenter,AlignLeft,FontBigNumbers,ViewModelTypeLocking",
)
STUB = STUB.replace(
    "canvas_draw_str(c,x-canvas_string_width(c,s),y,s);",
    "canvas_draw_str(c,a==AlignLeft?x:x-canvas_string_width(c,s),y,s);",
)
source = (ROOT / "applications/main/bad_usb/views/bad_usb_view.c").read_text()
header = (ROOT / "applications/main/bad_usb/helpers/ducky_script.h").read_text()
types = header[
    header.index("typedef enum {") : header.index("typedef struct BadUsbScript")
]
model = source[
    source.index("struct BadUsb {") : source.index("static void bad_usb_draw_callback")
]
func = source[
    source.index("static void bad_usb_draw_callback") : source.index(
        "static bool bad_usb_input_callback"
    )
]
icons = "\n".join(
    f"static const Icon {name}={{{w},{h}}};"
    for name, w, h in sorted(set(re.findall(r"\b(I_\w+_(\d+)x(\d+))\b", func)))
)
ADAPTER = r"""
#include <stdarg.h>
#define MAX_NAME_LEN 64
typedef void(*BadUsbButtonCallback)(InputKey,void*);
typedef enum {BadUsbHidInterfaceUsb,BadUsbHidInterfaceBle} BadUsbHidInterface;
typedef enum {BtStatusOff,BtStatusAdvertising,BtStatusConnected} BtStatus;
typedef struct {BtStatus status;} Bt;
static void furi_string_printf(FuriString* s,const char* fmt,...) {char b[256];va_list v;va_start(v,fmt);vsnprintf(b,sizeof(b),fmt,v);va_end(v);furi_string_set_str(s,b);}
static void furi_string_cat_printf(FuriString* s,const char* fmt,...) {char b[256];va_list v;va_start(v,fmt);vsnprintf(b,sizeof(b),fmt,v);va_end(v);size_t n=strlen(s->text)+strlen(b)+1;s->text=realloc(s->text,n);strcat(s->text,b);}
static int canvas_current_font_height(Canvas* c) {(void)c;return 8;}
static void elements_button_center(Canvas* c,const char* text) {canvas_draw_str_aligned(c,64+strlen(text)*3,62,AlignRight,AlignBottom,text);}
static void elements_button_left(Canvas* c,const char* text) {canvas_draw_str(c,4,62,text);}
static void elements_button_right(Canvas* c,const char* text) {canvas_draw_str_aligned(c,127,62,AlignRight,AlignBottom,text);}
"""
TEST = r"""
int main(void) {
 Bt bt={BtStatusAdvertising};BadUsbModel m={.bt=&bt,.interface=BadUsbHidInterfaceBle};strcpy(m.file_name,"Harmless UI fixture");strcpy(m.layout,"en-US");m.state.line_nb=2;m.state.line_cur=1;m.state.delay_remain=100;m.state.elapsed=125000;
 Canvas c={.w=128,.h=64};
 for(unsigned pass=0;pass<100;pass++) {
  for(unsigned iface=0;iface<2;iface++) {
   m.interface=iface;
   for(unsigned state=0;state<=BadUsbStateFileError;state++) {
    m.state.state=state;canvas_clear(&c);bad_usb_draw_callback(&c,&m);
   }
  }
 }
 m.interface=BadUsbHidInterfaceBle;m.state.state=BadUsbStateNotConnected;canvas_clear(&c);bad_usb_draw_callback(&c,&m);
 assert(drawn(&c,"Pair host")&&drawn(&c,"Arm")&&drawn(&c,"(en-US) BLE 02:05"));
 bt.status=BtStatusOff;canvas_clear(&c);bad_usb_draw_callback(&c,&m);assert(drawn(&c,"BLE idle"));
 m.state.interrupted=true;canvas_clear(&c);bad_usb_draw_callback(&c,&m);assert(drawn(&c,"Link lost")&&drawn(&c,"Stopped"));
 m.state.state=BadUsbStateIdle;canvas_clear(&c);bad_usb_draw_callback(&c,&m);assert(drawn(&c,"Linked")&&drawn(&c,"Run again")&&drawn(&c,"Run"));
 m.state.interrupted=false;canvas_clear(&c);bad_usb_draw_callback(&c,&m);assert(drawn(&c,"Press Run"));
 m.interface=BadUsbHidInterfaceUsb;m.state.state=BadUsbStateNotConnected;canvas_clear(&c);bad_usb_draw_callback(&c,&m);assert(drawn(&c,"Connect")&&drawn(&c,"USB cable"));
 m.state.state=BadUsbStateWillRun;canvas_clear(&c);bad_usb_draw_callback(&c,&m);assert(drawn(&c,"Armed")&&drawn(&c,"Cancel"));
 puts("PASS: HID USB/BLE states, explicit arming, lost-link/reconnect feedback, elapsed clock and repeated production rendering");
}
"""
with tempfile.TemporaryDirectory(prefix="echo-hid-view-") as d:
    path = Path(d) / "view.c"
    exe = Path(d) / "view"
    path.write_text(STUB + types + ADAPTER + icons + model + func + TEST)
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
