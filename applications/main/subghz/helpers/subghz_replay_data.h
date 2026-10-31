#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ECHO_REPLAY_FILE_MAX    (256U * 1024U)
#define ECHO_REPLAY_LINE_MAX    8192U
#define ECHO_REPLAY_KEY_MAX     32U
#define ECHO_REPLAY_TX_LIMIT_MS 10000U

typedef struct {
    uint32_t bytes;
    uint32_t fingerprint; // FNV-1a, an identifier only, not a cryptographic integrity check.
    uint32_t frequency;
    uint32_t bits;
    uint32_t pulses;
    uint64_t duration_us;
    uint8_t key[ECHO_REPLAY_KEY_MAX];
    size_t key_size;
    char protocol[48];
    char preset[80];
    bool raw;
} EchoReplayCapture;

typedef struct {
    EchoReplayCapture capture;
    char line[ECHO_REPLAY_LINE_MAX + 1];
    size_t used;
    uint32_t fields;
    bool failed;
} EchoReplayParser;

void echo_replay_parser_init(EchoReplayParser* parser);
bool echo_replay_parser_feed(EchoReplayParser* parser, const uint8_t* data, size_t size);
bool echo_replay_parser_finish(EchoReplayParser* parser);
// Returns -1 if protocol/width/key length differ or decoded keys are unavailable.
int echo_replay_changed_bits(const EchoReplayCapture* a, const EchoReplayCapture* b);
