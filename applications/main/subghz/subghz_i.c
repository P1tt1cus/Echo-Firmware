#include "subghz_i.h"
#include "../echo/echo_file_save.h"

#include "assets_icons.h"
#include "subghz/types.h"
#include <furi.h>
#include <notification/notification.h>
#include <notification/notification_messages.h>
#include <flipper_format/flipper_format.h>
#include <flipper_format/flipper_format_i.h>

#define TAG "SubGhz"

void subghz_blink_start(SubGhz* subghz) {
    furi_assert(subghz);
    notification_message(subghz->notifications, &sequence_blink_stop);
    notification_message(subghz->notifications, &sequence_blink_start_magenta);
}

void subghz_blink_stop(SubGhz* subghz) {
    furi_assert(subghz);
    notification_message(subghz->notifications, &sequence_blink_stop);
}

bool subghz_tx_start(SubGhz* subghz, FlipperFormat* flipper_format) {
    switch(subghz_txrx_tx_start(subghz->txrx, flipper_format)) {
    case SubGhzTxRxStartTxStateErrorParserOthers:
        dialog_message_show_storage_error(
            subghz->dialogs, "Cannot send capture.\nCheck file, preset\nand protocol data.");
        break;
    case SubGhzTxRxStartTxStateErrorEncoderUnavailable:
        dialog_message_show_storage_error(
            subghz->dialogs, "No transmit encoder\nfor this protocol.\nCapture retained.");
        break;
    case SubGhzTxRxStartTxStateErrorRadio:
        dialog_message_show_storage_error(
            subghz->dialogs, "Radio could not start.\nCheck selected radio\nand retry.");
        break;
    case SubGhzTxRxStartTxStateErrorOnlyRx:
        uint32_t frequency = subghz_txrx_get_preset(subghz->txrx).frequency;
        SubGhzTx can_tx = subghz_txrx_radio_device_check_tx(subghz->txrx, frequency);
        if(can_tx == SubGhzTxAllowed) {
            dialog_message_show_storage_error(
                subghz->dialogs, "Radio rejected TX.\nCheck selected radio\nand retry.");
        } else {
            subghz_dialog_message_freq_error(subghz, can_tx);
        }
        break;

    case SubGhzTxRxStartTxStateOk:
        return true;
    default:
        dialog_message_show_storage_error(subghz->dialogs, "Transmission failed.");
        break;
    }
    return false;
}

void subghz_dialog_message_freq_error(SubGhz* subghz, SubGhzTx can_tx) {
    DialogsApp* dialogs = subghz->dialogs;
    const char* header_text = "TX unavailable";
    const char* message_text;

    switch(can_tx) {
    case SubGhzTxAllowed:
    default:
        return;
    case SubGhzTxBlockedRegionNotProvisioned:
        message_text =
            "Region is not configured.\nCheck Region Information\nand restore region data.";
        break;
    case SubGhzTxBlockedRegion:
        message_text =
            "Receive-only frequency\nunder current region\nsettings. Check Region Info.";
        break;
    case SubGhzTxBlockedDefault:
        message_text = "Outside enabled TX bands.\nCheck capture frequency\nand radio settings.";
        break;
    case SubGhzTxUnsupported:
        header_text = "Unsupported frequency";
        message_text =
            "Selected radio cannot\noperate at this frequency.\nCheck capture settings.";
        break;
    }

    DialogMessage* message = dialog_message_alloc();
    dialog_message_set_header(message, header_text, 64, 3, AlignCenter, AlignTop);
    dialog_message_set_text(message, message_text, 64, 20, AlignCenter, AlignTop);

    dialog_message_show(dialogs, message);
    dialog_message_free(message);
}

