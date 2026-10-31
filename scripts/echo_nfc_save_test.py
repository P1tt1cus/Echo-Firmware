"""Exercise production NFC original/shadow saving and exact-pair rename with faults."""

import ast
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def literal(path, name):
    tree = ast.parse(path.read_text())
    return next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
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


STUB = literal(ROOT / "scripts/echo_shared_menu_test.py", "STUB")
ADAPTER = literal(ROOT / "scripts/echo_file_save_test.py", "ADAPTER")
ADAPTER = ADAPTER.replace(
    "typedef struct {bool open;FS_Error error;} File;",
    "typedef struct {bool open;FS_Error error;int index;} File;\n#define FSAM_READ 2\n#define FSOM_OPEN_EXISTING 2",
)
a = ADAPTER.index("static bool storage_file_open(")
b = ADAPTER.index("\nstatic FS_Error storage_file_get_error", a)
ADAPTER = (
    ADAPTER[:a]
    + r"""static bool storage_file_open(File* f,const char* path,int access,int mode){assert(!f->open&&(access==FSAM_WRITE||access==FSAM_READ));if(fault()){f->error=FSE_DENIED;return false;}int i=find(path);if(mode==FSOM_CREATE_NEW){if(i>=0){f->error=FSE_EXIST;return false;}i=put(path,"");}else{assert(mode==FSOM_OPEN_EXISTING);if(i<0){f->error=FSE_NOT_EXIST;return false;}}f->index=i;f->open=true;f->error=FSE_OK;return true;}
static uint64_t storage_file_size(File* f){assert(f->open);return strlen(files[f->index].data);}
static bool storage_file_copy_to_file(File* from,File* to,size_t size){assert(from->open&&to->open&&size==strlen(files[from->index].data));strcpy(files[to->index].data,"partial");if(fault())return false;strcpy(files[to->index].data,files[from->index].data);return true;}
static bool storage_file_sync(File* f){assert(f->open);return !fault();}
"""
    + ADAPTER[b:]
)
ADAPTER = ADAPTER.replace(
    "return s->manual?(scene==LfRfidSceneSaveType):(scene==LfRfidSceneSavedKeyMenu);",
    "return s->manual?(scene==LfRfidSceneSaveType):(scene==LfRfidSceneSavedKeyMenu||scene==200);",
)
# Record the first committed copy so tests can inject second-copy plus cleanup failure.
ADAPTER = ADAPTER.replace(
    "static unsigned handles;", "static unsigned handles,first_commit;"
)
ADAPTER = ADAPTER.replace(
    "strcpy(files[i].path,to);return FSE_OK;",
    'strcpy(files[i].path,to);if(!strcmp(to,"/ext/nfc/Renamed.nfc"))first_commit=step;return FSE_OK;',
)
NFC_ADAPTER = r"""
#define NFC_APP_FOLDER "/ext/nfc"
#define NFC_APP_EXTENSION ".nfc"
#define NFC_APP_SHADOW_EXTENSION ".shd"
#define NFC_BYTE_INPUT_STORE_SIZE 16
static void path_extract_filename(FuriString* path,FuriString* name,bool strip){const char* begin=strrchr(path->text,'/');assert(begin);char b[512];strcpy(b,begin+1);if(strip){char* dot=strrchr(b,'.');if(dot)*dot=0;}furi_string_set_str(name,b);}
static void furi_string_left(FuriString* s,size_t count){assert(count<=strlen(s->text));s->text[count]=0;}
static void furi_string_cat(FuriString* s,const char* suffix){furi_string_cat_printf(s,"%s",suffix);}
static void furi_string_set_n(FuriString* dest,FuriString* src,size_t start,size_t count){char b[512];assert(count<sizeof(b));memcpy(b,src->text+start,count);b[count]=0;furi_string_set_str(dest,b);}
typedef struct {uint8_t uid[4];} NfcDevice;
typedef int NfcProtocol;
typedef struct {Storage* storage;void* dialogs;FuriString* file_path;FuriString* file_name;NfcDevice* nfc_device;SceneManager* scene_manager;uint8_t byte_input_store[NFC_BYTE_INPUT_STORE_SIZE];char text_store[64];} NfcApp;
static bool nfc_device_save(NfcDevice* device,const char* path){(void)device;return writer(path,NULL);}
static const uint8_t* nfc_device_get_uid(NfcDevice* device,size_t* size){*size=4;return device->uid;}
static bool uid_ok=true;
static bool nfc_device_set_uid(NfcDevice* device,const uint8_t* uid,size_t size){assert(size==4);if(!uid_ok)return false;memcpy(device->uid,uid,size);return true;}
static NfcProtocol nfc_device_get_protocol(NfcDevice* d){(void)d;return 0;}
enum {NfcSceneSavedMenu=200,NfcSceneReadMenu,NfcSceneSaveSuccess,NfcSceneSaveName,NfcSceneSetType,NfcCustomEventByteInputDone,NfcCustomEventTextInputDone,DolphinDeedNfcAddSave,DolphinDeedNfcSave};
static bool scene_manager_search_and_switch_to_previous_scene(SceneManager* s,unsigned scene){s->next=scene;return true;}
enum {SubmenuIndexCommonRename=300};
static unsigned scene_manager_get_scene_state(SceneManager* s,unsigned scene){(void)scene;return s->state;}
static unsigned protocol_events;
static bool protocol_event(NfcApp* n,SceneManagerEvent e){(void)n;(void)e;protocol_events++;return false;}
static struct {struct{bool(*on_event)(NfcApp*,SceneManagerEvent);}scene_save_name;} support={{protocol_event}};
static void* nfc_protocol_support_get_untyped(NfcProtocol p,NfcApp* n){(void)p;(void)n;return &support;}
#define nfc_protocol_support_get(p,n) ((__typeof__(support)*)nfc_protocol_support_get_untyped(p,n))
"""
TEST = r"""
#define BASE "/ext/nfc/Card.nfc"
#define SHADOW "/ext/nfc/Card.shd"
#define NEWBASE "/ext/nfc/Renamed.nfc"
#define NEWSHADOW "/ext/nfc/Renamed.shd"
static void originals(void){expect(BASE,"original # bytes");expect(SHADOW,"modified # bytes");}
static void pair(void){put(BASE,"original # bytes");put(SHADOW,"modified # bytes");}
static void selection(NfcApp* n){furi_string_set_str(n->file_path,BASE);furi_string_set_str(n->file_name,"Card");}
int main(void){
 Storage storage=0;SceneManager manager={0};NfcDevice device={{1,2,3,4}};NfcApp app={.storage=&storage,.file_path=alloc_text(BASE),.file_name=alloc_text("Card"),.nfc_device=&device,.scene_manager=&manager,.byte_input_store={5,6,7,8}};
 reset();pair();assert(nfc_rename(&app,"Renamed"));expect(NEWBASE,"original # bytes");expect(NEWSHADOW,"modified # bytes");assert(find(BASE)<0&&find(SHADOW)<0&&!strcmp(app.file_path->text,NEWBASE)&&!strcmp(app.file_name->text,"Renamed")&&!handles);unsigned total=step,commit=first_commit;
 for(unsigned failure=1;failure<=total;failure++){
  reset();pair();selection(&app);fail_a=failure;bool renamed=nfc_rename(&app,"Renamed");
  if(renamed){expect(NEWBASE,"original # bytes");expect(NEWSHADOW,"modified # bytes");assert(dialogs);}
  else {originals();assert(!strcmp(app.file_path->text,BASE)&&!strcmp(app.file_name->text,"Card"));}
  assert(!handles);
 }
 reset();pair();selection(&app);fail_a=commit+2;fail_b=commit+4;assert(!nfc_rename(&app,"Renamed"));originals();expect(NEWBASE,"original # bytes");assert(strstr(message,"copy retained"));
 reset();selection(&app);put(BASE,"original # bytes");assert(nfc_rename(&app,"Renamed"));expect(NEWBASE,"original # bytes");assert(find(BASE)<0&&!writes);
 reset();pair();selection(&app);put(NEWSHADOW,"other shadow");assert(!nfc_rename(&app,"Renamed"));originals();expect(NEWSHADOW,"other shadow");assert(!writes);
 reset();pair();selection(&app);assert(nfc_rename(&app,"Card"));originals();
 reset();selection(&app);assert(!nfc_rename(&app,"Card"));
 // A failed shadow replacement leaves original, shadow and canonical selection intact.
 reset();pair();selection(&app);assert(nfc_save_shadow_file(&app));expect(BASE,"original # bytes");expect(SHADOW,"new");assert(!strcmp(app.file_path->text,BASE));total=step;
 for(unsigned failure=1;failure<=total;failure++){
  reset();pair();selection(&app);fail_a=failure;bool saved=nfc_save_shadow_file(&app);expect(BASE,"original # bytes");assert(!strcmp(app.file_path->text,BASE));
  if(saved)expect(SHADOW,"new");else expect(SHADOW,"modified # bytes");assert(!handles);
 }
 reset();selection(&app);assert(!nfc_save_shadow_file(&app));assert(find(SHADOW)<0);
 // New names cannot silently bind to an orphan modified file; path stays a folder.
 reset();furi_string_set_str(app.file_path,NFC_APP_FOLDER);furi_string_set_str(app.file_name,"Card");put(SHADOW,"unrelated");assert(!nfc_save(&app));expect(SHADOW,"unrelated");assert(find(BASE)<0&&!strcmp(app.file_path->text,NFC_APP_FOLDER));
 reset();assert(nfc_save(&app));expect(BASE,"new");assert(!strcmp(app.file_path->text,BASE));
 // The explicit destination argument is honoured, without replacing another card.
 reset();selection(&app);put(BASE,"original # bytes");FuriString* dest=alloc_text(NEWBASE);assert(nfc_save_file(&app,dest));expect(BASE,"original # bytes");expect(NEWBASE,"new");assert(!nfc_save_file(&app,dest));furi_string_free(dest);
 // Saved UID edit uses a shadow; failure restores the in-memory UID for retry.
 reset();pair();selection(&app);manager.next=0;fail_a=1;assert(nfc_scene_set_uid_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,NfcCustomEventByteInputDone}));originals();const uint8_t old[]={1,2,3,4};assert(!memcmp(device.uid,old,4)&&!manager.next);
 fail_a=0;assert(nfc_scene_set_uid_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,NfcCustomEventByteInputDone}));assert(!memcmp(device.uid,app.byte_input_store,4)&&manager.next==NfcSceneSaveSuccess);expect(BASE,"original # bytes");expect(SHADOW,"new");
 reset();pair();selection(&app);strcpy(app.text_store,"Renamed");manager.next=0;manager.state=SubmenuIndexCommonRename;assert(nfc_protocol_support_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,NfcCustomEventTextInputDone}));expect(NEWBASE,"original # bytes");expect(NEWSHADOW,"modified # bytes");assert(manager.next==NfcSceneSaveSuccess&&protocol_events==1);
 reset();pair();selection(&app);manager.next=0;fail_a=1;assert(nfc_protocol_support_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,NfcCustomEventTextInputDone}));originals();assert(!manager.next&&protocol_events==1&&!strcmp(app.file_name->text,"Card"));
 reset();pair();selection(&app);manager.state=0;strcpy(app.text_store,"Card");assert(nfc_protocol_support_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,NfcCustomEventTextInputDone}));expect(BASE,"original # bytes");expect(SHADOW,"new");strcpy(app.text_store,"Renamed");
 // Named updated/read data saved under a new name must serialize, not enter Rename.
 reset();pair();selection(&app);manager.state=0;manager.next=0;assert(nfc_protocol_support_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,NfcCustomEventTextInputDone}));originals();expect(NEWBASE,"new");assert(find(NEWSHADOW)<0&&writes==1);
 for(unsigned cycle=0;cycle<100;cycle++){reset();pair();selection(&app);assert(nfc_rename(&app,"Renamed"));assert(!handles);}
 furi_string_free(app.file_path);furi_string_free(app.file_name);
 puts("PASS: NFC exact original/shadow rename, every ordinary copy/sync/close/commit failure, collision/orphan rejection, retained copies, canonical selection, explicit save path, UID shadow edit/rollback, scene retry and 100 ownership cycles");
}
"""
source = (ROOT / "applications/main/nfc/nfc_app.c").read_text()
functions = "".join(
    function(source, n)
    for n in (
        "nfc_write_file",
        "nfc_save_file",
        "nfc_set_shadow_file_path",
        "nfc_save_internal",
    )
)
functions += "typedef struct {Storage* storage;const char* source;} NfcFileCopy;\n"
functions += "".join(
    function(source, n)
    for n in ("nfc_copy_file", "nfc_rename", "nfc_save_shadow_file", "nfc_save")
)
functions += function(
    (ROOT / "applications/main/nfc/scenes/nfc_scene_set_uid.c").read_text(),
    "nfc_scene_set_uid_on_event",
)
functions += function(
    (
        ROOT / "applications/main/nfc/helpers/protocol_support/nfc_protocol_support.c"
    ).read_text(),
    "nfc_protocol_support_scene_save_name_on_event",
)
helper = re.sub(
    r"^#(?:include|pragma).*\n",
    "",
    (ROOT / "applications/main/echo/echo_file_save.h").read_text(),
    flags=re.M,
)
with tempfile.TemporaryDirectory(prefix="echo-nfc-save-") as temp:
    p = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    p.write_text(STUB + ADAPTER + NFC_ADAPTER + helper + functions + TEST)
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

