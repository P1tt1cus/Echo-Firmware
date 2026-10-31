"""Run production browser ownership, selection and cancellation code under sanitizers."""

import ast
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "applications/services/gui/modules"
# Reuse only the host adapter constant, without executing the shared-menu suite.
tree = ast.parse((ROOT / "scripts/echo_shared_menu_test.py").read_text())
STUB = next(
    ast.literal_eval(node.value)
    for node in tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "STUB" for t in node.targets)
)
STUB = STUB.replace(
    "static FuriString* furi_string_alloc(void) {",
    "static int strings_live;\nstatic FuriString* furi_string_alloc(void) {strings_live++;",
).replace(
    "static void furi_string_free(FuriString* s) {",
    "static void furi_string_free(FuriString* s) {strings_live--;",
)
STUB = STUB.replace("bool popup_overlay;", "bool popup_overlay;bool sort_dirs_first;")
COMMON = r"""
#include <stdarg.h>
#include <strings.h>
#include <m-algo.h>
#define CUSTOM_ICON_MAX_SIZE 32
#define BROWSER_SORT_THRESHOLD 220
#define ITEM_LIST_LEN_MAX 50
#define LIST_ITEMS 5
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define CLAMP(x,hi,lo) MAX(MIN(x,hi),lo)
static int icons_live;
static void* icon_malloc(size_t n) {icons_live++;return malloc(n);}
static void icon_free(void* p) {if(p)icons_live--;free(p);}
static int furi_string_cmp(const FuriString* a,const FuriString* b) {return strcmp(a->text,b->text);}
static int furi_string_cmpi(const FuriString* a,const FuriString* b) {return strcasecmp(a->text,b->text);}
static void furi_string_printf(FuriString* s,const char* fmt,...) {char b[1024];va_list v;va_start(v,fmt);vsnprintf(b,sizeof(b),fmt,v);va_end(v);furi_string_set_str(s,b);}
static void path_extract_filename(FuriString* p,FuriString* dest,bool strip) {const char* n=strrchr(p->text,'/');furi_string_set_str(dest,n?n+1:p->text);if(strip){char* dot=strrchr(dest->text,'.');if(dot)*dot=0;}}

"""


def function(source, name):
    pos = source.index(name + "(")
    start = source.rfind("\n", 0, pos) + 1
    # These production functions keep their return type on a preceding line.
    if source[start:pos].strip() == "":
        start = source.rfind("\n", 0, start - 1) + 1
    brace = source.index("{", pos)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


source = (MODULES / "file_browser.c").read_text()
source = source.replace(
    "malloc(CUSTOM_ICON_MAX_SIZE)", "icon_malloc(CUSTOM_ICON_MAX_SIZE)"
)
for pointer in ("obj->custom_icon_data", "item.custom_icon_data"):
    source = source.replace("free(" + pointer + ")", "icon_free(" + pointer + ")")
