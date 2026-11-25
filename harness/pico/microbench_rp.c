/*
 * SHA-256 compression microbenchmark for the RP2350 (PQB_MICROBENCH=1 with
 * PQB_SLH_COMPRESS=mb). Console job sets (bench_rp.c):
 *
 *   run microbench   parts 0 to 3
 *   run mbops        part 4 for every mode; "run mbops_<soft|asm|sdk|reg|dma>" for one
 *
 * Part 0 checks what the accelerator does with a state it was not given: whether START
 *   loads the initial value, whether writes to SUM0 to SUM7 change them, and whether the
 *   next block continues from the accelerator's own state or from the written values.
 *   It writes to read-only registers; had a write faulted, the fault handler would have
 *   rebooted the board (pqb_rp_fault.c).
 * Part 1 times MB_N compressions of one buffer per path, in CPU cycles per compression
 *   (DWT cycle counter on core 0; the second figure comes from time_us_64()):
 *     soft, asm               portable C, OpenSSL's Thumb-2 assembly
 *     <m>_iv                  accelerator path m (sdk, reg, dma) from the initial value
 *     <m>_cont                continuation of the previous block
 *     <m>_replay              from a state one block after the initial value (rebuilt
 *                             by replaying that block); the loop also copies the 8 state
 *                             words in, as slhdsa-c's WOTS+ chain loop does
 *     soft_replaylike         portable C in the same loop as <m>_replay
 *     copy_only               the loop of <m>_replay without the compression
 *     reg_write16             START plus 16 WDATA writes, no wait
 *     reg_digest              START, 16 writes, wait for SUM_VLD (one block, no read)
 *     reg_read8               reading the 8 sums
 *     reg_csr                 one CSR read
 *     dispatch_reg_replay     reg_replay through the dispatcher (sha2_256_compress())
 *   and soft and reg_replay again with interrupts disabled (_noirq), which shows what USB
 *   and the FreeRTOS tick take from a timed loop.
 * Part 2 repeats soft and reg_replay on core 0 while a task on core 1 runs portable-C
 *   compressions, and reports core 1's rate (two-core builds: core 1 computes in C).
 * Part 3 checks 1000 pseudo-random cases for every path against portable C: a block from
 *   the initial value, a replayed block, a continuation, and a block from an unknown
 *   state (served in C by the accelerator paths).
 * Part 4 runs whole operations (run 0 inputs) per mode and reports compressions, time,
 *   cycles per compression including the scheme's own work, the output hash, and how the
 *   accelerator paths served the compressions.
 *
 * Output lines start with '#' so the CSV parsers skip them:
 *   #mb,rp2350,<name>,<n>,<cycles per compression (DWT)>,<from time_us_64>
 *   #mbcore1,rp2350,<n>,<cycles per compression on core 1, from time_us_64>
 *   #mbresume,rp2350,<key>=<value>,...
 *   #mbcheck,rp2350,<cases>,<mismatches asm>,<sdk>,<reg>,<dma>,<err flag after>
 *   #mbop,rp2350,<mode>,<op>,<compressions>,<wall_s>,<cycles per compression>,
 *         <out sha256>,<verified>,<cont>,<iv>,<replay>,<ring>,<soft_unknown>,<soft_other>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "hardware/clocks.h"
#include "hardware/regs/m33.h"
#include "hardware/structs/m33.h"
#include "hardware/sync.h"
#include "hardware/watchdog.h"
#include "mbedtls/sha256.h"
#include "pico/stdlib.h"

#include "common.h"
#include "sha256_mb_rp.h"
#include "sha256_rpreg.h"
#include "pqb_rp_fault.h"

void sha2_256_compress_soft(void* v);
void sha2_256_compress_asm(void* v);
void sha2_256_compress(void* v);

#define MB_N 20000

static uint32_t s_buf[32] __attribute__((aligned(16)));
static uint32_t s_s1[8];
static double s_cpu_hz;

static const uint32_t IV_WORDS[8] = { 0x67e6096au, 0x85ae67bbu, 0x72f36e3cu, 0x3af54fa5u,
                                      0x7f520e51u, 0x8c68059bu, 0xabd9831fu, 0x19cde05bu };

static void cyc_enable(void)
{
    m33_hw->demcr |= M33_DEMCR_TRCENA_BITS;
    m33_hw->dwt_ctrl |= M33_DWT_CTRL_CYCCNTENA_BITS;
}

static inline uint32_t cyc(void) { return m33_hw->dwt_cyccnt; }

static void fill(uint32_t* b, int n, uint32_t seed)
{
    uint32_t x = seed * 2654435761u + 1;
    for (int i = 0; i < n; i++) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        b[i] = x;
    }
}

static void report(const char* name, int n, uint32_t c0, uint32_t c1, uint64_t t0, uint64_t t1)
{
    printf("#mb,rp2350,%s,%d,%.1f,%.1f\n", name, n, (double)(c1 - c0) / n,
           (double)(t1 - t0) * 1e-6 * s_cpu_hz / n);
    fflush(stdout);
}

#define TIME_LOOP(name, setup, body)                                                     \
    do {                                                                                 \
        fill(s_buf, 24, 1);                                                              \
        setup;                                                                           \
        const uint64_t t0_ = time_us_64();                                               \
        const uint32_t c0_ = cyc();                                                      \
        for (int i_ = 0; i_ < MB_N; i_++) {                                              \
            body;                                                                        \
        }                                                                                \
        const uint32_t c1_ = cyc();                                                      \
        const uint64_t t1_ = time_us_64();                                               \
        report(name, MB_N, c0_, c1_, t0_, t1_);                                          \
    } while (0)

typedef void (*compress_fn)(void*);

static void make_s1(compress_fn f)
{
    fill(s_buf, 24, 7);
    memcpy(s_buf, IV_WORDS, 32);
    f(s_buf);
    memcpy(s_s1, s_buf, 32);
}

static void time_hw_paths(const char* m, int mode, compress_fn f)
{
    char name[48];
    pqb_mb_mode = mode;
    pqb_mb_hold();
    snprintf(name, sizeof(name), "%s_iv", m);
    TIME_LOOP(name, (void)0, {
        memcpy(s_buf, IV_WORDS, 32);
        s_buf[13] = (uint32_t)i_;
        f(s_buf);
    });
    snprintf(name, sizeof(name), "%s_cont", m);
    TIME_LOOP(name, memcpy(s_buf, IV_WORDS, 32), f(s_buf)); /* first block from the IV */
    make_s1(f);
    snprintf(name, sizeof(name), "%s_replay", m);
    TIME_LOOP(name, (void)0, {
        memcpy(s_buf, s_s1, 32);
        s_buf[13] = (uint32_t)i_;
        f(s_buf);
    });
    pqb_mb_release();
}