bool subghz_key_load(SubGhz* subghz, const char* file_path, bool show_dialog) {
    furi_assert(subghz);
    furi_assert(file_path);

    Storage* storage = furi_record_open(RECORD_STORAGE);
    FlipperFormat* fff_data_file = flipper_format_file_alloc(storage);
    Stream* fff_data_stream =
        flipper_format_get_raw_stream(subghz_txrx_get_fff_data(subghz->txrx));

    SubGhzLoadKeyState load_key_state = SubGhzLoadKeyStateParseErr;
    FuriString* temp_str = furi_string_alloc();
    uint32_t temp_data32;
    //Using NAN in order to avoid the null island problem
    float temp_lat = NAN;
    float temp_lon = NAN;
    SubGhzTx can_tx = SubGhzTxUnsupported;

    do {
        stream_clean(fff_data_stream);
        if(!flipper_format_file_open_existing(fff_data_file, file_path)) {
            FURI_LOG_E(TAG, "Error open file %s", file_path);
            break;
        }

        if(!flipper_format_read_header(fff_data_file, temp_str, &temp_data32)) {
            FURI_LOG_E(TAG, "Missing or incorrect header");
            break;
        }

        if(((!strcmp(furi_string_get_cstr(temp_str), SUBGHZ_KEY_FILE_TYPE)) ||
            (!strcmp(furi_string_get_cstr(temp_str), SUBGHZ_RAW_FILE_TYPE))) &&
           temp_data32 == SUBGHZ_KEY_FILE_VERSION) {
        } else {
            FURI_LOG_E(TAG, "Type or version mismatch");
            break;
        }

        //Load frequency
        if(!flipper_format_read_uint32(fff_data_file, "Frequency", &temp_data32, 1)) {
            FURI_LOG_E(TAG, "Missing Frequency");
            break;
        }

        if(!subghz_txrx_radio_device_is_frequency_valid(subghz->txrx, temp_data32)) {
            FURI_LOG_E(TAG, "Frequency not supported on chosen radio module");
            can_tx = SubGhzTxUnsupported;
            load_key_state = SubGhzLoadKeyStateUnsuportedFreq;
            break;
        }

        can_tx = subghz_txrx_radio_device_check_tx(subghz->txrx, temp_data32);
        if(can_tx != SubGhzTxAllowed) {
            FURI_LOG_E(TAG, "This frequency can only be used for RX");

            load_key_state = SubGhzLoadKeyStateOnlyRx;
            break;
        }

        //Load preset
        if(!flipper_format_read_string(fff_data_file, "Preset", temp_str)) {
            FURI_LOG_E(TAG, "Missing Preset");
            break;
        }

        furi_string_set_str(
            temp_str, subghz_txrx_get_preset_name(subghz->txrx, furi_string_get_cstr(temp_str)));
        if(!strcmp(furi_string_get_cstr(temp_str), "")) {
            break;
        }
        SubGhzSetting* setting = subghz_txrx_get_setting(subghz->txrx);

        if(!strcmp(furi_string_get_cstr(temp_str), "CUSTOM")) {
            //TODO FL-3551: add Custom_preset_module
            //delete preset if it already exists
            subghz_setting_delete_custom_preset(setting, furi_string_get_cstr(temp_str));
            //load custom preset from file
            if(!subghz_setting_load_custom_preset(
                   setting, furi_string_get_cstr(temp_str), fff_data_file)) {
                FURI_LOG_E(TAG, "Missing Custom preset");
                break;
            }
        }

        //Load latitude and longitude if present
        //Strict mode to fail if next key doesn't match, instead of reading whole file
        flipper_format_set_strict_mode(fff_data_file, true);
        //Save position and seek instead of rewinding whole file when keys aren't found
        Stream* fff_raw_stream = flipper_format_get_raw_stream(fff_data_file);
        size_t pos_before_lat_lon = stream_tell(fff_raw_stream);
        if(!flipper_format_read_float(fff_data_file, "Lat", (float*)&temp_lat, 1) ||
           !flipper_format_read_float(fff_data_file, "Lon", (float*)&temp_lon, 1)) {
            stream_seek(fff_raw_stream, pos_before_lat_lon, StreamOffsetFromStart);
            //Fallback to older keys "Latitute", "Longitude"
            if(!flipper_format_read_float(fff_data_file, "Latitute", (float*)&temp_lat, 1) ||
               !flipper_format_read_float(fff_data_file, "Longitude", (float*)&temp_lon, 1)) {
                FURI_LOG_W(TAG, "Missing Lat and Lon (optional)");
                stream_seek(fff_raw_stream, pos_before_lat_lon, StreamOffsetFromStart);
            }
        }
        flipper_format_set_strict_mode(fff_data_file, false);

        //Avoid null island when reading
        if(temp_lat == 0.0 && temp_lon == 0.0) {
            temp_lat = NAN;
            temp_lon = NAN;
        }

        size_t preset_index =
            subghz_setting_get_inx_preset_by_name(setting, furi_string_get_cstr(temp_str));

        //Edit TX power, if necessary.
        uint8_t* preset_data = subghz_setting_get_preset_data(setting, preset_index);
        size_t preset_data_size = subghz_setting_get_preset_data_size(setting, preset_index);
        subghz_txrx_set_tx_power(preset_data, preset_data_size, subghz->tx_power);

        //Set the Updated Preset.
        subghz_txrx_set_preset(
            subghz->txrx,
            furi_string_get_cstr(temp_str),
            temp_data32,
            temp_lat,
            temp_lon,
            preset_data,
            preset_data_size);

        //Load protocol
        if(!flipper_format_read_string(fff_data_file, "Protocol", temp_str)) {
            FURI_LOG_E(TAG, "Missing Protocol");
            break;
        }

        FlipperFormat* fff_data = subghz_txrx_get_fff_data(subghz->txrx);
        if(!strcmp(furi_string_get_cstr(temp_str), "RAW")) {
            //if RAW
            subghz->load_type_file = SubGhzLoadTypeFileRaw;
            subghz_protocol_raw_gen_fff_data(
                fff_data, file_path, subghz_txrx_radio_device_get_name(subghz->txrx));
        } else {
            subghz->load_type_file = SubGhzLoadTypeFileKey;
            stream_copy_full(
                flipper_format_get_raw_stream(fff_data_file),
                flipper_format_get_raw_stream(fff_data));
        }

        if(subghz_txrx_load_decoder_by_name_protocol(
               subghz->txrx, furi_string_get_cstr(temp_str))) {
            SubGhzProtocolStatus status = subghz_protocol_decoder_base_deserialize(
                subghz_txrx_get_decoder(subghz->txrx), fff_data);
            if(status != SubGhzProtocolStatusOk) {
                load_key_state = SubGhzLoadKeyStateProtocolDescriptionErr;
                break;
            }
        } else {
            FURI_LOG_E(TAG, "Protocol not found");
            break;
        }

        load_key_state = SubGhzLoadKeyStateOK;
    } while(0);

    furi_string_free(temp_str);
    flipper_format_free(fff_data_file);
    furi_record_close(RECORD_STORAGE);

    switch(load_key_state) {
    case SubGhzLoadKeyStateParseErr:
        if(show_dialog) {
            dialog_message_show_storage_error(subghz->dialogs, "Cannot parse\nfile");
        }
        return false;
    case SubGhzLoadKeyStateProtocolDescriptionErr:
        if(show_dialog) {
            dialog_message_show_storage_error(
                subghz->dialogs, "Error in protocol\nparameters\ndescription");
        }
        return false;

    case SubGhzLoadKeyStateUnsuportedFreq:
    case SubGhzLoadKeyStateOnlyRx:
        if(show_dialog) {
            subghz_dialog_message_freq_error(subghz, can_tx);
        }
        return false;

    case SubGhzLoadKeyStateOK:
        return true;

    default:
        furi_crash("SubGhz: Unknown load_key_state.");
        return false;
    }
}

