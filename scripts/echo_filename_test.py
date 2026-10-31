"""Exercise the production shared filename validator and its ownership."""

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
ADAPTER = r"""
#include <stdarg.h>
#define RECORD_STORAGE "storage"
typedef int Storage;
typedef enum {FSE_OK,FSE_EXIST,FSE_NOT_EXIST,FSE_NOT_READY,FSE_INVALID_PARAMETER,FSE_DENIED,FSE_INTERNAL} FS_Error;
typedef struct ValidatorIsFile ValidatorIsFile;
static FS_Error status=FSE_NOT_EXIST;static unsigned opens,closes,stats;static char checked[512];
static void* furi_record_open(const char* record) {(void)record;opens++;return NULL;}
static void furi_record_close(const char* record) {(void)record;closes++;}
static FS_Error storage_common_stat(Storage* s,const char* path,void* info) {(void)s;(void)info;stats++;strcpy(checked,path);return status;}
static FuriString* furi_string_alloc_printf(const char* fmt,...) {char b[512];va_list args;va_start(args,fmt);vsnprintf(b,sizeof(b),fmt,args);va_end(args);return alloc_text(b);}
static char* echo_strdup(const char* s) {char* p=malloc(strlen(s)+1);strcpy(p,s);return p;}
#define strdup echo_strdup
"""
TEST = r"""
int main(void) {
 FuriString* error=furi_string_alloc();
 for(unsigned cycle=0;cycle<100;cycle++) {
  ValidatorIsFile* v=validator_is_file_alloc_init("/ext/infrared",".ir",NULL);assert(!v->current_name);
  const char* invalid[]={"",".","..","../escape","nested/name","nested\\name","bad:name","a*b","a?b","a\"b","a<b","a>b","a|b","tab\tname","new\nline","del\177","trailing.","trailing "};
  unsigned before=stats;for(unsigned i=0;i<COUNT_OF(invalid);i++)assert(!validator_is_file_callback(invalid[i],error,v));assert(stats==before);
  status=FSE_NOT_EXIST;assert(validator_is_file_callback("Echo room 1",error,v));assert(!strcmp(checked,"/ext/infrared/Echo room 1.ir"));
  assert(validator_is_file_callback("Télécommande",error,v));
  const FS_Error failures[]={FSE_OK,FSE_EXIST,FSE_NOT_READY,FSE_INVALID_PARAMETER,FSE_DENIED,FSE_INTERNAL};
  for(unsigned i=0;i<COUNT_OF(failures);i++){status=failures[i];assert(!validator_is_file_callback("Echo",error,v));}
  assert(strstr(error->text,"Cannot check name"));validator_is_file_free(v);
  v=validator_is_file_alloc_init("/ext/nfc",".nfc","Existing");before=stats;assert(validator_is_file_callback("Existing",error,v)&&stats==before);assert(!validator_is_file_callback("..",error,v));validator_is_file_free(v);
 }
 assert(opens==closes);furi_string_free(error);puts("PASS: shared filename validation rejects empty/traversal/FAT-invalid/control/trailing characters, allows ordinary UTF-8 names, distinguishes collisions from SD errors and frees optional current-name ownership");
}
"""
source = re.sub(
    r"^#include.*$",
    "",
    (ROOT / "applications/services/gui/modules/validators.c").read_text(),
    flags=re.M,
)
with tempfile.TemporaryDirectory(prefix="echo-filename-") as d:
    p = Path(d) / "test.c"
    exe = Path(d) / "test"
    p.write_text(STUB + ADAPTER + source + TEST)
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
