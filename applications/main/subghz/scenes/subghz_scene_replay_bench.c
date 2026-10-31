#include "../subghz_i.h"
#include "../helpers/subghz_replay_data.h"
#include "../helpers/subghz_txrx_i.h"
#include <lib/subghz/blocks/generic.h>
#include <lib/subghz/blocks/custom_btn.h>

#define BENCH_DIR EXT_PATH("subghz/echo_bench")

typedef enum {
    BenchMenu,
    BenchLoading,
    BenchPage,
    BenchPrepared,
    BenchSending,
    BenchObservation,
} BenchMode;

enum {
    BenchSelectA = 1200,
    BenchSelectB,
    BenchCompare,
    BenchPrepare,
    BenchLastTest,
    BenchExport,
    BenchHelp,
    BenchSend,
    BenchReturn,
    BenchObserve,
    BenchUnknown,
    BenchAccepted,
    BenchNoChange,
    BenchUnexpected,
    BenchRetryReport,
};

struct SubGhzReplayBench {
    Storage* storage;
    EchoReplayParser* parser;
    EchoReplayCapture capture[2];
    bool loaded[2];
    FuriString* source[2];
    FuriString* snapshot[2];
    File* input;
    File* output;
    File* reference;
    uint32_t expected_size;
    uint32_t byte_differences;
    uint32_t first_difference;
    uint8_t loading_slot;
    BenchMode mode;
    SubGhzRadioDeviceType previous_radio;
    FuriString* report_base;
    FuriString* report_path;
    FuriString* test_status;
    const char* observation;
    bool report_saved;
    uint32_t started_tick;
    uint32_t elapsed_ms;
    bool prepared_raw;
};

static void bench_menu(SubGhz* subghz);
static void bench_finish(SubGhz* subghz, const char* status);

static void bench_button(GuiButtonType button, InputType type, void* context) {
    if(type != InputTypeShort) return;
    SubGhz* subghz = context;
    uint32_t event = BenchReturn;
    if(button == GuiButtonTypeRight) event = BenchRetryReport;
    if(button == GuiButtonTypeCenter) {
        if(subghz->replay_bench->mode == BenchPrepared)
            event = BenchSend;
        else if(!furi_string_empty(subghz->replay_bench->report_base))
            event = BenchObserve;
    }
    view_dispatcher_send_custom_event(subghz->view_dispatcher, event);
}

static void bench_page(SubGhz* subghz, const char* text, BenchMode mode, const char* action) {
    subghz->replay_bench->mode = mode;
    widget_reset(subghz->widget);
    widget_add_text_scroll_element(subghz->widget, 0, 0, 128, 49, text);
    if(action) {
        widget_add_button_element(
            subghz->widget, GuiButtonTypeCenter, action, bench_button, subghz);
    }
    widget_add_button_element(
        subghz->widget,
        GuiButtonTypeLeft,
        mode == BenchSending || mode == BenchLoading ? "Stop" : "Back",
        bench_button,
        subghz);
    view_dispatcher_switch_to_view(subghz->view_dispatcher, SubGhzViewIdWidget);
}

static void bench_callback(void* context, uint32_t event) {
    SubGhz* subghz = context;
    view_dispatcher_send_custom_event(subghz->view_dispatcher, event);
}

static void bench_menu(SubGhz* subghz) {
    SubGhzReplayBench* b = subghz->replay_bench;
    b->mode = BenchMenu;
    submenu_reset(subghz->submenu);
    submenu_set_header(subghz->submenu, "Replay Bench");
    submenu_add_item(
        subghz->submenu,
        b->loaded[0] ? "Capture A: loaded" : "Choose capture A",
        BenchSelectA,
        bench_callback,
        subghz);
    submenu_add_item(
        subghz->submenu,
        b->loaded[1] ? "Capture B: loaded" : "Choose capture B",
        BenchSelectB,
        bench_callback,
        subghz);
    submenu_add_item(subghz->submenu, "Compare A / B", BenchCompare, bench_callback, subghz);
    submenu_add_item(subghz->submenu, "Prepare A replay", BenchPrepare, bench_callback, subghz);
    submenu_add_item(
        subghz->submenu, "Last test / observation", BenchLastTest, bench_callback, subghz);
    submenu_add_item(subghz->submenu, "Save comparison", BenchExport, bench_callback, subghz);
    submenu_add_item(subghz->submenu, "Help", BenchHelp, bench_callback, subghz);
    view_dispatcher_switch_to_view(subghz->view_dispatcher, SubGhzViewIdMenu);
}