SubGhzLoadTypeFile subghz_get_load_type_file(SubGhz* subghz) {
    furi_assert(subghz);
    return subghz->load_type_file;
}

bool subghz_get_next_name_file(SubGhz* subghz, uint8_t max_len) {
    furi_assert(subghz);

    Storage* storage = furi_record_open(RECORD_STORAGE);
    FuriString* temp_str = furi_string_alloc();
    FuriString* file_name = furi_string_alloc();
    FuriString* file_path = furi_string_alloc();

    bool res = false;

    if(subghz_path_is_file(subghz->file_path)) {
        //get the name of the next free file
        path_extract_filename(subghz->file_path, file_name, true);
        path_extract_dirname(furi_string_get_cstr(subghz->file_path), file_path);

        storage_get_next_filename(
            storage,
            furi_string_get_cstr(file_path),
            furi_string_get_cstr(file_name),
            SUBGHZ_APP_FILENAME_EXTENSION,
            file_name,
            max_len);

        furi_string_printf(
            temp_str,
            "%s/%s%s",
            furi_string_get_cstr(file_path),
            furi_string_get_cstr(file_name),
            SUBGHZ_APP_FILENAME_EXTENSION);
        furi_string_set(subghz->file_path, temp_str);
        res = true;
    }

    furi_string_free(temp_str);
    furi_string_free(file_path);
    furi_string_free(file_name);
    furi_record_close(RECORD_STORAGE);

    return res;
}

