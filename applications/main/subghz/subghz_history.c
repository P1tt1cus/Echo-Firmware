#include "subghz_history.h"
#include <lib/subghz/receiver.h>
#include <rpc/rpc.h>
#include <flipper_format/flipper_format_i.h>

#include <furi.h>

#define SUBGHZ_HISTORY_MAX       65535 // uint16_t index max, ram limit below
// #define SUBGHZ_HISTORY_FREE_HEAP (23624 * (1 - MIN(rpc_get_sessions_count(instance->rpc), 1U)))
#define SUBGHZ_HISTORY_FREE_HEAP (4 * 1024)

#define TAG "SubGhzHistory"

typedef struct {
    FuriString* item_str;
    FlipperFormat* flipper_string;
    uint8_t type;
    SubGhzRadioPreset* preset;
    DateTime datetime;
    uint32_t hash_data;
    const SubGhzProtocol* protocol;
    uint16_t repeats;
    float latitude;
    float longitude;
} SubGhzHistoryItem;

ARRAY_DEF(SubGhzHistoryItemArray, SubGhzHistoryItem, M_POD_OPLIST) //-V658

#define M_OPL_SubGhzHistoryItemArray_t() ARRAY_OPLIST(SubGhzHistoryItemArray, M_POD_OPLIST)

typedef struct {
    SubGhzHistoryItemArray_t data;
} SubGhzHistoryStruct;

struct SubGhzHistory {
    uint32_t last_update_timestamp;
    uint16_t last_index_write;
    uint32_t code_last_hash_data;
    FuriString* tmp_string;
    SubGhzHistoryStruct* history;
    Rpc* rpc;
};

// Hashes only narrow the search. Compare the complete serialized capture, and
// restore both cursors because callers also use these streams for display/TX.
static bool subghz_history_data_equal(FlipperFormat* first, FlipperFormat* second) {
    if(first == second) return true;
    Stream* a = flipper_format_get_raw_stream(first);
    Stream* b = flipper_format_get_raw_stream(second);
    const size_t size = stream_size(a);
    if(!size || size != stream_size(b)) return false;
    const size_t a_pos = stream_tell(a), b_pos = stream_tell(b);
    bool equal = stream_seek(a, 0, StreamOffsetFromStart) &&
                 stream_seek(b, 0, StreamOffsetFromStart);
    uint8_t a_data[64], b_data[64];
    for(size_t offset = 0; equal && offset < size; offset += sizeof(a_data)) {
        const size_t count = MIN(sizeof(a_data), size - offset);
        equal = stream_read(a, a_data, count) == count && stream_read(b, b_data, count) == count &&
                memcmp(a_data, b_data, count) == 0;
    }
    const bool a_restored = stream_seek(a, a_pos, StreamOffsetFromStart);
    const bool b_restored = stream_seek(b, b_pos, StreamOffsetFromStart);
    return equal && a_restored && b_restored;
}

static bool subghz_history_item_matches(
    const SubGhzHistoryItem* item,
    uint32_t hash,
    const SubGhzProtocol* protocol,
    const SubGhzRadioPreset* preset,
    FlipperFormat* data) {
    return item->hash_data == hash && item->protocol == protocol &&
           item->preset->frequency == preset->frequency &&
           furi_string_equal(item->preset->name, preset->name) &&
           subghz_history_data_equal(item->flipper_string, data);
}

bool subghz_history_is_same(SubGhzHistory* instance, uint16_t first, uint16_t second) {
    const size_t count = SubGhzHistoryItemArray_size(instance->history->data);
    if(first >= count || second >= count) return false;
    const SubGhzHistoryItem* a = SubGhzHistoryItemArray_get(instance->history->data, first);
    const SubGhzHistoryItem* b = SubGhzHistoryItemArray_get(instance->history->data, second);
    return subghz_history_item_matches(a, b->hash_data, b->protocol, b->preset, b->flipper_string);
}

SubGhzHistory* subghz_history_alloc(void) {
    SubGhzHistory* instance = calloc(1, sizeof(SubGhzHistory));
    instance->tmp_string = furi_string_alloc();
    instance->history = malloc(sizeof(SubGhzHistoryStruct));
    SubGhzHistoryItemArray_init(instance->history->data);
    instance->rpc = furi_record_open(RECORD_RPC);
    return instance;
}

void subghz_history_free(SubGhzHistory* instance) {
    furi_assert(instance);
    furi_string_free(instance->tmp_string);
    for
        M_EACH(item, instance->history->data, SubGhzHistoryItemArray_t) {
            furi_string_free(item->item_str);
            furi_string_free(item->preset->name);
            free(item->preset);
            flipper_format_free(item->flipper_string);
            item->type = 0;
        }
    SubGhzHistoryItemArray_clear(instance->history->data);
    free(instance->history);
    furi_record_close(RECORD_RPC);
    free(instance);
}

uint32_t subghz_history_get_hash_data(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return item->hash_data;
}

const SubGhzProtocol* subghz_history_get_protocol(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return item->protocol;
}