static void bench_close_files(SubGhzReplayBench* b) {
    if(b->input) storage_file_free(b->input);
    if(b->output) storage_file_free(b->output);
    if(b->reference) storage_file_free(b->reference);
    b->input = b->output = b->reference = NULL;
}

// Reserve a new private filename, never overwrite a capture or an earlier report.
static File* bench_new_file(SubGhzReplayBench* b, FuriString* path, const char* suffix) {
    if(!storage_simply_mkdir(b->storage, BENCH_DIR)) return NULL;
    File* file = storage_file_alloc(b->storage);
    for(unsigned i = 0; i < 100; i++) {
        furi_string_printf(
            path,
            BENCH_DIR "/%lu-%lu-%u%s",
            furi_hal_rtc_get_timestamp(),
            furi_get_tick(),
            i,
            suffix);
        if(storage_file_open(file, furi_string_get_cstr(path), FSAM_WRITE, FSOM_CREATE_NEW))
            return file;
        if(storage_file_get_error(file) != FSE_EXIST) break;
    }
    storage_file_free(file);
    furi_string_reset(path);
    return NULL;
}

static void bench_remove_snapshot(SubGhzReplayBench* b, unsigned slot) {
    b->loaded[slot] = false;
    if(!furi_string_empty(b->snapshot[slot])) {
        storage_simply_remove(b->storage, furi_string_get_cstr(b->snapshot[slot]));
        furi_string_reset(b->snapshot[slot]);
    }
}

static void bench_load_failed(SubGhz* subghz, const char* reason) {
    SubGhzReplayBench* b = subghz->replay_bench;
    bench_close_files(b);
    bench_remove_snapshot(b, b->loading_slot);
    bench_page(subghz, reason, BenchPage, NULL);
}

static void bench_select(SubGhz* subghz, unsigned slot) {
    SubGhzReplayBench* b = subghz->replay_bench;
    if(slot && !b->loaded[0]) {
        bench_page(subghz, "Choose capture A first.", BenchPage, NULL);
        return;
    }
    FuriString* path = furi_string_alloc_set(EXT_PATH("subghz"));
    DialogsFileBrowserOptions options;
    dialog_file_browser_set_basic_options(&options, ".sub", NULL);
    options.base_path = EXT_PATH("subghz");
    if(!dialog_file_browser_show(subghz->dialogs, path, path, &options)) {
        furi_string_free(path);
        return;
    }
    // Snapshots use .tmp, so they cannot be selected by this browser.
    bench_remove_snapshot(b, slot);
    if(!slot) bench_remove_snapshot(b, 1);
    furi_string_set(b->source[slot], path);
    furi_string_free(path);
    b->loading_slot = slot;
    b->input = storage_file_alloc(b->storage);
    bool opened = storage_file_open(
        b->input, furi_string_get_cstr(b->source[slot]), FSAM_READ, FSOM_OPEN_EXISTING);
    uint64_t size = opened ? storage_file_size(b->input) : 0;
    if(!opened || !size || size > ECHO_REPLAY_FILE_MAX) {
        bench_load_failed(subghz, "Cannot open capture.\nLimit: 256 KiB per file.");
        return;
    }
    b->expected_size = size;
    b->output = bench_new_file(b, b->snapshot[slot], ".tmp");
    if(!b->output) {
        bench_load_failed(subghz, "Cannot create working copy.\nCheck SD space.");
        return;
    }
    if(slot) {
        b->reference = storage_file_alloc(b->storage);
        if(!storage_file_open(
               b->reference, furi_string_get_cstr(b->snapshot[0]), FSAM_READ, FSOM_OPEN_EXISTING)) {
            bench_load_failed(subghz, "Capture A copy unavailable.\nChoose A again.");
            return;
        }
        b->byte_differences = 0;
        b->first_difference = UINT32_MAX;
    }
    echo_replay_parser_init(b->parser);
    bench_page(
        subghz, "Reading capture...\nCreating working copy.\nBack cancels.", BenchLoading, NULL);
}

