/*
 * Force-included into the harness sources (harness/common and bench_rp.c; harness/pico/
 * CMakeLists.txt): their malloc(), calloc(), and free() calls go to the FreeRTOS heap,
 * which also holds every task stack, so one heap figure covers the harness's buffers and
 * the stacks of Blockstream's helper tasks, as on the ESP32 boards. The scheme and
 * lattice libraries allocate nothing themselves.
 */
#ifndef PQB_RP_ALLOC_H
#define PQB_RP_ALLOC_H

#include <stddef.h>
#include <stdlib.h>

void* pqb_malloc(size_t n);
void* pqb_calloc(size_t n, size_t size);
void pqb_free(void* p);

/* Per-run heap monitor: start records the current free size as the lowest so far; the
 * FreeRTOS heap lowers it on every allocation (traceMALLOC in FreeRTOSConfig.h). */
void pqb_heap_monitor_start(void);
size_t pqb_heap_monitor_min_free(void);
size_t pqb_heap_free(void);
size_t pqb_heap_largest_free_block(void);

#define malloc(n) pqb_malloc(n)
#define calloc(n, size) pqb_calloc(n, size)
#define free(p) pqb_free(p)

#endif
