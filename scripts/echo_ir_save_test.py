"""Fault-inject actual IR remote saves and edits with the real name container.

Storage/format adapters model normal API failures, not physical SD power loss.
"""

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
STUB = STUB[: STUB.index("typedef enum {InputKey")]
# FuriString supports aliases; keep the adapter's ownership semantics equivalent.
STUB = STUB.replace(
    "free(s->text);s->text=malloc(strlen(text)+1);strcpy(s->text,text);",
    "char* next=strdup(text);free(s->text);s->text=next;",
)
ADAPTER = literal(ROOT / "scripts/echo_file_save_test.py", "ADAPTER")
ADAPTER = ADAPTER[: ADAPTER.index("typedef struct {uint8_t data[4];} ProtocolDict;")]
ADAPTER = ADAPTER.replace("data[64]", "data[4096]")
ADAPTER = ADAPTER.replace(
    "static Entry files[100];",
    "static Entry files[100];static unsigned format_opens[100];",
)
ADAPTER = ADAPTER.replace(
    "if(i<0)return FSE_NOT_EXIST;files[i].path[0]=0;",
    "if(i<0)return FSE_NOT_EXIST;if(format_opens[i])return FSE_DENIED;files[i].path[0]=0;",
)
ADAPTER = ADAPTER.replace(
    "if(i<0)return FSE_NOT_EXIST;if(find(to)>=0)",
    "if(i<0)return FSE_NOT_EXIST;if(format_opens[i])return FSE_DENIED;if(find(to)>=0)",
)
ADAPTER = ADAPTER.replace(
    "static bool furi_string_equal(FuriString* a,FuriString* b){return !strcmp(a->text,b->text);}",
    "static bool furi_string_equal(FuriString* a,const char* b){return !strcmp(a->text,b);}",
)
IR = r"""
#include <toolbox/m_cstr_dup.h>
#include <infrared/signal/infrared_error_code.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define FURI_LOG_E(...) ((void)0)
#define FURI_LOG_I(...) ((void)0)
#define RECORD_STORAGE 1
static unsigned records,formats,signals;
static Storage* furi_record_open(int r){assert(r==RECORD_STORAGE);records++;static Storage s;return &s;}
static void furi_record_close(int r){assert(r==RECORD_STORAGE);records--;}
static void path_extract_filename(FuriString* path,FuriString* name,bool strip){const char* p=strrchr(path->text,'/');char b[512];strcpy(b,p?p+1:path->text);if(strip){char* dot=strrchr(b,'.');if(dot)*dot=0;}furi_string_set_str(name,b);}
typedef struct {unsigned value;} InfraredSignal;
static InfraredSignal* infrared_signal_alloc(void){signals++;return calloc(1,sizeof(InfraredSignal));}
static void infrared_signal_free(InfraredSignal* s){signals--;free(s);}
typedef struct {int index;size_t pos;bool open;} FlipperFormat;
static FlipperFormat* flipper_format_buffered_file_alloc(Storage* s){(void)s;formats++;return calloc(1,sizeof(FlipperFormat));}
static bool flipper_format_buffered_file_open_existing(FlipperFormat* f,const char* p){assert(!f->open);if(fault())return false;int i=find(p);if(i<0||files[i].directory)return false;f->index=i;f->pos=0;f->open=true;format_opens[i]++;return true;}
static bool flipper_format_buffered_file_close(FlipperFormat* f){if(fault())return false;if(f->open)format_opens[f->index]--;f->open=false;return true;}
static void flipper_format_free(FlipperFormat* f){assert(!f->open);formats--;free(f);}
static bool flipper_format_write_header_cstr(FlipperFormat* f,const char* header,unsigned version){assert(f->open&&!strcmp(header,"IR signals file")&&version==1);if(fault())return false;strcpy(files[f->index].data,"IR1\n");f->pos=4;return true;}
static bool flipper_format_read_header(FlipperFormat* f,FuriString* header,uint32_t* version){assert(f->open);if(fault()||strncmp(files[f->index].data,"IR1\n",4))return false;furi_string_set_str(header,"IR signals file");*version=1;f->pos=4;return true;}
static InfraredErrorCode infrared_signal_save(const InfraredSignal* s,FlipperFormat* f,const char* name){assert(f->open);if(fault()){strcat(files[f->index].data,"partial");return InfraredErrorCodeSignalMessageUnableToWriteCommand;}char b[100];snprintf(b,sizeof(b),"%s=%u\n",name,s->value);assert(strlen(files[f->index].data)+strlen(b)<sizeof(files[0].data));strcat(files[f->index].data,b);return InfraredErrorCodeNone;}
static InfraredErrorCode infrared_signal_read(InfraredSignal* s,FlipperFormat* f,FuriString* name){assert(f->open);if(fault())return InfraredErrorCodeSignalMessageUnableToReadCommand;const char* p=files[f->index].data+f->pos;const char* end=strchr(p,'\n');if(!end)return InfraredErrorCodeSignalNameNotFound;char b[100];assert((size_t)(end-p)<sizeof(b));memcpy(b,p,end-p);b[end-p]=0;char* eq=strchr(b,'=');if(!eq)return InfraredErrorCodeSignalMessageIsInvalid;*eq++=0;s->value=(unsigned)strtoul(eq,NULL,10);furi_string_set_str(name,b);f->pos=end-files[f->index].data+1;return InfraredErrorCodeNone;}
static InfraredErrorCode infrared_signal_read_name(FlipperFormat* f,FuriString* name){InfraredSignal s;return infrared_signal_read(&s,f,name);}
static InfraredErrorCode infrared_signal_search_by_index_and_read(InfraredSignal* s,FlipperFormat* f,size_t index){FuriString* name=furi_string_alloc();uint32_t version;InfraredErrorCode error=InfraredErrorCodeFileOperationFailed;if(flipper_format_read_header(f,name,&version)){for(size_t i=0;i<=index;i++){error=infrared_signal_read(s,f,name);if(INFRARED_ERROR_PRESENT(error))break;}}furi_string_free(name);return error;}
typedef struct InfraredRemote InfraredRemote;
static const char* infrared_remote_get_signal_name(const InfraredRemote*,size_t);
static size_t infrared_remote_get_signal_count(const InfraredRemote*);
static InfraredErrorCode infrared_remote_insert_signal(InfraredRemote*,const InfraredSignal*,const char*,size_t);
"""
# Read-only production frees close their format implicitly. Match that contract;
# write callbacks explicitly close and their return value is independently faulted.
IR = IR.replace(
    "assert(!f->open);formats--;free(f);",
    "if(f->open)format_opens[f->index]--;f->open=false;formats--;free(f);",
)
TEST = r"""
#define PATH "/ext/infrared/Test.ir"
#define ORIGINAL "IR1\nA=10\nB=20\nC=30\n"
static InfraredRemote* seed(void){reset();put(PATH,ORIGINAL);InfraredRemote* r=infrared_remote_alloc();infrared_remote_set_path(r,PATH);StringArray_push_back(r->signal_names,"A");StringArray_push_back(r->signal_names,"B");StringArray_push_back(r->signal_names,"C");return r;}
static void names(InfraredRemote* r,const char* expected){char b[256]="";for(size_t i=0;i<infrared_remote_get_signal_count(r);i++)strcat(b,infrared_remote_get_signal_name(r,i));assert(!strcmp(b,expected));}
static void balanced(InfraredRemote* r){infrared_remote_free(r);assert(!handles&&!records&&!formats&&!signals);for(unsigned i=0;i<100;i++)assert(!format_opens[i]);}
static InfraredErrorCode change(InfraredRemote* r,unsigned op){InfraredSignal s={40};switch(op){case 0:return infrared_remote_rename_signal(r,1,"D");case 1:return infrared_remote_delete_signal(r,1);case 2:return infrared_remote_append_signal(r,&s,"D");case 3:return infrared_remote_insert_signal(r,&s,"D",1);case 4:return infrared_remote_move_signal(r,0,2);default:return infrared_remote_move_signal(r,2,0);}}
static const char* new_text[]={"IR1\nA=10\nD=20\nC=30\n","IR1\nA=10\nC=30\n","IR1\nA=10\nB=20\nC=30\nD=40\n","IR1\nA=10\nD=40\nB=20\nC=30\n","IR1\nB=20\nC=30\nA=10\n","IR1\nC=30\nA=10\nB=20\n"};
static const char* new_names[]={"ADC","AC","ABCD","ADBC","BCA","CAB"};
int main(void){
 for(unsigned op=0;op<6;op++){
  InfraredRemote* r=seed();assert(!INFRARED_ERROR_PRESENT(change(r,op)));unsigned steps=step;expect(PATH,new_text[op]);names(r,new_names[op]);balanced(r);
  for(unsigned fail=1;fail<=steps;fail++){
   r=seed();fail_a=fail;InfraredErrorCode e=change(r,op);
   if(INFRARED_ERROR_PRESENT(e)){expect(PATH,ORIGINAL);names(r,"ABC");fail_a=0;assert(!INFRARED_ERROR_PRESENT(change(r,op)));expect(PATH,new_text[op]);names(r,new_names[op]);}
   else{expect(PATH,new_text[op]);names(r,new_names[op]);}
   balanced(r);
  }
 }
 // Every move permutation commits the expected order in one replacement.
 for(size_t from=0;from<3;from++)for(size_t to=0;to<3;to++){
  InfraredRemote* r=seed();assert(!INFRARED_ERROR_PRESENT(infrared_remote_move_signal(r,from,to)));
  char expected[4]="ABC";char c=expected[from];memmove(expected+from,expected+from+1,2-from);memmove(expected+to+1,expected+to,2-to);expected[to]=c;expected[3]=0;names(r,expected);
  InfraredRemote* read=infrared_remote_alloc();assert(!INFRARED_ERROR_PRESENT(infrared_remote_load(read,PATH)));names(read,expected);balanced(read);balanced(r);
 }
 // Commit failure followed by rollback failure retains the exact original.
 bool recovery_seen=false;
 for(unsigned a=1;a<45;a++)for(unsigned b=a+1;b<45;b++){
  InfraredRemote* r=seed();fail_a=a;fail_b=b;InfraredErrorCode e=change(r,0);
  if(INFRARED_ERROR_PRESENT(e)&&find(PATH)<0){assert(*r->recovery_path->text);expect(r->recovery_path->text,ORIGINAL);names(r,"ABC");FuriString* recovered=furi_string_alloc();infrared_remote_take_recovery_path(r,recovered);assert(*recovered->text&&!(*r->recovery_path->text));furi_string_free(recovered);recovery_seen=true;}
  balanced(r);
 }assert(recovery_seen);
 // Create plus first signal is one transaction and never erases prior data/state.
 InfraredSignal signal={42};unsigned create_steps;
 {InfraredRemote* r=seed();assert(!INFRARED_ERROR_PRESENT(infrared_remote_create_with_signal(r,"/ext/infrared/New.ir",&signal,"D")));create_steps=step;expect("/ext/infrared/New.ir","IR1\nD=42\n");names(r,"D");balanced(r);}
 for(unsigned fail=1;fail<=create_steps;fail++){
  InfraredRemote* r=seed();fail_a=fail;InfraredErrorCode e=infrared_remote_create_with_signal(r,"/ext/infrared/New.ir",&signal,"D");
  assert(INFRARED_ERROR_PRESENT(e));assert(find("/ext/infrared/New.ir")<0);expect(PATH,ORIGINAL);names(r,"ABC");assert(!strcmp(infrared_remote_get_path(r),PATH));balanced(r);
 }
 {InfraredRemote* r=seed();assert(INFRARED_ERROR_PRESENT(infrared_remote_create_with_signal(r,PATH,&signal,"D")));expect(PATH,ORIGINAL);names(r,"ABC");balanced(r);}
 // Empty remote, append and insert beyond the end.
 {InfraredRemote* r=seed();assert(!INFRARED_ERROR_PRESENT(infrared_remote_create(r,"/ext/infrared/Empty.ir")));names(r,"");expect("/ext/infrared/Empty.ir","IR1\n");assert(!INFRARED_ERROR_PRESENT(infrared_remote_insert_signal(r,&signal,"D",100)));names(r,"D");expect("/ext/infrared/Empty.ir","IR1\nD=42\n");balanced(r);}
 // Rename preserves exact bytes, rejects collisions and doesn't claim missing same-name success.
 {InfraredRemote* r=seed();put("/ext/infrared/Taken.ir","other");assert(INFRARED_ERROR_PRESENT(infrared_remote_rename(r,"/ext/infrared/Taken.ir")));expect(PATH,ORIGINAL);expect("/ext/infrared/Taken.ir","other");assert(!INFRARED_ERROR_PRESENT(infrared_remote_rename(r,PATH)));assert(!INFRARED_ERROR_PRESENT(infrared_remote_rename(r,"/ext/infrared/New.ir")));expect("/ext/infrared/New.ir",ORIGINAL);assert(find(PATH)<0);storage_common_remove(NULL,"/ext/infrared/New.ir");assert(INFRARED_ERROR_PRESENT(infrared_remote_rename(r,"/ext/infrared/New.ir")));balanced(r);}
 // Corrupt source cannot replace the original with a partial valid-looking file.
 {InfraredRemote* r=seed();strcpy(files[find(PATH)].data,"bad-header\nA=10\n");assert(INFRARED_ERROR_PRESENT(change(r,0)));expect(PATH,"bad-header\nA=10\n");names(r,"ABC");balanced(r);}
 for(unsigned i=0;i<100;i++){InfraredRemote* r=seed();assert(!INFRARED_ERROR_PRESENT(change(r,i%6)));balanced(r);}
 puts("PASS: IR staged create/append/insert/rename/delete/move; fault steps and retry preserve files/names, every move order, failed rollback recovery, collisions, checked close and 100 ownership cycles");
}
"""


def main():
    source = (ROOT / "applications/main/infrared/infrared_remote.c").read_text()
    source = re.sub(r"^#include .*\n", "", source, flags=re.M)
    helper = (ROOT / "applications/main/echo/echo_file_save.h").read_text()
    helper = re.sub(r"^#(?:include|pragma).*\n", "", helper, flags=re.M)
    with tempfile.TemporaryDirectory(prefix="echo-ir-save-") as tmp:
        path = Path(tmp)
        (path / "test.c").write_text(STUB + ADAPTER + IR + helper + source + TEST)
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


if __name__ == "__main__":
    main()
