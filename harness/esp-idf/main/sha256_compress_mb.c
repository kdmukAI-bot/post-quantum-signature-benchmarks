/*
 * Microbenchmark backend for slhdsa-c's sha2_256_compress() (PQB_SLH_COMPRESS=mb, used
 * only with PQB_MICROBENCH=1). The compression path is chosen at run time, and
 * compressions inside the timed section of an operation are counted, so one image can
 * time whole operations per path and divide by the number of compressions:
 *
 *   PQB_MB_SOFT    slhdsa-c's plain-C compression
 *   PQB_MB_IDF     the SHA unit through ESP-IDF's sha_core.h calls, as
 *                  sha256_compress_hw.c
 *   PQB_MB_REG     the SHA unit through its registers (volatile accesses)
 *   PQB_MB_RELAXED the same with relaxed ordering (pqb_sha_regs_compress_relaxed())
 *   PQB_MB_SHADOW  relaxed, writing only the changed M_MEM words
 *                  (pqb_sha_regs_compress_shadow())
 *   PQB_MB_MIN     the shadow path, also skipping H_MEM writes for initial-value and
 *                  continuation blocks (pqb_sha_regs_compress_min(), sha256_hwmin.h)
 *
 * Single core only: the microbenchmark build is never a dual-core build.
 */
#include <stdbool.h>
#include <stdint.h>

#include "esp_attr.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sha/sha_core.h"
#include "sha256_hwmin.h"
#include "sha256_hwreg.h"
#include "sha256_mb.h"

void sha2_256_compress_soft(void* v);

volatile int pqb_mb_mode = PQB_MB_SOFT;
volatile uint32_t pqb_mb_count = 0;
static volatile int s_active = 0; /* inside an operation's timed core call */
static volatile int s_held = 0;   /* this build holds the SHA unit */

static void pqb_hold_engine(void)
{
    if (pqb_mb_mode != PQB_MB_SOFT) {
        esp_sha_acquire_hardware();
        sha_ll_set_mode(SHA2_256);
        pqb_mb_shadow_reset();
        pqb_mb_min_reset();
        s_held = 1;
    }
    s_active = 1;
}

static void pqb_release_engine(void)
{
    s_active = 0;
    if (s_held) {
        s_held = 0;
        esp_sha_release_hardware();
    }
}

void pqb_core_begin(void) { pqb_hold_engine(); }
void pqb_core_end(void) { pqb_release_engine(); }
void pqb_mbedtls_core_begin(void) { pqb_hold_engine(); }
void pqb_mbedtls_core_end(void) { pqb_release_engine(); }

void pqb_mb_compress_idf(uint8_t* s)
{
    esp_sha_set_mode(SHA2_256);
    esp_sha_write_digest_state(SHA2_256, s);
    esp_sha_block(SHA2_256, s + 32, false);
    esp_sha_read_digest_state(SHA2_256, s);
}

void IRAM_ATTR pqb_mb_compress_reg(uint32_t* s) { pqb_sha_regs_compress(s); }
void IRAM_ATTR pqb_mb_compress_relaxed(uint32_t* s) { pqb_sha_regs_compress_relaxed(s); }

static uint32_t s_shadow[16];
void pqb_mb_shadow_reset(void) { pqb_sha_shadow_reset(s_shadow); }
void IRAM_ATTR pqb_mb_compress_shadow(uint32_t* s)
{
    pqb_sha_regs_compress_shadow(s, s_shadow);
}

static pqb_sha_min_t s_min;
void pqb_mb_min_reset(void) { pqb_sha_min_reset(&s_min); }
void IRAM_ATTR pqb_mb_compress_min(uint32_t* s) { pqb_sha_regs_compress_min(s, &s_min); }

void sha2_256_compress(void* v)
{
    if (!s_active) {
        /* Verification and output hashing run outside the timed section: plain C,
         * uncounted */
        sha2_256_compress_soft(v);
        return;
    }
    pqb_mb_count++;
    const int mode = pqb_mb_mode;
    if (mode == PQB_MB_SOFT) {
        sha2_256_compress_soft(v);
    } else if (mode == PQB_MB_IDF) {
        pqb_mb_compress_idf((uint8_t*)v);
    } else if (mode == PQB_MB_REG) {
        pqb_mb_compress_reg((uint32_t*)v);
    } else if (mode == PQB_MB_RELAXED) {
        pqb_mb_compress_relaxed((uint32_t*)v);
    } else if (mode == PQB_MB_SHADOW) {
        pqb_mb_compress_shadow((uint32_t*)v);
    } else {
        pqb_mb_compress_min((uint32_t*)v);
    }
}
