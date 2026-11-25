/* Run-time selectable SHA-256 compression for the microbenchmark
 * (sha256_compress_mb.c). */
#ifndef PQB_SHA256_MB_RP_H
#define PQB_SHA256_MB_RP_H

#include <stdint.h>

#define PQB_MB_SOFT 0
#define PQB_MB_ASM 1
#define PQB_MB_SDK 2
#define PQB_MB_REG 3
#define PQB_MB_DMA 4

extern volatile int pqb_mb_mode;
extern volatile uint32_t pqb_mb_calls;

void pqb_mb_hold(void);
void pqb_mb_release(void);
/* cont, iv, replay, ring, soft_unknown, soft_other_core for one accelerator mode */
void pqb_mb_counts(int mode, uint32_t out[6]);
void pqb_mb_counts_reset(void);
void pqb_mb_sdk_compress(void* v);
void pqb_mb_reg_compress(void* v);
void pqb_mb_dma_compress(void* v);

#endif
