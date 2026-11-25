/*
 * Peak stack and heap per operation on Linux (memory builds, make MEM=1).
 *
 * Stack: each run executes in a new thread on a 4 MiB stack that this file allocates and
 * fills with 0xA5 first (pthread_attr_setstack). The thread records the address of a
 * local variable on entry; after the thread ends, the lowest byte no longer equal to 0xA5
 * marks the deepest point reached. The peak is the distance between the two, so glibc's
 * thread descriptor and TLS (which it places at the top of a caller-supplied stack) and
 * the thread start-up frames are not counted, while everything the op calls is. A byte
 * that happens to be written with 0xA5 at the very bottom would hide up to a few bytes.
 *
 * Heap: the build links with -Wl,--wrap=malloc,--wrap=free,--wrap=calloc,--wrap=realloc,
 * so every allocation made by the benchmark and the scheme code (not by libc or libcrypto
 * internally) goes through the counters below. The peak is the highest number of bytes
 * outstanding during the op, above the level at its start.
 *
 * Both columns cover the whole op call: the timed library call plus the harness's untimed
 * work around it (loading keys and signatures into RAM, and verifying a new signature).
 */
#include "mem_linux.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

#define PQB_MEM_STACK_BYTES (4u << 20)
#define PQB_MEM_HDR 16

void* __real_malloc(size_t n);
void __real_free(void* p);
void* __real_calloc(size_t n, size_t m);
void* __real_realloc(void* p, size_t n);
void* __wrap_malloc(size_t n);
void __wrap_free(void* p);
void* __wrap_calloc(size_t n, size_t m);
void* __wrap_realloc(void* p, size_t n);

static long long s_cur;
static long long s_peak;

void* __wrap_malloc(size_t n)
{
    uint8_t* p = __real_malloc(n + PQB_MEM_HDR);
    if (!p) {
        return NULL;
    }
    *(size_t*)p = n;
    s_cur += (long long)n;
    if (s_cur > s_peak) {
        s_peak = s_cur;
    }
    return p + PQB_MEM_HDR;
}

void __wrap_free(void* q)
{
    if (!q) {
        return;
    }
    uint8_t* p = (uint8_t*)q - PQB_MEM_HDR;
    s_cur -= (long long)*(size_t*)p;
    __real_free(p);
}

void* __wrap_calloc(size_t n, size_t m)
{
    const size_t total = n * m;
    if (m && total / m != n) {
        return NULL;
    }
    void* p = __wrap_malloc(total);
    if (p) {
        memset(p, 0, total);
    }
    return p;
}

void* __wrap_realloc(void* q, size_t n)
{
    if (!q) {
        return __wrap_malloc(n);
    }
    const size_t old = *(size_t*)((uint8_t*)q - PQB_MEM_HDR);
    void* p = __wrap_malloc(n);
    if (p) {
        memcpy(p, q, old < n ? old : n);
        __wrap_free(q);
    }
    return p;
}

typedef struct {
    const char* op;
    uint32_t x, swn;
    op_result_t* r;
    int handled;
    uintptr_t sp_entry;
    long long heap_base;
} job_t;

static void* job_thread(void* arg)
{
    job_t* j = (job_t*)arg;
    volatile uint8_t marker = 0;
    j->sp_entry = (uintptr_t)&marker;
    j->heap_base = s_cur;
    s_peak = s_cur;
    j->handled = run_op(j->op, j->x, j->swn, j->r);
    return NULL;
}

int pqb_mem_run(const char* op, uint32_t x, uint32_t swn, op_result_t* r, pqb_mem_t* mem)
{
    uint8_t* stack = mmap(NULL, PQB_MEM_STACK_BYTES, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (stack == MAP_FAILED) {
        perror("mmap");
        return -1;
    }
    memset(stack, 0xA5, PQB_MEM_STACK_BYTES);
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstack(&attr, stack, PQB_MEM_STACK_BYTES);
    job_t j = { op, x, swn, r, 0, 0, 0 };
    pthread_t th;
    if (pthread_create(&th, &attr, job_thread, &j)) {
        perror("pthread_create");
        return -1;
    }
    pthread_join(th, NULL);
    pthread_attr_destroy(&attr);

    size_t i = 0;
    while (i < PQB_MEM_STACK_BYTES && stack[i] == 0xA5) {
        i++;
    }
    const uintptr_t lowest = (uintptr_t)stack + i;
    mem->stack_peak = j.sp_entry > lowest ? (size_t)(j.sp_entry - lowest) : 0;
    mem->heap_peak = s_peak > j.heap_base ? (size_t)(s_peak - j.heap_base) : 0;
    munmap(stack, PQB_MEM_STACK_BYTES);
    return j.handled;
}
