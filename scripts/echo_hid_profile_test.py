"""Exercise BLE HID profile setup/teardown and status callbacks without a radio."""

from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "applications/main/bad_usb/helpers/bad_usb_hid.c").read_text()


def function(name):
    m = re.search(
        r"^(?:static )?(?:void\*|void|bool)\s+" + name + r"\([^;]*?\) \{", source, re.M
    )
    assert m, name
    depth, end = 1, m.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[m.start() : end] + "\n"


start = source.index("typedef struct {\n    Bt* bt;")
struct = source[
    start : source.index("} BleHidInstance;", start) + len("} BleHidInstance;")
]
ADAPTER = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#define furi_assert assert
#define furi_check assert
#define RECORD_BT "bt"
#define HID_BT_KEYS_STORAGE_NAME ".bt_hid.keys"
#define APP_DATA_PATH(x) x
typedef enum {BtStatusOff,BtStatusAdvertising,BtStatusConnected} BtStatus;
typedef struct {int marker;} FuriHalBleProfileBase;
typedef void(*HidStateCallback)(bool,void*);
typedef struct {bool suppress_pin_screen;BtStatus status;} Bt;
typedef struct {int ble;} BadUsbHidConfig;
static Bt bt;static FuriHalBleProfileBase profile;static int ble_profile_hid_ext;
static BtStatus initial_status;static bool custom_path,restored,closed;
static unsigned calls;static bool reported;static void* consumer_context;
static void(*status_cb)(BtStatus,void*);static void* status_ctx;
static void* furi_record_open(const char* record) {(void)record;return &bt;}
static void furi_record_close(const char* record) {(void)record;closed=true;}
static void bt_disconnect(Bt* b) {b->status=BtStatusOff;}
static void furi_delay_ms(unsigned delay) {(void)delay;}
static void bt_keys_storage_set_storage_path(Bt* b,const char* path) {(void)b;(void)path;custom_path=true;}
static void bt_keys_storage_set_default_path(Bt* b) {(void)b;custom_path=false;}
static void hid_ble_adjust_config(BadUsbHidConfig* cfg) {(void)cfg;}
static FuriHalBleProfileBase* bt_profile_start(Bt* b,int templ,void* cfg) {(void)templ;(void)cfg;assert(!b->suppress_pin_screen&&custom_path);return &profile;}
static bool bt_profile_restore_default(Bt* b) {(void)b;assert(!custom_path);restored=true;return true;}
static void furi_hal_bt_start_advertising(void) {bt.status=initial_status;}
static void bt_set_status_changed_callback(Bt* b,void(*cb)(BtStatus,void*),void* ctx) {(void)b;status_cb=cb;status_ctx=ctx;}
static void consumer(bool connected,void* ctx) {assert(ctx==consumer_context);reported=connected;calls++;}
"""
TEST = r"""
int main(void) {
 for(unsigned previous=0;previous<2;previous++) {
  for(unsigned already_connected=0;already_connected<2;already_connected++) {
   bt.suppress_pin_screen=previous;initial_status=already_connected?BtStatusConnected:BtStatusAdvertising;
   custom_path=restored=closed=false;calls=0;BadUsbHidConfig cfg={0};
   BleHidInstance* i=hid_ble_init(&cfg);assert(i->is_connected==already_connected&&!i->state_callback&&!bt.suppress_pin_screen);
   int token=42;consumer_context=&token;hid_ble_set_state_callback(i,consumer,&token);
   assert(calls==1&&reported==already_connected&&hid_ble_is_connected(i)==already_connected);
   status_cb(BtStatusConnected,status_ctx);assert(calls==2&&reported&&hid_ble_is_connected(i));
   status_cb(BtStatusAdvertising,status_ctx);assert(calls==3&&!reported&&!hid_ble_is_connected(i));
   hid_ble_set_state_callback(i,NULL,NULL);status_cb(BtStatusOff,status_ctx);assert(calls==3);
   hid_ble_deinit(i);assert(!status_cb&&!custom_path&&restored&&closed&&bt.suppress_pin_screen==previous);
  }
 }
 puts("PASS: BLE profile initialized status, callback registration/removal, system pairing UI, key-store/profile restoration and prior PIN-screen preference");
}
"""
with tempfile.TemporaryDirectory(prefix="echo-hid-profile-") as d:
    path = Path(d) / "profile.c"
    exe = Path(d) / "profile"
    path.write_text(
        ADAPTER
        + struct
        + "\n"
        + "".join(
            function(n)
            for n in (
                "hid_ble_connection_status_callback",
                "hid_ble_init",
                "hid_ble_deinit",
                "hid_ble_set_state_callback",
                "hid_ble_is_connected",
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
            str(path),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)
