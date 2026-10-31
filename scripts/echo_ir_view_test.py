"""Production IR remote input/render tests without an IR transmitter."""

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
    "assert(x+(int)canvas_string_width(c,s)<=c->w);",
    'if(x+(int)canvas_string_width(c,s)>c->w)fprintf(stderr,"overflow: %s at %d\\n",s,x);assert(x+(int)canvas_string_width(c,s)<=c->w);',
)
ADAPTER = r"""
#include <stdarg.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define strlcpy echo_strlcpy
static size_t echo_strlcpy(char* dst,const char* src,size_t n) {size_t len=strlen(src);if(n){size_t c=MIN(len,n-1);memcpy(dst,src,c);dst[c]=0;}return len;}
static void furi_string_printf(FuriString* s,const char* fmt,...) {char b[256];va_list v;va_start(v,fmt);vsnprintf(b,sizeof(b),fmt,v);va_end(v);furi_string_set_str(s,b);}
static FuriString* furi_string_alloc_printf(const char* fmt,...) {char b[256];va_list v;va_start(v,fmt);vsnprintf(b,sizeof(b),fmt,v);va_end(v);return alloc_text(b);}
typedef struct {const char* name;size_t count;} InfraredRemote;
static size_t infrared_remote_get_signal_count(const InfraredRemote* r) {return r->count;}
static const char* infrared_remote_get_name(const InfraredRemote* r) {return r->name;}
static const char* infrared_remote_get_signal_name(const InfraredRemote* r,size_t i) {assert(i<r->count);return i%2?"Volume up long button name":"Power";}
"""
TEST = r"""
static unsigned calls;static InfraredRemoteViewEvent posted;static int32_t selected_index;
static void callback(void* ctx,InfraredRemoteViewEvent e,int32_t selected) {
 InfraredRemoteView* v=ctx;assert(!v->view->locked);calls++;posted=e;selected_index=selected;
 assert(infrared_remote_view_selected(v)==selected);
}
static bool key(InfraredRemoteView* v,InputKey k,InputType t) {InputEvent e={k,t};return infrared_remote_view_input(&e,v);}
int main(void) {
 InfraredRemote r={"Echo long synthetic remote filename",9};InfraredRemoteView* v=infrared_remote_view_alloc();Canvas c={.w=128,.h=64};
 for(size_t count=0;count<100;count++) {
  r.count=count;infrared_remote_view_configure(v,&r,999,callback,v);
  for(size_t i=0;i<count+2;i++) {canvas_clear(&c);infrared_remote_view_draw(&c,v->view->model);key(v,InputKeyDown,InputTypeShort);}
  assert(infrared_remote_view_selected(v)==(count?0:-2));
 }
 r.count=9;infrared_remote_view_configure(v,&r,1,callback,v);assert(infrared_remote_view_selected(v)==1);
 infrared_remote_view_status(v,1,"Parsed NEC",false);canvas_clear(&c);infrared_remote_view_draw(&c,v->view->model);assert(drawn(&c,"Parsed NEC")&&drawn(&c,"Hold OK: send"));
 calls=0;key(v,InputKeyOk,InputTypePress);assert(calls==1&&posted==InfraredRemoteViewPress&&selected_index==1&&infrared_remote_view_can_send(v,1));
 key(v,InputKeyOk,InputTypePress);key(v,InputKeyOk,InputTypeRepeat);assert(calls==1);
 key(v,InputKeyDown,InputTypeShort);assert(infrared_remote_view_selected(v)==1); // held selection is stable
 infrared_remote_view_status(v,1,"TX NEC",true);canvas_clear(&c);infrared_remote_view_draw(&c,v->view->model);assert(drawn(&c,"Release / Back stops"));
 assert(!key(v,InputKeyBack,InputTypeShort));assert(!infrared_remote_view_can_send(v,1));
 infrared_remote_view_cancel(v);key(v,InputKeyOk,InputTypeRelease);assert(calls==1); // stale release after Back
 key(v,InputKeyOk,InputTypePress);key(v,InputKeyOk,InputTypeRelease);assert(posted==InfraredRemoteViewRelease&&infrared_remote_view_can_send(v,1)); // short tap may finish one frame
 infrared_remote_view_cancel(v);key(v,InputKeyRight,InputTypeShort);assert(infrared_remote_view_selected(v)==4&&posted==InfraredRemoteViewSelect);
 infrared_remote_view_status(v,1,"STALE",true);assert(!((InfraredRemoteViewModel*)v->view->model)->transmitting); // old metadata cannot overwrite new selection
 key(v,InputKeyLeft,InputTypeShort);assert(infrared_remote_view_selected(v)==1);
 infrared_remote_view_configure(v,&r,-2,callback,v);calls=0;key(v,InputKeyOk,InputTypePress);key(v,InputKeyOk,InputTypeShort);key(v,InputKeyOk,InputTypeRelease);assert(calls==1&&posted==InfraredRemoteViewControl&&selected_index==-2);
 key(v,InputKeyDown,InputTypeShort);assert(infrared_remote_view_selected(v)==-1);key(v,InputKeyDown,InputTypeShort);assert(infrared_remote_view_selected(v)==0);
 infrared_remote_view_configure(v,&r,-1,callback,v);assert(infrared_remote_view_selected(v)==-1);
 infrared_remote_view_free(v);puts("PASS: IR remote layout, empty/long lists, wrap/page navigation, selection restoration, parsed/TX status, press/release/Back intent, unlocked callbacks and stale metadata");
}
"""
header = (ROOT / "applications/main/infrared/views/infrared_remote_view.h").read_text()
source = (ROOT / "applications/main/infrared/views/infrared_remote_view.c").read_text()
clean = lambda s: re.sub(r"^#(?:include|pragma).*$", "", s, flags=re.M)
with tempfile.TemporaryDirectory(prefix="echo-ir-view-") as d:
    p = Path(d) / "test.c"
    exe = Path(d) / "test"
    p.write_text(STUB + ADAPTER + clean(header) + clean(source) + TEST)
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
