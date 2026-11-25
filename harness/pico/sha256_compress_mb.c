/*
 * PQB_SLH_COMPRESS=mb: run-time selectable SHA-256 compression for the microbenchmark
 * (microbench_rp.c), with path counters. Modes:
 *   PQB_MB_SOFT  slhdsa-c's portable C
 *   PQB_MB_ASM   OpenSSL's Thumb-2 assembly (sha256_armv4_thumb.S)
 *   PQB_MB_SDK   the accelerator through the SDK's hardware_sha256 functions (level 2)
 *   PQB_MB_REG   the accelerator through its registers (level 3 candidate)
 *   PQB_MB_DMA   as reg, with each 16-word block written by a DMA channel paced by the
 *                accelerator's DREQ
 * The accelerator paths share sha256_rphw.h; each mode has its own copy of its state.
 */
#include <string.h>

#include "hardware/dma.h"
#include "hardware/sha256.h"
#include "sha256_mb_rp.h"
#include "sha256_rpreg.h"

#define PQB_RPH_COUNT 1

void sha2_256_compress_asm(void* v);

/* --- level-2 primitives (as sha256_compress_sdk.c) */
static inline void sdk_feed(const uint32_t* w)
{
    sha256_wait_ready_blocking();
    for (int i = 0; i < 16; i++) {
        sha256_put_word(w[i]);
    }
}

static inline void sdk_result(uint32_t* s)
{
    sha256_wait_valid_blocking();
    sha256_result_t r;
    sha256_get_result(&r, SHA256_BIG_ENDIAN);
    memcpy(s, r.words, 32);
}

static inline void sdk_setup(void)
{
    sha256_err_not_ready_clear();
    sha256_set_bswap(true);
}

#define RPH_START() sha256_start()
#define RPH_FEED(w) sdk_feed(w)
#define RPH_RESULT(s) sdk_result(s)
#define RPH_SETUP() sdk_setup()
#define RPH_NAME(x) sdk_##x
#include "sha256_rphw.h"
#undef RPH_START
#undef RPH_FEED
#undef RPH_RESULT
#undef RPH_SETUP
#undef RPH_NAME
#undef RPH_COUNT

/* --- level-3 register primitives (as sha256_compress_reg.c) */
#define RPH_START() reg_start()
#define RPH_FEED(w) reg_feed(w)
#define RPH_RESULT(s) reg_result(s)
#define RPH_SETUP() reg_setup()
#define RPH_NAME(x) reg_##x
#include "sha256_rphw.h"
#undef RPH_START
#undef RPH_FEED
#undef RPH_RESULT
#undef RPH_SETUP
#undef RPH_NAME
#undef RPH_COUNT

/* --- DMA primitives: one channel, claimed at first use, 32-bit transfers paced by
 * DREQ_SHA256 (the accelerator requests a whole block at a time) */
static int s_dma_ch = -1;

