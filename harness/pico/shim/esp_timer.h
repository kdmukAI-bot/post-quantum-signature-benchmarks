/* Stand-in for ESP-IDF's esp_timer.h, for harness/common/common.c compiled with
 * ESP_PLATFORM (harness/pico/CMakeLists.txt): the benchmark clock is the SDK's
 * time_us_64(), the RP2350's 64-bit microsecond system timer, the same resolution as
 * esp_timer_get_time(). */
#pragma once
#include <stdint.h>

#include "pico/time.h"

static inline int64_t esp_timer_get_time(void) { return (int64_t)time_us_64(); }
