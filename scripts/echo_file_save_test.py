"""Fault-inject production staged saves, RFID rename/save and scene recovery.

The in-memory filesystem models ordinary API failures, collisions and rollback;
it does not claim power-loss atomicity or physical SD endurance.
"""

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


def function(source, name):
    match = re.search(
        r"^(?:static )?(?:bool|void)\s+" + name + r"\([^;]*?\) \{", source, re.M
    )
    assert match, name
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start() : end] + "\n"


ADAPTER = r"""
#include <stdarg.h>
#define LFRFID_APP_FOLDER "/ext/lfrfid"
#define LFRFID_APP_FILENAME_EXTENSION ".rfid"
#define FSF_DIRECTORY 1
#define FSAM_WRITE 1
#define FSOM_CREATE_NEW 1
static bool furi_string_equal(FuriString* a,FuriString* b){return !strcmp(a->text,b->text);}
static bool furi_string_end_with(FuriString* s,const char* end){size_t a=strlen(s->text),b=strlen(end);return a>=b&&!strcmp(s->text+a-b,end);}
static void furi_string_printf(FuriString* s,const char* fmt,...){char b[1024];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);furi_string_set_str(s,b);}
static FuriString* furi_string_alloc_printf(const char* fmt,...){char b[1024];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);return alloc_text(b);}
static void furi_string_cat_printf(FuriString* s,const char* fmt,...){char b[1024];strcpy(b,s->text);va_list a;va_start(a,fmt);vsnprintf(b+strlen(b),sizeof(b)-strlen(b),fmt,a);va_end(a);furi_string_set_str(s,b);}
static void path_extract_dirname(const char* path,FuriString* output){char b[512];strcpy(b,path);char* slash=strrchr(b,'/');assert(slash);*slash=0;furi_string_set_str(output,b);}
typedef int Storage;
typedef enum {FSE_OK,FSE_NOT_EXIST,FSE_EXIST,FSE_DENIED,FSE_INTERNAL} FS_Error;
typedef struct {unsigned flags;} FileInfo;
typedef struct {char path[512],data[64];bool directory;} Entry;
static Entry files[100];static unsigned step,fail_a,fail_b,writes,dialogs;static bool race_create;static char message[256];
static bool fault(void){step++;return step==fail_a||step==fail_b;}
static int find(const char* path){for(unsigned i=0;i<COUNT_OF(files);i++)if(!strcmp(files[i].path,path)&&*files[i].path)return (int)i;return -1;}
static int put(const char* path,const char* data){assert(find(path)<0);for(unsigned i=0;i<COUNT_OF(files);i++)if(!*files[i].path){strcpy(files[i].path,path);strcpy(files[i].data,data);files[i].directory=false;return (int)i;}abort();}
static void expect(const char* path,const char* data){int i=find(path);assert(i>=0&&!strcmp(files[i].data,data));}
static void reset(void){memset(files,0,sizeof(files));step=fail_a=fail_b=writes=dialogs=0;race_create=false;*message=0;}
static FS_Error storage_common_stat(Storage* s,const char* path,FileInfo* info){(void)s;if(fault())return FSE_INTERNAL;int i=find(path);if(i<0)return FSE_NOT_EXIST;if(info)info->flags=files[i].directory?FSF_DIRECTORY:0;return FSE_OK;}
typedef struct {bool open;FS_Error error;} File;
static unsigned handles;
static File* storage_file_alloc(Storage* s){(void)s;handles++;return calloc(1,sizeof(File));}
static bool storage_file_open(File* f,const char* path,int access,int mode){assert(!f->open&&access==FSAM_WRITE&&mode==FSOM_CREATE_NEW);if(fault()){f->error=FSE_DENIED;return false;}if(find(path)>=0){f->error=FSE_EXIST;return false;}put(path,"");f->open=true;f->error=FSE_OK;return true;}
static FS_Error storage_file_get_error(File* f){return f->error;}
static bool storage_file_close(File* f){f->open=false;return !fault();}
static void storage_file_free(File* f){assert(!f->open);handles--;free(f);}
static FS_Error storage_common_remove(Storage* s,const char* path){(void)s;if(fault())return FSE_DENIED;int i=find(path);if(i<0)return FSE_NOT_EXIST;files[i].path[0]=0;return FSE_OK;}
static FS_Error storage_common_rename_safe(Storage* s,const char* from,const char* to){(void)s;if(fault())return FSE_DENIED;int i=find(from);if(i<0)return FSE_NOT_EXIST;if(find(to)>=0)return FSE_EXIST;strcpy(files[i].path,to);return FSE_OK;}
static bool storage_common_equivalent_path(Storage* s,const char* a,const char* b){(void)s;return !strcmp(a,b);}
static bool storage_simply_mkdir(Storage* s,const char* path){(void)s;(void)path;return !fault();}
static bool writer(const char* path,void* ctx){(void)ctx;int i=find(path);assert(i>=0);writes++;strcpy(files[i].data,"partial");if(fault())return false;strcpy(files[i].data,"new");if(race_create)put("/ext/lfrfid/Test.rfid","other");return true;}
static void dialog_message_show_storage_error(void* d,const char* text){(void)d;dialogs++;snprintf(message,sizeof(message),"%s",text);}
typedef struct {uint8_t data[4];} ProtocolDict;
static bool lfrfid_dict_file_save(ProtocolDict* dict,int protocol,const char* path){(void)dict;(void)protocol;return writer(path,NULL);}
typedef struct {unsigned state;bool manual;unsigned next;} SceneManager;
typedef struct {Storage* storage;void* dialogs;FuriString* file_path;FuriString* file_name;ProtocolDict* dict;int protocol_id;SceneManager* scene_manager;char text_store[64];uint8_t old_key_data[4],new_key_data[4];} LfRfid;
static bool lfrfid_save_key_data(LfRfid*,FuriString*);
typedef struct {int type,event;} SceneManagerEvent;
enum {SceneManagerEventTypeCustom,SceneManagerEventTypeBack,LfRfidEventNext,LfRfidSceneSaveSuccess,LfRfidSceneSavedKeyMenu,LfRfidSceneSaveType,LfRfidSceneSaveName,LfRfidSceneSaveData,DolphinDeedRfidAdd,DolphinDeedRfidSave};
static void scene_manager_next_scene(SceneManager* s,unsigned scene){s->next=scene;}
static bool scene_manager_has_previous_scene(SceneManager* s,unsigned scene){return s->manual?(scene==LfRfidSceneSaveType):(scene==LfRfidSceneSavedKeyMenu);}
static void scene_manager_set_scene_state(SceneManager* s,unsigned scene,unsigned state){(void)scene;s->state=state;}
static void dolphin_deed(int deed){(void)deed;}
static size_t protocol_dict_get_data_size(ProtocolDict* dict,int protocol){(void)dict;(void)protocol;return 4;}
static void protocol_dict_set_data(ProtocolDict* dict,int protocol,const uint8_t* bytes,size_t count){(void)protocol;assert(count==4);memcpy(dict->data,bytes,4);}
"""
TEST = r"""
#define DEST "/ext/lfrfid/Test.rfid"
static void preserved(FuriString* recovery){int i=find(DEST);if(i>=0&&!strcmp(files[i].data,"old"))return;assert(!furi_string_empty(recovery));expect(recovery->text,"old");}
int main(void){
 FuriString* recovery=furi_string_alloc();Storage storage=0;
 reset();put(DEST,"old");assert(echo_file_save(&storage,DEST,true,writer,NULL,recovery));expect(DEST,"new");assert(furi_string_empty(recovery)&&!handles);unsigned total=step;assert(total==7);
 for(unsigned fail=1;fail<=total;fail++){
  reset();put(DEST,"old");fail_a=fail;bool result=echo_file_save(&storage,DEST,true,writer,NULL,recovery);
  if(result){assert(fail==7);expect(DEST,"new");expect(recovery->text,"old");}else preserved(recovery);
  assert(!handles);
 }
 // Commit fails, then rollback fails: keep the only original and report its path.
 reset();put(DEST,"old");fail_a=6;fail_b=7;assert(!echo_file_save(&storage,DEST,true,writer,NULL,recovery));expect(DEST ".echo-old-0","old");assert(!strcmp(recovery->text,DEST ".echo-old-0")&&find(DEST)<0);
 reset();assert(echo_file_save(&storage,DEST,false,writer,NULL,recovery));expect(DEST,"new");assert(furi_string_empty(recovery));unsigned create_steps=step;
 for(unsigned fail=1;fail<=create_steps;fail++){reset();fail_a=fail;assert(!echo_file_save(&storage,DEST,false,writer,NULL,recovery));assert(find(DEST)<0&&!handles);}
 reset();put(DEST,"other");assert(!echo_file_save(&storage,DEST,false,writer,NULL,recovery));expect(DEST,"other");assert(!writes);
 reset();int dir=put(DEST,"");files[dir].directory=true;assert(!echo_file_save(&storage,DEST,true,writer,NULL,recovery)&&!writes);
 reset();race_create=true;assert(!echo_file_save(&storage,DEST,false,writer,NULL,recovery));expect(DEST,"other");
 // Interrupted-save artifacts are neither truncated nor silently removed.
 reset();put(DEST,"old");put(DEST ".echo-new-0","prior new");put(DEST ".echo-old-0","prior old");assert(echo_file_save(&storage,DEST,true,writer,NULL,recovery));expect(DEST,"new");expect(DEST ".echo-new-0","prior new");expect(DEST ".echo-old-0","prior old");
 for(unsigned kind=0;kind<2;kind++){reset();put(DEST,"old");for(unsigned slot=0;slot<32;slot++){char path[512];snprintf(path,sizeof(path),"%s.echo-%s-%u",DEST,kind?"old":"new",slot);put(path,"retained");}assert(!echo_file_save(&storage,DEST,true,writer,NULL,recovery));expect(DEST,"old");assert(!handles);}
 // Exercise actual app helpers and scene handlers, including data rollback.
 ProtocolDict dict={{1,2,3,4}};SceneManager manager={0};LfRfid app={.storage=&storage,.file_path=alloc_text(DEST),.file_name=alloc_text("Test"),.dict=&dict,.scene_manager=&manager,.old_key_data={1,2,3,4},.new_key_data={5,6,7,8}};
 reset();assert(!lfrfid_rename_key(&app,"Test"));put(DEST,"old");assert(lfrfid_rename_key(&app,"Test"));
 reset();put(DEST,"old");put("/ext/lfrfid/Other.rfid","other");assert(!lfrfid_rename_key(&app,"Other"));expect(DEST,"old");assert(!strcmp(app.file_path->text,DEST)&&!strcmp(app.file_name->text,"Test"));
 reset();put(DEST,"old");strcpy(app.text_store,"Renamed");assert(lfrfid_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,LfRfidEventNext}));expect("/ext/lfrfid/Renamed.rfid","old");assert(find(DEST)<0&&!writes&&manager.next==LfRfidSceneSaveSuccess);
 furi_string_set_str(app.file_path,DEST);furi_string_set_str(app.file_name,"Test");manager.next=0;reset();put(DEST,"old");fail_a=1;assert(lfrfid_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,LfRfidEventNext}));expect(DEST,"old");assert(!manager.next&&!strcmp(app.file_path->text,DEST)&&!strcmp(app.file_name->text,"Test"));
 reset();put(DEST,"old");fail_a=5;assert(lfrfid_scene_save_data_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,LfRfidEventNext}));expect(DEST,"old");assert(!memcmp(dict.data,app.old_key_data,4)&&!manager.next&&!strcmp(app.file_path->text,DEST));
 fail_a=0;assert(lfrfid_scene_save_data_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,LfRfidEventNext}));expect(DEST,"new");assert(!memcmp(dict.data,app.new_key_data,4)&&manager.next==LfRfidSceneSaveSuccess);
 // New-file failure leaves folder/name selection intact and permits retry.
 reset();manager.next=0;manager.manual=true;furi_string_set_str(app.file_path,LFRFID_APP_FOLDER);furi_string_reset(app.file_name);strcpy(app.text_store,"Test");fail_a=1;assert(lfrfid_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,LfRfidEventNext}));assert(!manager.next&&furi_string_empty(app.file_name)&&!strcmp(app.file_path->text,LFRFID_APP_FOLDER));fail_a=0;assert(lfrfid_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,LfRfidEventNext}));expect(DEST,"new");assert(!strcmp(app.file_path->text,DEST)&&!strcmp(app.file_name->text,"Test"));
 for(unsigned i=0;i<100;i++){reset();put(DEST,"old");assert(lfrfid_save_key(&app));expect(DEST,"new");assert(!handles);}
 furi_string_free(app.file_path);furi_string_free(app.file_name);furi_string_free(recovery);
 puts("PASS: production staged-save fault injection, collision/directory rejection, rollback/recovery retention, bounded artifact slots, RFID rename without rewriting, state preservation, edit retry/data rollback and 100 ownership cycles");
}
"""
helper = re.sub(
    r"^#(?:include|pragma).*\n",
    "",
    (ROOT / "applications/main/echo/echo_file_save.h").read_text(),
    flags=re.M,
)
rfid = (ROOT / "applications/main/lfrfid/lfrfid.c").read_text()
app = "".join(
    function(rfid, n)
    for n in (
        "lfrfid_save_key",
        "lfrfid_rename_key",
        "lfrfid_write_key_file",
        "lfrfid_save_key_data",
    )
)
app += function(
    (ROOT / "applications/main/lfrfid/scenes/lfrfid_scene_save_name.c").read_text(),
    "lfrfid_scene_save_name_on_event",
)
app += function(
    (ROOT / "applications/main/lfrfid/scenes/lfrfid_scene_save_data.c").read_text(),
    "lfrfid_scene_save_data_on_event",
)
with tempfile.TemporaryDirectory(prefix="echo-file-save-") as temp:
    p = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    p.write_text(STUB + ADAPTER + helper + app + TEST)
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

