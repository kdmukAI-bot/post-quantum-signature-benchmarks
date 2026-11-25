/*
 * Direct SHA-256 API for the SHRINCS and XMSS scheme code on Linux (SHA_API=direct),
 * replacing the OpenSSL-backed mbedTLS shim in shim/mbedtls/sha256.h. The Pi counterpart
 * of harness/esp-idf/main/shim_direct/.
 *
 * Implemented in shim/sha256_ctx_direct.c on top of slhdsa-c's incremental SHA-256, whose
 * compression function is the one selected with COMPRESS (sha2_256_compress()).
 *
 * An unstarted context (Jade's mbedtls_sha256_init() without starts()) is treated as
 * SHA-256, which is what upstream shrincs-c computes. SHA-224 is not used by the scheme
 * code and is rejected.
 */
#ifndef PQB_DIRECT_MBEDTLS_SHA256_H
#define PQB_DIRECT_MBEDTLS_SHA256_H

#include <stddef.h>

#include "slh_dsa/sha2_api.h"

typedef struct {
    int started;
    sha2_256_t s;
} mbedtls_sha256_context;

void mbedtls_sha256_init(mbedtls_sha256_context* c);
void mbedtls_sha256_free(mbedtls_sha256_context* c);
void mbedtls_sha256_clone(mbedtls_sha256_context* dst, const mbedtls_sha256_context* src);
int mbedtls_sha256_starts(mbedtls_sha256_context* c, int is224);
int mbedtls_sha256_update(mbedtls_sha256_context* c, const unsigned char* in, size_t len);
int mbedtls_sha256_finish(mbedtls_sha256_context* c, unsigned char* out);
int mbedtls_sha256(const unsigned char* in, size_t len, unsigned char* out, int is224);

#endif
