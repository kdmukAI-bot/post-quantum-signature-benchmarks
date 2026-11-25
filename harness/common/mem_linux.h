#ifndef PQB_MEM_LINUX_H
#define PQB_MEM_LINUX_H

#include <stddef.h>
#include <stdint.h>

#include "common.h"

typedef struct {
    size_t stack_peak; /* bytes of stack below the op thread's entry frame that were used */
    size_t heap_peak;  /* peak bytes allocated through malloc/calloc/realloc during the op,
                          above the level at its start */
} pqb_mem_t;

/* Runs one op (run_op) in a fresh thread whose stack was painted beforehand, and counts
 * heap use while it runs. Memory builds only (make MEM=1). */
int pqb_mem_run(const char* op, uint32_t x, uint32_t swn, op_result_t* r, pqb_mem_t* mem);

#endif
