/*
 * Wrapper over ESP-IDF's mbedtls/sha256.h.
 *
 * The Jade port of SHRINCS calls mbedtls_sha256_init() without mbedtls_sha256_starts()
 * before hashing in several places, where upstream shrincs-c calls SHA256_Init(). With
 * ESP-IDF's hardware SHA driver a zeroed context has mode 0, which is SHA1 in the chip's
 * SHA_TYPE enum. Unless PQB_JADE_SHA_SEMANTICS is defined, every init here also starts a
 * SHA-256 context, which gives upstream's results (init followed by clone or starts is
 * unaffected).
 */
#pragma once
#include_next <mbedtls/sha256.h>

#ifndef PQB_JADE_SHA_SEMANTICS
static inline void pqb_sha256_init_started(mbedtls_sha256_context* ctx)
{
    mbedtls_sha256_init(ctx);
    mbedtls_sha256_starts(ctx, 0);
}
#define mbedtls_sha256_init(ctx) pqb_sha256_init_started(ctx)
#endif
