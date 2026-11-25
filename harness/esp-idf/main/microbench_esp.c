/*
 * SHA-256 compression microbenchmark (PQB_MICROBENCH=1, with PQB_SLH_COMPRESS=mb).
 *
 * Part 1 times N compressions of one buffer per path, in CPU cycles per compression:
 *   soft         slhdsa-c's plain-C compression
 *   idf          the SHA unit through ESP-IDF's sha_core.h calls (set mode, write state,
 *                block, read state), as sha256_compress_hw.c does per compression
 *   idf_nomode   the same without the set-mode call
 *   reg          the SHA unit through its registers (sha256_hwreg.h), in IRAM
 *   relaxed      the same with relaxed ordering (one barrier before and after the start)
 *   shadow       relaxed, writing only the M_MEM words that changed; timed twice, once on
 *                one repeated block (no M_MEM writes after the first) and once on a block
 *                that changes in 5 of 16 words per call, as in slhdsa-c's WOTS+ chain
 *                loop
 *   min_chain    the min path (sha256_hwmin.h) on the same changing block; the state
 *                carries over between calls here, so every call is a continuation with 5
 *                changed words
 *   min_cont     the min path when each block continues from the previous output
 *   min_iv       the min path when each block starts from the initial value
 *   dispatch_reg the microbenchmark's sha2_256_compress() dispatcher in front of reg
 * and the pieces of the register path:
 *   reg_write24  writing the 8 state and 16 block words only
 *   reg_read8    reading the 8 state words only
 *   reg_run      SHA_CONTINUE_REG plus polling SHA_BUSY_REG until idle (no data transfer)
 *   reg_busy1    one SHA_BUSY_REG read
 * Part 2 repeats soft and reg on core 0 while a task on core 1 runs plain-C compressions,
 * and reports the core 1 rate too (the hybrid dual-core setting).
 * Part 3 checks that soft, idf, reg, relaxed, and shadow give identical state for 1000
 * pseudo-random inputs, and that the unit leaves M_MEM unchanged after hashing a block.
 * Part 4 runs whole signing operations (run 0 inputs) per path, counts the compressions
 * in the timed section, and reports cycles per compression including the scheme's own
 * work.
 *
 * Output lines start with '#' so scripts/summarize.py ignores them:
 *   #mb,<target>,<name>,<n>,<cycles per compression (cycle counter)>,<from esp_timer>
 *   #mbcore1,<target>,<n>,<cycles per compression on core 1>
 *   #mbcheck,<target>,<inputs>,<mismatches idf>,<mismatches reg>,<relaxed>,<shadow>
 *   #mbmkeep,<target>,<blocks>,<M_MEM words changed by hashing>
 *   #mbcheckmin,<target>,<inputs>,<mismatches of the min path>
 *   #mbop,<target>,<path>,<op>,<compressions>,<wall_s>,<cycles per compression>,
 *         <out sha256>,<verified>
 *   #mbcold,<target>,<variant>,<n>,<mismatches>,<outputs equal to the input state>
 * Part 5 (part_cold(), run first) tests the path that takes the unit for one compression.
 * Compile with -DPQB_MB_QUICK (PQB_COPTS) to run part 5 only.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "common.h"
#include "esp_cpu.h"
#include "esp_private/esp_clk.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "sha/sha_core.h"
#include "sha256_hwmin.h"
#include "sha256_hwreg.h"
#include "sha256_mb.h"
#include "sdkconfig.h"

void sha2_256_compress_soft(void* v);
void sha2_256_compress(void* v);

#define MB_N 20000
#define MB_STACK_BYTES (48 * 1024)

static uint32_t s_buf[24] __attribute__((aligned(16)));
static uint32_t s_buf1[24] __attribute__((aligned(16)));
static double s_cpu_hz;
static volatile int s_core1_run;
static volatile uint32_t s_core1_count;
static volatile int64_t s_core1_t0, s_core1_t1;

static void fill(uint32_t* b, uint32_t seed)
{
    uint32_t x = seed * 2654435761u + 1;
    for (int i = 0; i < 24; i++) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        b[i] = x;
    }
}

static void report(const char* name, int n, uint32_t c0, uint32_t c1, int64_t t0, int64_t t1)
{
    printf("#mb,%s,%s,%d,%.1f,%.1f\n", CONFIG_IDF_TARGET, name, n, (double)(c1 - c0) / n,
           (double)(t1 - t0) * 1e-6 * s_cpu_hz / n);
    fflush(stdout);
}

#define TIME_LOOP(name, body)                                                            \
    do {                                                                                 \
        fill(s_buf, 1);                                                                  \
        const int64_t t0_ = esp_timer_get_time();                                        \
        const uint32_t c0_ = esp_cpu_get_cycle_count();                                  \
        for (int i_ = 0; i_ < MB_N; i_++) {                                              \
            body;                                                                        \
        }                                                                                \
        const uint32_t c1_ = esp_cpu_get_cycle_count();                                  \
        const int64_t t1_ = esp_timer_get_time();                                        \
        report(name, MB_N, c0_, c1_, t0_, t1_);                                          \
    } while (0)

static void IRAM_ATTR reg_write24(uint32_t* s)
{
    volatile uint32_t* const h = (volatile uint32_t*)(PQB_SHA_H_ADDR);
    volatile uint32_t* const m = (volatile uint32_t*)(PQB_SHA_M_ADDR);
    for (int i = 0; i < 8; i++) {
        h[i] = s[i];
    }
    for (int i = 0; i < 16; i++) {
        m[i] = s[8 + i];
    }
}

static void IRAM_ATTR reg_read8(uint32_t* s)
{
    volatile uint32_t* const h = (volatile uint32_t*)(PQB_SHA_H_ADDR);
    for (int i = 0; i < 8; i++) {
        s[i] = h[i];
    }
}

static uint32_t s_polls;

static void IRAM_ATTR reg_run(void)
{
    sha_ll_continue_block(SHA2_256);
    while (sha_ll_busy()) {
        s_polls++;
    }
}

static void IRAM_ATTR reg_busy1(void) { (void)sha_ll_busy(); }

static void core1_load_task(void* arg)
{
    (void)arg;
    fill(s_buf1, 7);
    uint32_t n = 0;
    s_core1_t0 = esp_timer_get_time();
    while (s_core1_run) {
        sha2_256_compress_soft(s_buf1);
        n++;
    }
    s_core1_t1 = esp_timer_get_time();
    s_core1_count = n;
    s_core1_run = -1;
    vTaskDelete(NULL);
}

static void part_compress(const char* suffix)
{
    char name[48];
    snprintf(name, sizeof(name), "soft%s", suffix);
    TIME_LOOP(name, sha2_256_compress_soft(s_buf));

    esp_sha_acquire_hardware();
    sha_ll_set_mode(SHA2_256);
    if (!suffix[0]) {
        TIME_LOOP("idf", pqb_mb_compress_idf((uint8_t*)s_buf));
        TIME_LOOP("idf_nomode", {
            esp_sha_write_digest_state(SHA2_256, s_buf);
            esp_sha_block(SHA2_256, s_buf + 8, false);
            esp_sha_read_digest_state(SHA2_256, s_buf);
        });
        sha_ll_set_mode(SHA2_256);
    }
    snprintf(name, sizeof(name), "reg%s", suffix);
    TIME_LOOP(name, pqb_mb_compress_reg(s_buf));
    snprintf(name, sizeof(name), "relaxed%s", suffix);
    TIME_LOOP(name, pqb_mb_compress_relaxed(s_buf));
    pqb_mb_shadow_reset();
    snprintf(name, sizeof(name), "shadow_same%s", suffix);
    TIME_LOOP(name, pqb_mb_compress_shadow(s_buf));
    pqb_mb_shadow_reset();
    snprintf(name, sizeof(name), "shadow_chain%s", suffix);
    TIME_LOOP(name, {
        s_buf[12] ^= (uint32_t)i_;
        s_buf[13] = s_buf[0];
        s_buf[14] = s_buf[1];
        s_buf[15] = s_buf[2];
        s_buf[16] = s_buf[3];
        pqb_mb_compress_shadow(s_buf);
    });
    pqb_mb_min_reset();
    snprintf(name, sizeof(name), "min_chain%s", suffix);
    TIME_LOOP(name, {
        s_buf[12] ^= (uint32_t)i_;
        s_buf[13] = s_buf[0];
        s_buf[14] = s_buf[1];
        s_buf[15] = s_buf[2];
        s_buf[16] = s_buf[3];
        pqb_mb_compress_min(s_buf);
    });
    snprintf(name, sizeof(name), "min_cont%s", suffix);
    TIME_LOOP(name, {
        s_buf[12] ^= (uint32_t)i_;
        pqb_mb_compress_min(s_buf);
    });
    snprintf(name, sizeof(name), "min_iv%s", suffix);
    TIME_LOOP(name, {
        s_buf[0] = PQB_IV0;
        s_buf[1] = PQB_IV1;
        s_buf[2] = PQB_IV2;
        s_buf[3] = PQB_IV3;
        s_buf[4] = PQB_IV4;
        s_buf[5] = PQB_IV5;
        s_buf[6] = PQB_IV6;
        s_buf[7] = PQB_IV7;
        s_buf[12] ^= (uint32_t)i_;
        pqb_mb_compress_min(s_buf);
    });
    if (!suffix[0]) {
        TIME_LOOP("reg_write24", reg_write24(s_buf));
        TIME_LOOP("reg_read8", reg_read8(s_buf));
        s_polls = 0;
        TIME_LOOP("reg_run", reg_run());
        printf("#mbpolls,%s,%.2f\n", CONFIG_IDF_TARGET, (double)s_polls / MB_N);
        TIME_LOOP("reg_busy1", reg_busy1());
    }
    esp_sha_release_hardware();
}

static void part_check(void)
{
    uint32_t a[24], b[24], c[24], d[24], e[24], prev[24];
    int bad_idf = 0, bad_reg = 0, bad_relaxed = 0, bad_shadow = 0;
    esp_sha_acquire_hardware();
    sha_ll_set_mode(SHA2_256);
    for (uint32_t k = 0; k < 1000; k++) {
        fill(a, k + 100);
        memcpy(b, a, sizeof(a));
        memcpy(c, a, sizeof(a));
        memcpy(d, a, sizeof(a));
        sha2_256_compress_soft(a);
        pqb_mb_compress_idf((uint8_t*)b);
        pqb_mb_compress_reg(c);
        pqb_mb_compress_relaxed(d);
        bad_idf += memcmp(a, b, 32) != 0;
        bad_reg += memcmp(a, c, 32) != 0;
        bad_relaxed += memcmp(a, d, 32) != 0;
    }

    /* Shadow path: consecutive blocks share 0, 10, or 15 of their 16 words, and nothing
     * else touches the unit in between. */
    pqb_mb_shadow_reset();
    memset(prev, 0, sizeof(prev));
    for (uint32_t k = 0; k < 1000; k++) {
        fill(a, k + 2000);
        if (k % 3 == 1) {
            memcpy(a + 8, prev + 8, 40);
        } else if (k % 3 == 2) {
            memcpy(a + 8, prev + 8, 60);
        }
        memcpy(prev, a, sizeof(a));
        memcpy(e, a, sizeof(a));
        sha2_256_compress_soft(a);
        pqb_mb_compress_shadow(e);
        bad_shadow += memcmp(a, e, 32) != 0;
    }

    /* Min path: mix of fresh states, initial-value states, and continuations of the
     * previous output, with blocks sharing words as above. */
    int bad_min = 0;
    pqb_mb_min_reset();
    memset(prev, 0, sizeof(prev));
    for (uint32_t k = 0; k < 3000; k++) {
        fill(a, k + 7000);
        if (k % 3 == 1) {
            memcpy(a + 8, prev + 8, 40);
        }
        if (k % 4 == 1) {
            memcpy(a, prev, 32); /* prev holds the previous output here */
        } else if (k % 4 == 2) {
            const uint32_t iv[8] = { PQB_IV0, PQB_IV1, PQB_IV2, PQB_IV3,
                                     PQB_IV4, PQB_IV5, PQB_IV6, PQB_IV7 };
            memcpy(a, iv, 32);
        }
        memcpy(e, a, sizeof(a));
        memcpy(prev + 8, a + 8, 64);
        sha2_256_compress_soft(a);
        pqb_mb_compress_min(e);
        bad_min += memcmp(a, e, 32) != 0;
        memcpy(prev, e, 32);
    }
    printf("#mbcheckmin,%s,3000,%d\n", CONFIG_IDF_TARGET, bad_min);

    /* Does hashing a block leave M_MEM as written? */
    int changed = 0;
    volatile uint32_t* const m = (volatile uint32_t*)(PQB_SHA_M_ADDR);
    for (uint32_t k = 0; k < 1000; k++) {
        fill(a, k + 5000);
        pqb_mb_compress_reg(a);
        for (int i = 0; i < 16; i++) {
            changed += m[i] != a[8 + i];
        }
    }
    esp_sha_release_hardware();
    printf("#mbcheck,%s,1000,%d,%d,%d,%d\n", CONFIG_IDF_TARGET, bad_idf, bad_reg, bad_relaxed,
           bad_shadow);
    printf("#mbmkeep,%s,1000,%d\n", CONFIG_IDF_TARGET, changed);
    fflush(stdout);
}

