/*
 * PQB_SLH_COMPRESS=sdk (level 2): slhdsa-c's sha2_256_compress() on the RP2350's SHA-256
 * accelerator through the Pico SDK's documented hardware_sha256 functions
 * (sha256_start(), sha256_wait_ready_blocking(), sha256_put_word(),
 * sha256_wait_valid_blocking(), sha256_get_result()). The SDK's higher-level pico_sha256
 * hashes whole messages with its own padding and has no call for one raw compression, so
 * it cannot stand behind slhdsa-c's compression function. How compressions from other
 * states are served: sha256_rphw.h.
 */
#include <string.h>

#include "hardware/sha256.h"

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

void pqb_core_begin(void) { sdk_hold(); }
void pqb_core_end(void) { sdk_release(); }
/* SHRINCS and XMSS hash through the direct context API in every harness/pico build */
void pqb_mbedtls_core_begin(void) { sdk_hold(); }
void pqb_mbedtls_core_end(void) { sdk_release(); }

void sha2_256_compress(void* v) { sdk_compress(v); }