static void bench_load_tick(SubGhz* subghz) {
    SubGhzReplayBench* b = subghz->replay_bench;
    uint8_t data[256], reference[256];
    // Bound work per dispatcher tick; SD analysis never holds a GUI model lock.
    for(unsigned iteration = 0; iteration < 16; iteration++) {
        uint32_t offset = b->parser->capture.bytes;
        size_t count = storage_file_read(b->input, data, sizeof(data));
        if(storage_file_get_error(b->input) != FSE_OK) {
            bench_load_failed(subghz, "Capture read failed.");
            return;
        }
        if(!count) {
            if(offset != b->expected_size || !echo_replay_parser_finish(b->parser) ||
               !storage_file_sync(b->output)) {
                bench_load_failed(
                    subghz,
                    "Invalid or changed capture.\nExpected .sub version 1.\nMax line: 8192 bytes.");
                return;
            }
            if(b->loading_slot && b->capture[0].bytes > offset) {
                if(b->first_difference == UINT32_MAX) b->first_difference = offset;
                b->byte_differences += b->capture[0].bytes - offset;
            }
            b->capture[b->loading_slot] = b->parser->capture;
            b->loaded[b->loading_slot] = true;
            bench_close_files(b);
            bench_menu(subghz);
            return;
        }
        if(!echo_replay_parser_feed(b->parser, data, count) ||
           storage_file_write(b->output, data, count) != count) {
            bench_load_failed(
                subghz, "Invalid capture or SD write error.\nSource was not changed.");
            return;
        }
        if(b->reference) {
            size_t other = storage_file_read(b->reference, reference, count);
            if(storage_file_get_error(b->reference) != FSE_OK) {
                bench_load_failed(subghz, "Capture A read failed.");
                return;
            }
            for(size_t i = 0; i < count; i++) {
                if(i >= other || data[i] != reference[i]) {
                    b->byte_differences++;
                    if(b->first_difference == UINT32_MAX) b->first_difference = offset + i;
                }
            }
        }
    }
}

static void bench_capture_text(FuriString* text, SubGhzReplayBench* b, unsigned slot) {
    const EchoReplayCapture* c = &b->capture[slot];
    furi_string_cat_printf(
        text,
        "%c: %s\nProtocol: %s\nFrequency: %lu Hz\nPreset: %s\nBytes: %lu\nFingerprint FNV1a: %08lX\n",
        'A' + slot,
        furi_string_get_cstr(b->source[slot]),
        c->protocol,
        c->frequency,
        c->preset,
        c->bytes,
        c->fingerprint);
    if(c->raw) {
        furi_string_cat_printf(
            text, "RAW pulses: %lu\nDuration: %llu us\n", c->pulses, c->duration_us);
    } else {
        furi_string_cat_printf(text, "Declared bits: %lu\nKey: ", c->bits);
        for(size_t i = 0; i < c->key_size; i++)
            furi_string_cat_printf(text, "%02X", c->key[i]);
        if(!c->key_size) furi_string_cat(text, "not available");
        furi_string_cat(text, "\n");
    }
}

