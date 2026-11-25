/* Native-word-order SHA-256 context API over OpenSSL's ARM assembly block function; see
 * shim_native/mbedtls/sha256.h.
 *
 * Small fills avoid calls into libc: the padding zeroes are written with straight-line
 * word stores (a switch that falls through), and the one-shot copies its tail the same
 * way. On the ARM1176, a call to memset() or memcpy() for a few bytes costs more than the
 * stores themselves, mostly in the PLT stub and the library routine's setup. */
#include <stdlib.h>
#include <string.h>

#include <mbedtls/sha256.h> /* angle brackets: the SHA_API header dir, not shim/mbedtls */
#include "sha256_block.h"

#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "sha256_ctx_native.c assumes a little-endian target"
#endif

static const uint32_t SHA256_IV[8] = {
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
};

static inline void start(mbedtls_sha256_context* c)
{
    memcpy(c->head.h, SHA256_IV, sizeof(SHA256_IV));
    c->head.total = 0;
    c->head.used = 0;
    c->head.started = 1;
}

int mbedtls_sha256_starts(mbedtls_sha256_context* c, int is224)
{
    if (is224) {
        abort();
    }
    start(c);
    return 0;
}

void pqb_sha256_update_blocks(mbedtls_sha256_context* c, const unsigned char* in, size_t len)
{
    if (!c->head.started) {
        start(c);
    }
    uint8_t* b = (uint8_t*)c->buf;
    c->head.total += len;
    const uint32_t used = c->head.used;
    if (used) {
        const size_t take = 64 - used;
        if (len < take) {
            memcpy(b + used, in, len);
            c->head.used = used + (uint32_t)len;
            return;
        }
        memcpy(b + used, in, take);
        pqb_sha256_blocks(c->head.h, b, 1);
        in += take;
        len -= take;
    }
    if (len >= 64) {
        const size_t nb = len / 64;
        pqb_sha256_blocks(c->head.h, in, nb);
        in += 64 * nb;
        len -= 64 * nb;
    }
    if (len) {
        memcpy(b, in, len);
    }
    c->head.used = (uint32_t)len;
}

/* Zeroes block words first..13 (everything before the 64-bit length field). */
static inline void zero_words_to_length(uint32_t* w, uint32_t first)
{
    switch (first) {
    case 0: w[0] = 0; /* fall through */
    case 1: w[1] = 0; /* fall through */
    case 2: w[2] = 0; /* fall through */
    case 3: w[3] = 0; /* fall through */
    case 4: w[4] = 0; /* fall through */
    case 5: w[5] = 0; /* fall through */
    case 6: w[6] = 0; /* fall through */
    case 7: w[7] = 0; /* fall through */
    case 8: w[8] = 0; /* fall through */
    case 9: w[9] = 0; /* fall through */
    case 10: w[10] = 0; /* fall through */
    case 11: w[11] = 0; /* fall through */
    case 12: w[12] = 0; /* fall through */
    case 13: w[13] = 0; /* fall through */
    default: break;
    }
}

int mbedtls_sha256_finish(mbedtls_sha256_context* c, unsigned char* out)
{
    if (!c->head.started) {
        start(c);
    }
    uint8_t* b = (uint8_t*)c->buf;
    const uint64_t bits = c->head.total << 3;
    uint32_t u = c->head.used;
    b[u++] = 0x80;
    /* Zero up to the next word boundary. u <= 56 stays <= 56 (56 is a multiple of 4). */
    switch (u & 3) {
    case 1: b[u++] = 0; /* fall through */
    case 2: b[u++] = 0; /* fall through */
    case 3: b[u++] = 0; /* fall through */
    default: break;
    }
    if (u > 56) {
        /* No room for the length (u is 60 or 64): hash this block, then a zero one. */
        if (u == 60) {
            c->buf[15] = 0;
        }
        pqb_sha256_blocks(c->head.h, b, 1);
        u = 0;
    }
    zero_words_to_length(c->buf, u >> 2);
    c->buf[14] = __builtin_bswap32((uint32_t)(bits >> 32));
    c->buf[15] = __builtin_bswap32((uint32_t)bits);
    pqb_sha256_blocks(c->head.h, b, 1);

#pragma GCC unroll 8
    for (int i = 0; i < 8; i++) {
        const uint32_t w = __builtin_bswap32(c->head.h[i]);
        memcpy(out + 4 * i, &w, 4); /* one (possibly unaligned) word store */
    }
    return 0;
}

/* Copies n < 64 bytes from any address into the word-aligned block buffer w. */
static inline void copy_tail(uint32_t* w, const uint8_t* s, size_t n)
{
    const uint32_t words = (uint32_t)(n >> 2);
    uint32_t x;
#define PQB_COPY_WORD(i) memcpy(&x, s + 4 * (i), 4); w[i] = x /* one word load */
    switch (words) {
    case 15: PQB_COPY_WORD(14); /* fall through */
    case 14: PQB_COPY_WORD(13); /* fall through */
    case 13: PQB_COPY_WORD(12); /* fall through */
    case 12: PQB_COPY_WORD(11); /* fall through */
    case 11: PQB_COPY_WORD(10); /* fall through */
    case 10: PQB_COPY_WORD(9); /* fall through */
    case 9: PQB_COPY_WORD(8); /* fall through */
    case 8: PQB_COPY_WORD(7); /* fall through */
    case 7: PQB_COPY_WORD(6); /* fall through */
    case 6: PQB_COPY_WORD(5); /* fall through */
    case 5: PQB_COPY_WORD(4); /* fall through */
    case 4: PQB_COPY_WORD(3); /* fall through */
    case 3: PQB_COPY_WORD(2); /* fall through */
    case 2: PQB_COPY_WORD(1); /* fall through */
    case 1: PQB_COPY_WORD(0); /* fall through */
    default: break;
    }
#undef PQB_COPY_WORD
    uint8_t* b = (uint8_t*)w + 4 * words;
    s += 4 * words;
    switch (n & 3) {
    case 3: b[2] = s[2]; /* fall through */
    case 2: b[1] = s[1]; /* fall through */
    case 1: b[0] = s[0]; /* fall through */
    default: break;
    }
}

/* One-shot: full blocks straight from the input, then the tail through the buffer. */
int mbedtls_sha256(const unsigned char* in, size_t len, unsigned char* out, int is224)
{
    if (is224) {
        abort();
    }
    mbedtls_sha256_context c;
    start(&c);
    c.head.total = len;
    const size_t nb = len / 64;
    if (nb) {
        pqb_sha256_blocks(c.head.h, in, nb);
    }
    c.head.used = (uint32_t)(len - 64 * nb);
    copy_tail(c.buf, in + 64 * nb, c.head.used);
    return mbedtls_sha256_finish(&c, out);
}
