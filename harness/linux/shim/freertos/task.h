/* Minimal stand-in for FreeRTOS's task.h. The scheme code uses FreeRTOS only in its
 * dual-core paths (compiled out by CONFIG_FREERTOS_UNICORE) and for a periodic
 * vTaskDelay(1) yield in the single-core WOTS+C grinding loop, which is a no-op here.
 * On ESP the FreeRTOS headers also bring in stdbool.h, which wots_c.c relies on. */
#ifndef PQ_BENCH_SHIM_FREERTOS_TASK_H
#define PQ_BENCH_SHIM_FREERTOS_TASK_H

#include <stdbool.h>

static inline void vTaskDelay(unsigned int ticks) { (void)ticks; }

#endif
