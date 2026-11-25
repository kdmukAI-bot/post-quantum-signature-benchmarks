/* Heap functions behind pqb_rp_alloc.h (failure hooks: pqb_rp_fault.c). */
#include <stdio.h>
#include <string.h>

#include "FreeRTOS.h"
#include "pico/stdlib.h"
#include "task.h"

#include "pqb_rp_alloc.h"

#undef malloc
#undef calloc
#undef free

static volatile size_t s_min_free;

void* pqb_malloc(size_t n) { return pvPortMalloc(n ? n : 1); }

void* pqb_calloc(size_t n, size_t size)
{
    if (size && n > (size_t)-1 / size) {
        return NULL;
    }
    void* p = pvPortMalloc(n * size ? n * size : 1);
    if (p) {
        memset(p, 0, n * size);
    }
    return p;
}

void pqb_free(void* p) { vPortFree(p); }

/* Called by heap_4 inside pvPortMalloc(), after it has taken the block (traceMALLOC). */
void pqb_heap_note(void)
{
    const size_t f = xPortGetFreeHeapSize();
    if (f < s_min_free) {
        s_min_free = f;
    }
}

void pqb_heap_monitor_start(void) { s_min_free = xPortGetFreeHeapSize(); }

size_t pqb_heap_monitor_min_free(void) { return s_min_free; }

size_t pqb_heap_free(void) { return xPortGetFreeHeapSize(); }

size_t pqb_heap_largest_free_block(void)
{
    HeapStats_t st;
    vPortGetHeapStats(&st);
    return st.xSizeOfLargestFreeBlockInBytes;
}