static void part_ops(void)
{
    static const char* const OPS[] = { "slh_dsa_sign", "sphincs40_sign", "shrincs_sign",
                                       "xmss_sign" };
    static const char* const PATHS[] = { "soft", "idf", "reg", "relaxed", "shadow", "min" };
    for (int p = 0; p < 6; p++) {
        for (size_t o = 0; o < sizeof(OPS) / sizeof(OPS[0]); o++) {
            op_result_t r;
            memset(&r, 0, sizeof(r));
            pqb_mb_mode = p;
            pqb_mb_count = 0;
#if defined(SHRINCS_L)
            const uint32_t swn = 96;
#else
            const uint32_t swn = 2040;
#endif
            int handled = run_slh_op(OPS[o], 0, &r);
            if (!handled) {
                handled = run_shrincs_op(OPS[o], 0, swn, &r);
            }
            if (!handled) {
                handled = run_xmss_op(OPS[o], 0, &r);
            }
            const uint32_t count = pqb_mb_count;
            pqb_mb_mode = PQB_MB_SOFT;
            uint8_t h[32];
            mbedtls_sha256(r.out, r.out_len, h, 0);
            char hex[65];
            for (int i = 0; i < 32; i++) {
                sprintf(hex + 2 * i, "%02x", h[i]);
            }
            printf("#mbop,%s,%s,%s,%u,%.4f,%.1f,%s,%d\n", CONFIG_IDF_TARGET, PATHS[p], OPS[o],
                   (unsigned)count, r.wall_s, r.wall_s * s_cpu_hz / count, hex, r.verified);
            fflush(stdout);
            free(r.out);
        }
    }
}

