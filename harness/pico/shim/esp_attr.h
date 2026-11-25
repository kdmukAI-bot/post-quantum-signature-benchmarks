/* Stand-in for ESP-IDF's esp_attr.h (used by harness/esp-idf/main/sha256_ctx_fast.c).
 * Placement attributes have no meaning here; harness/pico places code with its linker
 * options. */
#pragma once
#define DRAM_ATTR
#define IRAM_ATTR
