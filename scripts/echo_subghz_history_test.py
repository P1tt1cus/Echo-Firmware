"""Compile actual history/deduplication code with m-array and synthetic stream/decoder adapters."""

import ast
import re
from pathlib import Path
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
#define MIN(a,b) ((a)<(b)?(a):(b))
#define FURI_LOG_E(...) ((void)0)
#define FURI_LOG_D(...) ((void)0)
#define RECORD_RPC 1
#define SUBGHZ_HISTORY_MAX 65535
#define SUBGHZ_HISTORY_FREE_HEAP (4*1024)
static void cat_text(FuriString* s,const char* t) {s->text=realloc(s->text,strlen(s->text)+strlen(t)+1);strcat(s->text,t);}
static void cat_string(FuriString* s,const FuriString* t) {cat_text(s,t->text);}
#define furi_string_cat(s,t) _Generic((t), FuriString*:cat_string, const FuriString*:cat_string, default:cat_text)(s,t)
static void furi_string_printf(FuriString* s,const char* fmt,...) {char b[1024];va_list v;va_start(v,fmt);vsnprintf(b,sizeof(b),fmt,v);va_end(v);furi_string_set_str(s,b);}
static bool furi_string_equal(const FuriString* a,const FuriString* b) {return !strcmp(a->text,b->text);}
typedef int Rpc;
typedef struct {unsigned second;} DateTime;
static unsigned now,formats,serializations;
static uint32_t furi_get_tick(void) {return now;}
static void furi_hal_rtc_get_datetime(DateTime* d) {d->second=now;}
static void* furi_record_open(int r) {(void)r;return NULL;}
static void furi_record_close(int r) {(void)r;}
static size_t memmgr_get_free_heap(void) {return 64000;}
typedef struct {uint8_t data[512];size_t size,pos;bool short_read;} Stream;
typedef Stream FlipperFormat;
enum {StreamOffsetFromStart};
static Stream* flipper_format_get_raw_stream(FlipperFormat* f) {return f;}
static FlipperFormat* flipper_format_string_alloc(void) {formats++;return calloc(1,sizeof(FlipperFormat));}
static void flipper_format_free(FlipperFormat* f) {assert(formats);formats--;free(f);}
static size_t stream_size(Stream* s) {return s->size;}
static size_t stream_tell(Stream* s) {return s->pos;}
static bool stream_seek(Stream* s,int32_t n,int offset) {(void)offset;if(n<0||(size_t)n>s->size)return false;s->pos=n;return true;}
static size_t stream_read(Stream* s,uint8_t* data,size_t n) {n=MIN(n,s->size-s->pos);if(s->short_read&&n)n--;memcpy(data,s->data+s->pos,n);s->pos+=n;return n;}
static bool flipper_format_rewind(FlipperFormat* f) {return stream_seek(f,0,0);}
static bool flipper_format_read_string(FlipperFormat* f,const char* k,FuriString* out) {(void)f;(void)k;furi_string_set_str(out,"Test");return true;}
static bool flipper_format_read_hex(FlipperFormat* f,const char* k,uint8_t* out,size_t n) {(void)f;(void)k;memset(out,0,n);return true;}
typedef struct {uint32_t frequency;FuriString* name;uint8_t* data;size_t data_size;float latitude,longitude;} SubGhzRadioPreset;
typedef struct {void(*get_string_brief)(void*,FuriString*);} Decoder;
typedef struct {uint8_t type;Decoder* decoder;} SubGhzProtocol;
typedef struct {SubGhzProtocol* protocol;uint32_t hash;char key[180];bool fail;} SubGhzProtocolDecoderBase;
enum {SubGhzProtocolStatusOk,SubGhzProtocolStatusError};
static uint32_t subghz_protocol_decoder_base_get_hash_data_long(SubGhzProtocolDecoderBase* d) {return d->hash;}
static int subghz_protocol_decoder_base_serialize(SubGhzProtocolDecoderBase* d,FlipperFormat* f,SubGhzRadioPreset* p) {
 serializations++;if(d->fail)return SubGhzProtocolStatusError;
 int size=snprintf((char*)f->data,sizeof(f->data),"%u %s %s %u",p->frequency,p->name->text,d->key,p->data_size?p->data[0]:0);
 assert(size>0&&(size_t)size<sizeof(f->data));f->size=f->pos=size;return SubGhzProtocolStatusOk;
}
static void brief(void* d,FuriString* text) {(void)d;furi_string_set_str(text,"Test capture");}
typedef struct SubGhzHistory SubGhzHistory;
static bool subghz_history_full(SubGhzHistory* h);
"""


def function(source, name):
    match = re.search(
        r"^(?:static )?(?:bool|void|SubGhzHistory\*)\s+" + name + r"\(", source, re.M
    )
    assert match, name
    start = pos = match.start()
    brace = source.index("{", pos)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


TEST = r"""
static void add(SubGhzHistory* h,SubGhzProtocolDecoderBase* d,SubGhzRadioPreset* p) {now+=1000;assert(subghz_history_add_to_history(h,d,p));}
int main(void) {
 Decoder decoder={brief};SubGhzProtocol proto={0,&decoder},other={0,&decoder};
 SubGhzProtocolDecoderBase d={.protocol=&proto,.hash=0,.key="KEY_A"};
 SubGhzRadioPreset p={.frequency=433920000,.name=alloc_text("AM650")};
 SubGhzHistory* h=subghz_history_alloc();
 assert(subghz_history_add_to_history(h,&d,&p));assert(h->last_index_write==1); // hash zero at boot
 now=1;assert(!subghz_history_add_to_history(h,&d,&p));assert(h->last_index_write==1);
 strcpy(d.key,"KEY_B");assert(subghz_history_add_to_history(h,&d,&p));assert(!subghz_history_is_same(h,0,1));
 strcpy(d.key,"KEY_A");d.protocol=&other;assert(subghz_history_add_to_history(h,&d,&p));assert(!subghz_history_is_same(h,0,2));
 d.protocol=&proto;p.frequency=315000000;assert(subghz_history_add_to_history(h,&d,&p));assert(!subghz_history_is_same(h,0,3));
 p.frequency=433920000;furi_string_set_str(p.name,"FM238");assert(subghz_history_add_to_history(h,&d,&p));assert(!subghz_history_is_same(h,0,4));
 furi_string_set_str(p.name,"AM650");now=UINT32_MAX-100;assert(subghz_history_add_to_history(h,&d,&p));
 now=100;assert(!subghz_history_add_to_history(h,&d,&p)); // tick wrap
 now=700;assert(subghz_history_add_to_history(h,&d,&p)); // exact 600ms boundary
 assert(h->last_index_write==7);
 SubGhzHistoryItem* last=SubGhzHistoryItemArray_get(h->history->data,6);last->repeats=UINT16_MAX;
 add(h,&d,&p);assert(SubGhzHistoryItemArray_get(h->history->data,7)->repeats==UINT16_MAX);
 Stream* first=SubGhzHistoryItemArray_get(h->history->data,0)->flipper_string;
 Stream* latest=SubGhzHistoryItemArray_get(h->history->data,7)->flipper_string;
 first->pos=3;latest->pos=4;assert(subghz_history_is_same(h,0,7));assert(first->pos==3&&latest->pos==4);
 latest->short_read=true;assert(!subghz_history_is_same(h,0,7));assert(first->pos==3&&latest->pos==4);latest->short_read=false;
 assert(!subghz_history_is_same(h,99,0));
 d.fail=true;unsigned count=h->last_index_write,live=formats;assert(!subghz_history_add_to_history(h,&d,&p));assert(h->last_index_write==count&&formats==live);d.fail=false;
 // Retain newest exact duplicate, and every hash/protocol/frequency/preset collision.
 subghz_history_remove_duplicates(h);assert(h->last_index_write==5);
 last=SubGhzHistoryItemArray_get(h->history->data,4);assert(last->datetime.second==now&&last->repeats==UINT16_MAX);
 subghz_history_remove_duplicates(h);assert(h->last_index_write==5);
 subghz_history_reset(h);assert(!h->last_index_write&&!formats);
 for(int i=0;i<40;i++) {memset(d.key,'A'+i%4,170);d.key[170]=0;add(h,&d,&p);}
 subghz_history_remove_duplicates(h);assert(h->last_index_write==4); // compares across 64-byte chunks
 subghz_history_reset(h);for(int i=0;i<20;i++)add(h,&d,&p);subghz_history_remove_duplicates(h);assert(h->last_index_write==1);
 subghz_history_reset(h);subghz_history_remove_duplicates(h);assert(!h->last_index_write);
 subghz_history_free(h);furi_string_free(p.name);assert(!formats);
 printf("PASS: exact Sub-GHz duplicates, collisions, frequency/preset/protocol identity, cursor restoration, failed serialization, wrap/boundary timing, saturation and repeated deletion (%u serializations)\n",serializations);
}
"""
source = (ROOT / "applications/main/subghz/subghz_history.c").read_text()
types = source[source.index("typedef struct {") : source.index("// Hashes only")]
functions = "".join(
    function(source, name)
    for name in (
        "subghz_history_data_equal",
        "subghz_history_item_matches",
        "subghz_history_is_same",
        "subghz_history_alloc",
        "subghz_history_free",
        "subghz_history_reset",
        "subghz_history_delete_item",
        "subghz_history_full",
        "subghz_history_add_to_history",
        "subghz_history_remove_duplicates",
    )
)
# Match the production public prototype to the definition.
ADAPTER = ADAPTER.replace("static bool subghz_history_full", "bool subghz_history_full")
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "history.c"
    path.write_text(STUB + ADAPTER + types + functions + TEST)
    binary = Path(folder) / "history"
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
