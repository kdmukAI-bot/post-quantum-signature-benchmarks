/*
 * PQB_SLH_COMPRESS=hwshadow: the register-level backend (sha256_compress_hwreg.c) with
 * relaxed register ordering and M_MEM writes limited to the words that changed since the
 * previous block (pqb_sha_regs_compress_shadow() in sha256_hwreg.h).
 */
#define PQB_HWREG_SHADOW 1
#include "sha256_compress_hwreg.c"
