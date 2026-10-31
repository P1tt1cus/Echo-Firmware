"""Sanitizer tests for the production Replay Bench capture parser and comparisons."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "applications/main/subghz/helpers"
TEST = r"""
#include "subghz_replay_data.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char* header =
 "Filetype: Flipper SubGhz Key File\nVersion: 1\nFrequency: 433920000\n"
 "Preset: FuriHalSubGhzPresetOok650Async\nProtocol: Princeton\nBit: 24\n";

static bool parse(EchoReplayParser* p,const char* text,size_t stride) {
 echo_replay_parser_init(p);
 size_t len=strlen(text);
 for(size_t i=0;i<len;i+=stride) {
  size_t count=len-i<stride?len-i:stride;
  if(!echo_replay_parser_feed(p,(const uint8_t*)text+i,count))return false;
 }
 return echo_replay_parser_finish(p);
}

int main(void) {
 assert(sizeof(EchoReplayParser)<1024);
 EchoReplayParser* p=malloc(sizeof(*p));
 char text[1024];snprintf(text,sizeof(text),"%sKey: 00 00 00 00 00 12 34 56\nTE: 350\n",header);
 EchoReplayCapture a={0};
 for(size_t stride=1;stride<300;stride++) {
  assert(parse(p,text,stride));
  assert(p->capture.frequency==433920000&&p->capture.bits==24&&p->capture.key_size==8);
  assert(p->capture.bytes==strlen(text));
  if(stride==1)a=p->capture;
  else assert(!memcmp(&a,&p->capture,sizeof(a)));
 }
 EchoReplayCapture b=a;b.key[7]^=3;assert(echo_replay_changed_bits(&a,&b)==2);
 b=a;b.key[0]=255;assert(echo_replay_changed_bits(&a,&b)==0); // Padding outside declared width.
 b.bits=23;assert(echo_replay_changed_bits(&a,&b)==-1);
 b=a;strcpy(b.protocol,"Other");assert(echo_replay_changed_bits(&a,&b)==-1);
 b=a;b.key_size=0;assert(echo_replay_changed_bits(&a,&b)==-1);
 b=a;b.raw=true;assert(echo_replay_changed_bits(&a,&b)==-1);
 a.bits=257;assert(echo_replay_changed_bits(&a,&a)==-1);
 const char* raw="Filetype: Flipper SubGhz RAW File\r\nVersion: 1\r\nFrequency: 433920000\r\nPreset: FuriHalSubGhzPresetOok650Async\r\nProtocol: RAW\r\nRAW_Data: 100 -200 300\r\nRAW_Data: -400 500";
 for(size_t stride=1;stride<64;stride++) {
  assert(parse(p,raw,stride));assert(p->capture.raw);
  assert(p->capture.pulses==5&&p->capture.duration_us==1500);
 }
 char large_raw[7000];
 snprintf(large_raw,sizeof(large_raw),"Filetype: Flipper SubGhz RAW File\nVersion: 1\nFrequency: 433920000\nPreset: FuriHalSubGhzPresetOok650Async\nProtocol: RAW\nRAW_Data: ");
 for(unsigned i=0;i<1000;i++)strcat(large_raw,"1 -2 ");
 assert(parse(p,large_raw,17));assert(p->capture.pulses==2000&&p->capture.duration_us==3000);
 const char* bad[]={"", "Version: 1\n", "Filetype: Wrong\n", "Filetype: Flipper SubGhz Key File\nVersion: 2\n", "Frequency: 4294967296\n", "Frequency: -1\n", "Version: 1\nVersion: 1\n", "Key: GG\n", "Key: 0\n", "Key: 00zz\n", "RAW_Data: 0\n", "RAW_Data: -\n", "RAW_Data: 2147483648\n", "RAW_Data: 100 -100 garbage\n"};
 for(size_t i=0;i<sizeof(bad)/sizeof(*bad);i++)assert(!parse(p,bad[i],1));
 snprintf(text,sizeof(text),"%sKey: 00 00 00 00 00 12 34 56\nProtocol: Other",header);
 assert(!parse(p,text,7)); // Duplicate known fields cannot disagree with the loader.
 snprintf(text,sizeof(text),"%sKey: 00 00 00 00 00 12 34 56",header);
 assert(parse(p,text,1)); // Final line need not have a newline.
 echo_replay_parser_init(p);
 uint8_t zeros[]={0};assert(!echo_replay_parser_feed(p,zeros,1));
 assert(!echo_replay_parser_feed(p,(const uint8_t*)header,strlen(header)));
 char* longline=malloc(ECHO_REPLAY_LINE_MAX+2);memset(longline,'x',ECHO_REPLAY_LINE_MAX+1);
 echo_replay_parser_init(p);assert(!echo_replay_parser_feed(p,(uint8_t*)longline,ECHO_REPLAY_LINE_MAX+1));
 free(longline);
 echo_replay_parser_init(p);
 uint8_t comment[256];memset(comment,'x',sizeof(comment));comment[0]='#';comment[255]='\n';
 for(unsigned i=0;i<1024;i++)assert(echo_replay_parser_feed(p,comment,sizeof(comment)));
 assert(!echo_replay_parser_feed(p,comment,1));
 // Deterministic malformed input corpus, including arbitrary chunk boundaries.
 unsigned seed=42;uint8_t fuzz[1024];
 for(unsigned run=0;run<2000;run++) {
  size_t len=run%sizeof(fuzz);
  for(size_t i=0;i<len;i++){seed=seed*1664525U+1013904223U;fuzz[i]=seed>>24;}
  echo_replay_parser_init(p);echo_replay_parser_feed(p,fuzz,len);echo_replay_parser_finish(p);
 }
 free(p);
 puts("PASS: Replay capture parsing, chunk boundaries, raw timing totals, key differences, malformed input and size bounds");
}
"""

with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    test = folder / "test.c"
    test.write_text(TEST)
    binary = folder / "test"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsanitize=address,undefined",
            "-I",
            str(HELPERS),
            str(test),
            str(HELPERS / "subghz_replay_data.c"),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
