"""Validate IR file parsing and ownership with production functions under sanitizers."""

from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "lib/infrared/signal/infrared_signal.c").read_text()


def function(source, name):
    m = re.search(
        r"^(?:static )?(?:inline )?(?:void|bool|InfraredErrorCode|int32_t)\s+"
        + name
        + r"\([^;]*?\) \{",
        source,
        re.M,
    )
    assert m, name
    depth, end = 1, m.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[m.start() : end] + "\n"


ADAPTER = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#define FURI_LOG_E(...) ((void)0)
#define furi_assert assert
#define INFRARED_MIN_FREQUENCY 10000
#define INFRARED_MAX_FREQUENCY 1000000
#define MAX_TIMINGS_AMOUNT 1024
#define INFRARED_SIGNAL_FREQUENCY_KEY "frequency"
#define INFRARED_SIGNAL_DUTY_CYCLE_KEY "duty_cycle"
#define INFRARED_SIGNAL_DATA_KEY "data"
typedef struct {uint32_t protocol,address,command;} InfraredMessage;
typedef struct {size_t timings_size;uint32_t* timings;uint32_t frequency;float duty_cycle;} InfraredRawSignal;
typedef struct {bool is_raw;union {InfraredMessage message;InfraredRawSignal raw;} payload;} InfraredSignal;
static unsigned addr_bits=8,cmd_bits=8;static bool protocol_valid=true;
static bool infrared_is_protocol_valid(unsigned p) {(void)p;return protocol_valid;}
static unsigned infrared_get_protocol_address_length(unsigned p) {(void)p;return addr_bits;}
static unsigned infrared_get_protocol_command_length(unsigned p) {(void)p;return cmd_bits;}
typedef struct {uint32_t frequency,count;float duty;bool fields_ok,data_ok,zero_pulse;} FlipperFormat;
static bool flipper_format_read_uint32(FlipperFormat* f,const char* key,uint32_t* data,size_t count) {
 if(!strcmp(key,"frequency")){assert(count==1);*data=f->frequency;return f->fields_ok;}
 assert(count==f->count);if(!f->data_ok)return false;for(size_t i=0;i<count;i++)data[i]=i+1;if(f->zero_pulse)data[count/2]=0;return true;
}
static bool flipper_format_read_float(FlipperFormat* f,const char* key,float* value,size_t count) {(void)key;assert(count==1);*value=f->duty;return f->fields_ok;}
static bool flipper_format_get_value_count(FlipperFormat* f,const char* key,uint32_t* count) {(void)key;*count=f->count;return f->fields_ok;}
static struct {void* ptr;size_t bytes;} blocks[16];static size_t allocated,peak;static unsigned allocations,frees;
static void* tracked_malloc(size_t n) {void* p=malloc(n);assert(p);for(unsigned i=0;i<16;i++)if(!blocks[i].ptr){blocks[i].ptr=p;blocks[i].bytes=n;allocated+=n;if(allocated>peak)peak=allocated;allocations++;return p;}abort();}
static void tracked_free(void* p) {if(!p)return;for(unsigned i=0;i<16;i++)if(blocks[i].ptr==p){allocated-=blocks[i].bytes;blocks[i].ptr=NULL;frees++;free(p);return;}abort();}
#define malloc tracked_malloc
#define free tracked_free
"""
TEST = r"""
static void rejected(InfraredSignal* signal,FlipperFormat* f) {
 InfraredSignal before=*signal;size_t bytes=allocated;unsigned count=allocations;
 assert(INFRARED_ERROR_PRESENT(infrared_signal_read_raw(signal,f)));
 assert(!memcmp(signal,&before,sizeof(before))&&allocated==bytes);
 if(!f->data_ok||f->zero_pulse)assert(allocations==count+1);else assert(allocations==count);
}
int main(void) {
 InfraredMessage message={0,255,255};assert(infrared_signal_is_message_valid(&message));message.command=256;assert(!infrared_signal_is_message_valid(&message));
 addr_bits=cmd_bits=32;message.address=message.command=UINT32_MAX;assert(infrared_signal_is_message_valid(&message));
 addr_bits=cmd_bits=0;message.address=message.command=0;assert(infrared_signal_is_message_valid(&message));message.address=1;assert(!infrared_signal_is_message_valid(&message));protocol_valid=false;assert(!infrared_signal_is_message_valid(&message));protocol_valid=true;
 InfraredSignal signal={.payload.message={0,1,42}};FlipperFormat file={38000,0,.33,true,true,false};
 rejected(&signal,&file);file.count=MAX_TIMINGS_AMOUNT+1;rejected(&signal,&file);file.count=4;
 file.frequency=0;rejected(&signal,&file);file.frequency=INFRARED_MAX_FREQUENCY+1;rejected(&signal,&file);file.frequency=38000;
 const float invalid_duties[]={0,-1,1.01f,NAN,INFINITY,-INFINITY};for(unsigned i=0;i<sizeof(invalid_duties)/sizeof(*invalid_duties);i++){file.duty=invalid_duties[i];rejected(&signal,&file);}file.duty=.33f;
 file.fields_ok=false;rejected(&signal,&file);file.fields_ok=true;file.data_ok=false;rejected(&signal,&file);file.data_ok=true;file.zero_pulse=true;rejected(&signal,&file);file.zero_pulse=false;
 file.count=MAX_TIMINGS_AMOUNT;unsigned before=allocations;peak=0;assert(infrared_signal_read_raw(&signal,&file)==InfraredErrorCodeNone);assert(signal.is_raw&&signal.payload.raw.timings_size==MAX_TIMINGS_AMOUNT&&allocations==before+1&&peak==MAX_TIMINGS_AMOUNT*sizeof(uint32_t));
 assert(infrared_signal_is_raw_valid(&signal.payload.raw));uint32_t* old=signal.payload.raw.timings;
 file.count=0;rejected(&signal,&file);assert(signal.payload.raw.timings==old&&old[0]==1);
 // Public setters still support callers' clamping policy but never erase valid data on invalid length.
 infrared_signal_set_raw_signal(&signal,old,0,38000,.33f);assert(signal.payload.raw.timings==old);
 infrared_signal_set_raw_signal(&signal,old,MAX_TIMINGS_AMOUNT,38000,.33f);assert(signal.payload.raw.timings!=old&&signal.payload.raw.timings[1023]==1024); // aliased source remains valid while copying
 infrared_signal_set_raw_signal(&signal,signal.payload.raw.timings,4,0,NAN);assert(signal.payload.raw.frequency==INFRARED_MIN_FREQUENCY&&signal.payload.raw.duty_cycle==.33f);
 file.count=4;for(unsigned i=0;i<100;i++)assert(infrared_signal_read_raw(&signal,&file)==InfraredErrorCodeNone);
 infrared_signal_clear_timings(&signal);assert(!allocated&&allocations==frees);
 puts("PASS: IR empty/oversized/malformed RAW rejection, NaN/carrier/timing validation, preserved prior signal, 32-bit protocol masks, alias-safe setter and balanced ownership; maximum RAW read uses one 4096-byte allocation");
}
"""
errors = (ROOT / "lib/infrared/signal/infrared_error_code.h").read_text()
errors = (
    re.sub(r"^#(?:pragma|ifdef|endif|define __cplusplus).*$", "", errors, flags=re.M)
    .replace('extern "C" {', "")
    .replace("\n}\n", "\n")
)
with tempfile.TemporaryDirectory(prefix="echo-ir-file-") as d:
    p = Path(d) / "test.c"
    exe = Path(d) / "test"
    p.write_text(
        ADAPTER
        + errors
        + "".join(
            function(source, n)
            for n in (
                "infrared_signal_clear_timings",
                "infrared_signal_is_message_valid",
                "infrared_signal_is_raw_valid",
                "infrared_signal_read_raw",
                "infrared_signal_set_raw_signal",
            )
        )
        + TEST
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
