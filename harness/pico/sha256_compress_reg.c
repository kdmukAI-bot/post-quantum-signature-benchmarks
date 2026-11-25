/*
 * PQB_SLH_COMPRESS=reg (level 3): slhdsa-c's sha2_256_compress() on the RP2350's SHA-256
 * accelerator through its registers (sha256_rpreg.h). How compressions from other states
 * are served: sha256_rphw.h.
 */
#include "sha256_rpreg.h"

#define RPH_START() reg_start()
#define RPH_FEED(w) reg_feed(w)
#define RPH_RESULT(s) reg_result(s)
#define RPH_SETUP() reg_setup()
#define RPH_NAME(x) reg_##x
#include "sha256_rphw.h"

void pqb_core_begin(void) { reg_hold(); }
void pqb_core_end(void) { reg_release(); }
void pqb_mbedtls_core_begin(void) { reg_hold(); }
void pqb_mbedtls_core_end(void) { reg_release(); }

void sha2_256_compress(void* v) { reg_compress(v); }
