#include "subghz_replay_data.h"

#include <ctype.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

static char* trim(char* text) {
    while(*text == ' ' || *text == '\t' || *text == '\r')
        text++;
    size_t length = strlen(text);
    while(length && isspace((unsigned char)text[length - 1]))
        text[--length] = 0;
    return text;
}

static bool number(const char* text, uint32_t* value) {
    if(!*text) return false;
    uint32_t result = 0;
    for(; *text; text++) {
        if(*text < '0' || *text > '9' || result > (UINT32_MAX - (*text - '0')) / 10) return false;
        result = result * 10 + (*text - '0');
    }
    *value = result;
    return true;
}

static int hex(char c) {
    if(c >= '0' && c <= '9') return c - '0';
    if(c >= 'a' && c <= 'f') return c - 'a' + 10;
    if(c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static bool parse_line(EchoReplayParser* p) {
    p->line[p->used] = 0;
    char* field = trim(p->line);
    if(!*field || *field == '#') return true;
    char* value = strchr(field, ':');
    if(!value) return false;
    *value++ = 0;
    value = trim(value);
    field = trim(field);
    const char* names[] = {"Filetype", "Version", "Frequency", "Preset", "Protocol", "Bit", "Key"};
    size_t index;
    for(index = 0; index < sizeof(names) / sizeof(names[0]); index++) {
        if(strcmp(field, names[index]) == 0) break;
    }
    if(index < sizeof(names) / sizeof(names[0])) {
        if(p->fields & (1U << index)) return false;
        p->fields |= 1U << index;
    }
    EchoReplayCapture* c = &p->capture;
    uint32_t value32;
    switch(index) {
    case 0:
        c->raw = strcmp(value, "Flipper SubGhz RAW File") == 0;
        return c->raw || strcmp(value, "Flipper SubGhz Key File") == 0;
    case 1:
        return number(value, &value32) && value32 == 1;
    case 2:
        return number(value, &c->frequency) && c->frequency != 0;
    case 3:
        if(!*value || strlen(value) >= sizeof(c->preset)) return false;
        strcpy(c->preset, value);
        return true;
    case 4:
        if(!*value || strlen(value) >= sizeof(c->protocol)) return false;
        strcpy(c->protocol, value);
        return true;
    case 5:
        return number(value, &c->bits) && c->bits > 0;
    case 6:
        while(*value) {
            if(c->key_size == ECHO_REPLAY_KEY_MAX || !value[1]) return false;
            int hi = hex(value[0]), lo = hex(value[1]);
            if(hi < 0 || lo < 0) return false;
            c->key[c->key_size++] = (hi << 4) | lo;
            value += 2;
            if(*value && !isspace((unsigned char)*value)) return false;
            while(isspace((unsigned char)*value))
                value++;
        }
        return c->key_size != 0;
    default:
        if(strcmp(field, "RAW_Data") != 0) return true;
        if(!*value) return false;
        while(*value) {
            if(*value == '-') value++;
            char* end = value;
            while(*end >= '0' && *end <= '9')
                end++;
            if(end == value || (*end && !isspace((unsigned char)*end))) return false;
            char saved = *end;
            *end = 0;
            bool valid = number(value, &value32) && value32 > 0 && value32 <= 1000000;
            *end = saved;
            if(!valid) return false;
            c->pulses++;
            c->duration_us += value32;
            value = end;
            while(isspace((unsigned char)*value))
                value++;
        }
        return true;
    }
}

void echo_replay_parser_init(EchoReplayParser* p) {
    memset(p, 0, sizeof(*p));
    p->capture.fingerprint = 2166136261U;
}

bool echo_replay_parser_feed(EchoReplayParser* p, const uint8_t* data, size_t size) {
    if(p->failed || size > ECHO_REPLAY_FILE_MAX - p->capture.bytes) return !(p->failed = true);
    p->capture.bytes += size;
    for(size_t i = 0; i < size; i++) {
        p->capture.fingerprint = (p->capture.fingerprint ^ data[i]) * 16777619U;
        if(data[i] == '\n') {
            if(!parse_line(p)) return !(p->failed = true);
            p->used = 0;
        } else {
            if(data[i] == 0 || p->used == ECHO_REPLAY_LINE_MAX) return !(p->failed = true);
            p->line[p->used++] = data[i];
        }
    }
    return true;
}

bool echo_replay_parser_finish(EchoReplayParser* p) {
    if(p->failed || (p->used && !parse_line(p))) return false;
    p->used = 0;
    if((p->fields & 31U) != 31U) return false;
    if(p->capture.raw != (strcmp(p->capture.protocol, "RAW") == 0)) return false;
    return !p->capture.raw || p->capture.pulses > 0;
}

int echo_replay_changed_bits(const EchoReplayCapture* a, const EchoReplayCapture* b) {
    if(a->raw || b->raw || !a->key_size || a->key_size != b->key_size || !a->bits ||
       a->bits != b->bits || strcmp(a->protocol, b->protocol) != 0 || a->bits > a->key_size * 8)
        return -1;
    int changed = 0;
    // Flipper keys are big-endian and right-aligned in the stored byte array.
    for(uint32_t bit = 0; bit < a->bits; bit++) {
        size_t byte = a->key_size - 1 - bit / 8;
        if((a->key[byte] ^ b->key[byte]) & (1U << (bit % 8))) changed++;
    }
    return changed;
}
