"""Exercise the production Echo launcher draw/input callbacks with sanitizers."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STUB = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define COUNT_OF(a) (sizeof(a)/sizeof(*(a)))
typedef struct {unsigned labels;} Canvas;
typedef int Icon;
static const Icon I_EchoRadio_10=0,I_EchoRemotes_10=0,I_EchoSessions_10=0,I_EchoTools_10=0,I_EchoSettings_10=0;
enum {ColorBlack,ColorWhite,FontPrimary,FontSecondary};
enum {InputKeyBack,InputKeyUp,InputKeyDown,InputKeyOk,InputKeyLeft};
enum {InputTypeShort,InputTypeRepeat,InputTypeLong,InputTypePress,InputTypeRelease};
typedef struct {int key,type;} InputEvent;
typedef struct {void* echo_menu;unsigned calls,selected;} LoaderMenuApp;
static bool locked;
#define with_view_model(view,type,body,commit) do {assert(!locked);locked=true;type=(view);body;locked=false;(void)(commit);} while(0)
static void loader_menu_echo_callback(LoaderMenuApp* app,unsigned i) {assert(!locked);app->calls++;app->selected=i;}
static void canvas_clear(Canvas* c) {c->labels=0;}
static void canvas_set_color(Canvas* c,int v) {(void)c;(void)v;}
static void canvas_set_font(Canvas* c,int v) {(void)c;(void)v;}
static void canvas_draw_str(Canvas* c,unsigned x,unsigned y,const char* s) {assert(x+strlen(s)*6<=128 && y<64);if(strcmp(s,"ECHO"))c->labels++;}
static void canvas_draw_icon(Canvas* c,unsigned x,unsigned y,const Icon* i) {(void)c;(void)i;assert(x+10<=128 && y+10<=64);}
static void canvas_draw_line(Canvas* c,unsigned x,unsigned y,unsigned x2,unsigned y2) {(void)c;assert(x<128 && x2<128 && y<64 && y2<64);}
static void canvas_draw_rbox(Canvas* c,unsigned x,unsigned y,unsigned w,unsigned h,unsigned r) {(void)c;(void)r;assert(x+w<=128 && y+h<=64);}
"""
TEST = r"""
int main(void) {
 EchoMenuModel model={0};LoaderMenuApp app={.echo_menu=&model};Canvas canvas={0};
 InputEvent event={InputKeyUp,InputTypeShort};
 assert(loader_menu_echo_input(&event,&app) && model.selected==4);
 event=(InputEvent){InputKeyDown,InputTypeRepeat};
 assert(loader_menu_echo_input(&event,&app) && model.selected==0);
 for(unsigned i=0;i<5;i++) {
  model.selected=i;loader_menu_echo_draw(&canvas,&model);assert(canvas.labels==5);
  event=(InputEvent){InputKeyOk,InputTypeLong};loader_menu_echo_input(&event,&app);assert(app.calls==i);
  event=(InputEvent){InputKeyOk,InputTypeShort};loader_menu_echo_input(&event,&app);assert(app.calls==i+1 && app.selected==i);
 }
 event=(InputEvent){InputKeyBack,InputTypeShort};assert(!loader_menu_echo_input(&event,&app));
 assert(!locked);
}
"""
production = (ROOT / "applications/services/loader/loader_menu.c").read_text()
start = production.index("typedef struct {\n    uint32_t selected;\n} EchoMenuModel;")
end = production.index("static void loader_menu_build_echo(", start)
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    source = folder / "echo_menu.c"
    source.write_text(STUB + production[start:end] + TEST)
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsanitize=address,undefined",
            str(source),
            "-o",
            str(folder / "test"),
        ],
        check=True,
    )
    subprocess.run([str(folder / "test")], check=True)
print(
    "PASS: five visible rows, bounds, wrap/repeat, Back, short-OK only, unlocked callbacks"
)
