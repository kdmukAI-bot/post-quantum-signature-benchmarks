/* Stand-in for Jade's random.h. Only key generation from a fresh random seed uses it,
 * which none of the benchmarked operations do. */
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "pico/rand.h"

static inline void get_random(void* bytes_out, size_t len)
{
    uint8_t* p = (uint8_t*)bytes_out;
    while (len > 0) {
        const uint32_t r = get_rand_32();
        for (int i = 0; i < 4 && len > 0; i++, len--) {
            *p++ = (uint8_t)(r >> (8 * i));
        }
    }
}
