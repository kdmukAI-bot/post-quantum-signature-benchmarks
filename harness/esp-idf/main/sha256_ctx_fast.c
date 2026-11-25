/*
 * Direct SHA-256 context API with fewer copies (PQB_DIRECT_FAST=1, in place of
 * sha256_ctx_direct.c). Same interface (shim_direct/mbedtls/sha256.h) and the same
 * results; the differences are in how much memory each call touches:
 *
 *   init     marks the context unstarted instead of clearing all 108 bytes; every field
 *            is written by starts(), clone(), or the automatic start before it is read
 *   clone    copies the state and the buffered bytes only (as slhdsa-c's
 *            sha2_256_copy()), instead of the whole structure
 *   finish   pads in place and writes the bit length directly
 *   one-shot hashes from a local buffer without building a context
 *
 * Message blocks still go through slhdsa-c's sha2_256_update() and the selected
 * sha2_256_compress(). SHA-224 is not used by the scheme code and is rejected.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "esp_attr.h"
#include "mbedtls/sha256.h"

/* SHA-256 initial hash value as big-endian bytes, the state layout slhdsa-c uses */
static const DRAM_ATTR uint8_t H0[32] = {
    0x6A, 0x09, 0xE6, 0x67, 0xBB, 0x67, 0xAE, 0x85, 0x3C, 0x6E, 0xF3,
    0x72, 0xA5, 0x4F, 0xF5, 0x3A, 0x51, 0x0E, 0x52, 0x7F, 0x9B, 0x05,
    0x68, 0x8C, 0x1F, 0x83, 0xD9, 0xAB, 0x5B, 0xE0, 0xCD, 0x19
};

void mbedtls_sha256_init(mbedtls_sha256_context* c) { c->started = 0; }

void mbedtls_sha256_free(mbedtls_sha256_context* c) { (void)c; }

void mbedtls_sha256_clone(mbedtls_sha256_context* dst, const mbedtls_sha256_context* src)
{
    if (!src->started) {
        dst->started = 0;
        return;
    }
    dst->started = 1;
    dst->s.i = src->s.i;
    dst->s.len = src->s.len;
    memcpy(dst->s.s, src->s.s, 32 + src->s.i);
}

static inline void start(mbedtls_sha256_context* c)
{
    memcpy(c->s.s, H0, 32);
    c->s.i = 0;
    c->s.len = 0;
    c->started = 1;
}

int mbedtls_sha256_starts(mbedtls_sha256_context* c, int is224)
{
    if (is224) {
        abort();
    }
    start(c);
    return 0;
}

int mbedtls_sha256_update(mbedtls_sha256_context* c, const unsigned char* in, size_t len)
{
    if (!c->started) {
        start(c);
    }
    sha2_256_update(&c->s, in, len);
    return 0;
}

/* Pad the buffered tail (i bytes at mp) of a message of total_len bytes and compress. */
static inline void pad_and_compress(uint32_t* st, size_t i, size_t total_len)
{
    uint8_t* mp = (uint8_t*)&st[8];
    mp[i++] = 0x80;
    if (i > 56) {
        memset(mp + i, 0, 64 - i);
        sha2_256_compress(st);
        i = 0;
    }
    memset(mp + i, 0, 56 - i);
    const uint64_t bits = (uint64_t)total_len << 3;
    mp[56] = (uint8_t)(bits >> 56);
    mp[57] = (uint8_t)(bits >> 48);
    mp[58] = (uint8_t)(bits >> 40);
    mp[59] = (uint8_t)(bits >> 32);
    mp[60] = (uint8_t)(bits >> 24);
    mp[61] = (uint8_t)(bits >> 16);
    mp[62] = (uint8_t)(bits >> 8);
    mp[63] = (uint8_t)bits;
    sha2_256_compress(st);
}

int mbedtls_sha256_finish(mbedtls_sha256_context* c, unsigned char* out)
{
    if (!c->started) {
        start(c);
    }
    pad_and_compress(c->s.s, c->s.i, c->s.len);
    memcpy(out, c->s.s, 32);
    return 0;
}

int mbedtls_sha256(const unsigned char* in, size_t len, unsigned char* out, int is224)
{
    if (is224) {
        abort();
    }
    uint32_t st[8 + 16];
    const size_t total = len;
    memcpy(st, H0, 32);
    while (len >= 64) {
        memcpy(&st[8], in, 64);
        sha2_256_compress(st);
        in += 64;
        len -= 64;
    }
    memcpy(&st[8], in, len);
    pad_and_compress(st, len, total);
    memcpy(out, st, 32);
    return 0;
}