typedef struct {
    Storage* storage;
    Stream* source;
} SubGhzFileWrite;

static bool subghz_write_signal_file(const char* path, void* context) {
    SubGhzFileWrite* write = context;
    File* file = storage_file_alloc(write->storage);
    bool result = false;
    uint8_t buffer[256];
    do {
        if(!storage_file_open(file, path, FSAM_WRITE, FSOM_OPEN_EXISTING)) break;
        size_t remaining = stream_size(write->source);
        if(!remaining || !stream_rewind(write->source)) break;
        while(remaining) {
            size_t count = MIN(remaining, sizeof(buffer));
            if(stream_read(write->source, buffer, count) != count) break;
            if(storage_file_write(file, buffer, count) != count) break;
            remaining -= count;
        }
        if(remaining) break;
        result = storage_file_sync(file);
    } while(false);
    if(!storage_file_close(file)) result = false;
    storage_file_free(file);
    return result;
}

bool subghz_save_protocol_to_file(
    SubGhz* subghz,
    FlipperFormat* flipper_format,
    const char* dev_file_name,
    SubGhzSaveMode mode) {
    furi_assert(subghz);
    furi_assert(flipper_format);
    furi_assert(dev_file_name);
    Storage* storage = furi_record_open(RECORD_STORAGE);
    FuriString* file_dir = furi_string_alloc();
    FuriString* recovery = furi_string_alloc();
    FlipperFormat* saved_data = flipper_format_string_alloc();
    Stream* source = flipper_format_get_raw_stream(flipper_format);
    Stream* copy = flipper_format_get_raw_stream(saved_data);
    size_t position = stream_tell(source);
    size_t size = stream_size(source);
    bool saved = false;
    path_extract_dirname(dev_file_name, file_dir);
    do {
        // Strip transient fields from a private copy, preserving the live capture
        // and its cursor even when saving fails. RAW recordings use file rename.
        size_t copied = stream_copy_full(source, copy);
        bool restored = stream_seek(source, position, StreamOffsetFromStart);
        if(!size || copied != size || !restored) break;
        if(flipper_format_key_exist(saved_data, "Repeat")) {
            if(!flipper_format_rewind(saved_data) ||
               !flipper_format_delete_key(saved_data, "Repeat"))
                break;
        }
        if(!storage_simply_mkdir(storage, furi_string_get_cstr(file_dir))) break;
        SubGhzFileWrite write = {.storage = storage, .source = copy};
        saved = echo_file_save(
            storage,
            dev_file_name,
            mode == SubGhzSaveUpdate,
            subghz_write_signal_file,
            &write,
            recovery);
    } while(false);
    if(mode == SubGhzSaveAutosave) {
        // Receiver callback runs on the worker. The UI tick stops/joins it before
        // opening a dialog; blocking here could deadlock a concurrent Stop.
        if(!saved) subghz->autosave_failed = true;
    } else if(!furi_string_empty(recovery)) {
        const char* suffix = strrchr(furi_string_get_cstr(recovery), '.');
        FuriString* message = furi_string_alloc_printf(
            "%s\nPrior file kept as\n<file>%s",
            saved ? "Saved." : "Save failed.",
            suffix ? suffix : ".echo-old");
        dialog_message_show_storage_error(subghz->dialogs, furi_string_get_cstr(message));
        furi_string_free(message);
    } else if(!saved) {
        dialog_message_show_storage_error(
            subghz->dialogs,
            mode == SubGhzSaveUpdate ? "Updated signal\nnot saved\nCheck SD card" :
                                       "Cannot save signal\nCheck name/SD card");
    }
    flipper_format_free(saved_data);
    furi_string_free(recovery);
    furi_string_free(file_dir);
    furi_record_close(RECORD_STORAGE);
    return saved;
}

