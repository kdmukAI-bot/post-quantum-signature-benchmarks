/* Stand-in for Jade's random.h. Only key generation from a fresh random seed uses it,
 * which none of the benchmarked operations do. */
#ifndef PQ_BENCH_SHIM_RANDOM_H
#define PQ_BENCH_SHIM_RANDOM_H

#include <stddef.h>
#include <sys/random.h>

static inline void get_random(void* bytes_out, size_t len)
{
    unsigned char* p = (unsigned char*)bytes_out;
    while (len > 0) {
        ssize_t n = getrandom(p, len, 0);
        if (n > 0) {
            p += n;
            len -= (size_t)n;
        }
    }
}

#endif
