# Environment: ESP32-P4 (Waveshare ESP32-P4 WiFi6 Touch LCD 4.3)

| Item | Value |
|---|---|
| Chip (each log's `#env` line) | esp32p4, revision v3.2, two cores, 400 MHz |
| Console | UART0 through the board's CH343 USB bridge, 115200 baud; reset over RTS before each job set |
| ESP-IDF | v5.5.5, Docker image `ghcr.io/kdmukai-bot/seedsigner-micropython-builder-base:idf-v5.5.5` (image ID d36f337d2170), the same image in rounds 2 and 3 |
| Compiler | riscv32-esp-elf-gcc 14.2.0 (esp-14.2.0_20260121) |
| Flash setting | 2 MB, DIO, 80 MHz |
| Cache, levels 1 and 2 | L2 cache 128 KiB, 64-byte lines |
| Cache, level 3 (`sdkconfig.opt-cache.esp32p4`) | L2 cache 256 KiB, 64-byte lines |
| Free internal heap before a job set (`#env`) | 589,352 bytes at level 1, 589,336 at level 2, 421,756 to 421,884 at level 3 |

Safeguards in every build (each build's `config/sdkconfig.h`): ESP-IDF's defaults, that is
the FreeRTOS stack-overflow canary check, assertions on (level 2), no compiler stack
protector, the interrupt watchdog, and the hardware stack guard; the task watchdog and the
FreeRTOS end-of-stack watchpoint are off. ESP-IDF's optimization setting is -O2 at every
level (`opt=O2` in the `#env` line); level-3 builds compile the scheme code with -O3
(`PQB_COPTS`).

Build options per level (all with `PQB_SHA_API=direct`, `PQB_SHRINCS=B|L`, and
`PQB_DUAL_CORE=0|1`; round 3 builds one core only; scripts `r2_esp_build_all.sh` and
`r3_esp_build_all.sh`):

| Level | Options | Variant string in the logs |
|---|---|---|
| 1 | `PQB_SLH_COMPRESS=soft` | `shrincs-<B|L> compress-soft sha-api-direct <single|dual>-core r<2|3>-L1` |
| 2 | `PQB_SLH_COMPRESS=hw` | `shrincs-<B|L> compress-hw sha-api-direct <single|dual>-core r<2|3>-L2` |
| 3 | `PQB_SLH_COMPRESS=hwshadow PQB_DIRECT_FAST=1 PQB_IRAM=1 PQB_COPTS=-O3`, `SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.opt-cache"` | `shrincs-<B|L> compress-hwshadow sha-api-direct <single|dual>-core r<2|3>-L3-opt-iram-cache-fast-O3` |

Each round-2 build has the same CMake options (apart from `PQB_TAG`) and an identical
`config/sdkconfig.h` as the first-round build it is compared with, so the first round's
operations are built the same way; the differences are the linked lattice code and vector
blob, one task per run, and the console command handling. Round 3 rebuilt the round-2
configurations, changing only how times are printed.
