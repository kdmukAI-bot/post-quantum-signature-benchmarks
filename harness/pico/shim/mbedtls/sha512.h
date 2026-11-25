/* mbedTLS SHA-512 one-shot API, implemented in harness/pico/sha512_slhdsa.c over
 * slhdsa-c's portable SHA-512 (one call per SLH-DSA, SPHINCS+, and SHRINCS key
 * generation). */
#pragma once
#include <stddef.h>

int mbedtls_sha512(const unsigned char* in, size_t len, unsigned char* out, int is384);
