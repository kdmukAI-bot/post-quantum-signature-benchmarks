/*
 * slhdsa-c's sha2_256_compress() on the RP2350's SHA-256 accelerator: the logic shared by
 * the level-2 backend (sha256_compress_sdk.c, the SDK's hardware_sha256 functions), the
 * level-3 backend (sha256_compress_reg.c, direct register access), and the
 * microbenchmark (sha256_compress_mb.c).
 *
 * The accelerator cannot resume from a given state. Its only state input is CSR.START,
 * which loads the SHA-256 initial value; SUM0 to SUM7 are read-only, and nothing else
 * accepts a chaining value (RP2350 datasheet, SHA-256 accelerator registers; checked on
 * the device by microbench_rp.c). A compression from an arbitrary state therefore has to
 * be rebuilt from the initial value. slhdsa-c's compression call passes the state and one
 * 64-byte block (eight big-endian state words, then the block), and its hot paths start
 * every hash from a precomputed state one block away from the initial value: SHA-256 of
 * PK.seed padded to 64 bytes (SLH-DSA and SPHINCS+ through slhdsa-c's own code; SHRINCS
 * and XMSS through the direct context API, whose PK.seed contexts hold the same block).
 * Each call is served in one of four ways:
 *
 *   continuation  the input state is the accelerator's own last result (the next block of
 *                 a multi-block message): write the block
 *   initial value the input state is the SHA-256 initial value: START, write the block
 *   replay        the input state is the result of one block from the initial value that
 *                 this file has seen before (the precomputed PK.seed state, an HMAC key
 *                 block): START, write that earlier block again, then the new block
 *   software      anything else: slhdsa-c's portable C (sha2_256_compress_soft())
 *
 * Every first-block result is remembered with its block in a small ring, and the entry
 * that served the last replay is kept in front of it, so a signature's PK.seed state
 * stays available. A replay costs a second block on the accelerator; that is the price of
 * the missing state input. Results are identical to the portable C in every case (a state
 * equal to a known state is the same state).
 *
 * Sharing between the cores follows the ESP32 harness (docs/knowledge/
 * esp32-sha-unit-raw-compression.md): pqb_core_begin() and pqb_mbedtls_core_begin() let
 * the calling core hold the accelerator for a whole operation; while it is held, the
 * other core (Blockstream's two-core paths) computes in portable C. With nobody holding
 * it (untimed work such as shrincs_restore()), a call takes a lock for one compression
 * and falls back to portable C if the other core has it.
 *
 * Before including this file, define these as static inline functions or macros:
 *   RPH_START()          start a new hash (the initial value), WDATA ready afterwards
 *   RPH_FEED(w)          write one 16-word block; waits for WDATA_RDY first if needed
 *   RPH_RESULT(s)        wait for SUM_VLD and store the eight state words in slhdsa-c's
 *                        layout (big-endian bytes)
 *   RPH_SETUP()          configure CSR (byte swapping on) when a core takes the unit
 * and RPH_NAME(x) to prefix this file's functions (several copies in one binary).
 * Optionally RPH_FEED2(a, b) writes two blocks in a row (a replay); it defaults to two
 * RPH_FEED calls.
 */
#include <stdint.h>
#include <string.h>

#include <stdbool.h>

#include "hardware/sync.h"
#include "pico/platform.h"

void sha2_256_compress_soft(void* v);

/* Software path for states the accelerator cannot serve and for the core that does not
 * hold it: slhdsa-c's portable C, or another function named by PQB_RPH_SOFT_FN (CMake
 * option PQB_FALLBACK=asm: OpenSSL's Thumb-2 assembly). */
#ifndef PQB_RPH_SOFT_FN
#define PQB_RPH_SOFT_FN sha2_256_compress_soft
#endif
void PQB_RPH_SOFT_FN(void* v);

#ifndef PQB_RPH_COMMON_ONCE
#define PQB_RPH_COMMON_ONCE
/* The SHA-256 initial value in slhdsa-c's state layout, read as little-endian words */
static const uint32_t RPH_IV[8] = { 0x67e6096au, 0x85ae67bbu, 0x72f36e3cu, 0x3af54fa5u,
                                    0x7f520e51u, 0x8c68059bu, 0xabd9831fu, 0x19cde05bu };

typedef struct {
    uint32_t out[8];  /* state after one block from the initial value */
    uint32_t blk[16]; /* that block */
} rph_prefix_t;

#define RPH_RING 8

static inline int rph_eq8(const uint32_t* a, const uint32_t* b)
{
    return a[0] == b[0] && a[1] == b[1] && a[2] == b[2] && a[3] == b[3] && a[4] == b[4]
        && a[5] == b[5] && a[6] == b[6] && a[7] == b[7];
}