/* Part 5: one compression per acquire and release of the unit, as the unheld path of the
 * register backends does. Variants: (a) set the mode right after acquiring, (b) read
 * SHA_BUSY_REG once before setting the mode, (c) ESP-IDF's esp_sha_set_mode(), which
 * waits for idle first. Counts mismatches against plain C, and outputs equal to the input
 * state (the block was never hashed). */
static void part_cold(void)
{
    uint32_t a[24], b[24], in0[8];
    for (int v = 0; v < 3; v++) {
        int bad = 0, unhashed = 0;
        for (uint32_t k = 0; k < 1000; k++) {
            fill(a, k + 9000);
            memcpy(b, a, sizeof(a));
            memcpy(in0, a, sizeof(in0));
            sha2_256_compress_soft(a);
            esp_sha_acquire_hardware();
            if (v == 0) {
                sha_ll_set_mode(SHA2_256);
            } else if (v == 1) {
                (void)sha_ll_busy();
                sha_ll_set_mode(SHA2_256);
            } else {
                esp_sha_set_mode(SHA2_256);
            }
            pqb_sha_regs_compress(b);
            esp_sha_release_hardware();
            bad += memcmp(a, b, 32) != 0;
            unhashed += memcmp(in0, b, 32) == 0;
        }
        printf("#mbcold,%s,%c,1000,%d,%d\n", CONFIG_IDF_TARGET, "abc"[v], bad, unhashed);
        fflush(stdout);
    }
}

