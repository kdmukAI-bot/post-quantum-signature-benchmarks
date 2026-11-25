# The FreeRTOS end-of-stack watchpoint slows the ESP32-P4 by 12 to 31%

`CONFIG_FREERTOS_WATCHPOINT_END_OF_STACK` makes FreeRTOS arm a hardware watchpoint on the
last 32 bytes of the running task's stack at every context switch, so that a store into
that region panics immediately instead of being found at the next context switch. On the
ESP32-P4 this setting slows ordinary computation by roughly a quarter. On the ESP32-S3 it
has no measurable cost.

ESP-IDF's Kconfig help for the option mentions two side effects only: one fewer hardware
watchpoint for gdb, and up to 60 bytes of usable stack lost to alignment. It does not
mention a speed cost.

## Measurements

ESP32-P4 chip revision v3.2 at 400 MHz, ESP-IDF v5.5.5, one core, Blockstream's Jade
scheme sources unmodified. Change in signing time when only the watchpoint is enabled,
against the same build with ESP-IDF's default settings:

| SHA-256 path | SLH-DSA-128s | SPHINCS+ 2^40 | SHRINCS-B | XMSS 2^10 |
|---|---|---|---|---|
| Plain C (level 1) | +23.3% | +23.5% | +28.0% | +25.2% |
| SHA unit through ESP-IDF's driver functions (level 2) | +13.9% | +14.7% | +28.0% | +21.2% |
| SHA unit through registers, tuned build (level 3) | +21.3% | +21.9% | +28.5% | +24.0% |

The slowdown appears with plain-C hashing, so it is not specific to the SHA peripheral.

With the watchpoint and assertions off together (the MicroPython-style profile), n=10, the
ESP32-P4's signing times grew by 12.5% to 30.8% at all three levels, on one core and on
two. On the ESP32-S3 (Xtensa), the same pair of settings changed no time by more than 0.2%
at any level or core count.

The second setting in the MicroPython-style profile, ESP-IDF assertions compiled out
(`CONFIG_COMPILER_OPTIMIZATION_ASSERTIONS_DISABLE`), changed the ESP32-P4 level 3 times by
-0.2% to +3.6% on its own.

## Cause

Not investigated. The watchpoint is armed for stores only (`ESP_CPU_WATCHPOINT_STORE`,
`vPortSetStackWatchpoint()` in the RISC-V FreeRTOS port). A hypothesis, not tested: an
active store trigger slows the ESP32-P4 core's handling of stores.

## Rules

- On the ESP32-P4, treat `CONFIG_FREERTOS_WATCHPOINT_END_OF_STACK` as a setting with a
  large performance cost. Measure with and without it before keeping it in a build where
  speed matters.
- The ESP32-P4 has a cheaper overflow check enabled by default:
  `CONFIG_ESP_SYSTEM_HW_STACK_GUARD` panics as soon as the stack pointer leaves the
  running task's stack bounds. FreeRTOS's canary check at context switches is also on by
  default. The watchpoint additionally catches stores into the last 32 bytes of the stack
  that do not move the stack pointer out of bounds.
- When publishing ESP32-P4 timings, state whether this watchpoint was enabled.

## Reproducing

The screening logs behind these figures are not part of this repository's data. To repeat
the measurement, build the ESP32-P4 benchmark with `scripts/esp_opt_build.sh` twice per
level, once with ESP-IDF's defaults (the report's builds) and once with an sdkconfig
overlay that adds `CONFIG_FREERTOS_WATCHPOINT_END_OF_STACK=y`, and compare signing times
on one core. Adding `CONFIG_COMPILER_OPTIMIZATION_ASSERTIONS_DISABLE=y` to the second
build gives the combined case; on its own, that setting gives the assertions figure.