static FuriString* bench_comparison(SubGhzReplayBench* b) {
    FuriString* text = furi_string_alloc_set("Echo Replay Bench 1\n\n");
    if(!b->loaded[0]) {
        furi_string_cat(text, "No capture A selected.");
        return text;
    }
    if(b->loaded[1]) {
        const EchoReplayCapture* a = &b->capture[0];
        const EchoReplayCapture* c = &b->capture[1];
        furi_string_cat_printf(
            text,
            "\nCHANGES\nFrequency: %s\nPreset: %s\nProtocol: %s\nBit count: %s\nFile byte differences: %lu\n",
            a->frequency == c->frequency ? "same" : "CHANGED",
            strcmp(a->preset, c->preset) ? "CHANGED" : "same",
            strcmp(a->protocol, c->protocol) ? "CHANGED" : "same",
            a->bits == c->bits ? "same" : "CHANGED",
            b->byte_differences);
        if(b->byte_differences)
            furi_string_cat_printf(
                text, "First byte offset: %lu (zero based)\n", b->first_difference);
        int changed = echo_replay_changed_bits(a, c);
        if(changed >= 0) {
            furi_string_cat_printf(
                text, "Changed key bits: %d / %lu\nXOR bytes: ", changed, a->bits);
            for(size_t i = 0; i < a->key_size; i++)
                furi_string_cat_printf(text, "%02X", a->key[i] ^ c->key[i]);
            furi_string_cat(text, "\n");
        } else {
            furi_string_cat(text, "Key bit comparison unavailable.\n");
        }
        furi_string_cat(
            text,
            "\nByte comparison includes formatting and metadata. RAW timings are not aligned. Changed bits do not prove encryption or rolling codes.\n");
    }
    furi_string_cat(text, "\nCAPTURES\n");
    bench_capture_text(text, b, 0);
    if(b->loaded[1]) {
        furi_string_cat(text, "\n");
        bench_capture_text(text, b, 1);
    }
    return text;
}

static bool bench_write_report(SubGhzReplayBench* b) {
    if(furi_string_empty(b->report_path)) return false;
    FuriString* text = furi_string_alloc_set(b->report_base);
    furi_string_cat_printf(
        text,
        "\nTransmission: %s\nElapsed: %lu ms\nReceiver observation (manual): %s\n",
        furi_string_get_cstr(b->test_status),
        b->elapsed_ms,
        b->observation);
    File* file = storage_file_alloc(b->storage);
    bool ok = storage_file_open(
        file, furi_string_get_cstr(b->report_path), FSAM_WRITE, FSOM_CREATE_ALWAYS);
    if(ok)
        ok = storage_file_write(file, furi_string_get_cstr(text), furi_string_size(text)) ==
                 furi_string_size(text) &&
             storage_file_sync(file);
    storage_file_free(file);
    furi_string_free(text);
    b->report_saved = ok;
    return ok;
}

static bool bench_begin_report(SubGhzReplayBench* b) {
    if(!b->report_saved && !furi_string_empty(b->report_base)) return false;
    File* file = bench_new_file(b, b->report_path, ".txt");
    if(!file) return false;
    storage_file_free(file);
    FuriString* comparison = bench_comparison(b);
    furi_string_set(b->report_base, comparison);
    furi_string_free(comparison);
    furi_string_cat_printf(
        b->report_base,
        "\nTimestamp: %lu\nRadio: internal CC1101\n",
        furi_hal_rtc_get_timestamp());
    b->observation = "Unknown / not observed";
    b->elapsed_ms = 0;
    return true;
}

static void bench_show_result(SubGhz* subghz) {
    SubGhzReplayBench* b = subghz->replay_bench;
    FuriString* text = furi_string_alloc_printf(
        "LAST TEST\n%s\nReceiver: %s\nReport: %s\n%s",
        furi_string_get_cstr(b->test_status),
        b->observation,
        b->report_saved ? "saved" : "SAVE FAILED; retry Save report",
        furi_string_get_cstr(b->report_path));
    bench_page(subghz, furi_string_get_cstr(text), BenchPage, "Observe");
    widget_add_button_element(subghz->widget, GuiButtonTypeRight, "Save", bench_button, subghz);
    furi_string_free(text);
}

