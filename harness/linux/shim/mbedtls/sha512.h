/* mbedTLS SHA-512 one-shot shim backed by OpenSSL (see sha256.h). */
#ifndef PQ_BENCH_SHIM_MBEDTLS_SHA512_H
#define PQ_BENCH_SHIM_MBEDTLS_SHA512_H

#include <stddef.h>

int mbedtls_sha512(const unsigned char* in, size_t len, unsigned char* out, int is384);

#endif