uint16_t subghz_history_get_repeats(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return item->repeats;
}

uint32_t subghz_history_get_frequency(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return item->preset->frequency;
}

SubGhzRadioPreset* subghz_history_get_radio_preset(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return item->preset;
}

const char* subghz_history_get_preset(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return furi_string_get_cstr(item->preset->name);
}

float subghz_history_get_latitude(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return item->latitude;
}

float subghz_history_get_longitude(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return item->longitude;
}

void subghz_history_reset(SubGhzHistory* instance) {
    furi_assert(instance);
    furi_string_reset(instance->tmp_string);
    for
        M_EACH(item, instance->history->data, SubGhzHistoryItemArray_t) {
            furi_string_free(item->item_str);
            furi_string_free(item->preset->name);
            free(item->preset);
            flipper_format_free(item->flipper_string);
            item->type = 0;
        }
    SubGhzHistoryItemArray_reset(instance->history->data);
    instance->last_index_write = 0;
    instance->code_last_hash_data = 0;
}

void subghz_history_delete_item(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);

    if(idx < SubGhzHistoryItemArray_size(instance->history->data)) {
        SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
        furi_string_free(item->item_str);
        furi_string_free(item->preset->name);
        free(item->preset);
        flipper_format_free(item->flipper_string);
        item->type = 0;
        SubGhzHistoryItemArray_remove_v(instance->history->data, idx, idx + 1);
        instance->last_index_write--;
    }
}

uint16_t subghz_history_get_item(SubGhzHistory* instance) {
    furi_assert(instance);
    return instance->last_index_write;
}

uint8_t subghz_history_get_type_protocol(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    return item->type;
}

const char* subghz_history_get_protocol_name(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    if(!item || !item->flipper_string) {
        FURI_LOG_E(TAG, "Missing Item");
        furi_string_reset(instance->tmp_string);
        return furi_string_get_cstr(instance->tmp_string);
    }
    flipper_format_rewind(item->flipper_string);
    if(!flipper_format_read_string(item->flipper_string, "Protocol", instance->tmp_string)) {
        FURI_LOG_E(TAG, "Missing Protocol");
        furi_string_reset(instance->tmp_string);
    }
    return furi_string_get_cstr(instance->tmp_string);
}

DateTime subghz_history_get_datetime(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    if(item) {
        return item->datetime;
    } else {
        return (DateTime){};
    }
}

FlipperFormat* subghz_history_get_raw_data(SubGhzHistory* instance, uint16_t idx) {
    furi_assert(instance);
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    if(item->flipper_string) {
        return item->flipper_string;
    } else {
        return NULL;
    }
}
bool subghz_history_get_text_space_left(
    SubGhzHistory* instance,
    FuriString* output,
    bool ignore_full,
    bool show_sats,
    uint8_t sats) {
    furi_assert(instance);
    if(!ignore_full) {
        if(memmgr_get_free_heap() < SUBGHZ_HISTORY_FREE_HEAP) {
            if(output != NULL) furi_string_set(output, "Memory is FULL");
            return true;
        }
        if(instance->last_index_write == SUBGHZ_HISTORY_MAX) {
            if(output != NULL) furi_string_set(output, "History is FULL");
            return true;
        }
    }
    if(output != NULL) {
        if(show_sats) {
            furi_string_printf(output, "%d", sats);
        } else {
            furi_string_printf(output, "%02u", instance->last_index_write);
        }
    }
    return false;
}

uint16_t subghz_history_get_last_index(SubGhzHistory* instance) {
    return instance->last_index_write;
}
void subghz_history_get_text_item_menu(SubGhzHistory* instance, FuriString* output, uint16_t idx) {
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    furi_string_set(output, item->item_str);
}

void subghz_history_get_time_item_menu(SubGhzHistory* instance, FuriString* output, uint16_t idx) {
    SubGhzHistoryItem* item = SubGhzHistoryItemArray_get(instance->history->data, idx);
    DateTime* t = &item->datetime;
    furi_string_printf(output, "%.2d:%.2d:%.2d ", t->hour, t->minute, t->second);
}