static void bench_prepare(SubGhz* subghz) {
    SubGhzReplayBench* b = subghz->replay_bench;
    if(!b->loaded[0]) {
        bench_page(subghz, "Choose capture A first.", BenchPage, NULL);
        return;
    }
    EchoReplayCapture* c = &b->capture[0];
    if((!c->raw && c->bytes > 8192) ||
       (c->raw && c->duration_us > ECHO_REPLAY_TX_LIMIT_MS * 1000ULL)) {
        bench_page(
            subghz,
            "Replay limit:\ndecoded files <= 8 KiB;\nRAW duration <= 10 s.\nComparison is still available.",
            BenchPage,
            NULL);
        return;
    }
    subghz_custom_btns_reset();
    subghz_block_generic_global.endless_tx = false;
    if(!subghz_key_load(subghz, furi_string_get_cstr(b->snapshot[0]), false)) {
        bench_page(
            subghz,
            "Cannot prepare capture.\nCheck protocol, preset and current TX region settings.\nNo transmission started.",
            BenchPage,
            NULL);
        return;
    }
    SubGhzProtocolDecoderBase* decoder = subghz_txrx_get_decoder(subghz->txrx);
    if(!decoder || (!c->raw && decoder->protocol->type != SubGhzProtocolTypeStatic) ||
       !subghz_txrx_protocol_is_transmittable(subghz->txrx, false)) {
        bench_page(
            subghz,
            "Compare only.\nThis decoded protocol cannot be replayed unchanged by the bench.\nDynamic encoders can advance counters.",
            BenchPage,
            NULL);
        return;
    }
    uint32_t repeat = 1;
    if(!c->raw && !flipper_format_insert_or_update_uint32(
                      subghz_txrx_get_fff_data(subghz->txrx), "Repeat", &repeat, 1)) {
        bench_page(subghz, "Cannot configure encoder.", BenchPage, NULL);
        return;
    }
    b->prepared_raw = c->raw;
    FuriString* text = furi_string_alloc_printf(
        "PREPARED: A\n%s\n%lu Hz / internal radio\n%s\n10 s maximum; Back cancels.\nOK starts transmission.",
        c->protocol,
        c->frequency,
        c->raw ? "One RAW file pass." :
                 "One encoder run; Repeat=1.\nFraming is protocol-specific.");
    bench_page(subghz, furi_string_get_cstr(text), BenchPrepared, "Send");
    furi_string_free(text);
}

static void bench_send(SubGhz* subghz) {
    SubGhzReplayBench* b = subghz->replay_bench;
    if(b->mode != BenchPrepared) return;
    if(!bench_begin_report(b)) {
        bench_page(
            subghz,
            "Cannot reserve a test report.\nCheck SD or save the previous result first.",
            BenchPage,
            NULL);
        return;
    }
    furi_string_cat(
        b->report_base,
        b->prepared_raw ? "Requested: one RAW pass\n" : "Requested: one encoder run, Repeat=1\n");
    furi_string_cat(b->report_base, "Transmission deadline: 10000 ms\n");
    furi_string_set(b->test_status, "Starting; completion unconfirmed");
    if(!bench_write_report(b)) {
        furi_string_set(b->test_status, "Not started: report write failed");
        bench_page(subghz, "Report write failed.\nNo transmission started.", BenchPage, NULL);
        return;
    }
    subghz_block_generic_global.endless_tx = false;
    b->started_tick = furi_get_tick();
    SubGhzTxRxStartTxState result =
        subghz_txrx_tx_start(subghz->txrx, subghz_txrx_get_fff_data(subghz->txrx));
    if(result != SubGhzTxRxStartTxStateOk) {
        furi_string_set(b->test_status, "Start failed; no completed transmission");
        bench_write_report(b);
        bench_show_result(subghz);
        return;
    }
    subghz->state_notifications = SubGhzNotificationStateTx;
    bench_page(
        subghz,
        "TRANSMITTING A\nBack / Stop ends the run.\nReceiver response is not measured automatically.",
        BenchSending,
        NULL);
}

