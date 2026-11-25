/*
 * Counting SHA-256 compression (COMPRESS=count): forwards to slhdsa-c's plain-C
 * compression and counts calls, to measure how many compressions each operation performs.
 * Build it with SHA_API=direct so that SHRINCS and XMSS hashing also passes through here.
 *
 * Only calls inside the timed core of an operation are counted (between the pqb_core_* or
 * pqb_mbedtls_core_* hooks, which this file overrides). The count for each run is printed
 * to stderr at the end of the run's core section, and the total at exit.
 */
#include <stdio.h>
#include <stdlib.h>

void sha2_256_compress_soft(void* v);

static unsigned long long total_calls;
static unsigned long long window_start;
static unsigned long long timed_calls;
static int in_window;

void sha2_256_compress(void* v)
{
    total_calls++;
    sha2_256_compress_soft(v);
}

static void begin(void)
{
    window_start = total_calls;
    in_window = 1;
}

static void end(void)
{
    if (in_window) {
        const unsigned long long n = total_calls - window_start;
        timed_calls += n;
        fprintf(stderr, "core_compressions=%llu\n", n);
        in_window = 0;
    }
}

void pqb_core_begin(void) { begin(); }
void pqb_core_end(void) { end(); }
void pqb_mbedtls_core_begin(void) { begin(); }
void pqb_mbedtls_core_end(void) { end(); }

static void report(void)
{
    fprintf(stderr, "timed_compressions_total=%llu all_compressions=%llu\n", timed_calls,
            total_calls);
}

__attribute__((constructor)) static void register_report(void) { atexit(report); }
