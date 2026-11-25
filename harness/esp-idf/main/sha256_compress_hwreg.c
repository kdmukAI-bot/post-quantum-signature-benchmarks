/*
 * slhdsa-c's sha2_256_compress() on the ESP32 SHA unit through its registers
 * (PQB_SLH_COMPRESS=hwreg).
 *
 * Same engine-sharing rule as sha256_compress_hw.c: pqb_core_begin() lets the calling
 * core hold the unit for a whole operation; compressions on that core use the unit,
 * compressions on the other core (Blockstream's dual-core paths) fall back to plain C,
 * and with nobody holding it (verification) each compression takes and releases the unit.
 *
 * Differences from sha256_compress_hw.c: the mode is set once when the unit is taken
 * instead of on every compression, the register accesses are inlined (sha256_hwreg.h)
 * instead of going through four ESP-IDF calls, and the function is placed in IRAM so the
 * hot path never waits for a flash cache refill.
 *
 * With PQB_HWREG_SHADOW (PQB_SLH_COMPRESS=hwshadow, sha256_compress_hwshadow.c), the core
 * holding the unit writes only the M_MEM words that differ from the previous block
 * (pqb_sha_regs_compress_shadow()). The shadow copy is reset each time the unit is taken.
 *
 * With PQB_HWREG_MIN (PQB_SLH_COMPRESS=hwmin, sha256_compress_hwmin.c), it also skips the
 * H_MEM writes for blocks that start from the SHA-256 initial value or continue from the
 * previous output (pqb_sha_regs_compress_min(), sha256_hwmin.h).
 */
#include <stdbool.h>
#include <stdint.h>

#include "esp_attr.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sha/sha_core.h"
#include "sha256_hwmin.h"
#include "sha256_hwreg.h"
#include "soc/soc_caps.h"

#if !SOC_SHA_SUPPORT_RESUME
#error "hardware SLH-DSA compression needs SOC_SHA_SUPPORT_RESUME"
#endif

void sha2_256_compress_soft(void* v);

static volatile int s_owner_core = -1;
#if defined(PQB_HWREG_MIN)
/* M_MEM and H_MEM as last written or read by the holding core */
static pqb_sha_min_t s_min;
#elif defined(PQB_HWREG_SHADOW)
static uint32_t s_shadow[16]; /* M_MEM as last written by the holding core */
#endif

static void pqb_hold_engine(void)
{
    esp_sha_acquire_hardware(); /* also resets the unit */
    sha_ll_set_mode(SHA2_256);
#if defined(PQB_HWREG_MIN)
    pqb_sha_min_reset(&s_min);
#elif defined(PQB_HWREG_SHADOW)
    pqb_sha_shadow_reset(s_shadow);
#endif
    s_owner_core = xPortGetCoreID();
}

static void pqb_release_engine(void)
{
    s_owner_core = -1;
    esp_sha_release_hardware();
}

void pqb_core_begin(void) { pqb_hold_engine(); }
void pqb_core_end(void) { pqb_release_engine(); }

#ifdef PQB_SHA_API_DIRECT
/* SHRINCS and XMSS hash through the direct SHA-256 API in this build, which never touches
 * mbedTLS, so the engine can be held around them too. */
void pqb_mbedtls_core_begin(void) { pqb_hold_engine(); }
void pqb_mbedtls_core_end(void) { pqb_release_engine(); }
#endif

void IRAM_ATTR sha2_256_compress(void* v)
{
    uint32_t* s = (uint32_t*)v;
    const int owner = s_owner_core;
    if (__builtin_expect(owner == (int)xPortGetCoreID(), 1)) {
#if defined(PQB_HWREG_MIN)
        pqb_sha_regs_compress_min(s, &s_min);
#elif defined(PQB_HWREG_SHADOW)
        pqb_sha_regs_compress_shadow(s, s_shadow);
#else
        pqb_sha_regs_compress(s);
#endif
    } else if (owner >= 0) {
        sha2_256_compress_soft(v);
    } else {
        esp_sha_acquire_hardware();
        sha_ll_set_mode(SHA2_256);
        pqb_sha_regs_compress(s);
        esp_sha_release_hardware();
    }
}
