/*
 * PQB_SLH_COMPRESS=hwshare: the M_MEM-skipping register backend (as hwshadow), plus a
 * rule that lets the second core use the SHA unit while the first core has stopped
 * hashing.
 *
 * Blockstream's dual-core paths split the WOTS+ chains of each key between the cores and
 * make core 0 wait for core 1's last chain. With the hybrid rule of hwshadow (core 0 on
 * the unit, core 1 in plain C), that wait is a plain-C chain on core 1, several times
 * longer than the same chain on the unit. Here core 1 uses the unit whenever core 0 has
 * not compressed anything since core 1's previous compression (in practice, while core 0
 * is blocked waiting), and plain C otherwise.
 *
 * Coordination: every use of the unit by either core takes s_lock (compare and swap).
 * Core 0 counts its compressions in s_seq0; core 1 compares that count with the value it
 * saw after its own previous compression. When core 1 uses the unit it writes all
 * registers and marks core 0's M_MEM copy stale, and core 0 rewrites M_MEM in full on its
 * next compression. The ESP-IDF lock and clock handling are unchanged: the core in
 * pqb_core_begin() holds the unit for the whole operation, as in the other backends. With
 * nobody holding it (verification), each compression takes and releases the unit.
 *
 * With PQB_SHARE_SLH_ONLY (PQB_SLH_COMPRESS=hwshareslh, sha256_compress_hwshareslh.c), the
 * sharing rule and its lock apply only inside pqb_core_begin() (SLH-DSA operations); inside
 * pqb_mbedtls_core_begin() (SHRINCS and XMSS) the backend behaves as hwshadow, without the
 * lock.
 */
#include <stdbool.h>
#include <stdint.h>

#include "esp_attr.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sha/sha_core.h"
#include "sha256_hwreg.h"
#include "soc/soc_caps.h"

#if !SOC_SHA_SUPPORT_RESUME
#error "hardware SLH-DSA compression needs SOC_SHA_SUPPORT_RESUME"
#endif

void sha2_256_compress_soft(void* v);

static volatile int s_owner_core = -1;
static uint32_t s_shadow[16];     /* M_MEM as last written by the owner core */
static volatile int s_lock;       /* 0 free, otherwise 1 + the core using the unit */
static volatile int s_stale;      /* the other core wrote the registers since */
static volatile uint32_t s_seq0;  /* compressions by the owner core */
static uint32_t s_seen;           /* s_seq0 after the other core's last compression */
#ifdef PQB_SHARE_SLH_ONLY
static volatile int s_share; /* the sharing rule is on for the current operation */
#else
#define s_share 1
#endif

static inline __attribute__((always_inline)) int try_lock(int who)
{
    int expected = 0;
    return __atomic_compare_exchange_n(&s_lock, &expected, who, false, __ATOMIC_ACQUIRE,
                                       __ATOMIC_RELAXED);
}

static inline __attribute__((always_inline)) void unlock(void)
{
    __atomic_store_n(&s_lock, 0, __ATOMIC_RELEASE);
}

static void pqb_hold_engine(void)
{
    esp_sha_acquire_hardware(); /* also resets the unit */
    sha_ll_set_mode(SHA2_256);
    pqb_sha_shadow_reset(s_shadow);
    s_stale = 0;
    s_lock = 0;
    s_seen = s_seq0 - 1; /* the other core starts in plain C */
    s_owner_core = xPortGetCoreID();
}

static void pqb_release_engine(void)
{
    s_owner_core = -1;
    esp_sha_release_hardware();
}

#ifdef PQB_SHARE_SLH_ONLY
void pqb_core_begin(void)
{
    s_share = 1;
    pqb_hold_engine();
}
#else
void pqb_core_begin(void) { pqb_hold_engine(); }
#endif
void pqb_core_end(void) { pqb_release_engine(); }

#ifdef PQB_SHA_API_DIRECT
#ifdef PQB_SHARE_SLH_ONLY
void pqb_mbedtls_core_begin(void)
{
    s_share = 0;
    pqb_hold_engine();
}
#else
void pqb_mbedtls_core_begin(void) { pqb_hold_engine(); }
#endif
void pqb_mbedtls_core_end(void) { pqb_release_engine(); }
#endif

void IRAM_ATTR sha2_256_compress(void* v)
{
    uint32_t* s = (uint32_t*)v;
    const int owner = s_owner_core;
    const int core = (int)xPortGetCoreID();
    if (__builtin_expect(owner == core, 1)) {
        if (!s_share) {
            pqb_sha_regs_compress_shadow(s, s_shadow);
            return;
        }
        while (!try_lock(1 + core)) {
        }
        if (s_stale) {
            pqb_sha_shadow_reset(s_shadow);
            s_stale = 0;
        }
        pqb_sha_regs_compress_shadow(s, s_shadow);
        s_seq0 = s_seq0 + 1;
        unlock();
    } else if (owner >= 0) {
        if (!s_share) {
            sha2_256_compress_soft(v);
            return;
        }
        const uint32_t seq = s_seq0;
        if (seq == s_seen && try_lock(1 + core)) {
            pqb_sha_regs_compress_relaxed(s);
            s_stale = 1;
            unlock();
        } else {
            sha2_256_compress_soft(v);
        }
        s_seen = s_seq0;
    } else {
        esp_sha_acquire_hardware();
        sha_ll_set_mode(SHA2_256);
        pqb_sha_regs_compress(s);
        esp_sha_release_hardware();
    }
}
