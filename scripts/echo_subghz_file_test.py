"""Run the production RAW file worker with memory-backed storage and scheduling adapters.

No radio is used. Sanitizers cover parser/queue ownership, failure, EOF and restart;
thread races and physical DMA timing still require hardware validation.
"""

from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <ctype.h>
#define furi_assert assert
#define furi_check assert
#define MIN(a,b) ((a)<(b)?(a):(b))
#define FURI_LOG_I(...) ((void)0)
#define FURI_LOG_E(...) ((void)0)
#define RECORD_STORAGE 1
#include "lib/toolbox/level_duration.h"
typedef struct SubGhzFileEncoderWorker SubGhzFileEncoderWorker;
typedef void (*SubGhzFileEncoderWorkerCallbackEnd)(void*);
typedef struct {char* text;size_t len,capacity;} FuriString;
static FuriString* furi_string_alloc(void){FuriString* s=calloc(1,sizeof(*s));s->capacity=32;s->text=calloc(s->capacity,1);return s;}
static void furi_string_free(FuriString* s){free(s->text);free(s);}
static void furi_string_set(FuriString* s,const char* text){size_t n=strlen(text);if(n>=s->capacity){s->capacity=n+1;s->text=realloc(s->text,s->capacity);}memmove(s->text,text,n+1);s->len=n;}
static void furi_string_reset(FuriString* s){s->len=0;s->text[0]=0;}
static bool furi_string_empty(FuriString* s){return !s->len;}
static size_t furi_string_size(FuriString* s){return s->len;}
static char furi_string_get_char(FuriString* s,size_t i){assert(i<s->len);return s->text[i];}
static const char* furi_string_get_cstr(FuriString* s){return s->text;}
static void furi_string_push_back(FuriString* s,char c){if(s->len+1>=s->capacity){s->capacity*=2;s->text=realloc(s->text,s->capacity);}s->text[s->len++]=c;s->text[s->len]=0;}
static void furi_string_trim(FuriString* s){size_t start=0;while(start<s->len&&isspace((unsigned char)s->text[start]))start++;while(s->len>start&&isspace((unsigned char)s->text[s->len-1]))s->len--;s->len-=start;memmove(s->text,s->text+start,s->len);s->text[s->len]=0;}
static void furi_string_printf(FuriString* s,const char* fmt,...){char b[64];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);furi_string_set(s,b);}
typedef struct {const char* text;size_t size,pos,fail_at;bool opened;} Stream;
typedef Stream FlipperFormat;
typedef int Storage;
static const char* fixture;static size_t fixture_size,fail_at=SIZE_MAX;static bool open_ok=true;static unsigned opens,closes,threads,joins;
static Storage* furi_record_open(int x){(void)x;static Storage s;return &s;}
static void furi_record_close(int x){(void)x;}
static FlipperFormat* flipper_format_buffered_file_alloc(Storage* s){(void)s;return calloc(1,sizeof(Stream));}
static bool flipper_format_buffered_file_open_existing(FlipperFormat* f,const char* path){(void)path;assert(!f->opened);if(!open_ok)return false;*f=(Stream){fixture,fixture_size,0,fail_at,true};opens++;return true;}
static void flipper_format_buffered_file_close(FlipperFormat* f){assert(f->opened);f->opened=false;closes++;}
static void flipper_format_free(FlipperFormat* f){assert(!f->opened);free(f);}
static Stream* flipper_format_get_raw_stream(FlipperFormat* f){return f;}
static size_t stream_read(Stream* s,uint8_t* b,size_t n){assert(n==1&&s->opened);if(s->pos>=s->size||s->pos>=s->fail_at)return 0;*b=s->text[s->pos++];return 1;}
static size_t stream_tell(Stream* s){return s->pos;}
static size_t stream_size(Stream* s){return s->size;}
typedef struct {int32_t data[2048];size_t head,count;} FuriStreamBuffer;
static void (*send_hook)(void),(*delay_hook)(void),(*empty_receive_hook)(void);
static FuriStreamBuffer* furi_stream_buffer_alloc(size_t n,size_t trigger){assert(n==8192&&trigger==4);return calloc(1,sizeof(FuriStreamBuffer));}
static void furi_stream_buffer_free(FuriStreamBuffer* s){free(s);}
static void furi_stream_buffer_reset(FuriStreamBuffer* s){s->head=s->count=0;}
static size_t furi_stream_buffer_spaces_available(FuriStreamBuffer* s){return (2048-s->count)*4;}
static size_t furi_stream_buffer_send(FuriStreamBuffer* s,const void* v,size_t n,unsigned timeout){assert(n==4&&timeout==10);if(send_hook){send_hook();return 0;}if(s->count==2048)return 0;s->data[(s->head+s->count++)%2048]=*(int32_t*)v;return 4;}
static size_t furi_stream_buffer_receive(FuriStreamBuffer* s,void* v,size_t n,unsigned timeout){assert(n==4&&!timeout);if(!s->count){if(empty_receive_hook)empty_receive_hook();return 0;}*(int32_t*)v=s->data[s->head++%2048];s->count--;return 4;}
typedef struct {int32_t (*run)(void*);void* ctx;} FuriThread;
static FuriThread* furi_thread_alloc_ex(const char* name,size_t stack,int32_t (*fn)(void*),void* ctx){(void)name;assert(stack==2048);FuriThread* t=malloc(sizeof(*t));*t=(FuriThread){fn,ctx};return t;}
static void furi_thread_start(FuriThread* t){(void)t;threads++;}
static void furi_thread_join(FuriThread* t){(void)t;joins++;}
static void furi_thread_free(FuriThread* t){free(t);}
static void furi_delay_ms(unsigned ms){(void)ms;assert(delay_hook);delay_hook();}
typedef int SubGhzDevice;
static const SubGhzDevice* subghz_devices_get_by_name(const char* name){assert(*name);static SubGhzDevice dev;return &dev;}
static bool subghz_devices_is_async_complete_tx(const SubGhzDevice* dev){assert(dev);return true;}
"""
CLIENT_ADAPTER = r"""
#define FURI_LOG_W(...) ((void)0)
#define SAMPLES_TO_READ_PER_TICK 400
static bool furi_string_equal(FuriString* s,const char* t){return !strcmp(s->text,t);}
typedef struct {bool is_running;FuriString* file_name;FuriString* radio_device_name;SubGhzFileEncoderWorker* file_worker_encoder;} SubGhzProtocolEncoderRAW;
typedef int SubGhzReceiver;
typedef struct {SubGhzFileEncoderWorker* decode_raw_file_worker_encoder;void* txrx;void* scene_manager;void* subghz_receiver;int state_notifications;} SubGhz;
enum {SubGhzSceneDecodeRAW,SubGhzDecodeRawStateLoaded,SubGhzNotificationStateIDLE};
static bool metadata_ok=true;static char last_progress[64];static unsigned decoded;
static FlipperFormat* subghz_txrx_get_fff_data(void* txrx){(void)txrx;return NULL;}
static bool flipper_format_rewind(FlipperFormat* f){(void)f;return metadata_ok;}
static bool flipper_format_read_string(FlipperFormat* f,const char* key,FuriString* value){(void)f;assert(!strcmp(key,"File_name"));furi_string_set(value,"test.sub");return metadata_ok;}
static SubGhzReceiver* subghz_txrx_get_receiver(void* txrx){(void)txrx;return NULL;}
static void subghz_receiver_decode(SubGhzReceiver* r,bool level,uint32_t duration){(void)r;(void)level;assert(duration);decoded++;}
static void scene_manager_set_scene_state(void* manager,int scene,int state){(void)manager;assert(scene==SubGhzSceneDecodeRAW&&state==SubGhzDecodeRawStateLoaded);}
static void subghz_view_receiver_add_data_progress(void* view,const char* text){(void)view;snprintf(last_progress,sizeof(last_progress),"%s",text);}
"""


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


protocol = (ROOT / "lib/subghz/protocols/raw.c").read_text()
decode = (
    ROOT / "applications/main/subghz/scenes/subghz_scene_decode_raw.c"
).read_text()
CLIENTS = "".join(
    function(protocol, n)
    for n in (
        "subghz_protocol_encoder_raw_stop",
        "subghz_protocol_encoder_raw_worker_init",
    )
) + "".join(
    function(decode, n)
    for n in ("subghz_scene_decode_raw_start", "subghz_scene_decode_raw_next")
)

TEST = r"""
#define HEADER "Filetype: Flipper SubGhz RAW File\nVersion: 1\nFrequency: 433920000\nPreset: FuriHalSubGhzPresetOok650Async\nProtocol: RAW\n"
static SubGhzFileEncoderWorker* current;
static unsigned delays,callbacks;static bool drain;
static void cancel_send(void){current->worker_running=false;}
static void publish_last_pulse(void){empty_receive_hook=NULL;int32_t pulse=42;furi_stream_buffer_send(current->stream,&pulse,4,10);current->producer_done=true;}
static void end_callback(void* ctx){assert(ctx==current);callbacks++;}
static void advance(void){delays++;if(drain){LevelDuration d;do{d=subghz_file_encoder_worker_get_level_duration(current);}while(!level_duration_is_reset(d)&&!level_duration_is_wait(d));}if(delays==3)current->worker_running=false;}
static void run_worker(SubGhzFileEncoderWorker* w,bool consume){current=w;delays=0;drain=consume;delay_hook=advance;assert(!w->thread->run(w));assert(!w->worker_running&&!w->flipper_format->opened);}
static void set_file(const char* text){fixture=text;fixture_size=strlen(text);fail_at=SIZE_MAX;open_ok=true;}
static bool start(SubGhzFileEncoderWorker* w,const char* text){set_file(text);return subghz_file_encoder_worker_start(w,"test.sub",NULL);}
static void rejected(SubGhzFileEncoderWorker* w,const char* text){unsigned before=threads;assert(!start(w,text));assert(!w->worker_running&&w->read_error&&!w->stream->count&&!w->flipper_format->opened&&threads==before);assert(level_duration_is_reset(subghz_file_encoder_worker_get_level_duration(w)));}
int main(void){
 SubGhzFileEncoderWorker* w=subghz_file_encoder_worker_alloc();current=w;FuriString* progress=furi_string_alloc();
 subghz_file_encoder_worker_get_text_progress(w,progress);assert(!strcmp(progress->text,"Read 000%"));
 w->worker_running=true;
 empty_receive_hook=publish_last_pulse;LevelDuration last=subghz_file_encoder_worker_get_level_duration(w);assert(!level_duration_is_reset(last)&&level_duration_get_duration(last)==42);assert(level_duration_is_reset(subghz_file_encoder_worker_get_level_duration(w)));w->producer_done=false;w->worker_stopping=false;
 const char* bad[]={"RAW_Data:","RAW_Data: 0","RAW_Data: -0","RAW_Data: 1000001","RAW_Data: -2147483648","RAW_Data: 4294967296","RAW_Data: 99999999999999999999999","RAW_Data: 12 nope","RAW_Data: 12, ,13","XRAW_Data: 12","RAW_Data: 0x12","RAW_Data: +","RAW_Data: 1-2"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++){assert(!subghz_file_encoder_worker_data_parse(w,bad[i]));assert(!w->stream->count);}
 assert(subghz_file_encoder_worker_data_parse(w,"RAW_Data: +100, -200\t300,\r"));assert(w->stream->count==3);
 LevelDuration d=subghz_file_encoder_worker_get_level_duration(w);assert(level_duration_get_level(d)&&level_duration_get_duration(d)==100);
 d=subghz_file_encoder_worker_get_level_duration(w);assert(!level_duration_get_level(d)&&level_duration_get_duration(d)==200);subghz_file_encoder_worker_get_level_duration(w);assert(level_duration_is_wait(subghz_file_encoder_worker_get_level_duration(w)));
 char record[6200]="RAW_Data:";for(unsigned i=0;i<512;i++)strcat(record," -1000000");assert(subghz_file_encoder_worker_data_parse(w,record));assert(w->stream->count==512);furi_stream_buffer_reset(w->stream);strcat(record," 1");assert(!subghz_file_encoder_worker_data_parse(w,record)&&!w->stream->count);
 send_hook=cancel_send;assert(!subghz_file_encoder_worker_data_parse(w,"RAW_Data: 1"));send_hook=NULL;assert(!w->worker_running);
 rejected(w,"");rejected(w,"Filetype: wrong\nVersion: 1\nProtocol: RAW\nRAW_Data: 1\n");rejected(w,"Filetype: Flipper SubGhz RAW File\nVersion: 2\nProtocol: RAW\nRAW_Data: 1\n");rejected(w,HEADER);rejected(w,HEADER "RAW_Data: 1 junk\n");rejected(w,"Filetype: Flipper SubGhz RAW File\nVersion: 1\nProtocol: Princeton\nRAW_Data: 1\n");
 set_file(HEADER "RAW_Data: 1\n");open_ok=false;assert(!subghz_file_encoder_worker_start(w,"missing",NULL)&&w->read_error);open_ok=true;
 char huge[20000];memset(huge,'x',sizeof(huge));memcpy(huge,HEADER,sizeof(HEADER)-1);huge[sizeof(huge)-1]=0;rejected(w,huge);
 // A long series of short comment lines also has a bounded metadata scan.
 memset(huge,'\n',sizeof(huge));memcpy(huge,HEADER,sizeof(HEADER)-1);huge[sizeof(huge)-1]=0;rejected(w,huge);assert(w->flipper_format->pos<=16385);
 set_file(HEADER "RAW_Data: 1\n");fail_at=10;assert(!subghz_file_encoder_worker_start(w,"short",NULL));
 set_file(HEADER "RAW_Data: 1\n");char nul[sizeof(HEADER)+20];memcpy(nul,fixture,fixture_size);nul[fixture_size-2]=0;fixture=nul;assert(!subghz_file_encoder_worker_start(w,"nul",NULL));
 assert(start(w,HEADER "\n# pulses\nRAW_Data: 10 -20\nRAW_Data: 30 -40"));assert(w->stream->count==2&&!w->device);subghz_file_encoder_worker_callback_end(w,end_callback,w);run_worker(w,true);assert(callbacks==1&&w->producer_done&&!w->read_error);assert(level_duration_is_reset(subghz_file_encoder_worker_get_level_duration(w)));
 subghz_file_encoder_worker_get_text_progress(w,progress);assert(!strcmp(progress->text,"Read 100%"));
 assert(start(w,HEADER "RAW_Data: 10\nRAW_Data: 20 broken\n"));run_worker(w,true);assert(w->read_error&&callbacks==2);subghz_file_encoder_worker_get_text_progress(w,progress);assert(!strcmp(progress->text,"File error"));
 assert(start(w,HEADER "RAW_Data: 10\nRAW_Data: 20\n"));w->flipper_format->fail_at=w->flipper_format->pos+5;run_worker(w,true);assert(w->read_error);
 // Reuse resets the selected device, counters, flags and buffered pulses.
 set_file(HEADER "RAW_Data: 1\n");assert(subghz_file_encoder_worker_start(w,"first","cc1101"));assert(w->device);run_worker(w,true);assert(start(w,HEADER "RAW_Data: -9\n"));assert(!w->device&&!w->read_error&&!w->producer_done&&w->stream->count==1);run_worker(w,false);assert(w->producer_done);assert(!level_duration_is_reset(subghz_file_encoder_worker_get_level_duration(w)));assert(level_duration_is_reset(subghz_file_encoder_worker_get_level_duration(w)));
 w->file_size=UINT32_MAX;w->read_offset=UINT32_MAX;subghz_file_encoder_worker_get_text_progress(w,progress);assert(!strcmp(progress->text,"Read 100%"));w->file_size=1;subghz_file_encoder_worker_get_text_progress(w,progress);assert(!strcmp(progress->text,"Read 100%"));
 for(unsigned i=0;i<100;i++){assert(start(w,HEADER "RAW_Data: 1 -2\n"));run_worker(w,true);rejected(w,HEADER "RAW_Data: 0\n");}
 subghz_file_encoder_worker_free(w);
 SubGhzProtocolEncoderRAW encoder={.file_name=furi_string_alloc(),.radio_device_name=furi_string_alloc()};furi_string_set(encoder.radio_device_name,"cc1101");set_file(HEADER "RAW_Data: 0\n");assert(!subghz_protocol_encoder_raw_worker_init(&encoder));assert(!encoder.file_worker_encoder&&!encoder.is_running);subghz_protocol_encoder_raw_stop(&encoder);furi_string_free(encoder.file_name);furi_string_free(encoder.radio_device_name);
 SubGhz app={0};metadata_ok=false;assert(!subghz_scene_decode_raw_start(&app)&&!app.decode_raw_file_worker_encoder);metadata_ok=true;
 for(unsigned i=0;i<100;i++){set_file(HEADER "RAW_Data: 0\n");assert(!subghz_scene_decode_raw_start(&app)&&!app.decode_raw_file_worker_encoder);}
 set_file(HEADER "RAW_Data: 1 -2\n");assert(subghz_scene_decode_raw_start(&app));run_worker(app.decode_raw_file_worker_encoder,false);assert(!subghz_scene_decode_raw_next(&app)&&decoded==2&&!strcmp(last_progress,"Done!"));subghz_file_encoder_worker_free(app.decode_raw_file_worker_encoder);app.decode_raw_file_worker_encoder=NULL;
 set_file(HEADER "RAW_Data: 1 -2\nRAW_Data: broken\n");assert(subghz_scene_decode_raw_start(&app));run_worker(app.decode_raw_file_worker_encoder,false);assert(!subghz_scene_decode_raw_next(&app)&&decoded==2&&!strcmp(last_progress,"File error"));subghz_file_encoder_worker_free(app.decode_raw_file_worker_encoder);
 assert(opens==closes);furi_string_free(progress);
 puts("PASS: production RAW parser, bounded header/records, malformed/short reads, first-record priming, EOF/error termination, callback once, queue cancellation, safe progress and 100 reuse cycles (host scheduling adapter; no RF)");
}
"""
source = (ROOT / "lib/subghz/subghz_file_encoder_worker.c").read_text()
source = re.sub(r"^#include .*\n", "", source, flags=re.M)
with tempfile.TemporaryDirectory(prefix="echo-subghz-file-") as temp:
    p = Path(temp) / "test.c"
    exe = Path(temp) / "test"
    p.write_text(ADAPTER + source + CLIENT_ADAPTER + CLIENTS + TEST)
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-g",
            "-fsanitize=address,undefined",
            "-I",
            str(ROOT),
            str(p),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)
