"""Fault-inject Sub-GHz saves, rename/retry, worker teardown and deferred autosave UI."""

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


def function(source, name):
    m = re.search(
        r"^(?:static )?(?:bool|void)\s+" + name + r"\([^;]*?\) \{", source, re.M
    )
    assert m, name
    depth, end = 1, m.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[m.start() : end] + "\n"


STUB = literal(ROOT / "scripts/echo_shared_menu_test.py", "STUB")
ADAPTER = literal(ROOT / "scripts/echo_file_save_test.py", "ADAPTER")
ADAPTER = ADAPTER.replace("data[64]", "data[4096]").replace(
    "typedef struct {bool open;FS_Error error;} File;",
    "typedef struct {bool open;FS_Error error;int index;size_t pos;} File;\n#define FSOM_OPEN_EXISTING 2",
)
a = ADAPTER.index("static bool storage_file_open(")
b = ADAPTER.index("\nstatic FS_Error storage_file_get_error", a)
ADAPTER = (
    ADAPTER[:a]
    + r"""static bool storage_file_open(File* f,const char* path,int access,int mode){assert(!f->open&&access==FSAM_WRITE);if(fault()){f->error=FSE_DENIED;return false;}int i=find(path);if(mode==FSOM_CREATE_NEW){if(i>=0){f->error=FSE_EXIST;return false;}i=put(path,"");}else{assert(mode==FSOM_OPEN_EXISTING);if(i<0){f->error=FSE_NOT_EXIST;return false;}}f->index=i;f->pos=0;f->open=true;f->error=FSE_OK;return true;}
static size_t storage_file_write(File* f,const void* bytes,size_t count){assert(f->open);if(fault())count--;assert(f->pos+count<sizeof(files[0].data));memcpy(files[f->index].data+f->pos,bytes,count);f->pos+=count;files[f->index].data[f->pos]=0;return count;}
static bool storage_file_sync(File* f){assert(f->open);return !fault();}
"""
    + ADAPTER[b:]
)
ADAPTER = ADAPTER.replace(
    "static bool scene_manager_has_previous_scene(SceneManager* s,unsigned scene){return s->manual?(scene==LfRfidSceneSaveType):(scene==LfRfidSceneSavedKeyMenu);}",
    "static unsigned previous_scene;\nstatic bool scene_manager_has_previous_scene(SceneManager* s,unsigned scene){(void)s;return scene==previous_scene;}",
)
ADAPTER = ADAPTER.replace(
    "static void dialog_message_show_storage_error(void* d,const char* text){(void)d;",
    "static bool require_stopped,radio_running;\nstatic void dialog_message_show_storage_error(void* d,const char* text){(void)d;if(require_stopped)assert(!radio_running);",
)
SUB_ADAPTER = r"""
#define MIN(a,b) ((a)<(b)?(a):(b))
#define RECORD_STORAGE 1
#define SUBGHZ_APP_FOLDER "/ext/subghz"
#define SUBGHZ_APP_FILENAME_EXTENSION ".sub"
static unsigned records,formats;
static Storage* furi_record_open(int r){(void)r;records++;static Storage s;return &s;}
static void furi_record_close(int r){(void)r;records--;}
typedef struct {char text[4096];size_t pos;} Stream;
typedef struct {Stream stream;} FlipperFormat;
static bool copy_short,restore_fail,delete_fail,read_short;
static FlipperFormat* flipper_format_string_alloc(void){formats++;return calloc(1,sizeof(FlipperFormat));}
static void flipper_format_free(FlipperFormat* f){formats--;free(f);}
static Stream* flipper_format_get_raw_stream(FlipperFormat* f){return &f->stream;}
static size_t stream_size(Stream* s){return strlen(s->text);}
static size_t stream_tell(Stream* s){return s->pos;}
enum {StreamOffsetFromStart};
static bool stream_seek(Stream* s,size_t p,int mode){assert(mode==StreamOffsetFromStart);if(restore_fail)return false;assert(p<=strlen(s->text));s->pos=p;return true;}
static bool stream_rewind(Stream* s){s->pos=0;return true;}
static size_t stream_copy_full(Stream* from,Stream* to){strcpy(to->text,from->text);from->pos=strlen(from->text);to->pos=strlen(to->text);return copy_short?strlen(to->text)-1:strlen(to->text);}
static size_t stream_read(Stream* s,void* bytes,size_t count){count=MIN(count,strlen(s->text)-s->pos);if(read_short&&count)count--;memcpy(bytes,s->text+s->pos,count);s->pos+=count;return count;}
static bool flipper_format_key_exist(FlipperFormat* f,const char* key){assert(!strcmp(key,"Repeat"));return strstr(f->stream.text,"Repeat:")!=NULL;}
static bool flipper_format_rewind(FlipperFormat* f){return stream_rewind(&f->stream);}
static bool flipper_format_delete_key(FlipperFormat* f,const char* key){assert(!strcmp(key,"Repeat"));if(delete_fail)return false;char* start=strstr(f->stream.text,"Repeat:");assert(start);char* end=strchr(start,'\n');assert(end);memmove(start,end+1,strlen(end+1)+1);return true;}
typedef enum {SubGhzSaveNew,SubGhzSaveUpdate,SubGhzSaveAutosave} SubGhzSaveMode;
typedef struct {bool running;} SubGhzFileEncoderWorker;
typedef struct {void* dialogs;FuriString* file_path;FuriString* file_path_tmp;FuriString* error_str;FlipperFormat* txrx;FlipperFormat* history;SceneManager* scene_manager;char file_name_tmp[64];volatile bool autosave_failed;unsigned idx_menu_chosen,rx_key_state,state_notifications;SubGhzFileEncoderWorker* decode_raw_file_worker_encoder;} SubGhz;
enum {SubGhzRxKeyStateTX=100,SubGhzRxKeyStateStart,SubGhzRxKeyStateIDLE,SubGhzRxKeyStateRAWSave,SubGhzSceneReadRAW,SubGhzSceneDecodeRAW,SubGhzCustomEventManagerNoSet=0,SubGhzCustomEventManagerSetRAW=1,SubGhzCustomEventSceneSaveName=200,SubGhzSceneSaveSuccess,SubGhzSceneSavedMenu,SubGhzSceneMoreRAW,SubGhzSceneShowErrorSub,SubGhzCustomEventSceneSaveSuccess,SubGhzSceneReceiver,SubGhzSceneSaved,SubGhzDecodeRawStateStart,SubGhzNotificationStateIDLE,DolphinDeedSubGhzSave,DolphinDeedSubGhzAddManually};
static unsigned stopped,started,worker_freed,worker_stopped;
static SubGhz* active;
static void subghz_txrx_stop(FlipperFormat* t){(void)t;stopped++;radio_running=false;active->autosave_failed=true;}
static void subghz_txrx_rx_start(FlipperFormat* t){(void)t;started++;radio_running=true;}
static unsigned subghz_rx_key_state_get(SubGhz* s){return s->rx_key_state;}
static void subghz_rx_key_state_set(SubGhz* s,unsigned state){s->rx_key_state=state;}
static void subghz_file_name_clear(SubGhz* s){furi_string_set_str(s->file_path,SUBGHZ_APP_FOLDER);furi_string_reset(s->file_path_tmp);}
static bool subghz_path_is_file(FuriString* s){return furi_string_end_with(s,".sub");}
static FlipperFormat* subghz_txrx_get_fff_data(FlipperFormat* f){return f;}
static FlipperFormat* subghz_history_get_raw_data(FlipperFormat* f,unsigned idx){assert(!idx);return f;}
static bool scene_manager_previous_scene(SceneManager* s){s->next=999;return true;}
static unsigned scene_manager_get_scene_state(SceneManager* s,unsigned scene){(void)scene;return s->state;}
static bool scene_manager_search_and_switch_to_previous_scene(SceneManager* s,unsigned scene){s->next=scene;return true;}
static const char* subghz_txrx_radio_device_get_name(FlipperFormat* f){(void)f;return "cc1101";}
static void subghz_protocol_raw_gen_fff_data(FlipperFormat* f,const char* path,const char* radio){(void)f;assert(strstr(path,".sub")&&*radio);}
static void subghz_txrx_set_rx_callback(FlipperFormat* f,void* callback,SubGhz* ctx){(void)f;(void)ctx;assert(!callback);}
static bool subghz_file_encoder_worker_is_running(SubGhzFileEncoderWorker* w){assert(w);return w->running;}
static void subghz_file_encoder_worker_stop(SubGhzFileEncoderWorker* w){assert(w->running);w->running=false;worker_stopped++;}
static void subghz_file_encoder_worker_free(SubGhzFileEncoderWorker* w){assert(w&&!w->running);free(w);worker_freed++;}
"""
TEST = r"""
#define DEST "/ext/subghz/Test.sub"
#define ORIGINAL "Filetype: Flipper SubGhz Key File\nVersion: 1\nRepeat: 3\nProtocol: Princeton\nKey: 00 00 00 00 00 00 00 01\n"
#define CLEAN "Filetype: Flipper SubGhz Key File\nVersion: 1\nProtocol: Princeton\nKey: 00 00 00 00 00 00 00 01\n"
int main(void){
 FlipperFormat capture={.stream={ORIGINAL,4}};SceneManager manager={0};SubGhz app={.file_path=alloc_text(SUBGHZ_APP_FOLDER),.file_path_tmp=furi_string_alloc(),.error_str=furi_string_alloc(),.txrx=&capture,.history=&capture,.scene_manager=&manager};active=&app;
 reset();put(DEST,"old");assert(subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveUpdate));expect(DEST,CLEAN);assert(!strcmp(capture.stream.text,ORIGINAL)&&capture.stream.pos==4&&!formats&&!records&&!handles);unsigned total=step;
 for(unsigned failure=1;failure<=total;failure++){
  reset();put(DEST,"old");fail_a=failure;bool saved=subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveUpdate);
  if(saved){expect(DEST,CLEAN);assert(dialogs);}else expect(DEST,"old");assert(!strcmp(capture.stream.text,ORIGINAL)&&capture.stream.pos==4&&!formats&&!records&&!handles);
 }
 bool* bad[]={&copy_short,&restore_fail,&delete_fail,&read_short};for(unsigned i=0;i<4;i++){reset();put(DEST,"old");*bad[i]=true;assert(!subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveUpdate));expect(DEST,"old");assert(!strcmp(capture.stream.text,ORIGINAL));*bad[i]=false;capture.stream.pos=4;}
 reset();put(DEST,"other");assert(!subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveNew));expect(DEST,"other");
 reset();app.autosave_failed=false;fail_a=1;assert(!subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveAutosave));assert(app.autosave_failed&&!dialogs);radio_running=true;require_stopped=true;app.rx_key_state=SubGhzRxKeyStateTX;assert(!subghz_scene_receiver_handle_save_error(&app)&&!stopped);app.rx_key_state=SubGhzRxKeyStateStart;assert(subghz_scene_receiver_handle_save_error(&app)&&stopped==1&&started==1&&radio_running&&!app.autosave_failed&&dialogs==1);assert(!subghz_scene_receiver_handle_save_error(&app));require_stopped=false;
 // Failed save retries use the same folder rather than appending names repeatedly.
 reset();strcpy(app.file_name_tmp,"Test");fail_a=1;assert(subghz_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveName}));assert(!strcmp(app.file_path->text,SUBGHZ_APP_FOLDER)&&!manager.next&&find(DEST)<0);fail_a=0;assert(subghz_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveName}));expect(DEST,CLEAN);assert(!strcmp(app.file_path->text,DEST)&&manager.next==SubGhzSceneSaveSuccess);
 reset();put(DEST,"old");subghz_save_to_file(&app);expect(DEST,CLEAN);
 reset();manager.next=0;app.file_name_tmp[0]=0;assert(subghz_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveName}));assert(!manager.next&&dialogs==1);
 // Rename cannot overwrite another signal, and Back restores the original path.
 reset();put(DEST,"original bytes # comment");put("/ext/subghz/Other.sub","other");furi_string_set_str(app.file_path,SUBGHZ_APP_FOLDER);furi_string_set_str(app.file_path_tmp,DEST);strcpy(app.file_name_tmp,"Other");manager.next=0;assert(subghz_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveName}));expect(DEST,"original bytes # comment");expect("/ext/subghz/Other.sub","other");assert(!manager.next&&!strcmp(app.file_path->text,SUBGHZ_APP_FOLDER));assert(subghz_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeBack,0}));assert(!strcmp(app.file_path->text,DEST));
 furi_string_set_str(app.file_path,SUBGHZ_APP_FOLDER);strcpy(app.file_name_tmp,"Renamed");assert(subghz_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveName}));expect("/ext/subghz/Renamed.sub","original bytes # comment");assert(find(DEST)<0&&!strcmp(app.file_path->text,"/ext/subghz/Renamed.sub")&&furi_string_empty(app.file_path_tmp));
 furi_string_set_str(app.file_path_tmp,"/ext/subghz/Renamed.sub");assert(subghz_rename_file(&app,"/ext/subghz/Renamed.sub"));furi_string_set_str(app.file_path_tmp,DEST);assert(!subghz_rename_file(&app,DEST));
 // Saving decoded RAW data can then close the app without a dangling worker.
 previous_scene=SubGhzSceneDecodeRAW;app.decode_raw_file_worker_encoder=malloc(sizeof(*app.decode_raw_file_worker_encoder));app.decode_raw_file_worker_encoder->running=true;assert(subghz_scene_save_success_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveSuccess}));assert(!app.decode_raw_file_worker_encoder&&worker_stopped==1&&worker_freed==1);assert(subghz_scene_save_success_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveSuccess}));assert(worker_freed==1);
 // Multi-chunk writes and short writes keep both capture memory and the original.
 memset(capture.stream.text,'X',1200);capture.stream.text[1200]=0;capture.stream.pos=2;reset();assert(subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveNew));expect(DEST,capture.stream.text);assert(capture.stream.pos==2);
 reset();put(DEST,"old");assert(subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveUpdate));total=step;
 for(unsigned failure=1;failure<=total;failure++){reset();put(DEST,"old");fail_a=failure;bool saved=subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveUpdate);if(saved)expect(DEST,capture.stream.text);else expect(DEST,"old");assert(capture.stream.pos==2&&!formats&&!records&&!handles);}
 for(unsigned cycle=0;cycle<100;cycle++){reset();put(DEST,"old");assert(subghz_save_protocol_to_file(&app,&capture,DEST,SubGhzSaveUpdate));assert(!formats&&!records&&!handles);}
 furi_string_free(app.file_path);furi_string_free(app.file_path_tmp);furi_string_free(app.error_str);
 puts("PASS: Sub-GHz short read/write/sync/close failures, staged updates, collision rejection, preserved capture/cursor, transient Repeat removal, save/rename retry and selection, deferred autosave dialog after stop/join, RAW save teardown and 100 ownership cycles");
}
"""
source = (ROOT / "applications/main/subghz/subghz_i.c").read_text()
functions = "typedef struct {Storage* storage;Stream* source;} SubGhzFileWrite;\n"
functions += "".join(
    function(source, n)
    for n in (
        "subghz_write_signal_file",
        "subghz_save_protocol_to_file",
        "subghz_save_to_file",
        "subghz_rename_file",
    )
)
functions += function(
    (ROOT / "applications/main/subghz/scenes/subghz_scene_save_name.c").read_text(),
    "subghz_scene_save_name_on_event",
)
functions += function(
    (ROOT / "applications/main/subghz/scenes/subghz_scene_save_success.c").read_text(),
    "subghz_scene_save_success_on_event",
)
functions += function(
    (ROOT / "applications/main/subghz/scenes/subghz_scene_receiver.c").read_text(),
    "subghz_scene_receiver_handle_save_error",
)
helper = re.sub(
    r"^#(?:include|pragma).*\n",
    "",
    (ROOT / "applications/main/echo/echo_file_save.h").read_text(),
    flags=re.M,
)
with tempfile.TemporaryDirectory(prefix="echo-subghz-save-") as temp:
    p = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    p.write_text(STUB + ADAPTER + SUB_ADAPTER + helper + functions + TEST)
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