static void dma_setup_channel(void)
{
    if (s_dma_ch >= 0) {
        return;
    }
    s_dma_ch = dma_claim_unused_channel(true);
    dma_channel_config c = dma_channel_get_default_config((uint)s_dma_ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_dreq(&c, DREQ_SHA256);
    dma_channel_configure((uint)s_dma_ch, &c, (void*)&sha256_hw->wdata, NULL, 16, false);
}

static inline void dma_feed(const uint32_t* w)
{
    dma_channel_hw_t* const ch = dma_channel_hw_addr((uint)s_dma_ch);
    while (ch->ctrl_trig & DMA_CH0_CTRL_TRIG_BUSY_BITS) {
    }
    ch->read_addr = (uintptr_t)w;
    ch->transfer_count = 16;
    ch->ctrl_trig = ch->ctrl_trig; /* re-trigger with the same configuration */
}

/* Two blocks in one transfer of 32 words. Two separate transfers stalled on the device:
 * the second channel trigger can come after the accelerator has raised its request for
 * the next block, and the request is then not seen (microbenchmark, round 4). One
 * transfer over both blocks is how the SDK's pico_sha256 feeds long messages. */
static uint32_t s_dma_pair[32] __attribute__((aligned(16)));

static inline void dma_feed2(const uint32_t* a, const uint32_t* b)
{
    dma_channel_hw_t* const ch = dma_channel_hw_addr((uint)s_dma_ch);
    while (ch->ctrl_trig & DMA_CH0_CTRL_TRIG_BUSY_BITS) {
    }
    memcpy(s_dma_pair, a, 64);
    memcpy(s_dma_pair + 16, b, 64);
    ch->read_addr = (uintptr_t)s_dma_pair;
    ch->transfer_count = 32;
    ch->ctrl_trig = ch->ctrl_trig;
}

static inline void dma_result(uint32_t* s)
{
    dma_channel_hw_t* const ch = dma_channel_hw_addr((uint)s_dma_ch);
    while (ch->ctrl_trig & DMA_CH0_CTRL_TRIG_BUSY_BITS) {
    }
    reg_result(s);
}

static inline void dma_setup(void)
{
    dma_setup_channel();
    reg_setup();
}

#define RPH_START() reg_start()
#define RPH_FEED(w) dma_feed(w)
#define RPH_FEED2(a, b) dma_feed2(a, b)
#define RPH_RESULT(s) dma_result(s)
#define RPH_SETUP() dma_setup()
#define RPH_NAME(x) dmax_##x
#include "sha256_rphw.h"

volatile int pqb_mb_mode = PQB_MB_SOFT;
volatile uint32_t pqb_mb_calls;

void sha2_256_compress(void* v)
{
    pqb_mb_calls++;
    switch (pqb_mb_mode) {
    case PQB_MB_ASM:
        sha2_256_compress_asm(v);
        break;
    case PQB_MB_SDK:
        sdk_compress(v);
        break;
    case PQB_MB_REG:
        reg_compress(v);
        break;
    case PQB_MB_DMA:
        dmax_compress(v);
        break;
    default:
        sha2_256_compress_soft(v);
        break;
    }
}

static void hold(void)
{
    switch (pqb_mb_mode) {
    case PQB_MB_SDK:
        sdk_hold();
        break;
    case PQB_MB_REG:
        reg_hold();
        break;
    case PQB_MB_DMA:
        dmax_hold();
        break;
    default:
        break;
    }
}

static void release(void)
{
    sdk_release();
    reg_release();
    dmax_release();
}

void pqb_core_begin(void) { hold(); }
void pqb_core_end(void) { release(); }
void pqb_mbedtls_core_begin(void) { hold(); }
void pqb_mbedtls_core_end(void) { release(); }

void pqb_mb_hold(void) { hold(); }
void pqb_mb_release(void) { release(); }

void pqb_mb_counts(int mode, uint32_t out[6])
{
    const rph_counts_t* n = mode == PQB_MB_SDK ? &sdk_st.n
        : mode == PQB_MB_REG                   ? &reg_st.n
                                               : &dmax_st.n;
    out[0] = n->cont;
    out[1] = n->iv;
    out[2] = n->replay;
    out[3] = n->ring;
    out[4] = n->soft_unknown;
    out[5] = n->soft_other_core;
}

void pqb_mb_counts_reset(void)
{
    memset(&sdk_st.n, 0, sizeof(sdk_st.n));
    memset(&reg_st.n, 0, sizeof(reg_st.n));
    memset(&dmax_st.n, 0, sizeof(dmax_st.n));
    pqb_mb_calls = 0;
}

/* The accelerator paths without the dispatcher, for the per-path timing loops */
void pqb_mb_sdk_compress(void* v) { sdk_compress(v); }
void pqb_mb_reg_compress(void* v) { reg_compress(v); }
void pqb_mb_dma_compress(void* v) { dmax_compress(v); }