/* --- part 0 */
static void part_resume(void)
{
    uint32_t a[24], b[24], ha[8], st[8], ref_cont[24], ref_written[24];
    fill(a + 8, 16, 11);
    fill(b + 8, 16, 12);
    pqb_mb_mode = PQB_MB_REG;
    pqb_mb_hold();

    reg_setup();
    reg_start();
    uint32_t after_start[8];
    reg_read8(after_start);
    const int iv_after_start = !memcmp(after_start, IV_WORDS, 32);

    reg_feed(a + 8);
    reg_result(ha);

    volatile uint32_t* const sum = (volatile uint32_t*)&sha256_hw->sum[0];
    uint32_t written[8];
    for (int i = 0; i < 8; i++) {
        written[i] = 0x11111111u * (uint32_t)(i + 1);
        sum[i] = __builtin_bswap32(written[i]);
    }
    reg_read8(st);
    const int readback_changed = memcmp(st, ha, 32) != 0;
    const int readback_is_written = !memcmp(st, written, 32);

    reg_feed(b + 8);
    uint32_t out[8];
    reg_result(out);

    memcpy(ref_cont, ha, 32);
    memcpy(ref_cont + 8, b + 8, 64);
    sha2_256_compress_soft(ref_cont);
    memcpy(ref_written, written, 32);
    memcpy(ref_written + 8, b + 8, 64);
    sha2_256_compress_soft(ref_written);

    /* writing a 17th word right after 16 (WDATA_RDY low) */
    reg_start();
    reg_write16(a + 8);
    sha256_hw->wdata = 0;
    const int err_set = (sha256_hw->csr & SHA256_CSR_ERR_WDATA_NOT_RDY_BITS) != 0;
    reg_setup();
    pqb_mb_release();

    printf("#mbresume,rp2350,iv_after_start=%d,sum_readback_changed=%d,"
           "sum_readback_is_written=%d,next_block_continues_own_state=%d,"
           "next_block_uses_written_state=%d,err_wdata_not_rdy_on_17th_word=%d\n",
           iv_after_start, readback_changed, readback_is_written,
           !memcmp(out, ref_cont, 32), !memcmp(out, ref_written, 32), err_set);
    fflush(stdout);
}

