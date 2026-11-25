/*
 * Minimal sampling profiler for pq_bench on the Pi (make ... prof builds pq_bench_prof
 * with this file linked in). The dev image has no perf tool, so this samples with the
 * process CPU-time timer: every ITIMER_PROF tick (at most one kernel jiffy), SIGPROF
 * records the interrupted program counter and link register. At exit the samples are
 * written as hex "pc lr" lines to the file named by PQB_PROF_OUT (default sigprof.txt).
 * Map them to functions on the host with nm on a non-PIE build (OPT=...-nopie or
 * ...-fullstatic), whose addresses are fixed.
 *
 * The link register attributes samples in leaf library routines such as memcpy() to their
 * callers, since those routines return through it.
 */
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <ucontext.h>

#define PQB_PROF_MAX 400000

static unsigned long prof_pc[PQB_PROF_MAX];
static unsigned long prof_lr[PQB_PROF_MAX];
static volatile int prof_n;

static void on_sigprof(int sig, siginfo_t* si, void* ctx)
{
    (void)sig;
    (void)si;
    const ucontext_t* uc = (const ucontext_t*)ctx;
    const int i = prof_n;
    if (i < PQB_PROF_MAX) {
        prof_pc[i] = uc->uc_mcontext.arm_pc;
        prof_lr[i] = uc->uc_mcontext.arm_lr;
        prof_n = i + 1;
    }
}

static void prof_dump(void)
{
    struct itimerval off;
    memset(&off, 0, sizeof(off));
    setitimer(ITIMER_PROF, &off, NULL);
    const char* path = getenv("PQB_PROF_OUT");
    FILE* f = fopen(path ? path : "sigprof.txt", "w");
    if (!f) {
        return;
    }
    for (int i = 0; i < prof_n; i++) {
        fprintf(f, "%lx %lx\n", prof_pc[i], prof_lr[i]);
    }
    fclose(f);
}

__attribute__((constructor)) static void prof_start(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = on_sigprof;
    sa.sa_flags = SA_SIGINFO | SA_RESTART;
    sigaction(SIGPROF, &sa, NULL);
    struct itimerval it;
    memset(&it, 0, sizeof(it));
    it.it_interval.tv_usec = 1000;
    it.it_value.tv_usec = 1000;
    setitimer(ITIMER_PROF, &it, NULL);
    atexit(prof_dump);
}
