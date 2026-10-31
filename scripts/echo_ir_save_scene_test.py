"""Exercise production IR save/rename retry UI and joined-worker recovery reporting."""

from pathlib import Path
import re
import subprocess
import tempfile
import echo_ir_save_test as base

ROOT = base.ROOT


def function(source, name):
    match = re.search(
        r"^(?:static )?(?:bool|void|InfraredErrorCode)\s+" + name + r"\([^;]*?\) \{",
        source,
        re.M,
    )
    assert match, name
    end, depth = match.end(), 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start() : end] + "\n"


ADAPTER = r"""
#define INFRARED_DEFAULT_REMOTE_NAME "Remote"
#define INFRARED_APP_FOLDER "/ext/infrared"
#define INFRARED_APP_EXTENSION ".ir"
typedef struct {int current_button_index,edit_target;bool is_learning_new_remote;} InfraredAppState;
typedef struct {unsigned next;} SceneManager;
typedef struct {InfraredRemote* remote;FuriString* file_path;InfraredSignal* current_signal;InfraredAppState app_state;char text_store[1][64];SceneManager* scene_manager;void* view_dispatcher;void* task_thread;} InfraredApp;
typedef struct {unsigned type,event;} SceneManagerEvent;
enum {SceneManagerEventTypeCustom,InfraredCustomEventTypeTextEditDone,InfraredCustomEventTypeTaskFinished,InfraredEditTargetButton,InfraredEditTargetRemote,InfraredSceneEditRenameDone,InfraredSceneLearnDone,InfraredViewTextInput,DolphinDeedIrSave};
#define InfraredButtonIndexNone -1
static unsigned current_view,started,joined,notified,deeds;
static InfraredErrorCode task_error;
static void infrared_show_save_recovery(const InfraredApp*);
static void infrared_find_vacant_remote_name(FuriString* name,const char* path){assert(!strcmp(name->text,"Remote")&&!strcmp(path,"/ext/infrared"));}
static void path_append(FuriString* path,const char* name){furi_string_cat_printf(path,"/%s",name);}
static void furi_string_cat(FuriString* path,const char* suffix){furi_string_cat_printf(path,"%s",suffix);}
static void scene_manager_next_scene(SceneManager* s,unsigned scene){s->next=scene;}
static void view_dispatcher_switch_to_view(void* v,unsigned view){(void)v;current_view=view;}
static void infrared_show_error_message(const InfraredApp* app,const char* fmt,...){(void)app;notified++;va_list a;va_start(a,fmt);vsnprintf(message,sizeof(message),fmt,a);va_end(a);}
static void furi_thread_join(void* thread){(void)thread;joined++;}
static InfraredErrorCode furi_thread_get_return_code(void* thread){(void)thread;assert(joined);return task_error;}
static int32_t infrared_scene_edit_rename_task_callback(void* ctx){(void)ctx;return 0;}
static void infrared_blocking_task_start(InfraredApp* app,int32_t(*callback)(void*)){(void)app;assert(callback==infrared_scene_edit_rename_task_callback);started++;}
static void dolphin_deed(unsigned deed){assert(deed==DolphinDeedIrSave);deeds++;}
"""
TEST = r"""
int main(void){
 reset();InfraredRemote* remote=infrared_remote_alloc();InfraredSignal signal={42};SceneManager manager={0};InfraredApp app={.remote=remote,.file_path=furi_string_alloc_set("/ext/infrared/Old.ir"),.current_signal=&signal,.scene_manager=&manager};
 put("/ext/infrared/Old.ir","IR1\nA=10\n");infrared_remote_set_path(remote,"/ext/infrared/Old.ir");StringArray_push_back(remote->signal_names,"A");
 assert(infrared_rename_current_remote(&app,"Old")==InfraredErrorCodeNone);
 put("/ext/infrared/Taken.ir","existing");assert(INFRARED_ERROR_PRESENT(infrared_rename_current_remote(&app,"Taken")));assert(!strcmp(app.file_path->text,"/ext/infrared/Old.ir"));
 assert(infrared_rename_current_remote(&app,"New")==InfraredErrorCodeNone);assert(!strcmp(app.file_path->text,"/ext/infrared/New.ir"));expect("/ext/infrared/New.ir","IR1\nA=10\n");
 app.app_state.edit_target=InfraredEditTargetButton;app.app_state.current_button_index=0;strcpy(app.text_store[0],"Edited");
 assert(infrared_scene_edit_rename_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,InfraredCustomEventTypeTextEditDone}));assert(started==1);
 task_error=InfraredErrorCodeFileOperationFailed;
 assert(infrared_scene_edit_rename_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,InfraredCustomEventTypeTaskFinished}));assert(current_view==InfraredViewTextInput&&!manager.next&&app.app_state.current_button_index==0&&!strcmp(app.text_store[0],"Edited"));
 task_error=InfraredErrorCodeNone;furi_string_set_str(remote->recovery_path,"/ext/infrared/New.ir.echo-old-2");unsigned before=notified;
 assert(infrared_scene_edit_rename_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,InfraredCustomEventTypeTaskFinished}));assert(joined==2&&notified==before+1&&strstr(message,".echo-old-2")&&!(*remote->recovery_path->text));assert(manager.next==InfraredSceneEditRenameDone&&app.app_state.current_button_index==InfraredButtonIndexNone);
 infrared_show_save_recovery(&app);assert(notified==before+1);
 // Learned data and edited name survive a failed append and can be retried.
 manager.next=0;app.app_state.is_learning_new_remote=false;strcpy(app.text_store[0],"Learned");fail_a=step+1;
 assert(infrared_scene_learn_enter_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,InfraredCustomEventTypeTextEditDone}));assert(!manager.next&&!deeds&&current_view==InfraredViewTextInput&&!strcmp(app.text_store[0],"Learned")&&signal.value==42);expect("/ext/infrared/New.ir","IR1\nA=10\n");
 fail_a=0;assert(infrared_scene_learn_enter_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,InfraredCustomEventTypeTextEditDone}));assert(manager.next==InfraredSceneLearnDone&&deeds==1);expect("/ext/infrared/New.ir","IR1\nA=10\nLearned=42\n");
 manager.next=0;app.app_state.is_learning_new_remote=true;fail_a=step+1;
 assert(infrared_scene_learn_enter_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,InfraredCustomEventTypeTextEditDone}));assert(!manager.next&&deeds==1&&find("/ext/infrared/Remote.ir")<0);
 fail_a=0;assert(infrared_scene_learn_enter_name_on_event(&app,(SceneManagerEvent){SceneManagerEventTypeCustom,InfraredCustomEventTypeTextEditDone}));expect("/ext/infrared/Remote.ir","IR1\nLearned=42\n");assert(!strcmp(app.file_path->text,"/ext/infrared/Remote.ir"));assert(manager.next==InfraredSceneLearnDone&&deeds==2);
 infrared_remote_free(remote);furi_string_free(app.file_path);assert(!records&&!formats&&!handles&&!signals);
 puts("PASS: IR rename browser selection, collision/unchanged name, worker join/recovery notice, rename retry index/name and learned signal retry");
}
"""
with tempfile.TemporaryDirectory(prefix="echo-ir-save-scene-") as tmp:
    path = Path(tmp)
    source = (ROOT / "applications/main/infrared/infrared_remote.c").read_text()
    source = re.sub(r"^#include .*\n", "", source, flags=re.M)
    helper = (ROOT / "applications/main/echo/echo_file_save.h").read_text()
    helper = re.sub(r"^#(?:include|pragma).*\n", "", helper, flags=re.M)
    app = (ROOT / "applications/main/infrared/infrared_app.c").read_text()
    extracted = "".join(
        function(app, n)
        for n in [
            "infrared_add_remote_with_button",
            "infrared_rename_current_remote",
            "infrared_show_save_recovery",
            "infrared_blocking_task_finalize",
        ]
    )
    for name in ["edit_rename", "learn_enter_name"]:
        extracted += function(
            (
                ROOT / f"applications/main/infrared/scenes/infrared_scene_{name}.c"
            ).read_text(),
            f"infrared_scene_{name}_on_event",
        )
    (path / "test.c").write_text(
        base.STUB
        + base.ADAPTER
        + base.IR
        + helper
        + source
        + ADAPTER
        + extracted
        + TEST
    )
    subprocess.run(
        [
            "cc",
            "-std=gnu11",
            "-g",
            "-O1",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
            "-Wno-unused-function",
            "-I" + str(ROOT / "lib/mlib"),
            "-I" + str(ROOT / "lib"),
            str(path / "test.c"),
            "-o",
            str(path / "test"),
        ],
        check=True,
    )
    subprocess.run([str(path / "test")], check=True)
