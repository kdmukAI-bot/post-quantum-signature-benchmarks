/*
 * mbedTLS SHA-256 API shim backed by OpenSSL (implemented in shim/mbedtls_shim.c), for
 * building Blockstream's Jade benchmark scheme code
 * (third_party/jade-hbs/main/{shrincs,xmss}) on Linux. OpenSSL's headers stay out of this
 * file because SHRINCS defines its own SHA256_CTX type.
 *
 * The Jade port of SHRINCS calls mbedtls_sha256_init() without mbedtls_sha256_starts()
 * before hashing in several places (upstream shrincs-c calls SHA256_Init() there). What
 * an unstarted context computes depends on the mbedTLS backend:
 *   - default here: treat it as SHA-256 (what upstream shrincs-c computes);
 *   - SHIM_EMULATE_ESP_UNSTARTED_SHA1: mimic ESP-IDF's hardware SHA driver, where a zeroed
 *     context has mode 0 (SHA1 in the chip's SHA_TYPE enum), so the hardware computes
 *     SHA-1 and finish() returns the 20-byte digest followed by 12 zero bytes.
 */
#ifndef PQ_BENCH_SHIM_MBEDTLS_SHA256_H
#define PQ_BENCH_SHIM_MBEDTLS_SHA256_H

#include <stddef.h>

/* Opaque storage for OpenSSL's SHA256_CTX and SHA_CTX (plain structs, safe to copy);
 * sizes are checked in mbedtls_shim.c. */
typedef struct {
    int mode;
    unsigned long long s256[16];
    unsigned long long s1[16];
} mbedtls_sha256_context;

void mbedtls_sha256_init(mbedtls_sha256_context* c);
void mbedtls_sha256_free(mbedtls_sha256_context* c);
void mbedtls_sha256_clone(mbedtls_sha256_context* dst, const mbedtls_sha256_context* src);
int mbedtls_sha256_starts(mbedtls_sha256_context* c, int is224);
int mbedtls_sha256_update(mbedtls_sha256_context* c, const unsigned char* in, size_t len);
int mbedtls_sha256_finish(mbedtls_sha256_context* c, unsigned char* out);
int mbedtls_sha256(const unsigned char* in, size_t len, unsigned char* out, int is224);

#endif