# The exported dictionary writer must report final close/flush failure, which
# callers previously could not distinguish from a completed file.
DICT_ADAPTER = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#define furi_check assert
#define PROTOCOL_NO -1
#define RECORD_STORAGE 1
#define LFRFID_DICT_FILETYPE "Flipper RFID key"
typedef int ProtocolDict;
typedef int ProtocolId;
typedef int Storage;
typedef int FlipperFormat;
static unsigned op,fail,records,formats,close_calls;
static bool next(void){return ++op!=fail;}
static Storage* furi_record_open(int record){(void)record;records++;static Storage s;return &s;}
static void furi_record_close(int record){(void)record;records--;}
static FlipperFormat* flipper_format_file_alloc(Storage* s){(void)s;formats++;return malloc(sizeof(FlipperFormat));}
static void flipper_format_free(FlipperFormat* f){formats--;free(f);}
static size_t protocol_dict_get_data_size(ProtocolDict* d,ProtocolId p){(void)d;(void)p;return 5;}
static const char* protocol_dict_get_name(ProtocolDict* d,ProtocolId p){(void)d;(void)p;return "EM4100";}
static void protocol_dict_get_data(ProtocolDict* d,ProtocolId p,uint8_t* bytes,size_t count){(void)d;(void)p;assert(count==5);for(unsigned i=0;i<count;i++)bytes[i]=i;}
static bool flipper_format_file_open_always(FlipperFormat* f,const char* path){(void)f;(void)path;return next();}
static bool flipper_format_write_header_cstr(FlipperFormat* f,const char* type,uint32_t version){(void)f;(void)type;assert(version==1);return next();}
static bool flipper_format_write_string_cstr(FlipperFormat* f,const char* key,const char* value){(void)f;(void)key;(void)value;return next();}
static bool flipper_format_write_hex(FlipperFormat* f,const char* key,const uint8_t* bytes,size_t count){(void)f;(void)key;assert(count==5&&bytes[4]==4);return next();}
static bool flipper_format_file_close(FlipperFormat* f){(void)f;close_calls++;return next();}
"""
DICT_TEST = r"""
int main(void){ProtocolDict dict=0;for(unsigned cycle=0;cycle<100;cycle++){for(unsigned failure=0;failure<=5;failure++){op=0;fail=failure;close_calls=0;bool ok=lfrfid_dict_file_save(&dict,0,"test.rfid");assert(ok==(failure==0));assert(close_calls==1&&!records&&!formats);}}puts("PASS: production RFID serializer reports open/header/protocol/data/final-close errors and balances ownership");}
"""
with tempfile.TemporaryDirectory(prefix="echo-rfid-serialize-") as temp:
    p = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    p.write_text(
        DICT_ADAPTER
        + function(
            (ROOT / "lib/lfrfid/lfrfid_dict_file.c").read_text(),
            "lfrfid_dict_file_save",
        )
        + DICT_TEST
    )
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