static void bench_finish(SubGhz* subghz, const char* status) {
    SubGhzReplayBench* b = subghz->replay_bench;
    subghz_block_generic_global.endless_tx = false;
    subghz_txrx_stop(subghz->txrx);
    subghz->state_notifications = SubGhzNotificationStateIDLE;
    b->elapsed_ms =
        (uint32_t)(furi_get_tick() - b->started_tick) * 1000U / furi_kernel_get_tick_frequency();
    furi_string_set(b->test_status, status);
    bench_write_report(b);
    b->mode = BenchPage;
}

void subghz_replay_bench_free(SubGhz* subghz) {
    SubGhzReplayBench* b = subghz->replay_bench;
    if(!b) return;
    if(b->mode == BenchSending) bench_finish(subghz, "Stopped on exit; completion unconfirmed");
    bench_close_files(b);
    subghz_txrx_stop(subghz->txrx);
    subghz_txrx_sleep(subghz->txrx);
    subghz_txrx_radio_device_set(subghz->txrx, b->previous_radio);
    for(unsigned i = 0; i < 2; i++) {
        bench_remove_snapshot(b, i);
        furi_string_free(b->source[i]);
        furi_string_free(b->snapshot[i]);
    }
    furi_string_free(b->report_base);
    furi_string_free(b->report_path);
    furi_string_free(b->test_status);
    furi_record_close(RECORD_STORAGE);
    free(b->parser);
    free(b);
    subghz->replay_bench = NULL;
}

void subghz_scene_replay_bench_on_enter(void* context) {
    SubGhz* subghz = context;
    SubGhzReplayBench* b = calloc(1, sizeof(SubGhzReplayBench));
    subghz->replay_bench = b;
    b->storage = furi_record_open(RECORD_STORAGE);
    b->parser = malloc(sizeof(EchoReplayParser));
    for(unsigned i = 0; i < 2; i++) {
        b->source[i] = furi_string_alloc();
        b->snapshot[i] = furi_string_alloc();
    }
    b->report_base = furi_string_alloc();
    b->report_path = furi_string_alloc();
    b->test_status = furi_string_alloc();
    b->observation = "Unknown / not observed";
    b->report_saved = true;
    b->previous_radio = subghz_txrx_radio_device_get(subghz->txrx);
    subghz_txrx_stop(subghz->txrx);
    subghz_txrx_sleep(subghz->txrx);
    subghz_txrx_radio_device_set(subghz->txrx, SubGhzRadioDeviceTypeInternal);
    bench_menu(subghz);
}