MANUAL_TEST = r"""
int main(void){
 FlipperFormat capture={.stream={"Filetype: test\nRepeat: 5\nKey: 01\n",0}};SceneManager manager={0};SubGhz app={.file_path=alloc_text(SUBGHZ_APP_FOLDER),.file_path_tmp=furi_string_alloc(),.error_str=furi_string_alloc(),.txrx=&capture,.scene_manager=&manager};strcpy(app.file_name_tmp,"Manual");
 reset();fail_a=1;assert(subghz_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveName}));assert(!manager.next&&!strcmp(app.file_path->text,SUBGHZ_APP_FOLDER));fail_a=0;assert(subghz_scene_save_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,SubGhzCustomEventSceneSaveName}));expect("/ext/subghz/Manual.sub","Filetype: test\nKey: 01\n");assert(manager.next==SubGhzSceneSaveSuccess&&furi_string_empty(app.file_path_tmp)&&!strcmp(app.file_path->text,SUBGHZ_APP_FOLDER));
 furi_string_free(app.file_path);furi_string_free(app.file_path_tmp);furi_string_free(app.error_str);assert(!handles&&!records&&!formats);puts("PASS: separately compiled Add Manually save/retry branch");
}
"""
manual_functions = functions.replace(
    function(
        (
            ROOT / "applications/main/subghz/scenes/subghz_scene_save_success.c"
        ).read_text(),
        "subghz_scene_save_success_on_event",
    ),
    "",
)
with tempfile.TemporaryDirectory(prefix="echo-subghz-manual-save-") as temp:
    p = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    p.write_text(STUB + ADAPTER + SUB_ADAPTER + helper + manual_functions + MANUAL_TEST)
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-g",
            "-fsanitize=address,undefined",
            "-DSUBGHZ_ADD_MANUALLY",
            "-I",
            str(ROOT / "lib/mlib"),
            str(p),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)