/* --- part 2 */
static volatile int s_core1_run;
static volatile uint32_t s_core1_count;
static volatile uint64_t s_core1_t0, s_core1_t1;
static SemaphoreHandle_t s_core1_done;

static void core1_task(void* arg)
{
    (void)arg;
    static uint32_t buf[32] __attribute__((aligned(16)));
    fill(buf, 24, 99);
    uint32_t n = 0;
    s_core1_t0 = time_us_64();
    while (s_core1_run) {
        sha2_256_compress_soft(buf);
        n++;
    }
    s_core1_t1 = time_us_64();
    s_core1_count = n;
    xSemaphoreGive(s_core1_done);
    vTaskDelete(NULL);
}

static void core1_start(void)
{
    s_core1_run = 1;
    xTaskCreatePinnedToCore(core1_task, "mb_core1", 4096, NULL, 5, NULL, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
}

static void core1_stop(void)
{
    s_core1_run = 0;
    xSemaphoreTake(s_core1_done, portMAX_DELAY);
    printf("#mbcore1,rp2350,%u,%.1f\n", (unsigned)s_core1_count,
           (double)(s_core1_t1 - s_core1_t0) * 1e-6 * s_cpu_hz / s_core1_count);
    fflush(stdout);
}

/* --- part 3 */
static int check_path(compress_fn f, int mode, int cases)
{
    int bad = 0;
    pqb_mb_mode = mode;
    if (mode >= PQB_MB_SDK) {
        pqb_mb_hold();
    }
    for (int k = 0; k < cases; k++) {
        uint32_t p[24], b1[24], b2[24], x[24];
        fill(p + 8, 16, 1000 + 4 * k);
        fill(b1 + 8, 16, 1001 + 4 * k);
        fill(b2 + 8, 16, 1002 + 4 * k);
        fill(x, 8, 1003 + 4 * k);
        uint32_t ref[4][8], t[24];
        memcpy(t, IV_WORDS, 32);
        memcpy(t + 8, p + 8, 64);
        sha2_256_compress_soft(t);
        memcpy(ref[0], t, 32);
        memcpy(t + 8, b1 + 8, 64);
        sha2_256_compress_soft(t);
        memcpy(ref[1], t, 32);
        memcpy(t + 8, b2 + 8, 64);
        sha2_256_compress_soft(t);
        memcpy(ref[2], t, 32);
        memcpy(t, x, 32);
        memcpy(t + 8, b1 + 8, 64);
        sha2_256_compress_soft(t);
        memcpy(ref[3], t, 32);

        memcpy(t, IV_WORDS, 32);
        memcpy(t + 8, p + 8, 64);
        f(t);
        bad += memcmp(t, ref[0], 32) != 0;
        memcpy(t, ref[0], 32); /* replay */
        memcpy(t + 8, b1 + 8, 64);
        f(t);
        bad += memcmp(t, ref[1], 32) != 0;
        memcpy(t + 8, b2 + 8, 64); /* continuation */
        f(t);
        bad += memcmp(t, ref[2], 32) != 0;
        memcpy(t, x, 32); /* unknown state */
        memcpy(t + 8, b1 + 8, 64);
        f(t);
        bad += memcmp(t, ref[3], 32) != 0;
    }
    if (mode >= PQB_MB_SDK) {
        pqb_mb_release();
    }
    return bad;
}

/* --- part 4 */
typedef struct {
    const char* op;
    uint32_t swn;
    op_result_t r;
    int handled;
    SemaphoreHandle_t done;
} mbop_ctx_t;

static void mbop_task(void* arg)
{
    mbop_ctx_t* c = (mbop_ctx_t*)arg;
    c->handled = run_op(c->op, 0, c->swn, &c->r);
    xSemaphoreGive(c->done);
    vTaskDelete(NULL);
}

static const char* const MODE_NAMES[] = { "soft", "asm", "sdk", "reg", "dma" };

static void part_ops(int mode)
{
#if defined(SHRINCS_L)
    static const struct {
        const char* op;
        uint32_t swn;
    } OPS[] = { { "shrincs_sign", 96 }, { "shrincs_keygen", 0 }, { "shrincs_verify", 140 },
                { "shrincs_verify_stateless", 140 } };
#else
    static const struct {
        const char* op;
        uint32_t swn;
    } OPS[] = { { "slh_dsa_sign", 0 },      { "sphincs40_sign", 0 },
                { "shrincs_sign", 2040 },   { "xmss_sign", 0 },
                { "shrincs_keygen", 0 },    { "slh_dsa_verify", 0 },
                { "sphincs40_verify", 0 },  { "shrincs_verify", 2040 },
                { "shrincs_verify_stateless", 2040 }, { "xmss_verify", 0 } };
#endif
    SemaphoreHandle_t done = xSemaphoreCreateBinary();
    for (size_t i = 0; i < sizeof(OPS) / sizeof(OPS[0]); i++) {
        mbop_ctx_t c;
        memset(&c, 0, sizeof(c));
        c.op = OPS[i].op;
        c.swn = OPS[i].swn;
        pqb_current_op = c.op;
        c.done = done;
        pqb_mb_mode = mode;
        pqb_mb_counts_reset();
        xTaskCreatePinnedToCore(mbop_task, "mbop", 48 * 1024, &c, 5, NULL, 0);
        xSemaphoreTake(done, portMAX_DELAY);
        vTaskDelay(pdMS_TO_TICKS(50));
        /* includes the untimed checks after the op */
        const uint32_t calls = pqb_mb_calls;
        uint32_t n[6] = { 0 };
        if (mode >= PQB_MB_SDK) {
            pqb_mb_counts(mode, n);
        }
        pqb_mb_mode = PQB_MB_SOFT;
        uint8_t h[32];
        char hex[65] = "";
        if (c.handled == 1) {
            mbedtls_sha256(c.r.out, c.r.out_len, h, 0);
            for (int j = 0; j < 32; j++) {
                sprintf(hex + 2 * j, "%02x", h[j]);
            }
        }
        printf("#mbop,rp2350,%s,%s,%u,%.6f,%.1f,%s,%d,%u,%u,%u,%u,%u,%u\n", MODE_NAMES[mode],
               c.op, (unsigned)calls, c.r.wall_s, c.r.wall_s * s_cpu_hz / (calls ? calls : 1),
               hex, c.r.verified, (unsigned)n[0], (unsigned)n[1], (unsigned)n[2],
               (unsigned)n[3], (unsigned)n[4], (unsigned)n[5]);
        fflush(stdout);
        free(c.r.out);
    }
    vSemaphoreDelete(done);
}

void pqb_microbench(const char* set)
{
    s_cpu_hz = (double)clock_get_hz(clk_sys);
    cyc_enable();
    if (!strncmp(set, "mbops", 5)) {
        const char* m = set[5] == '_' ? set + 6 : NULL;
        for (int mode = 0; mode < 5; mode++) {
            if (!m || !strcmp(m, MODE_NAMES[mode])) {
                part_ops(mode);
            }
        }
        return;
    }

    part_resume();

    /* part 1 */
    pqb_mb_mode = PQB_MB_SOFT;
    TIME_LOOP("soft", (void)0, sha2_256_compress_soft(s_buf));
    TIME_LOOP("asm", (void)0, sha2_256_compress_asm(s_buf));
    make_s1(sha2_256_compress_soft);
    TIME_LOOP("soft_replaylike", (void)0, {
        memcpy(s_buf, s_s1, 32);
        s_buf[13] = (uint32_t)i_;
        sha2_256_compress_soft(s_buf);
    });
    TIME_LOOP("copy_only", (void)0, {
        memcpy(s_buf, s_s1, 32);
        s_buf[13] = (uint32_t)i_;
        __asm volatile("" ::: "memory");
    });
    time_hw_paths("sdk", PQB_MB_SDK, pqb_mb_sdk_compress);
    time_hw_paths("reg", PQB_MB_REG, pqb_mb_reg_compress);
    time_hw_paths("dma", PQB_MB_DMA, pqb_mb_dma_compress);

    pqb_mb_mode = PQB_MB_REG;
    pqb_mb_hold();
    reg_setup();
    TIME_LOOP("reg_write16", (void)0, {
        reg_start();
        reg_write16(s_buf + 8);
    });
    reg_wait_valid();
    TIME_LOOP("reg_digest", (void)0, {
        reg_start();
        reg_write16(s_buf + 8);
        reg_wait_valid();
    });
    TIME_LOOP("reg_read8", (void)0, reg_read8(s_buf));
    volatile uint32_t sink = 0;
    TIME_LOOP("reg_csr", (void)0, sink += sha256_hw->csr);
    make_s1(pqb_mb_reg_compress);
    TIME_LOOP("dispatch_reg_replay", (void)0, {
        memcpy(s_buf, s_s1, 32);
        s_buf[13] = (uint32_t)i_;
        sha2_256_compress(s_buf);
    });
    {
        /* timed with interrupts disabled; printed afterwards (USB output needs them) */
        uint32_t c[4];
        uint64_t t[4];
        const uint32_t irq = save_and_disable_interrupts();
        t[0] = time_us_64();
        c[0] = cyc();
        for (int i = 0; i < MB_N; i++) {
            memcpy(s_buf, s_s1, 32);
            s_buf[13] = (uint32_t)i;
            pqb_mb_reg_compress(s_buf);
        }
        c[1] = cyc();
        t[1] = time_us_64();
        fill(s_buf, 24, 1);
        t[2] = time_us_64();
        c[2] = cyc();
        for (int i = 0; i < MB_N; i++) {
            sha2_256_compress_soft(s_buf);
        }
        c[3] = cyc();
        t[3] = time_us_64();
        restore_interrupts(irq);
        report("reg_replay_noirq", MB_N, c[0], c[1], t[0], t[1]);
        report("soft_noirq", MB_N, c[2], c[3], t[2], t[3]);
    }
    pqb_mb_release();

    /* part 2 */
    s_core1_done = xSemaphoreCreateBinary();
    core1_start();
    TIME_LOOP("soft_with_core1_soft", (void)0, sha2_256_compress_soft(s_buf));
    core1_stop();
    pqb_mb_mode = PQB_MB_REG;
    pqb_mb_hold();
    make_s1(pqb_mb_reg_compress);
    core1_start();
    TIME_LOOP("reg_replay_with_core1_soft", (void)0, {
        memcpy(s_buf, s_s1, 32);
        s_buf[13] = (uint32_t)i_;
        pqb_mb_reg_compress(s_buf);
    });
    core1_stop();
    pqb_mb_release();
    vSemaphoreDelete(s_core1_done);

    /* part 3 */
    const int cases = 1000;
    const int bad_asm = check_path(sha2_256_compress_asm, PQB_MB_ASM, cases);
    const int bad_sdk = check_path(pqb_mb_sdk_compress, PQB_MB_SDK, cases);
    const int bad_reg = check_path(pqb_mb_reg_compress, PQB_MB_REG, cases);
    const int bad_dma = check_path(pqb_mb_dma_compress, PQB_MB_DMA, cases);
    const int err = (sha256_hw->csr & SHA256_CSR_ERR_WDATA_NOT_RDY_BITS) != 0;
    printf("#mbcheck,rp2350,%d,%d,%d,%d,%d,%d\n", cases, bad_asm, bad_sdk, bad_reg, bad_dma,
           err);
    fflush(stdout);
    pqb_mb_mode = PQB_MB_SOFT;
}