bool subghz_scene_replay_bench_on_event(void* context, SceneManagerEvent event) {
    SubGhz* subghz = context;
    SubGhzReplayBench* b = subghz->replay_bench;
    if(event.type == SceneManagerEventTypeTick) {
        if(b->mode == BenchLoading) bench_load_tick(subghz);
        if(b->mode == BenchSending) {
            if(subghz_devices_is_async_complete_tx(subghz->txrx->radio_device)) {
                bench_finish(subghz, "Encoder completed; receiver response unverified");
                bench_show_result(subghz);
            } else if(
                (uint32_t)(furi_get_tick() - b->started_tick) >=
                10U * furi_kernel_get_tick_frequency()) {
                bench_finish(subghz, "Stopped at time limit; may be partial");
                bench_show_result(subghz);
            }
        }
        return true;
    }
    if(event.type == SceneManagerEventTypeBack ||
       (event.type == SceneManagerEventTypeCustom && event.event == BenchReturn)) {
        if(b->mode == BenchSending) {
            bench_finish(subghz, "Stopped by user; may be partial");
            bench_show_result(subghz);
        } else if(b->mode == BenchLoading) {
            bench_close_files(b);
            bench_remove_snapshot(b, b->loading_slot);
            bench_menu(subghz);
        } else if(b->mode != BenchMenu) {
            bench_menu(subghz);
        } else {
            if(!scene_manager_previous_scene(subghz->scene_manager)) {
                view_dispatcher_stop(subghz->view_dispatcher);
            }
        }
        return true;
    }
    if(event.type != SceneManagerEventTypeCustom) return false;
    if(event.event == BenchSend && b->mode == BenchPrepared) {
        bench_send(subghz);
        return true;
    }
    if(b->mode == BenchSending || b->mode == BenchLoading || b->mode == BenchPrepared) return true;
    if(event.event == BenchRetryReport && !furi_string_empty(b->report_base)) {
        bench_write_report(b);
        bench_show_result(subghz);
        return true;
    }
    if(event.event == BenchObserve && !furi_string_empty(b->report_base)) {
        b->mode = BenchObservation;
        submenu_reset(subghz->submenu);
        submenu_set_header(subghz->submenu, "Receiver observation");
        submenu_add_item(
            subghz->submenu, "Unknown / not observed", BenchUnknown, bench_callback, subghz);
        submenu_add_item(
            subghz->submenu, "Expected response", BenchAccepted, bench_callback, subghz);
        submenu_add_item(
            subghz->submenu, "No visible change", BenchNoChange, bench_callback, subghz);
        submenu_add_item(
            subghz->submenu, "Unexpected response", BenchUnexpected, bench_callback, subghz);
        view_dispatcher_switch_to_view(subghz->view_dispatcher, SubGhzViewIdMenu);
        return true;
    }
    if(b->mode == BenchObservation && event.event >= BenchUnknown &&
       event.event <= BenchUnexpected) {
        static const char* observations[] = {
            "Unknown / not observed",
            "Expected response",
            "No visible change",
            "Unexpected response"};
        b->observation = observations[event.event - BenchUnknown];
        bench_write_report(b);
        bench_show_result(subghz);
        return true;
    }
    if(b->mode != BenchMenu) return true;
    switch(event.event) {
    case BenchSelectA:
        bench_select(subghz, 0);
        break;
    case BenchSelectB:
        bench_select(subghz, 1);
        break;
    case BenchCompare: {
        FuriString* text = bench_comparison(b);
        bench_page(subghz, furi_string_get_cstr(text), BenchPage, NULL);
        furi_string_free(text);
        break;
    }
    case BenchPrepare:
        bench_prepare(subghz);
        break;
    case BenchLastTest:
        if(furi_string_empty(b->report_base))
            bench_page(subghz, "No test in this session.", BenchPage, NULL);
        else
            bench_show_result(subghz);
        break;
    case BenchExport: {
        if(!b->loaded[0]) {
            bench_page(subghz, "Choose capture A first.", BenchPage, NULL);
            break;
        }
        FuriString* path = furi_string_alloc();
        File* file = bench_new_file(b, path, ".txt");
        FuriString* text = bench_comparison(b);
        furi_string_cat(text, "\nComparison export; no transmission performed by this action.\n");
        bool ok = file &&
                  storage_file_write(file, furi_string_get_cstr(text), furi_string_size(text)) ==
                      furi_string_size(text) &&
                  storage_file_sync(file);
        if(file) storage_file_free(file);
        if(ok)
            furi_string_printf(text, "Comparison saved\n%s", furi_string_get_cstr(path));
        else
            furi_string_set(text, "Report write failed. Check SD space.");
        bench_page(subghz, furi_string_get_cstr(text), BenchPage, NULL);
        furi_string_free(text);
        furi_string_free(path);
        break;
    }
    case BenchHelp:
        bench_page(
            subghz,
            "REPLAY BENCH\nChoose A, then B to compare saved .sub files. Choosing a new A clears B.\n\nPrepare A checks the encoder without transmitting. Send starts one bounded run. RAW plays its recorded pulses once; decoded static protocols request Repeat=1. Dynamic decoded signals are comparison-only.\n\nReports separate encoder completion from your observed receiver response. Nothing here proves encryption or anti-replay protection.\n\nInternal radio; existing TX restrictions. Max file 256 KiB; max line 8192 bytes. Working copies are removed on exit. Reports: /ext/subghz/echo_bench",
            BenchPage,
            NULL);
        break;
    default:
        break;
    }
    return true;
}

void subghz_scene_replay_bench_on_exit(void* context) {
    SubGhz* subghz = context;
    subghz_replay_bench_free(subghz);
    widget_reset(subghz->widget);
    submenu_reset(subghz->submenu);
}
