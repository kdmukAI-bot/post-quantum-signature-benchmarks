/* Shared declarations for the microbenchmark build (PQB_MICROBENCH=1). */
#pragma once

#include <stdint.h>

enum {
    PQB_MB_SOFT = 0,
    PQB_MB_IDF = 1,
    PQB_MB_REG = 2,
    PQB_MB_RELAXED = 3,
    PQB_MB_SHADOW = 4,
    PQB_MB_MIN = 5
};

extern volatile int pqb_mb_mode;
extern volatile uint32_t pqb_mb_count;

void pqb_mb_compress_idf(uint8_t* s);
void pqb_mb_compress_reg(uint32_t* s);
void pqb_mb_compress_relaxed(uint32_t* s);
void pqb_mb_compress_shadow(uint32_t* s);
void pqb_mb_shadow_reset(void);
void pqb_mb_compress_min(uint32_t* s);
void pqb_mb_min_reset(void);
void pqb_microbench(void);
