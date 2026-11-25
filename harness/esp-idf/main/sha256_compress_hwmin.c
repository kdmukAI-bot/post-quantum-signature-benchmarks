/*
 * PQB_SLH_COMPRESS=hwmin: the register-level backend (sha256_compress_hwreg.c) with the
 * fewest register writes: unchanged M_MEM words are skipped, and H_MEM is not written for
 * blocks that start from the SHA-256 initial value or continue from the previous output
 * (pqb_sha_regs_compress_min() in sha256_hwmin.h).
 */
#define PQB_HWREG_MIN 1
#include "sha256_compress_hwreg.c"
