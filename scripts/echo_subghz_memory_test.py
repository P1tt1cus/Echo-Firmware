"""Production RX lifecycle: allocate only for live reception, retain across hops, free on full stop."""

from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, name):
    m = re.search(
        r"^(?:static )?(?:void|uint32_t)\s+" + name + r"\([^;]*?\) \{", source, re.M
    )
    assert m, name
    end = m.end()
    depth = 1
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
#define furi_assert assert
#define SUBGHZ_ADD_MANUALLY 1
#define FURI_LOG_E(...) ((void)0)
typedef void (*SubGhzWorkerOverrunCallback)(void*);
typedef void (*SubGhzWorkerPairCallback)(bool,uint32_t,void*);
typedef struct {bool running;void* context;SubGhzWorkerOverrunCallback overrun;SubGhzWorkerPairCallback pair;} SubGhzWorker;
typedef struct {SubGhzWorker* worker;void* receiver;void* radio_device;int txrx_state;} SubGhzTxRx;
enum {SubGhzTxRxStateSleep,SubGhzTxRxStateIDLE,SubGhzTxRxStateRx,SubGhzTxRxStateTx};
static bool async_rx,speaker;static unsigned allocations,frees,starts,stops,callbacks;
static SubGhzWorker* subghz_worker_alloc(void){allocations++;return calloc(1,sizeof(SubGhzWorker));}
static void subghz_worker_free(SubGhzWorker* w){assert(w&&!w->running&&!async_rx);frees++;free(w);}
static void subghz_worker_set_context(SubGhzWorker* w,void* c){w->context=c;}
static void subghz_worker_set_overrun_callback(SubGhzWorker* w,SubGhzWorkerOverrunCallback cb){w->overrun=cb;}
static void subghz_worker_set_pair_callback(SubGhzWorker* w,SubGhzWorkerPairCallback cb){w->pair=cb;}
static void subghz_receiver_reset(void* r){assert(r==(void*)1);}
static void subghz_receiver_decode(bool level,uint32_t duration,void* r){assert(level&&duration==350&&r==(void*)1);callbacks++;}
static void subghz_worker_rx_callback(bool level,uint32_t duration,void* ctx){SubGhzWorker* w=ctx;assert(w&&w->running);w->pair(level,duration,w->context);}
static void subghz_worker_start(SubGhzWorker* w){assert(w&&!w->running&&w->pair&&w->overrun);w->running=true;starts++;}
static void subghz_worker_stop(SubGhzWorker* w){assert(w&&w->running&&!async_rx);w->running=false;stops++;}
static bool subghz_worker_is_running(SubGhzWorker* w){assert(w);return w->running;}
static void subghz_devices_idle(void* r){(void)r;}
static uint32_t subghz_devices_set_frequency(void* r,uint32_t frequency){(void)r;return frequency;}
static void subghz_devices_flush_rx(void* r){(void)r;}
static void subghz_txrx_speaker_on(SubGhzTxRx* t){(void)t;speaker=true;}
static void subghz_txrx_speaker_off(SubGhzTxRx* t){(void)t;speaker=false;}
static void subghz_txrx_speaker_mute(SubGhzTxRx* t){(void)t;speaker=false;}
static void subghz_txrx_speaker_unmute(SubGhzTxRx* t){(void)t;}
static void subghz_txrx_tx_stop(SubGhzTxRx* t){t->txrx_state=SubGhzTxRxStateIDLE;}
static void subghz_devices_start_async_rx(void* r,void(*cb)(bool,uint32_t,void*),void* ctx){(void)r;assert(!async_rx);async_rx=true;cb(true,350,ctx);}
static void subghz_devices_stop_async_rx(void* r){(void)r;async_rx=false;}
"""
TEST = r"""
int main(void){
 SubGhzTxRx txrx={.receiver=(void*)1,.txrx_state=SubGhzTxRxStateIDLE};
 subghz_txrx_stop(&txrx);assert(!txrx.worker&&!allocations); // browsing/offline/TX never need RX buffer
 for(unsigned i=0;i<100;i++){
  unsigned before=allocations;assert(subghz_txrx_rx(&txrx,433920000)==433920000);assert(allocations==before+1&&txrx.worker&&speaker&&async_rx);
  SubGhzWorker* worker=txrx.worker;
  for(unsigned hop=0;hop<5;hop++){subghz_txrx_rx_end(&txrx);assert(txrx.worker==worker&&!worker->running&&!async_rx&&!speaker);subghz_txrx_rx(&txrx,433920000);assert(txrx.worker==worker&&allocations==before+1);}
  subghz_txrx_stop(&txrx);assert(!txrx.worker&&!async_rx&&!speaker&&allocations==frees);subghz_txrx_stop(&txrx);assert(allocations==frees);
 }
 assert(starts==600&&stops==600&&callbacks==600);
 txrx.txrx_state=SubGhzTxRxStateTx;subghz_txrx_stop(&txrx);assert(!txrx.worker&&allocations==frees);
 puts("PASS: RX allocation on demand, ready worker before ISR, ISR stopped before join/free, retained across hops, full-stop release, no-op/TX paths and 100 cycles");
}
"""
source = (ROOT / "applications/main/subghz/helpers/subghz_txrx.c").read_text()
with tempfile.TemporaryDirectory(prefix="echo-subghz-memory-") as tmp:
    p = Path(tmp)
    p.joinpath("test.c").write_text(
        ADAPTER
        + "".join(
            function(source, n)
            for n in ["subghz_txrx_rx", "subghz_txrx_rx_end", "subghz_txrx_stop"]
        )
        + TEST
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-g",
            "-fsanitize=address,undefined",
            str(p / "test.c"),
            "-o",
            str(p / "test"),
        ],
        check=True,
    )
    subprocess.run([str(p / "test")], check=True)
