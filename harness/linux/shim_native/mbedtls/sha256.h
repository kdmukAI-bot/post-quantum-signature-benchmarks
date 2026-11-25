/*
 * Native-word-order SHA-256 API for the SHRINCS and XMSS scheme code on the Pi
 * (SHA_API=native), replacing the OpenSSL-backed mbedTLS shim in shim/mbedtls/sha256.h.
 *
 * Implemented in shim/sha256_ctx_native.c directly over OpenSSL's ARM assembly block
 * function (shim/sha256_block.h), so it needs COMPRESS=asm or COMPRESS=asmrev. The
 * chaining state is kept in native word order, so no byte swapping happens between
 * blocks, only when the digest is written out. Full blocks are hashed straight from the
 * caller's buffer.
 *
 * init, clone, and the common case of update (the input fits in the partial block) are
 * inline functions here. With link-time optimization (OPT=...-lto), the scheme's update
 * calls with constant lengths then become inline copies instead of calls to memcpy().
 *
 * An unstarted context (Jade's mbedtls_sha256_init() without starts()) is treated as
 * SHA-256, which is what upstream shrincs-c computes. SHA-224 is not used by the scheme
 * code and is rejected.
 */
#ifndef PQB_NATIVE_MBEDTLS_SHA256_H
#define PQB_NATIVE_MBEDTLS_SHA256_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    uint32_t h[8];   /* chaining state, native word order */
    uint64_t total;  /* bytes hashed so far */
    uint32_t used;   /* bytes waiting in buf */
    uint32_t started;
} pqb_sha256_head_t;

typedef struct {
    pqb_sha256_head_t head;
    uint32_t buf[16]; /* partial block; uint32_t for alignment */
} mbedtls_sha256_context;

/* The general case of update (starts an unstarted context, fills and hashes blocks). */
void pqb_sha256_update_blocks(mbedtls_sha256_context* c, const unsigned char* in, size_t len);

static inline void mbedtls_sha256_init(mbedtls_sha256_context* c)
{
    c->head.total = 0;
    c->head.used = 0;
    c->head.started = 0;
}

static inline void mbedtls_sha256_free(mbedtls_sha256_context* c) { (void)c; }

/* Copies the fixed-size head and only the buffered bytes, not the whole block buffer. */
static inline void mbedtls_sha256_clone(mbedtls_sha256_context* dst,
                                        const mbedtls_sha256_context* src)
{
    dst->head = src->head;
    if (src->head.used) {
        memcpy(dst->buf, src->buf, src->head.used);
    }
}

static inline int mbedtls_sha256_update(mbedtls_sha256_context* c, const unsigned char* in,
                                        size_t len)
{
    const size_t used = c->head.used;
    if (c->head.started && len < 64 && used + len < 64) {
        memcpy((uint8_t*)c->buf + used, in, len);
        c->head.used = used + (uint32_t)len;
        c->head.total += len;
        return 0;
    }
    pqb_sha256_update_blocks(c, in, len);
    return 0;
}

int mbedtls_sha256_starts(mbedtls_sha256_context* c, int is224);
int mbedtls_sha256_finish(mbedtls_sha256_context* c, unsigned char* out);
int mbedtls_sha256(const unsigned char* in, size_t len, unsigned char* out, int is224);

#endif
