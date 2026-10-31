"""Exercise production NFC completeness/status rendering and Details/Back routing."""

import ast
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "applications/main/nfc/helpers/protocol_support/nfc_protocol_support.c"
tree = ast.parse((ROOT / "scripts/echo_shared_menu_test.py").read_text())
STUB = next(
    ast.literal_eval(n.value)
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets)
)
ADAPTER = r"""
#include <stdarg.h>
static void furi_string_cat(FuriString* s,const char* t) {size_t n=strlen(s->text)+strlen(t)+1;s->text=realloc(s->text,n);strcat(s->text,t);}
static void furi_string_cat_printf(FuriString* s,const char* fmt,...) {char b[512];va_list v;va_start(v,fmt);vsnprintf(b,sizeof(b),fmt,v);va_end(v);furi_string_cat(s,b);}
typedef enum {NfcProtocolMfClassic,NfcProtocolMfUltralight,NfcProtocolIso14443_3a,NfcProtocolIso14443_3b,NfcProtocolIso14443_4a,NfcProtocolIso14443_4b,NfcProtocolOther} NfcProtocol;
enum {NfcProtocolFeatureEmulateUid=1,NfcProtocolFeatureEmulateFull=2};
enum {SceneManagerEventTypeCustom,SceneManagerEventTypeBack,SceneManagerEventTypeTick};
enum {GuiButtonTypeCenter,GuiButtonTypeLeft,GuiButtonTypeRight};
typedef struct {int type,event;} SceneManagerEvent;
typedef struct {uint8_t type,sectors,keys;} MfClassicData;
typedef struct {unsigned pages_read,pages_total;bool auth_complete;} MfUltralightData;
typedef struct {NfcProtocol protocol;MfClassicData classic;MfUltralightData ul;} NfcDevice;
typedef struct {char text[2048];unsigned resets,buttons;} Widget;
typedef struct {NfcDevice* nfc_device;FuriString* file_name;bool shadow,echo_status_visible;unsigned features;Widget* widget;} NfcApp;
typedef void(*NfcProtocolSupportCommonOnEnter)(NfcApp*);
static NfcProtocol nfc_device_get_protocol(NfcDevice* d) {return d->protocol;}
static const void* nfc_device_get_data(NfcDevice* d,NfcProtocol p) {assert(d->protocol==p);return p==NfcProtocolMfClassic?(const void*)&d->classic:(const void*)&d->ul;}
static uint8_t mf_classic_get_total_sectors_num(uint8_t t) {return t;}
static void mf_classic_get_read_sectors_and_keys(const MfClassicData* d,uint8_t* s,uint8_t* k) {*s=d->sectors;*k=d->keys;}
static bool mf_classic_is_card_read(const MfClassicData* d) {return d->sectors==d->type&&d->keys==2*d->type;}
static bool mf_ultralight_is_all_data_read(const MfUltralightData* d) {return d->pages_read==d->pages_total&&d->auth_complete;}
static bool nfc_protocol_support_has_feature(NfcProtocol p,NfcApp* a,unsigned f) {assert(p==a->nfc_device->protocol);return (a->features&f)!=0;}
static bool nfc_has_shadow_file(NfcApp* a) {return a->shadow;}
static void widget_reset(Widget* w) {w->resets++;w->buttons=0;w->text[0]=0;}
static void widget_add_text_scroll_element(Widget* w,int x,int y,int width,int height,const char* text) {assert(x==0&&y==0&&width==128&&height==52);assert(strlen(text)<sizeof(w->text));strcpy(w->text,text);}
static void nfc_protocol_support_common_widget_callback(int b,int type,void* ctx) {(void)b;(void)type;(void)ctx;}
static void widget_add_button_element(Widget* w,int b,const char* text,void(*cb)(int,int,void*),void* ctx) {(void)cb;(void)ctx;assert(b==GuiButtonTypeCenter&&!strcmp(text,"Details"));w->buttons++;}
"""
TEST = r"""
static unsigned restored;
static void restore(NfcApp* a) {restored++;a->echo_status_visible=false;}
static bool contains(FuriString* t,const char* s) {return strstr(t->text,s)!=NULL;}
int main(void) {
 NfcDevice d={.protocol=NfcProtocolMfClassic,.classic={16,0,0}};Widget w={0};
 NfcApp a={.nfc_device=&d,.widget=&w,.features=NfcProtocolFeatureEmulateFull};a.file_name=alloc_text("");FuriString* t=furi_string_alloc();
 nfc_protocol_support_render_status(&a,t);assert(contains(t,"Data: partial")&&contains(t,"Sectors: 0/16")&&contains(t,"Some keys missing.")&&contains(t,"Not saved yet."));
 d.classic.sectors=16;d.classic.keys=31;nfc_protocol_support_render_status(&a,t);assert(contains(t,"Data: partial"));
 d.classic.keys=32;nfc_protocol_support_render_status(&a,t);assert(contains(t,"Data: complete")&&!contains(t,"Some keys missing"));
 d.protocol=NfcProtocolMfUltralight;d.ul=(MfUltralightData){4,45,false};nfc_protocol_support_render_status(&a,t);assert(contains(t,"Pages: 4/45")&&contains(t,"Data: partial"));
 d.ul.pages_read=45;nfc_protocol_support_render_status(&a,t);assert(contains(t,"auth\ndata still incomplete")&&!contains(t,"Supported data read."));
 d.ul.auth_complete=true;nfc_protocol_support_render_status(&a,t);assert(contains(t,"Supported data read."));
 for(int p=NfcProtocolIso14443_3a;p<=NfcProtocolIso14443_4b;p++) {d.protocol=p;a.features=NfcProtocolFeatureEmulateUid;nfc_protocol_support_render_status(&a,t);assert(contains(t,"Card identified.")&&contains(t,"UID only")&&!contains(t,"Data: complete"));}
 d.protocol=NfcProtocolOther;a.features=0;furi_string_set_str(a.file_name,"test");nfc_protocol_support_render_status(&a,t);assert(contains(t,"See Info for coverage.")&&contains(t,"Emulation unavailable")&&contains(t,"Saved capture."));
 a.shadow=true;nfc_protocol_support_render_status(&a,t);assert(contains(t,"Modified copy (.shd).")&&contains(t,"not verified here"));
 SceneManagerEvent center={SceneManagerEventTypeCustom,GuiButtonTypeCenter},left={SceneManagerEventTypeCustom,GuiButtonTypeLeft},back={SceneManagerEventTypeBack,0},tick={SceneManagerEventTypeTick,0};
 assert(!nfc_protocol_support_status_event(&a,left,restore));
 for(int i=0;i<100;i++) {assert(nfc_protocol_support_status_event(&a,center,restore));assert(a.echo_status_visible&&w.buttons==1);assert(nfc_protocol_support_status_event(&a,left,restore));assert(!nfc_protocol_support_status_event(&a,tick,restore));assert(nfc_protocol_support_status_event(&a,i%2?center:back,restore));assert(!a.echo_status_visible);}
 assert(restored==100);furi_string_free(t);furi_string_free(a.file_name);
 puts("PASS: NFC partial/full/UID/auth-incomplete status, capabilities, saved/shadow distinction and 100 Status/Details/Back cycles");
}
"""
source = SOURCE.read_text()
start = source.index("static void nfc_protocol_support_render_status(")
end = source.index("// Common scene handlers", start)
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "nfc_status.c"
    path.write_text(STUB + ADAPTER + source[start:end] + TEST)
    binary = Path(folder) / "nfc_status"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-function",
            "-Wno-unused-variable",
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