static void mb_task(void* arg)
{
    SemaphoreHandle_t done = (SemaphoreHandle_t)arg;
    s_cpu_hz = (double)esp_clk_cpu_freq();
    part_cold();
#ifdef PQB_MB_QUICK
    xSemaphoreGive(done);
    vTaskDelete(NULL);
#endif

    part_compress("");

    /* Part 2: core 1 busy with plain-C compressions */
    s_core1_run = 1;
    xTaskCreatePinnedToCore(core1_load_task, "pqb_load", 4096, NULL, 5, NULL, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
    part_compress("_core1busy");
    s_core1_run = 0;
    while (s_core1_run != -1) {
        vTaskDelay(1);
    }
    printf("#mbcore1,%s,%u,%.1f\n", CONFIG_IDF_TARGET, (unsigned)s_core1_count,
           (double)(s_core1_t1 - s_core1_t0) * 1e-6 * s_cpu_hz / s_core1_count);

    part_check();
    part_ops();

    xSemaphoreGive(done);
    vTaskDelete(NULL);
}

void pqb_microbench(void)
{
    SemaphoreHandle_t done = xSemaphoreCreateBinary();
    xTaskCreatePinnedToCore(mb_task, "pqb_mb", MB_STACK_BYTES, done, 5, NULL, 0);
    xSemaphoreTake(done, portMAX_DELAY);
    vTaskDelay(pdMS_TO_TICKS(50));
}