items = source[source.index("typedef enum {") : source.index("struct FileBrowser {")]
models = source[
    source.index("struct FileBrowser {") : source.index(
        "static const Icon* BrowserItemIcons"
    )
]
DECL = r"""
typedef struct {int unused;} BrowserWorker;
typedef struct FileBrowser FileBrowser;
typedef void(*FileBrowserCallback)(void*);
typedef bool(*FileBrowserLoadItemCallback)(FuriString*,void*,uint8_t**,FuriString*);
static unsigned load_requests;
static void file_browser_worker_load(BrowserWorker* w,int offset,int count) {(void)w;(void)offset;(void)count;load_requests++;}
"""
# Compile the real completion callback and m-array ownership methods.
BROWSER_TEST = r"""
static void add(FileBrowser* b,const char* name) {FuriString* s=alloc_text(name);browser_list_item_cb(b,s,false,false);furi_string_free(s);}
int main(void) {
 BrowserItem_t src,dst;BrowserItem_t_init(&src);BrowserItem_t_init(&dst);
 src.custom_icon_data=icon_malloc(CUSTOM_ICON_MAX_SIZE);memset(src.custom_icon_data,0x5a,CUSTOM_ICON_MAX_SIZE);
 BrowserItem_t_set(&dst,&src);assert(dst.custom_icon_data&&dst.custom_icon_data!=src.custom_icon_data);
 assert(!memcmp(dst.custom_icon_data,src.custom_icon_data,CUSTOM_ICON_MAX_SIZE));
 BrowserItem_t_set(&dst,&dst);assert(dst.custom_icon_data[0]==0x5a);
 icon_free(src.custom_icon_data);src.custom_icon_data=NULL;BrowserItem_t_set(&dst,&src);assert(!dst.custom_icon_data);
 BrowserItem_t_clear(&src);BrowserItem_t_clear(&dst);assert(icons_live==0&&strings_live==0);
 FileBrowser b={0};b.view=view_alloc();view_allocate_model(b.view,0,sizeof(FileBrowserModel));
 FileBrowserModel* m=b.view->model;items_array_init(m->items);m->is_root=true;
 for(int pass=0;pass<200;pass++) {
  m->item_cnt=3;m->item_idx=0;add(&b,"z.sub");add(&b,"a.sub");add(&b,"m.sub");
  browser_list_item_cb(&b,NULL,false,true);
  assert(m->item_idx==2);assert(!strcmp(items_array_get(m->items,2)->name->text,"z.sub"));
  items_array_reset(m->items);assert(strings_live==0); // selection string must be freed
 }
 m->item_cnt=5;m->item_idx=4;add(&b,"only.sub");browser_list_item_cb(&b,NULL,false,true);
 assert(m->item_cnt==1&&m->item_idx==0);assert(!m->list_loading);
 items_array_reset(m->items);m->item_cnt=5;m->item_idx=4;browser_list_item_cb(&b,NULL,false,true);
 assert(!m->item_cnt&&!m->item_idx);assert(!browser_is_list_load_required(m));
 m->is_root=false;assert(!browser_is_list_load_required(m));
 assert(!load_requests);items_array_clear(m->items);view_free(b.view);
 assert(strings_live==0&&icons_live==0);
 puts("PASS: browser icon ownership, 200 selection restores without leaks, first-row selection and shrinking/empty directories");
}
"""
worker = (MODULES / "file_browser_worker.c").read_text()
WORKER_STUB = r"""
#define FILE_NAME_LEN_MAX 254
#define LONG_LOAD_THRESHOLD 100
#define WorkerEvtStop 1
#define RECORD_STORAGE 1
#define FSE_OK 0
static unsigned reads,stop_after,total_entries,opened,closed,items,finishes,long_loads;
static uint32_t furi_thread_flags_get(void) {return reads>=stop_after?WorkerEvtStop:0;}
typedef int Storage;
typedef struct {int unused;} File;
typedef struct {bool dir;} FileInfo;
typedef struct {
 void* cb_ctx;
 void(*list_load_cb)(void*,uint32_t);
 void(*list_item_cb)(void*,FuriString*,bool,bool);
 void(*long_load_cb)(void*);
} BrowserWorker;
static Storage* furi_record_open(int r) {(void)r;return (Storage*)1;}
static void furi_record_close(int r) {(void)r;}
static File* storage_file_alloc(Storage* s) {(void)s;return calloc(1,sizeof(File));}
static void storage_file_free(File* f) {free(f);}
static bool storage_dir_open(File* f,const char* p) {(void)f;(void)p;opened++;return true;}
static bool storage_dir_read(File* f,FileInfo* info,char* name,size_t n) {(void)f;info->dir=false;if(reads>=total_entries)return false;snprintf(name,n,"%u.sub",reads++);return true;}
static void storage_dir_close(File* f) {(void)f;closed++;}
static int storage_file_get_error(File* f) {(void)f;return FSE_OK;}
static bool file_info_is_dir(FileInfo* info) {return info->dir;}
static bool browser_filter_by_name(BrowserWorker* b,FuriString* n,bool dir) {(void)b;(void)n;(void)dir;return true;}
static void loaded(void* c,uint32_t offset) {(void)c;(void)offset;}
static void item(void* c,FuriString* n,bool dir,bool last) {(void)c;(void)n;(void)dir;if(last)finishes++;else items++;}
static void long_load(void* c) {(void)c;long_loads++;}
static void reset(unsigned limit) {reads=opened=closed=items=finishes=long_loads=0;stop_after=limit;total_entries=10000;}
"""
WORKER_TEST = r"""
int main(void) {
 BrowserWorker b={.list_load_cb=loaded,.list_item_cb=item,.long_load_cb=long_load};
 FuriString* path=alloc_text("/ext/test");FuriString* name=alloc_text("");uint32_t count;int32_t index;
 reset(7);browser_folder_init(&b,path,name,&count,&index);assert(reads==7&&count==7&&opened==closed);
 reset(7);browser_folder_load_full(&b,path);assert(reads==7&&items==7&&!finishes&&opened==closed);
 reset(7);browser_folder_load_chunked(&b,path,500,50);assert(reads==7&&!items&&!finishes&&opened==closed);
 reset(15);browser_folder_load_chunked(&b,path,10,50);assert(reads==15&&items==5&&!finishes&&opened==closed);
 reset(UINT32_MAX);total_entries=15;browser_folder_load_full(&b,path);assert(items==15&&finishes==1&&opened==closed);
 reset(UINT32_MAX);total_entries=150;browser_folder_init(&b,path,name,&count,&index);assert(count==150&&long_loads==1&&opened==closed);
 furi_string_free(path);furi_string_free(name);assert(strings_live==0&&icons_live==0);
 puts("PASS: browser cancellation during counting, full loading, offset scan and chunk loading; directory cleanup and normal completion");
}
"""

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    for name, code in {
        "browser": STUB
        + COMMON
        + items
        + DECL
        + models
        + function(source, "browser_is_list_load_required")
        + function(source, "browser_update_offset")
        + function(
            source[
                source.index(
                    "static void\n    browser_list_item_cb(void* context, FuriString* item_path, bool is_folder, bool is_last) {"
                ) :
            ],
            "browser_list_item_cb",
        )
        + BROWSER_TEST,
        "worker": STUB
        + COMMON
        + WORKER_STUB
        + function(worker, "browser_worker_stopping")
        + function(worker, "browser_folder_init")
        + function(worker, "browser_folder_load_chunked")
        + function(worker, "browser_folder_load_full")
        + WORKER_TEST,
    }.items():
        path = folder / (name + ".c")
        path.write_text(code)
        binary = folder / name
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-unused-function",
                "-Wno-unused-variable",
                "-Wno-unused-but-set-variable",
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
