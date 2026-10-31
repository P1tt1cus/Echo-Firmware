"""Exercise actual IR reorder rendering, wrap order, cancellation and unlocked save callbacks."""

import ast
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def literal(path, name):
    return next(
        ast.literal_eval(n.value)
        for n in ast.parse(path.read_text()).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
    )


STUB = literal(ROOT / "scripts/echo_shared_menu_test.py", "STUB")
ADAPTER = r"""
#include <toolbox/m_cstr_dup.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define strlcpy echo_strlcpy
static size_t echo_strlcpy(char* dst,const char* src,size_t n){size_t len=strlen(src);if(n){size_t c=MIN(len,n-1);memcpy(dst,src,c);dst[c]=0;}return len;}
static void elements_scrollbar_pos(Canvas* c,unsigned x,unsigned y,unsigned h,unsigned pos,unsigned count){assert(x==128&&y+h<=64&&count&&pos<count);(void)c;}
"""
TEST = r"""
static unsigned calls,old_index,new_index;
static void callback(uint32_t from,uint32_t to,void* ctx){InfraredMoveView* v=ctx;assert(!v->view->locked);calls++;old_index=from;new_index=to;}
static bool key(InfraredMoveView* v,InputKey k,InputType t){InputEvent e={k,t};return infrared_move_view_input_callback(&e,v);}
static void order(InfraredMoveView* v,const char* names){InfraredMoveViewModel* m=v->view->model;assert(InfraredMoveViewItemArray_size(m->labels)==strlen(names));for(size_t i=0;i<strlen(names);i++)assert((*InfraredMoveViewItemArray_cget(m->labels,i))[0]==names[i]);}
static void seed(InfraredMoveView* v){infrared_move_view_reset(v);infrared_move_view_add_item(v,"A");infrared_move_view_add_item(v,"B");infrared_move_view_add_item(v,"C");infrared_move_view_set_callback(v,callback,v);calls=0;}
int main(void){
 InfraredMoveView* v=infrared_move_view_alloc();Canvas c={.w=128,.h=64};
 for(unsigned count=0;count<100;count++){
  infrared_move_view_reset(v);for(unsigned i=0;i<count;i++)infrared_move_view_add_item(v,"Long synthetic button label that must fit within its row");
  for(unsigned i=0;i<count+1;i++){canvas_clear(&c);infrared_move_view_draw_callback(&c,v->view->model);assert(drawn(&c,"OK pick  Back exit"));key(v,InputKeyDown,InputTypeShort);}
 }
 infrared_move_view_reset(v);key(v,InputKeyUp,InputTypeShort);key(v,InputKeyOk,InputTypeShort);assert(!((InfraredMoveViewModel*)v->view->model)->is_moving);canvas_clear(&c);infrared_move_view_draw_callback(&c,v->view->model);assert(drawn(&c,"No buttons"));
 // Crossing either edge displays insertion order, not an endpoint swap.
 seed(v);key(v,InputKeyOk,InputTypeShort);key(v,InputKeyUp,InputTypeShort);order(v,"BCA");canvas_clear(&c);infrared_move_view_draw_callback(&c,v->view->model);assert(drawn(&c,"OK save  Back cancel"));
 assert(key(v,InputKeyBack,InputTypePress));assert(!calls);assert(key(v,InputKeyBack,InputTypeShort));order(v,"ABC");assert(!calls);assert(!key(v,InputKeyBack,InputTypeRelease));assert(!key(v,InputKeyBack,InputTypeShort));
 seed(v);key(v,InputKeyUp,InputTypeShort);key(v,InputKeyOk,InputTypeShort);key(v,InputKeyDown,InputTypeShort);order(v,"CAB");key(v,InputKeyOk,InputTypeShort);assert(calls==1&&old_index==2&&new_index==0);key(v,InputKeyOk,InputTypeRelease);assert(calls==1);
 // A no-op pick/save never starts a worker; cancel restores all permutations.
 seed(v);key(v,InputKeyOk,InputTypeShort);key(v,InputKeyOk,InputTypeShort);assert(!calls);
 for(unsigned from=0;from<3;from++)for(unsigned steps=1;steps<7;steps++){
  seed(v);for(unsigned i=0;i<from;i++)key(v,InputKeyDown,InputTypeShort);key(v,InputKeyOk,InputTypeShort);for(unsigned i=0;i<steps;i++)key(v,InputKeyDown,InputTypeRepeat);key(v,InputKeyBack,InputTypeShort);order(v,"ABC");assert(!calls&&((InfraredMoveViewModel*)v->view->model)->current_idx==(int)from);
 }
 for(unsigned i=0;i<100;i++){seed(v);key(v,InputKeyOk,InputTypeShort);key(v,InputKeyDown,InputTypeShort);key(v,InputKeyOk,InputTypeShort);assert(calls==1&&old_index==0&&new_index==1);order(v,"BAC");}
 infrared_move_view_reset(v);assert(!v->callback&&!v->callback_context);infrared_move_view_free(v);
 puts("PASS: IR reorder bounded rendering/empty/long lists, wrap insertion order, Back cancellation/restoration, no-op suppression, callbacks outside lock and 100 cycles");
}
"""
clean = lambda s: re.sub(r"^#(?:include|pragma).*$", "", s, flags=re.M)
with tempfile.TemporaryDirectory(prefix="echo-ir-move-") as tmp:
    p = Path(tmp)
    p.joinpath("test.c").write_text(
        STUB
        + ADAPTER
        + clean(
            (ROOT / "applications/main/infrared/views/infrared_move_view.h").read_text()
        )
        + clean(
            (ROOT / "applications/main/infrared/views/infrared_move_view.c").read_text()
        )
        + TEST
    )
    subprocess.run(
        [
            "cc",
            "-std=gnu11",
            "-g",
            "-fsanitize=address,undefined",
            "-I" + str(ROOT / "lib/mlib"),
            "-I" + str(ROOT / "lib"),
            str(p / "test.c"),
            "-o",
            str(p / "test"),
        ],
        check=True,
    )
    subprocess.run([str(p / "test")], check=True)
