/* Stand-in for Jade's random.h. Only key generation from a fresh random seed uses it,
 * which none of the benchmarked operations do. */
#pragma once
#include <stddef.h>
#include "esp_random.h"

static inline void get_random(void* bytes_out, size_t len) { esp_fill_random(bytes_out, len); }