bool subghz_history_add_to_history(
    SubGhzHistory* instance,
    void* context,
    SubGhzRadioPreset* preset) {
    furi_assert(instance);
    furi_assert(context);

    if(subghz_history_full(instance)) return false;

    SubGhzProtocolDecoderBase* decoder_base = context;
    uint32_t hash_data = subghz_protocol_decoder_base_get_hash_data_long(decoder_base);
    FlipperFormat* capture = flipper_format_string_alloc();
    if(subghz_protocol_decoder_base_serialize(decoder_base, capture, preset) !=
       SubGhzProtocolStatusOk) {
        FURI_LOG_E(TAG, "Capture serialization failed");
        flipper_format_free(capture);
        return false;
    }

    uint16_t repeats = 0;
    SubGhzHistoryItemArray_it_t it;
    SubGhzHistoryItemArray_it_last(it, instance->history->data);
    while(!SubGhzHistoryItemArray_end_p(it)) {
        SubGhzHistoryItem* search = SubGhzHistoryItemArray_ref(it);
        if(subghz_history_item_matches(
               search, hash_data, decoder_base->protocol, preset, capture)) {
            if(it->index + 1 == (size_t)instance->last_index_write &&
               (uint32_t)(furi_get_tick() - instance->last_update_timestamp) < 600) {
                instance->last_update_timestamp = furi_get_tick();
                flipper_format_free(capture);
                return false;
            }
            repeats = search->repeats < UINT16_MAX ? search->repeats + 1 : UINT16_MAX;
            break;
        }
        SubGhzHistoryItemArray_previous(it);
    }

    instance->code_last_hash_data = hash_data;
    instance->last_update_timestamp = furi_get_tick();

    SubGhzHistoryItem* item = SubGhzHistoryItemArray_push_raw(instance->history->data);
    item->preset = malloc(sizeof(SubGhzRadioPreset));
    item->type = decoder_base->protocol->type;
    // if(decoder_base->protocol->filter & SubGhzProtocolFilter_Weather) {
    //     // Other code uses protocol type to check if signal is usable
    //     // so we can't change the actual protocol type, we fake it here
    //     item->type = SubGhzProtocolWeatherStation;
    // }
    item->preset->frequency = preset->frequency;
    item->preset->name = furi_string_alloc();
    furi_string_set(item->preset->name, preset->name);
    item->preset->data = preset->data;
    item->preset->data_size = preset->data_size;
    furi_hal_rtc_get_datetime(&item->datetime);
    item->hash_data = hash_data;
    item->protocol = decoder_base->protocol;
    item->repeats = repeats;
    item->latitude = preset->latitude;
    item->longitude = preset->longitude;

    item->item_str = furi_string_alloc();
    item->flipper_string = capture;

    if(decoder_base->protocol && decoder_base->protocol->decoder &&
       decoder_base->protocol->decoder->get_string_brief) {
        decoder_base->protocol->decoder->get_string_brief(decoder_base, item->item_str);
        instance->last_index_write++;
        return true;
    }

    FuriString* text = furi_string_alloc();

    do {
        if(!flipper_format_rewind(item->flipper_string)) {
            FURI_LOG_E(TAG, "Rewind error");
            break;
        }
        if(!flipper_format_read_string(item->flipper_string, "Protocol", instance->tmp_string)) {
            FURI_LOG_E(TAG, "Missing Protocol");
            break;
        }
        if(!strcmp(furi_string_get_cstr(instance->tmp_string), "KeeLoq")) {
            furi_string_set(instance->tmp_string, "KL ");
            if(!flipper_format_read_string(item->flipper_string, "Manufacture", text)) {
                FURI_LOG_E(TAG, "Missing Protocol");
                break;
            }
            furi_string_cat(instance->tmp_string, text);
        }
        if(!flipper_format_rewind(item->flipper_string)) {
            FURI_LOG_E(TAG, "Rewind error");
            break;
        }
        uint8_t key_data[sizeof(uint64_t)] = {0};
        if(!flipper_format_read_hex(item->flipper_string, "Key", key_data, sizeof(uint64_t))) {
            FURI_LOG_D(TAG, "No Key");
        }
        uint64_t data = 0;
        for(uint8_t i = 0; i < sizeof(uint64_t); i++) {
            data = (data << 8) | key_data[i];
        }
        if(data != 0) {
            if(!(uint32_t)(data >> 32)) {
                furi_string_printf(
                    item->item_str,
                    "%s %lX",
                    furi_string_get_cstr(instance->tmp_string),
                    (uint32_t)(data & 0xFFFFFFFF));
            } else {
                furi_string_printf(
                    item->item_str,
                    "%s %lX%08lX",
                    furi_string_get_cstr(instance->tmp_string),
                    (uint32_t)(data >> 32),
                    (uint32_t)(data & 0xFFFFFFFF));
            }
        } else {
            furi_string_printf(item->item_str, "%s", furi_string_get_cstr(instance->tmp_string));
        }

    } while(false);

    furi_string_free(text);
    instance->last_index_write++;
    return true;
}

void subghz_history_remove_duplicates(SubGhzHistory* instance) {
    furi_assert(instance);

    // Deleting an earlier entry shifts the retained one. Re-fetch by its adjusted
    // index instead of retaining an invalidated pointer/iterator across removals.
    for(int32_t keep = (int32_t)SubGhzHistoryItemArray_size(instance->history->data) - 1; keep > 0;
        keep--) {
        for(int32_t earlier = keep - 1; earlier >= 0; earlier--) {
            if(subghz_history_is_same(instance, earlier, keep)) {
                subghz_history_delete_item(instance, earlier);
                keep--;
            }
        }
    }
}

bool subghz_history_full(SubGhzHistory* instance) {
    if(memmgr_get_free_heap() < SUBGHZ_HISTORY_FREE_HEAP) return true;
    if(instance->last_index_write >= SUBGHZ_HISTORY_MAX) return true;
    return false;
}
