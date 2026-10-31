"""Exercise the actual shared menu controls with the real m-array container and host GUI stubs."""

from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "applications/services/gui/modules"

STUB = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <m-array.h>
#define UNUSED(x) (void)(x)
#define furi_check assert
#define furi_assert assert
#define COUNT_OF(a) (sizeof(a)/sizeof(*(a)))
typedef struct {char* text;} FuriString;
static FuriString* furi_string_alloc(void) {FuriString* s=calloc(1,sizeof(*s));s->text=calloc(1,1);return s;}
static const char* furi_string_get_cstr(const FuriString* s) {return s->text;}
static size_t furi_string_size(const FuriString* s) {return strlen(s->text);}
static bool furi_string_empty(const FuriString* s) {return !*s->text;}
static void furi_string_set_str(FuriString* s,const char* text) {free(s->text);s->text=malloc(strlen(text)+1);strcpy(s->text,text);}
static void set_string(FuriString* s,const FuriString* src) {furi_string_set_str(s,src->text);}
#define furi_string_set(s,t) _Generic((t), FuriString*:set_string, const FuriString*:set_string, default:furi_string_set_str)(s,t)
static void furi_string_reset(FuriString* s) {furi_string_set_str(s,"");}
static FuriString* alloc_text(const char* text) {FuriString* s=furi_string_alloc();furi_string_set_str(s,text);return s;}
static FuriString* alloc_string(const FuriString* s) {return alloc_text(s->text);}
#define furi_string_alloc_set(s) _Generic((s), FuriString*:alloc_string, const FuriString*:alloc_string, default:alloc_text)(s)
static void furi_string_free(FuriString* s) {free(s->text);free(s);}
typedef enum {InputKeyUp,InputKeyDown,InputKeyLeft,InputKeyRight,InputKeyOk,InputKeyBack} InputKey;
typedef enum {InputTypePress,InputTypeRelease,InputTypeShort,InputTypeLong,InputTypeRepeat} InputType;
typedef struct {InputKey key;InputType type;} InputEvent;
typedef enum {ViewOrientationHorizontal,ViewOrientationHorizontalFlip,ViewOrientationVertical,ViewOrientationVerticalFlip} ViewOrientation;
enum {ColorBlack,ColorWhite,FontPrimary,FontSecondary,FontKeyboard,AlignRight,AlignBottom,AlignCenter,ViewModelTypeLocking,FuriTimerTypeOnce,FuriTimerTypePeriodic};
typedef struct {int w,h,font;char texts[64][256];unsigned count;} Canvas;
typedef struct {int w,h;} Icon;
static const Icon I_Lock_7x8={7,8},I_WarningDolphin_45x42={45,42};
static struct {bool popup_overlay;} momentum_settings;
static int canvas_width(Canvas* c) {return c->w;}
static int canvas_height(Canvas* c) {return c->h;}
static void point(Canvas* c,int x,int y) {if(!(x>=0&&x<c->w&&y>=0&&y<c->h))fprintf(stderr,"point %d,%d canvas %dx%d\n",x,y,c->w,c->h);assert(x>=0&&x<c->w&&y>=0&&y<c->h);}
static void canvas_clear(Canvas* c) {c->count=0;}
static void canvas_set_font(Canvas* c,int f) {c->font=f;}
static void canvas_set_color(Canvas* c,int color) {(void)c;(void)color;}
static size_t canvas_string_width(Canvas* c,const char* s) {(void)c;return strlen(s)*6;}
static void canvas_draw_str(Canvas* c,int x,int y,const char* s) {point(c,x,y);assert(x+(int)canvas_string_width(c,s)<=c->w);assert(c->count<64&&strlen(s)<256);strcpy(c->texts[c->count++],s);}
static void canvas_draw_str_aligned(Canvas* c,int x,int y,int a,int b,const char* s) {(void)a;(void)b;canvas_draw_str(c,x-canvas_string_width(c,s),y,s);}
static void canvas_draw_line(Canvas* c,int x,int y,int a,int b) {point(c,x,y);point(c,a,b);}
static void canvas_draw_box(Canvas* c,int x,int y,int w,int h) {point(c,x,y);point(c,x+w-1,y+h-1);}
#define canvas_draw_frame canvas_draw_box
static void canvas_draw_rbox(Canvas* c,int x,int y,int w,int h,int r) {(void)r;canvas_draw_box(c,x,y,w,h);}
#define canvas_draw_rframe canvas_draw_rbox
static void canvas_draw_icon(Canvas* c,int x,int y,const Icon* icon) {canvas_draw_box(c,x,y,icon->w,icon->h);}
static void canvas_draw_overlay(Canvas* c) {(void)c;}
static void elements_string_fit_width(Canvas* c,FuriString* s,size_t width) {(void)c;if(strlen(s->text)*6>width)s->text[width/6]=0;}
static void elements_multiline_text_aligned(Canvas* c,int x,int y,int a,int b,const char* s) {(void)a;(void)b;(void)s;point(c,x,y);}
static void elements_scrollable_text_line(Canvas* c,int x,int y,int width,FuriString* s,size_t scroll,bool ellipsis) {(void)scroll;(void)ellipsis;FuriString* t=alloc_string(s);elements_string_fit_width(c,t,width);canvas_draw_str(c,x,y,t->text);furi_string_free(t);}
static void elements_scrollable_text_line_centered(Canvas* c,int x,int y,int width,FuriString* s,size_t scroll,bool a,bool b) {(void)scroll;(void)a;(void)b;FuriString* t=alloc_string(s);elements_string_fit_width(c,t,width);canvas_draw_str(c,x-canvas_string_width(c,t->text)/2,y,t->text);furi_string_free(t);}
typedef struct {void* model;bool locked;ViewOrientation orientation;} View;
static View* view_alloc(void) {return calloc(1,sizeof(View));}
static void view_free(View* v) {assert(!v->locked);free(v->model);free(v);}
static void view_allocate_model(View* v,int type,size_t size) {(void)type;v->model=calloc(1,size);}
static void view_set_context(View* v,void* c) {(void)v;(void)c;}
static void view_set_draw_callback(View* v,void(*cb)(Canvas*,void*)) {(void)v;(void)cb;}
static void view_set_input_callback(View* v,bool(*cb)(InputEvent*,void*)) {(void)v;(void)cb;}
static void view_set_orientation(View* v,ViewOrientation o) {v->orientation=o;}
static void* view_get_model(View* v) {assert(!v->locked);v->locked=true;return v->model;}
static void view_commit_model(View* v,bool update) {(void)update;assert(v->locked);v->locked=false;}
#define with_view_model(v,decl,code,update) do {decl=view_get_model(v);code;view_commit_model(v,update);}while(0)
typedef struct {bool started;} FuriTimer;
static FuriTimer* furi_timer_alloc(void(*cb)(void*),int type,void* ctx) {(void)cb;(void)type;(void)ctx;return calloc(1,sizeof(FuriTimer));}
static void furi_timer_start(FuriTimer* t,unsigned time) {(void)time;t->started=true;}
static void furi_timer_stop(FuriTimer* t) {t->started=false;}
static void furi_timer_free(FuriTimer* t) {free(t);}
static unsigned furi_kernel_get_tick_frequency(void) {return 1000;}
static int furi_thread_get_current_id(void) {return 1;}
static const char* furi_thread_get_name(int id) {(void)id;return "Example application with a long name";}
static bool drawn(Canvas* c,const char* s) {for(unsigned i=0;i<c->count;i++)if(!strcmp(c->texts[i],s))return true;return false;}
"""

SUBMENU_TEST = r"""
static unsigned calls;static uint32_t selected;static InputType event_type;
static void select_cb(void* ctx,uint32_t id) {Submenu* s=ctx;assert(!s->view->locked);calls++;selected=id;}
static void extended_cb(void* ctx,InputType type,uint32_t id) {event_type=type;select_cb(ctx,id);}
static void key(Submenu* s,InputKey k,InputType t) {InputEvent e={k,t};submenu_view_input_callback(&e,s);}
int main(void) {
 Submenu* s=submenu_alloc();Canvas c={.w=128,.h=64};SubmenuModel* m=s->view->model;
 for(int i=0;i<6;i++)key(s,(InputKey)i,InputTypeShort);
 assert(m->position==0);submenu_view_draw_callback(&c,m);assert(drawn(&c,"No items"));
 for(int i=0;i<30;i++)submenu_add_item(s,"A very long menu label to fit",100+i,select_cb,s);
 submenu_set_header(s,"A very long header that must fit");
 for(unsigned i=0;i<60;i++) {submenu_view_draw_callback(&c,m);key(s,InputKeyDown,InputTypeRepeat);assert(m->position<30);}
 key(s,InputKeyUp,InputTypeShort);assert(m->position==29);key(s,InputKeyOk,InputTypeLong);assert(!calls);
 key(s,InputKeyOk,InputTypeShort);assert(calls==1&&selected==129);
 submenu_remove_item(s,129);assert(m->position==28);submenu_view_draw_callback(&c,m);
 submenu_add_item_ex(s,"Custom controls",300,extended_cb,s);submenu_set_selected_item(s,300);
 key(s,InputKeyOk,InputTypeLong);assert(calls==2&&selected==300&&event_type==InputTypeLong);
 submenu_add_lockable_item(s,"Locked",400,select_cb,s,true,"Unavailable");submenu_set_selected_item(s,400);
 key(s,InputKeyOk,InputTypeShort);assert(calls==2&&m->locked_message_visible);submenu_view_draw_callback(&c,m);
 key(s,InputKeyBack,InputTypeShort);assert(!m->locked_message_visible);
 submenu_set_orientation(s,ViewOrientationVertical);c.w=64;c.h=128;
 for(int i=0;i<45;i++){submenu_view_draw_callback(&c,m);key(s,InputKeyDown,InputTypeShort);}
 submenu_reset(s);c.w=128;c.h=64;submenu_view_draw_callback(&c,m);assert(!m->locked_message_visible);
 submenu_add_item(s,"Saved",999,select_cb,s);key(s,InputKeyUp,InputTypeShort);key(s,InputKeyDown,InputTypeShort);assert(m->position==0);
 submenu_view_draw_callback(&c,m);assert(drawn(&c,"Open saved items"));
 InputEvent back={InputKeyBack,InputTypeShort};assert(!submenu_view_input_callback(&back,s));submenu_free(s);
 puts("PASS: submenu bounds/portrait, wrap, empty/reset/remove, IDs, extended events, locks and callback locking");
}
"""

VARIABLE_TEST = r"""
static unsigned calls,changes;static uint32_t selected;
static void select_cb(void* ctx,uint32_t id) {(void)ctx;calls++;selected=id;}
static void change_cb(VariableItem* item) {changes++;variable_item_set_current_value_text(item,"On");}
static void key(VariableItemList* v,InputKey k,InputType t) {InputEvent e={k,t};variable_item_list_input_callback(&e,v);}
int main(void) {
 VariableItemList* v=variable_item_list_alloc();VariableItemListModel* m=v->view->model;Canvas c={.w=128,.h=64};
 variable_item_list_set_enter_callback(v,select_cb,v);
 for(int i=0;i<6;i++)key(v,(InputKey)i,InputTypeShort);
 assert(m->position==0&&!calls);variable_item_list_draw_callback(&c,m);assert(drawn(&c,"No items"));
 VariableItem* item=variable_item_list_add(v,"Read",0,NULL,NULL);
 key(v,InputKeyRight,InputTypeShort);assert(variable_item_get_current_value_index(item)==0);
 key(v,InputKeyOk,InputTypeLong);assert(!calls);key(v,InputKeyOk,InputTypeShort);assert(calls==1&&selected==0);
 item=variable_item_list_add(v,"Long setting label",3,change_cb,NULL);variable_item_set_current_value_text(item,"Off");
 key(v,InputKeyDown,InputTypeShort);key(v,InputKeyRight,InputTypeShort);assert(changes==1&&item->current_value_index==1);
 key(v,InputKeyRight,InputTypeRepeat);key(v,InputKeyRight,InputTypeRepeat);assert(changes==2&&item->current_value_index==2);
 key(v,InputKeyLeft,InputTypeShort);assert(changes==3&&item->current_value_index==1);
 variable_item_list_draw_callback(&c,m);assert(drawn(&c,"Left/Right: change"));
 variable_item_set_locked(item,true,"Unavailable");key(v,InputKeyRight,InputTypeShort);assert(changes==3&&m->locked_message_visible);variable_item_list_draw_callback(&c,m);
 key(v,InputKeyBack,InputTypeShort);assert(!m->locked_message_visible);key(v,InputKeyOk,InputTypeShort);assert(calls==1);
 key(v,InputKeyBack,InputTypeShort);
 for(int i=0;i<25;i++)variable_item_list_add(v,"Long action label that should scroll",0,NULL,NULL);
 variable_item_list_set_header(v,"Settings with a long title");
 for(int i=0;i<55;i++){variable_item_list_draw_callback(&c,m);key(v,InputKeyDown,InputTypeRepeat);}
 variable_item_list_reset(v);assert(m->position==0&&m->window_position==0&&!m->locked_message_visible);
 variable_item_list_draw_callback(&c,m);key(v,InputKeyOk,InputTypeShort);assert(calls==1);
 InputEvent back={InputKeyBack,InputTypeShort};assert(!variable_item_list_input_callback(&back,v));variable_item_list_free(v);
 puts("PASS: variable-list bounds, scroll, values/limits, zero-value actions, callbacks, locks, empty/reset and Back");
}
"""


def source(name):
    return re.sub(
        r"^#(?:include|pragma).*\n", "", (MODULES / name).read_text(), flags=re.M
    )


for module, test in [("submenu", SUBMENU_TEST), ("variable_item_list", VARIABLE_TEST)]:
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        path = folder / "test.c"
        path.write_text(
            STUB
            + source(module + ".h")
            + source("echo_menu.h")
            + source(module + ".c")
            + test
        )
        binary = folder / "test"
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-unused-function",
                "-Wno-unused-variable",
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

# The compact Tools renderer uses the same chrome, with existing app IDs intact.
menu = (MODULES / "menu.c").read_text()
start = menu.index("static void menu_draw_echo(")
end = menu.index("static void menu_draw_callback(", start)
menu_model = r"""
typedef struct {const char* label;} MenuItem;
ARRAY_DEF(MenuItemArray, MenuItem, M_POD_OPLIST);
typedef struct {MenuItemArray_t items;FuriString* title;size_t position;} MenuModel;
"""
menu_test = r"""
int main(void) {
 MenuModel m={0};MenuItemArray_init(m.items);m.title=alloc_text("Tools");Canvas c={.w=128,.h=64};
 menu_draw_echo(&c,&m);
 for(int i=0;i<25;i++){MenuItem* item=MenuItemArray_push_new(m.items);item->label="An app with a very long name";}
 for(int i=0;i<25;i++){m.position=i;canvas_clear(&c);menu_draw_echo(&c,&m);assert(drawn(&c,"Tools"));}
 MenuItemArray_clear(m.items);furi_string_free(m.title);puts("PASS: Tools menu bounds and scrolling");
}
"""
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    path = folder / "tools.c"
    path.write_text(
        STUB + source("echo_menu.h") + menu_model + menu[start:end] + menu_test
    )
    binary = folder / "test"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-function",
            "-Wno-unused-variable",
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
