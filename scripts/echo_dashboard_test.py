"""Exercise the production dashboard against a locking, bounds-checking GUI adapter."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEADER = r"""
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef enum {InputKeyUp, InputKeyDown, InputKeyLeft, InputKeyRight, InputKeyOk, InputKeyBack} InputKey;
typedef enum {InputTypePress, InputTypeRelease, InputTypeShort, InputTypeLong, InputTypeRepeat} InputType;
typedef struct {InputKey key; InputType type;} InputEvent;
typedef struct {int font; char rows[16][128]; unsigned count;} Canvas;
typedef struct {void* model; bool locked;} View;
enum {FontPrimary, FontSecondary, FontKeyboard, ColorWhite, ColorBlack, AlignRight, AlignBottom, ViewModelTypeLocking};

#define furi_check assert
static View* view_alloc(void) {return calloc(1,sizeof(View));}
static void view_free(View* v) {assert(!v->locked); free(v->model); free(v);}
static void view_allocate_model(View* v, int type, size_t n) {(void)type; v->model=calloc(1,n);}
static void view_set_context(View* v, void* c) {(void)v;(void)c;}
static void view_set_draw_callback(View* v, void (*cb)(Canvas*, void*)) {(void)v;(void)cb;}
static void view_set_input_callback(View* v, bool (*cb)(InputEvent*, void*)) {(void)v;(void)cb;}
static void* view_get_model(View* v) {assert(!v->locked);v->locked=true;return v->model;}
static void view_commit_model(View* v, bool update) {(void)update;assert(v->locked);v->locked=false;}
#define with_view_model(v, declaration, code, update) do { declaration = view_get_model(v); code; view_commit_model(v,update); } while(0)
static void canvas_clear(Canvas* c) {c->count=0;}
static void canvas_set_font(Canvas* c,int f) {c->font=f;}
static void canvas_set_color(Canvas* c,int f) {(void)c;(void)f;}
static void point(int x,int y) {assert(x>=0&&x<128&&y>=0&&y<64);}
static void canvas_draw_box(Canvas* c,int x,int y,int w,int h) {(void)c;point(x,y);point(x+w-1,y+h-1);}
#define canvas_draw_frame canvas_draw_box
static void canvas_draw_rbox(Canvas* c,int x,int y,int w,int h,int r) {(void)r;canvas_draw_box(c,x,y,w,h);}
static void canvas_draw_line(Canvas* c,int x,int y,int a,int b) {(void)c;point(x,y);point(a,b);}
static void canvas_draw_str(Canvas* c,int x,int y,const char* s) {
    point(x,y); assert(c->count<16); assert(strlen(s)<128);
    if(c->font==FontKeyboard) assert(x+strlen(s)*6<=128);
    strcpy(c->rows[c->count++],s);
}
static void canvas_draw_str_aligned(Canvas* c,int x,int y,int a,int b,const char* s) {
    (void)a;(void)b;canvas_draw_str(c,x,y,s);
}
"""
TEST = r"""
#include "echo_dashboard.h"
static unsigned calls;
static uint32_t choice;
static void select_cb(void* context,uint32_t id) {
 EchoDashboard* d=context; assert(!d->view->locked); calls++;choice=id;
 echo_dashboard_status(d,"Callback");
}
static void key(EchoDashboard* d,InputKey k,InputType type) {
 InputEvent e={k,type};assert(echo_dashboard_input(&e,d));
}
int main(void) {
 EchoDashboard* d=echo_dashboard_alloc();Canvas c={0};
 EchoDashboardItem items[7];
 for(unsigned i=0;i<7;i++) items[i]=(EchoDashboardItem){"Action","A short explanation",100+i,(EchoDashIcon)(i%6),i==6};
 echo_dashboard_configure(d,"Sub-GHz","123456789012",EchoDashRadio,items,7,103,select_cb,d);
 EchoDashboardModel* m=d->view->model;
 assert(m->selected==3&&strlen(m->status)==8);
 for(int i=0;i<28;i++) {echo_dashboard_draw(&c,m);key(d,InputKeyDown,InputTypeRepeat);}
 assert(m->selected==3);
 key(d,InputKeyLeft,InputTypeShort);assert(m->selected==0);
 key(d,InputKeyUp,InputTypeShort);assert(m->selected==6);
 key(d,InputKeyOk,InputTypeShort);assert(calls==0);
 key(d,InputKeyDown,InputTypeShort);assert(m->selected==0);
 key(d,InputKeyOk,InputTypeLong);key(d,InputKeyOk,InputTypeRepeat);assert(calls==0);
 key(d,InputKeyOk,InputTypeShort);assert(calls==1&&choice==100);
 key(d,InputKeyRight,InputTypeShort);assert(m->selected==6);
 InputEvent back={InputKeyBack,InputTypeShort};assert(!echo_dashboard_input(&back,d));
 echo_dashboard_configure(d,"NFC","SD ready",EchoDashRead,items,1,999,select_cb,d);
 key(d,InputKeyUp,InputTypeShort);assert(m->selected==0);echo_dashboard_draw(&c,m);
 echo_dashboard_free(d);
 puts("PASS: dashboard bounds, scrolling, wrap, IDs, locked actions, short OK, Back, callback locking");
}
"""

with tempfile.TemporaryDirectory() as temporary:
    temp = Path(temporary)
    (temp / "gui").mkdir()
    (temp / "gui/view.h").write_text(HEADER)
    (temp / "furi.h").write_text('#include "gui/view.h"\n')
    source = temp / "test.c"
    source.write_text(TEST)
    binary = temp / "test"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsanitize=address,undefined",
            "-I",
            str(temp),
            "-I",
            str(ROOT / "applications/main/echo"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