void subghz_save_to_file(void* context) {
    furi_assert(context);
    SubGhz* subghz = context;
    if(subghz_path_is_file(subghz->file_path)) {
        subghz_save_protocol_to_file(
            subghz,
            subghz_txrx_get_fff_data(subghz->txrx),
            furi_string_get_cstr(subghz->file_path),
            SubGhzSaveUpdate);
    }
}

bool subghz_load_protocol_from_file(SubGhz* subghz) {
    furi_assert(subghz);

    FuriString* file_path = furi_string_alloc();

    DialogsFileBrowserOptions browser_options;
    dialog_file_browser_set_basic_options(
        &browser_options, SUBGHZ_APP_FILENAME_EXTENSION, &I_sub1_10px);
    browser_options.base_path = SUBGHZ_APP_FOLDER;

    // Input events and views are managed by file_select
    bool res = dialog_file_browser_show(
        subghz->dialogs, subghz->file_path, subghz->file_path, &browser_options);

    if(res) {
        res = subghz_key_load(subghz, furi_string_get_cstr(subghz->file_path), true);
    }

    furi_string_free(file_path);

    return res;
}

bool subghz_rename_file(SubGhz* subghz, const char* destination) {
    furi_assert(subghz);
    Storage* storage = furi_record_open(RECORD_STORAGE);
    const char* source = furi_string_get_cstr(subghz->file_path_tmp);
    bool result;
    if(storage_common_equivalent_path(storage, source, destination)) {
        FileInfo info;
        result = storage_common_stat(storage, source, &info) == FSE_OK &&
                 !(info.flags & FSF_DIRECTORY);
    } else {
        result = storage_common_rename_safe(storage, source, destination) == FSE_OK;
    }
    if(!result) dialog_message_show_storage_error(subghz->dialogs, "Cannot rename\nsignal file");
    furi_record_close(RECORD_STORAGE);
    return result;
}

bool subghz_file_available(SubGhz* subghz) {
    furi_assert(subghz);
    bool ret = true;
    Storage* storage = furi_record_open(RECORD_STORAGE);

    FS_Error fs_result =
        storage_common_stat(storage, furi_string_get_cstr(subghz->file_path), NULL);

    if(fs_result != FSE_OK) {
        dialog_message_show_storage_error(subghz->dialogs, "File not available\n file/directory");
        ret = false;
    }

    furi_record_close(RECORD_STORAGE);
    return ret;
}

bool subghz_delete_file(SubGhz* subghz) {
    furi_assert(subghz);

    Storage* storage = furi_record_open(RECORD_STORAGE);
    bool result = storage_simply_remove(storage, furi_string_get_cstr(subghz->file_path_tmp));
    furi_record_close(RECORD_STORAGE);

    subghz_file_name_clear(subghz);

    return result;
}

void subghz_file_name_clear(SubGhz* subghz) {
    furi_assert(subghz);
    furi_string_set(subghz->file_path, SUBGHZ_APP_FOLDER);
    furi_string_reset(subghz->file_path_tmp);
}

bool subghz_path_is_file(FuriString* path) {
    return furi_string_end_with(path, SUBGHZ_APP_FILENAME_EXTENSION);
}

void subghz_lock(SubGhz* subghz) {
    furi_assert(subghz);
    subghz->lock = SubGhzLockOn;
}

void subghz_unlock(SubGhz* subghz) {
    furi_assert(subghz);
    subghz->lock = SubGhzLockOff;
}

bool subghz_is_locked(SubGhz* subghz) {
    furi_assert(subghz);
    return subghz->lock == SubGhzLockOn;
}

void subghz_rx_key_state_set(SubGhz* subghz, SubGhzRxKeyState state) {
    furi_assert(subghz);
    subghz->rx_key_state = state;
}

SubGhzRxKeyState subghz_rx_key_state_get(SubGhz* subghz) {
    furi_assert(subghz);
    return subghz->rx_key_state;
}
