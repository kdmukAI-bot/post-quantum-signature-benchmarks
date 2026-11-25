/*
 * slhdsa-c's sha2_256_compress() on the ESP32 SHA peripheral.
 *
 * Layout (from slh_dsa/sha2_256.c): v points to 8 state words then a 64-byte message block,
 * stored as big-endian bytes, which is also the byte order the peripheral's digest registers
 * use when ESP-IDF's mbedTLS driver saves and restores a context. The state is updated in
 * place. Requires SOC_SHA_SUPPORT_RESUME (ESP32-S3 and ESP32-P4 have it).
 *
 * The chip has one SHA engine. pqb_core_begin() lets the calling core hold it for a whole
 * operation; while it is held, compressions on that core use the engine without locking and
 * compressions on the other core (Blockstream's dual-core paths) fall back to plain C. With
 * nobody holding it (verification), each compression locks the engine, as mbedTLS does.
 */
#include <stdbool.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sha/sha_core.h"
#include "soc/soc_caps.h"

#if !SOC_SHA_SUPPORT_RESUME
#error "hardware SLH-DSA compression needs SOC_SHA_SUPPORT_RESUME"
#endif

void sha2_256_compress_soft(void* v);

static volatile int s_owner_core = -1;

static void pqb_hold_engine(void)
{
    esp_sha_acquire_hardware();
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

static inline void compress_on_engine(uint8_t* s)
{
    esp_sha_set_mode(SHA2_256);
    esp_sha_write_digest_state(SHA2_256, s);
    esp_sha_block(SHA2_256, s + 32, false);
    esp_sha_read_digest_state(SHA2_256, s);
}

void sha2_256_compress(void* v)
{
    uint8_t* s = (uint8_t*)v;
    const int owner = s_owner_core;
    if (owner == (int)xPortGetCoreID()) {
        compress_on_engine(s);
    } else if (owner >= 0) {
        sha2_256_compress_soft(v);
    } else {
        esp_sha_acquire_hardware();
        compress_on_engine(s);
        esp_sha_release_hardware();
    }
}
