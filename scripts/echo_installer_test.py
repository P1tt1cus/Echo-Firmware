"""Validate the production Echo installer renderer and public package identity."""

from pathlib import Path
import ast
import sys
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Reuse the same bounds-checking host canvas without executing the menu tests.
tree = ast.parse((ROOT / "scripts/echo_shared_menu_test.py").read_text())
stub = next(
    ast.literal_eval(node.value)
    for node in tree.body
    if isinstance(node, ast.Assign)
    and any(getattr(target, "id", None) == "STUB" for target in node.targets)
)

EXTRA = r"""
enum {AlignLeft,AlignTop};
static void canvas_draw_circle(Canvas* c,int x,int y,int r) {canvas_draw_box(c,x-r,y-r,r*2+1,r*2+1);}
static void elements_text_box(Canvas* c,int x,int y,size_t w,size_t h,int a,int b,const char* s,bool dots) {(void)a;(void)b;(void)dots;canvas_draw_box(c,x,y,w,h);assert(strlen(s)<256);strcpy(c->texts[c->count++],s);}
"""
TEST = r"""
int main(void) {
 Canvas c={.w=128,.h=64};
 for(unsigned i=0;i<256;i++)echo_install_draw(&c,"Installing Echo 75%",i,false);
 assert(drawn(&c,"100%")&&drawn(&c,"Installing Echo")&&!drawn(&c,"Installing Echo 75%"));
 echo_install_draw(&c,"Restarting... 100%",97,false);
 assert(drawn(&c,"Restarting Echo")&&drawn(&c,"100%")&&drawn(&c,"Please wait"));
 echo_install_draw(&c,"Waiting for SD card",0,false);
 assert(drawn(&c,"0%")&&drawn(&c,"Waiting for SD card"));
 echo_install_draw(&c,"Flash compare error\n#[4-100]",75,true);
 assert(drawn(&c,"Echo update failed")&&drawn(&c,"Flash compare error\n#[4-100]")&&drawn(&c,"OK: retry")&&drawn(&c,"Hold Back: exit"));
 puts("PASS: installer pixel bounds, all progress values, completion, SD wait and diagnostic/recovery visibility");
}
"""

header = (ROOT / "applications/system/updater/views/echo_install.h").read_text()
header = re.sub(r"^#(?:include|pragma).*\n", "", header, flags=re.M)
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    source = folder / "installer.c"
    source.write_text(stub + EXTRA + header + TEST)
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
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
assert 'version = "echo-1.1"' in (ROOT / "scripts/version.py").read_text()
assert 'DIST_SUFFIX = f"echo-1.1-{commit_sha}"' in (ROOT / "fbt_options.py").read_text()
assert '"Echo 1.1"' in (ROOT / "site_scons/commandline.scons").read_text()
print("PASS: Echo 1.1 version and clean package naming")

if "--package-check" in sys.argv:
    manifests = list((ROOT / "dist/f7-C").glob("f7-update-*/update.fuf"))
    assert manifests, "Build an update package first"
    for manifest in manifests:
        assert "Info: Echo 1.1\n" in manifest.read_text(), manifest
    print("PASS: generated package displays Echo 1.1")
