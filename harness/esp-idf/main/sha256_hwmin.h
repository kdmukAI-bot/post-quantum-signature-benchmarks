/*
 * Register-level SHA-256 compression with the fewest register writes
 * (PQB_SLH_COMPRESS=hwmin and the microbenchmark's "min" path). Builds on sha256_hwreg.h.
 *
 * In addition to writing only the M_MEM words that changed (as the shadow path does), it
 * avoids the 8 H_MEM writes in two cases:
 *   - the input state is the SHA-256 initial value: SHA_START_REG makes the unit use its
 *     built-in initial value (ESP-IDF uses it for the first block of every message);
 *   - the input state equals the previous output, which H_MEM still holds (the second and
 *     later blocks of a multi-block message): SHA_CONTINUE_REG without rewriting H_MEM.
 * Otherwise it writes H_MEM and uses SHA_CONTINUE_REG, as the other paths do.
 *
 * The shadow (pqb_sha_min_t) mirrors M_MEM and H_MEM exactly: pqb_sha_min_reset() writes
 * zeros to both and must be called whenever the unit is acquired, and every compression
 * through this path updates it. No other code may touch the unit while it is in use.
 */
#pragma once

#include <stdint.h>

#include "sha256_hwreg.h"

typedef struct {
    uint32_t m[16]; /* M_MEM as last written */
    uint32_t h[8];  /* H_MEM: the last output read back */
} pqb_sha_min_t;

/* SHA-256 initial value as slhdsa-c stores it: big-endian bytes, read as little-endian
 * words (bytes 6a 09 e6 67 are the word 0x67e6096a). */
#define PQB_IV0 0x67e6096au
#define PQB_IV1 0x85ae67bbu
#define PQB_IV2 0x72f36e3cu
#define PQB_IV3 0x3af54fa5u
#define PQB_IV4 0x7f520e51u
#define PQB_IV5 0x8c68059bu
#define PQB_IV6 0xabd9831fu
#define PQB_IV7 0x19cde05bu

static inline void pqb_sha_min_reset(pqb_sha_min_t* sh)
{
    uint32_t* const h = (uint32_t*)(PQB_SHA_H_ADDR);
    uint32_t* const m = (uint32_t*)(PQB_SHA_M_ADDR);
    PQB_IO_BARRIER();
    for (int i = 0; i < 8; i++) {
        h[i] = 0;
        sh->h[i] = 0;
    }
    for (int i = 0; i < 16; i++) {
        m[i] = 0;
        sh->m[i] = 0;
    }
    PQB_IO_BARRIER();
}

static inline __attribute__((always_inline)) int pqb_state_is_iv(const uint32_t* s)
{
    return s[0] == PQB_IV0 && s[1] == PQB_IV1 && s[2] == PQB_IV2 && s[3] == PQB_IV3 &&
           s[4] == PQB_IV4 && s[5] == PQB_IV5 && s[6] == PQB_IV6 && s[7] == PQB_IV7;
}

static inline __attribute__((always_inline)) int pqb_state_eq(const uint32_t* a,
                                                               const uint32_t* b)
{
    return a[0] == b[0] && a[1] == b[1] && a[2] == b[2] && a[3] == b[3] && a[4] == b[4] &&
           a[5] == b[5] && a[6] == b[6] && a[7] == b[7];
}

static inline __attribute__((always_inline)) void
pqb_sha_regs_compress_min(uint32_t* s, pqb_sha_min_t* sh)
{
    uint32_t* const h = (uint32_t*)(PQB_SHA_H_ADDR);
    uint32_t* const m = (uint32_t*)(PQB_SHA_M_ADDR);
    uint32_t* const shadow = sh->m;
    int start = 0;

    PQB_IO_BARRIER();
    if (pqb_state_eq(s, sh->h)) {
        /* H_MEM already holds this state */
    } else if (pqb_state_is_iv(s)) {
        start = 1;
    } else {
        pqb_sha_regs_write_h(s);
    }
    PQB_SHADOW_WORD(0);
    PQB_SHADOW_WORD(1);
    PQB_SHADOW_WORD(2);
    PQB_SHADOW_WORD(3);
    PQB_SHADOW_WORD(4);
    PQB_SHADOW_WORD(5);
    PQB_SHADOW_WORD(6);
    PQB_SHADOW_WORD(7);
    PQB_SHADOW_WORD(8);
    PQB_SHADOW_WORD(9);
    PQB_SHADOW_WORD(10);
    PQB_SHADOW_WORD(11);
    PQB_SHADOW_WORD(12);
    PQB_SHADOW_WORD(13);
    PQB_SHADOW_WORD(14);
    PQB_SHADOW_WORD(15);
    PQB_IO_BARRIER(); /* every H_MEM and M_MEM write lands before the start write */
    if (start) {
        sha_ll_start_block(SHA2_256);
    } else {
        sha_ll_continue_block(SHA2_256);
    }
    PQB_IO_BARRIER(); /* the start write lands before the first busy read */
    while (sha_ll_busy()) {
    }
    PQB_IO_BARRIER();
    for (int i = 0; i < 8; i++) {
        const uint32_t w = h[i];
        s[i] = w;
        sh->h[i] = w;
    }
}