SERIALIZER_ADAPTER = r"""
#include <stdarg.h>
#define NFC_FILE_HEADER "Flipper NFC device"
#define NFC_CURRENT_FORMAT_VERSION 4
#define NFC_DEVICE_TYPE_KEY "Device type"
#define NFC_DEVICE_UID_KEY "UID"
#define RECORD_STORAGE 1
typedef int Storage;
typedef int FlipperFormat;
typedef int NfcProtocol;
enum {NfcProtocolNum=1};
typedef struct {NfcProtocol protocol;void* protocol_data;void(*loading_callback)(void*,bool);void* loading_callback_context;} NfcDevice;
static unsigned op,fail,formats,records,close_calls,loading_calls;
static bool next(void){return ++op!=fail;}
static void furi_string_printf(FuriString* s,const char* fmt,...){char b[256];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);furi_string_set_str(s,b);}
static void furi_string_cat(FuriString* s,const char* end){char b[256];snprintf(b,sizeof(b),"%s%s",s->text,end);furi_string_set_str(s,b);}
static Storage* furi_record_open(int r){(void)r;records++;static Storage s;return &s;}
static void furi_record_close(int r){(void)r;records--;}
static FlipperFormat* flipper_format_buffered_file_alloc(Storage* s){(void)s;formats++;return malloc(sizeof(FlipperFormat));}
static void flipper_format_free(FlipperFormat* f){formats--;free(f);}
static bool flipper_format_buffered_file_open_always(FlipperFormat* f,const char* path){(void)f;(void)path;return next();}
static bool flipper_format_write_header_cstr(FlipperFormat* f,const char* type,uint32_t version){(void)f;(void)type;assert(version==4);return next();}
static bool flipper_format_write_comment(FlipperFormat* f,FuriString* text){(void)f;assert(*text->text);return next();}
static bool flipper_format_write_string_cstr(FlipperFormat* f,const char* key,const char* text){(void)f;(void)key;(void)text;return next();}
static const uint8_t* nfc_device_get_uid(NfcDevice* d,size_t* length){(void)d;static uint8_t uid[]={1,2,3,4};*length=4;return uid;}
static bool flipper_format_write_hex(FlipperFormat* f,const char* key,const uint8_t* uid,size_t length){(void)f;(void)key;assert(length==4&&uid[3]==4);return next();}
static bool flipper_format_buffered_file_close(FlipperFormat* f){(void)f;close_calls++;return next();}
static bool protocol_save(void* data,FlipperFormat* f){(void)data;(void)f;return next();}
static const struct {const char* protocol_name;bool(*save)(void*,FlipperFormat*);} supported={"ISO14443-3A",protocol_save};
static const __typeof__(supported)* nfc_devices[]={&supported};
static void loading(void* ctx,bool active){assert(ctx==&op);loading_calls++;if(!active)assert(close_calls==1);}
"""
SERIALIZER_TEST = r"""
int main(void){NfcDevice device={.loading_callback=loading,.loading_callback_context=&op};for(unsigned cycle=0;cycle<100;cycle++)for(unsigned failure=0;failure<=8;failure++){op=close_calls=loading_calls=0;fail=failure;bool ok=nfc_device_save(&device,"test.nfc");assert(ok==(failure==0));assert(close_calls==1&&loading_calls==2&&!records&&!formats);}puts("PASS: production NFC serializer rejects every open/write/protocol/final-flush-close failure and ends loading after close");}
"""
with tempfile.TemporaryDirectory(prefix="echo-nfc-serializer-") as temp:
    p = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    p.write_text(
        STUB
        + SERIALIZER_ADAPTER
        + function((ROOT / "lib/nfc/nfc_device.c").read_text(), "nfc_device_save")
        + SERIALIZER_TEST
    )
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
