/*
 * Replacement for slhdsa-c's sha2_256_compress() that calls OpenSSL's ARM assembly block
 * function directly (shim/sha256_block.h), rather than through SHA256_Transform() in the
 * shared libcrypto. Used by COMPRESS=asm and COMPRESS=asmrev, which differ only in how
 * the assembly loads message words.
 *
 * Layout (from slh_dsa/sha2_256.c): v points to 8 state words then a 64-byte message
 * block, all stored as big-endian bytes, inside a uint32_t array (so v is 4-byte
 * aligned). The assembly wants the state in native word order, so the eight state words
 * are byte-swapped in place before and after the call. No copy of the state is made. The
 * swap loops are unrolled explicitly: at -O2, GCC keeps them as loops, and on the ARM1176
 * each iteration then waits on its load, which made this wrapper cost about 135 cycles
 * per call.
 *
 * The function is kept out of line (noinline). With link-time optimization, GCC otherwise
 * inlines it into slhdsa-c's WOTS chain loop, where few registers are free, and the
 * sixteen swaps become a serial load, rev, store sequence that stalls on every load. That
 * made SLH-DSA signing take 1.7% more CPU time than with the call.
 */
#include <stdint.h>

#include "sha256_block.h"

#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "sha256_compress_asm.c assumes a little-endian target"
#endif

__attribute__((noinline)) void sha2_256_compress(void* v)
{
    uint32_t* s = (uint32_t*)v;
#pragma GCC unroll 8
    for (int i = 0; i < 8; i++) {
        s[i] = __builtin_bswap32(s[i]);
    }
    pqb_sha256_blocks(s, s + 8, 1);
#pragma GCC unroll 8
    for (int i = 0; i < 8; i++) {
        s[i] = __builtin_bswap32(s[i]);
    }
}
