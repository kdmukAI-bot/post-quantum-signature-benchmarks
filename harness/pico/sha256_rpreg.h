/*
 * Register-level primitives for the RP2350 SHA-256 accelerator (level 3 and the
 * microbenchmark). Against the SDK functions (sha256_compress_sdk.c) they write CSR whole
 * instead of through the set alias, wait for WDATA_RDY once per block, and read the sums
 * without the SDK's out-of-line sha256_get_result() call. Register semantics (RP2350
 * datasheet, SHA-256 accelerator): START loads the initial value and forces WDATA_RDY
 * high; after 16 words WDATA_RDY is low for 57 cycles while the block is digested;
 * SUM_VLD goes high when the sums are valid; with BSWAP set, words written as
 * little-endian loads of a byte buffer become big-endian message words.
 */
#ifndef PQB_SHA256_RPREG_H
#define PQB_SHA256_RPREG_H

#include <stdint.h>

#include "hardware/regs/sha256.h"
#include "hardware/structs/sha256.h"

#define PQB_REG_CSR_BASE (SHA256_CSR_BSWAP_BITS | (SHA256_CSR_DMA_SIZE_VALUE_32BIT << SHA256_CSR_DMA_SIZE_LSB))

static inline void reg_start(void) { sha256_hw->csr = PQB_REG_CSR_BASE | SHA256_CSR_START_BITS; }

static inline void reg_wait_ready(void)
{
    while (!(sha256_hw->csr & SHA256_CSR_WDATA_RDY_BITS)) {
    }
}

static inline void reg_wait_valid(void)
{
    while (!(sha256_hw->csr & SHA256_CSR_SUM_VLD_BITS)) {
    }
}

static inline void reg_write16(const uint32_t* w)
{
    io_wo_32* const d = &sha256_hw->wdata;
    *d = w[0]; *d = w[1]; *d = w[2]; *d = w[3];
    *d = w[4]; *d = w[5]; *d = w[6]; *d = w[7];
    *d = w[8]; *d = w[9]; *d = w[10]; *d = w[11];
    *d = w[12]; *d = w[13]; *d = w[14]; *d = w[15];
}

static inline void reg_feed(const uint32_t* w)
{
    reg_wait_ready();
    reg_write16(w);
}

static inline void reg_read8(uint32_t* s)
{
    const io_ro_32* const m = sha256_hw->sum;
    s[0] = __builtin_bswap32(m[0]); s[1] = __builtin_bswap32(m[1]);
    s[2] = __builtin_bswap32(m[2]); s[3] = __builtin_bswap32(m[3]);
    s[4] = __builtin_bswap32(m[4]); s[5] = __builtin_bswap32(m[5]);
    s[6] = __builtin_bswap32(m[6]); s[7] = __builtin_bswap32(m[7]);
}

static inline void reg_result(uint32_t* s)
{
    reg_wait_valid();
    reg_read8(s);
}

/* Clears a stale ERR_WDATA_NOT_RDY (write one to clear) and sets byte swapping */
static inline void reg_setup(void) { sha256_hw->csr = PQB_REG_CSR_BASE | SHA256_CSR_ERR_WDATA_NOT_RDY_BITS; }

#endif