/* Path counters, compiled in only for the microbenchmark (PQB_RPH_COUNT). */
typedef struct {
    uint32_t cont, iv, replay, ring, soft_unknown, soft_other_core;
} rph_counts_t;
#endif

typedef struct {
    uint32_t last[8]; /* the accelerator's last result, valid if last_valid */
    int last_valid;
    rph_prefix_t hot;
    int hot_valid;
    rph_prefix_t ring[RPH_RING];
    unsigned ring_next, ring_n;
#ifdef PQB_RPH_COUNT
    rph_counts_t n;
#endif
} RPH_NAME(state_t);

#ifndef RPH_FEED2
#define RPH_FEED2(a, b)                                                                  \
    do {                                                                                 \
        RPH_FEED(a);                                                                     \
        RPH_FEED(b);                                                                     \
    } while (0)
#define RPH_FEED2_DEFAULT
#endif

static RPH_NAME(state_t) RPH_NAME(st);
static volatile int RPH_NAME(owner) = -1; /* core holding the accelerator, or -1 */
static volatile int RPH_NAME(lock);       /* taken for single compressions when unheld */

#ifdef PQB_RPH_COUNT
#define RPH_COUNT(f) (RPH_NAME(st).n.f++)
#else
#define RPH_COUNT(f) ((void)0)
#endif

static void RPH_NAME(hw_compress)(uint32_t* s)
{
    RPH_NAME(state_t)* const t = &RPH_NAME(st);
    if (t->last_valid && rph_eq8(s, t->last)) {
        RPH_COUNT(cont);
        RPH_FEED(s + 8);
    } else if (t->hot_valid && rph_eq8(s, t->hot.out)) {
        RPH_COUNT(replay);
        RPH_START();
        RPH_FEED2(t->hot.blk, s + 8);
    } else if (rph_eq8(s, RPH_IV)) {
        RPH_COUNT(iv);
        rph_prefix_t* e = &t->ring[t->ring_next];
        memcpy(e->blk, s + 8, 64);
        RPH_START();
        RPH_FEED(s + 8);
        RPH_RESULT(s);
        memcpy(e->out, s, 32);
        t->ring_next = (t->ring_next + 1) % RPH_RING;
        if (t->ring_n < RPH_RING) {
            t->ring_n++;
        }
        memcpy(t->last, s, 32);
        t->last_valid = 1;
        return;
    } else {
        const rph_prefix_t* e = NULL;
        for (unsigned i = 0; i < t->ring_n; i++) {
            if (rph_eq8(s, t->ring[i].out)) {
                e = &t->ring[i];
                break;
            }
        }
        if (!e) {
            /* the accelerator is not touched, so its last result stays valid */
            RPH_COUNT(soft_unknown);
            PQB_RPH_SOFT_FN(s);
            return;
        }
        RPH_COUNT(ring);
        t->hot = *e;
        t->hot_valid = 1;
        RPH_START();
        RPH_FEED2(t->hot.blk, s + 8);
    }
    RPH_RESULT(s);
    memcpy(t->last, s, 32);
    t->last_valid = 1;
}

static inline int RPH_NAME(try_lock)(void)
{
    int expected = 0;
    return __atomic_compare_exchange_n(&RPH_NAME(lock), &expected, 1, false,
                                       __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
}

static inline void RPH_NAME(unlock)(void) { __atomic_store_n(&RPH_NAME(lock), 0, __ATOMIC_RELEASE); }

/* Takes the accelerator for the calling core until RPH_NAME(release)(). */
static void RPH_NAME(hold)(void)
{
    while (!RPH_NAME(try_lock)()) {
        tight_loop_contents();
    }
    RPH_NAME(owner) = (int)get_core_num();
    RPH_NAME(st).last_valid = 0; /* as the ESP32 backends reset their register copies */
    RPH_SETUP();
    RPH_NAME(unlock)();
}

static void RPH_NAME(release)(void) { RPH_NAME(owner) = -1; }

static void RPH_NAME(compress)(void* v)
{
    const int owner = RPH_NAME(owner);
    if (owner == (int)get_core_num()) {
        RPH_NAME(hw_compress)((uint32_t*)v);
    } else if (owner >= 0) {
        RPH_COUNT(soft_other_core);
        PQB_RPH_SOFT_FN(v);
    } else if (RPH_NAME(try_lock)()) {
        if (RPH_NAME(owner) < 0) {
            RPH_SETUP();
            RPH_NAME(hw_compress)((uint32_t*)v);
        } else {
            PQB_RPH_SOFT_FN(v);
        }
        RPH_NAME(unlock)();
    } else {
        RPH_COUNT(soft_other_core);
        PQB_RPH_SOFT_FN(v);
    }
}

#ifdef RPH_FEED2_DEFAULT
#undef RPH_FEED2
#undef RPH_FEED2_DEFAULT
#endif
