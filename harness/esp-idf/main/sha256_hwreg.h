/*
 * Register-level SHA-256 compression on the ESP32 SHA unit (ESP32-S3 and ESP32-P4),
 * shared by the hwreg backend (sha256_compress_hwreg.c) and the microbenchmark.
 *
 * It does the same register sequence as ESP-IDF's esp_sha_write_digest_state(),
 * esp_sha_block(), and esp_sha_read_digest_state(), without the per-call function layers:
 *
 *   write the 8 state words to H_MEM, write the 16 block words to M_MEM, write
 *   SHA_CONTINUE_REG (resume from H_MEM), poll SHA_BUSY_REG, read the 8 words of H_MEM.
 *
 * Byte order: ESP-IDF's low-level layer copies words between memory and the H_MEM and
 * M_MEM registers unchanged (sha_ll_write_digest(), sha_ll_fill_text_block(), and
 * sha_ll_read_digest() on both chips), so this does the same. slhdsa-c's state buffer
 * holds big-endian bytes, which is the order the unit uses.
 *
 * Preconditions: the caller holds the unit (esp_sha_acquire_hardware()), has set the mode
 * to SHA2_256 since acquiring it (acquiring resets the unit), and the unit is idle. The
 * ESP-IDF read path also aborts when the digest reads back as all zeros (a
 * fault-injection check); these paths do not.
 *
 * Three variants:
 *   pqb_sha_regs_compress()         volatile accesses throughout, as ESP-IDF does
 *   pqb_sha_regs_compress_relaxed() plain loads and stores to H_MEM and M_MEM with one
 *                                   barrier before the start write and one after it.
 *                                   Xtensa GCC puts a MEMW before every volatile access
 *                                   (-mserialize-volatile is its default), which makes
 *                                   each register write wait for the previous one to
 *                                   complete. On RISC-V the generated loads and stores
 *                                   are the same as the volatile ones.
 *   pqb_sha_regs_compress_shadow()  relaxed, and writes only the M_MEM words that differ
 *                                   from the previous block. This relies on the unit
 *                                   leaving M_MEM unchanged when it hashes a block, which
 *                                   the microbenchmark checks (#mbmkeep). The caller
 *                                   keeps the shadow copy and must reset it
 *                                   (pqb_sha_shadow_reset()) whenever the unit is
 *                                   acquired.
 */
#pragma once

#include <stdint.h>

#include "hal/sha_ll.h"
#include "hal/sha_types.h"
#include "soc/hwcrypto_reg.h"

#if defined(SHA_H_MEM)
#define PQB_SHA_H_ADDR SHA_H_MEM /* ESP32-P4 register names */
#define PQB_SHA_M_ADDR SHA_M_MEM
#else
#define PQB_SHA_H_ADDR SHA_H_BASE /* ESP32-S3 register names */
#define PQB_SHA_M_ADDR SHA_TEXT_BASE
#endif

#if defined(__XTENSA__)
#define PQB_IO_BARRIER() __asm__ __volatile__("memw" ::: "memory")
#else
#define PQB_IO_BARRIER() __asm__ __volatile__("" ::: "memory")
#endif

static inline __attribute__((always_inline)) void pqb_sha_regs_compress(uint32_t* s)
{
    volatile uint32_t* const h = (volatile uint32_t*)(PQB_SHA_H_ADDR);
    volatile uint32_t* const m = (volatile uint32_t*)(PQB_SHA_M_ADDR);

    h[0] = s[0];
    h[1] = s[1];
    h[2] = s[2];
    h[3] = s[3];
    h[4] = s[4];
    h[5] = s[5];
    h[6] = s[6];
    h[7] = s[7];
    m[0] = s[8];
    m[1] = s[9];
    m[2] = s[10];
    m[3] = s[11];
    m[4] = s[12];
    m[5] = s[13];
    m[6] = s[14];
    m[7] = s[15];
    m[8] = s[16];
    m[9] = s[17];
    m[10] = s[18];
    m[11] = s[19];
    m[12] = s[20];
    m[13] = s[21];
    m[14] = s[22];
    m[15] = s[23];
    sha_ll_continue_block(SHA2_256);
    while (sha_ll_busy()) {
    }
    s[0] = h[0];
    s[1] = h[1];
    s[2] = h[2];
    s[3] = h[3];
    s[4] = h[4];
    s[5] = h[5];
    s[6] = h[6];
    s[7] = h[7];
}

/* Start the block and wait for it, then read the state back with plain loads. */
static inline __attribute__((always_inline)) void pqb_sha_regs_run_read(uint32_t* s)
{
    uint32_t* const h = (uint32_t*)(PQB_SHA_H_ADDR);
    PQB_IO_BARRIER(); /* every H_MEM and M_MEM write lands before the start write */
    sha_ll_continue_block(SHA2_256);
    PQB_IO_BARRIER(); /* the start write lands before the first busy read */
    while (sha_ll_busy()) {
    }
    PQB_IO_BARRIER();
    s[0] = h[0];
    s[1] = h[1];
    s[2] = h[2];
    s[3] = h[3];
    s[4] = h[4];
    s[5] = h[5];
    s[6] = h[6];
    s[7] = h[7];
}

static inline __attribute__((always_inline)) void pqb_sha_regs_write_h(const uint32_t* s)
{
    uint32_t* const h = (uint32_t*)(PQB_SHA_H_ADDR);
    h[0] = s[0];
    h[1] = s[1];
    h[2] = s[2];
    h[3] = s[3];
    h[4] = s[4];
    h[5] = s[5];
    h[6] = s[6];
    h[7] = s[7];
}

static inline __attribute__((always_inline)) void pqb_sha_regs_compress_relaxed(uint32_t* s)
{
    uint32_t* const m = (uint32_t*)(PQB_SHA_M_ADDR);
    PQB_IO_BARRIER();
    pqb_sha_regs_write_h(s);
    m[0] = s[8];
    m[1] = s[9];
    m[2] = s[10];
    m[3] = s[11];
    m[4] = s[12];
    m[5] = s[13];
    m[6] = s[14];
    m[7] = s[15];
    m[8] = s[16];
    m[9] = s[17];
    m[10] = s[18];
    m[11] = s[19];
    m[12] = s[20];
    m[13] = s[21];
    m[14] = s[22];
    m[15] = s[23];
    pqb_sha_regs_run_read(s);
}

/* Write zeros to M_MEM and match the shadow to them. Call after acquiring the unit. */
static inline void pqb_sha_shadow_reset(uint32_t* shadow)
{
    uint32_t* const m = (uint32_t*)(PQB_SHA_M_ADDR);
    PQB_IO_BARRIER();
    for (int i = 0; i < 16; i++) {
        m[i] = 0;
        shadow[i] = 0;
    }
    PQB_IO_BARRIER();
}

#define PQB_SHADOW_WORD(i)                                                               \
    do {                                                                                 \
        const uint32_t w_ = s[8 + (i)];                                                  \
        if (w_ != shadow[(i)]) {                                                         \
            m[(i)] = w_;                                                                 \
            shadow[(i)] = w_;                                                            \
        }                                                                                \
    } while (0)

static inline __attribute__((always_inline)) void pqb_sha_regs_compress_shadow(
    uint32_t* s, uint32_t* shadow)
{
    uint32_t* const m = (uint32_t*)(PQB_SHA_M_ADDR);
    PQB_IO_BARRIER();
    pqb_sha_regs_write_h(s);
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
    pqb_sha_regs_run_read(s);
}
