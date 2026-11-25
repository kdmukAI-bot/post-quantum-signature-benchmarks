/*
 * OpenSSL's ARM SHA-256 block function, assembled from shim/openssl-armv4/sha256-armv4.S
 * and renamed at assembly time (sha256_block_data_order -> pqb_sha256_blocks), so it
 * cannot clash with the copy inside libcrypto.
 *
 * state: the eight chaining words in native (little-endian) word order, updated in place.
 * in:    num consecutive 64-byte message blocks, in any alignment.
 */
#ifndef PQB_SHA256_BLOCK_H
#define PQB_SHA256_BLOCK_H

#include <stddef.h>
#include <stdint.h>

void pqb_sha256_blocks(uint32_t state[8], const void* in, size_t num);

#endif
