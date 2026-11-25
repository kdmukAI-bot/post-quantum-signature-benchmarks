# Pi Zero 2 W builds: Cortex-A53 in 32-bit Linux, OpenSSL's SHA-256 paths, and emulation

The Pi Zero 2 W's BCM2710A1 has four Cortex-A53 cores (ARMv8-A). SeedSigner OS runs them
in 32-bit (AArch32) state: the pi02w image is built for `BR2_arm`, `BR2_cortex_a53`, and
`BR2_ARM_FPU_NEON_VFPV4` with glibc, and its SDK image (seedsigner-raspi-lvgl
`sdk-pi02w`) holds the matching cross-compiler and sysroot. This note collects what
matters when building and checking hash-based and lattice signature code for that
target. Build options named here are those of `harness/linux/Makefile`.

## The SDK compiler already targets the A53 with NEON

The Buildroot wrapper (`arm-Buildroot-linux-gnueabihf-gcc`, GCC 13.3.0) adds
`-mcpu=cortex-a53 -mfloat-abi=hard -mfpu=neon-vfpv4 -marm -march=armv8-a+crc+simd`
together with `-fstack-protector-strong -fPIE -pie` to every compilation (visible with
`gcc -v`). Passing the CPU flags again changes nothing; "tuning for the A53" in this
SDK means choosing code, not flags.

Because the target is ARMv8-A, the compiler and the sysroot's glibc use AArch32
instructions that ARMv7 lacks, for example `lda` and `stl` for C11 acquire loads and
release stores (Jade's two-core grinding uses them through `__atomic` built-ins).

## Check the ARM clock: without cpufreq the A53 stays at its minimum

A SeedSigner OS dev image for the Pi Zero 2 W (kernel 5.15.92-v7, built 2025-04-22) has
the firmware's `raspberrypi-cpufreq` platform driver but no cpufreq interface in sysfs
(`/sys/devices/system/cpu/cpu0/cpufreq` does not exist). With no cpufreq governor to
request a higher clock, the ARM ran at `arm_freq_min` (600 MHz) with a core fully busy,
although `config.txt` sets `arm_freq=1000`. The Pi Zero W's ARM1176 has no such step and
runs at 1 GHz, so the two boards' figures from such an image are not at their rated
clocks.

- **Read the clock, do not assume it.** `vcgencmd measure_clock arm` reports the
  firmware's current ARM clock, and the CPU cycle counter divided by wall time gives the
  clock a process actually saw. On this image the kernel's PMU driver is
  `armv7_cortex_a7`, and `perf_event_open()` with `PERF_COUNT_HW_CPU_CYCLES` works on the
  A53 (`harness/common/compress_bench.c` prints cycles and MHz); it read 600 to 601 MHz
  with one core busy.
- **`force_turbo=1` fixes the clock without cpufreq.** With that line in `config.txt`, the
  same image ran at 1,000 MHz (firmware readings 999.998 to 1,000.002 MHz over a
  seven-minute run, cycle counter 1,000 MHz) with the core at 1.275 V instead of 1.25 V.
  Cycle counts per SHA-256 compression were the same at 600 MHz and 1 GHz (within 4
  cycles), and run times scaled with the clock (600 MHz time over 1 GHz time: median 1.668
  over 64 operation groups, against 1.667), so figures from either clock convert by the
  clock ratio, but each must name its clock.
- **Throttling is a separate flag.** `vcgencmd get_throttled` (or
  `/sys/devices/platform/soc/soc:firmware/get_throttled`) read 0x0 at 600 MHz: the low
  clock is the minimum setting, not thermal or under-voltage throttling. The image has no
  thermal zone in sysfs; `vcgencmd measure_temp` reads the temperature.
- **`/proc/cpuinfo` reports "ARMv7 Processor rev 4 (v7l)"** because the kernel is 32-bit;
  its Features line (neon, vfpv4, idiva, crc32; no aes, pmull, sha1, or sha2) shows that
  this A53 has no ARMv8 cryptographic extension.

## OpenSSL 3.4.1 picks its SHA-256 code at run time

The SDK's libcrypto (OpenSSL 3.4.1) contains three SHA-256 block functions, all from
`crypto/sha/asm/sha256-armv4.pl`: integer code, NEON code
(`sha256_block_data_order_neon`), and ARMv8 cryptographic-extension code. The exported
entry point `sha256_block_data_order` loads `OPENSSL_armcap_P` on every call and jumps to
the ARMv8 code if bit ARMV8_SHA256 (1 << 4) is set, otherwise to the NEON code if bit
ARMV7_NEON (1 << 0) is set, otherwise falls through to the integer code. The bits are set
once, at library initialization, from the kernel's AT_HWCAP and AT_HWCAP2 words, unless
the environment variable `OPENSSL_armcap` gives a value, which replaces them (for example
`OPENSSL_armcap=0` forces the integer code, `OPENSSL_armcap=1` the NEON code).

Traps:

- **`OPENSSL_armcap_P` is hidden in `libcrypto.so`.** A program cannot read it through
  the shared library. Linking the SDK's `libcrypto.a` statically (the same build) gives
  access to it; `scripts/r4_pi02w_armcap_probe.c` prints it with the hardware capability
  words.
- **The generated assembly holds all three functions.** The perlasm output for the linux32
  flavour is one `.S` file whose preprocessor conditions select the code at assembly time:
  below `__ARM_MAX_ARCH__` 7 only the integer function is assembled; at 7 or more the NEON
  and ARMv8 functions are added and the integer entry point gains the capability check.
  Regenerating it from OpenSSL 3.4.1's perlasm gives the same file as the Pi Zero W builds
  use (`harness/linux/shim/openssl-armv4/sha256-armv4.S`); a "NEON build" needs no new
  perlasm run, only different assembly-time settings.
- **A stand-in `arm_arch.h` next to the `.S` file always wins.** The file includes
  `"arm_arch.h"` with quotes, so the copy in its own directory is found before any
  directory on the include path. The Pi Zero W stand-in fixes `__ARM_MAX_ARCH__` at 6,
  which leaves the NEON function out. To call the NEON code without the capability check,
  `harness/linux/shim/openssl-neon/make_neon_variants.py` copies only the K256 table (with
  its terminating zero word, which the NEON loop tests) and the NEON function into a
  separate file. Assembled, that function has the same 764 instruction words as
  `sha256_block_data_order_neon` in the SDK's `libcrypto.a`, apart from the PC-relative
  offset of the table.
- **The NEON function's state handling matches the integer function's.** The 64 rounds
  run in integer registers while NEON computes the message schedule, so the chaining
  state is loaded with one `ldmia` and stored at the end of each block. A big-endian
  single-block variant for slhdsa-c (`sha256-neon-be.S`) therefore needs the same edits as
  the integer one: byte-swap the eight words after the load, and the reloaded and final
  words around the last additions. The NEON code reads 64 bytes ahead for the next block
  and, on the last block, re-reads that block instead (its "avoid SEGV" step), so a
  single-block call reads only the 64 bytes it is given.

## SHA-256 cost on the A53

Measured with `harness/common/compress_bench.c` on a Pi Zero 2 W (cycle counter, median of
five repetitions of 200,000 chained calls), against the Pi Zero W figures of
`pi-zero-sha256-speed.md`:

| Code | Cycles per 64-byte block, Cortex-A53 | ARM1176 |
|---|---|---|
| slhdsa-c plain C (-O3 with LTO / -O2) | 1,482 / 1,665 | 2,610 (-O2) |
| OpenSSL integer assembly, word loads | 987 | 1,945 |
| the same as a big-endian single-block copy for slhdsa-c | 1,002 | 1,970 |
| OpenSSL NEON assembly, one block per call / four blocks per call | 963 / 911 | no NEON |
| NEON as a big-endian single-block copy / through a C byte-swap wrapper | 976 / 990 | |
| libcrypto `SHA256_Transform()`: NEON path / integer path forced | 973 / 1,000 | 2,085 |

Rules drawn from these:

- **On this 32-bit SeedSigner OS image, libcrypto runs the NEON code by itself**
  (`OPENSSL_armcap_P` is 0x1: the kernel reports NEON and no SHA-256 instructions), so a
  build that links libcrypto already gets NEON SHA-256 without any change.
- **NEON beats the integer code, by a little for single blocks.** The A53 issues two
  instructions per cycle, and the NEON version computes the message schedule in NEON
  registers while the integer rounds run, which saves about 2.5% per single block and 6%
  per block over four blocks. Hash-based signing calls the block function one block at a
  time, so the gain there is about 2 to 2.5% of signing time.
- **The same integer code needs about half the cycles of the ARM1176**, so per clock cycle
  the A53 runs SHA-256 about twice as fast. Whole operations follow: SLH-DSA-SHA2-128s
  signing took about 2.5 billion cycles on the A53 (4.14 s at 600 MHz) against 5.0
  billion on the ARM1176 (5.03 s at 1 GHz). Compare boards in cycles, or state each
  board's measured clock with its times.
- **Fusing the byte swaps into the assembly still pays**: the C wrapper around the NEON
  function costs 14 cycles more per compression than the big-endian copy (about 1.3% of
  SLH-DSA signing).
- **Link-time optimization still matters for SHRINCS and XMSS**: without it, SHRINCS
  signing took 8 to 9% and XMSS signing 14 to 18% more time, while SLH-DSA, whose time is
  almost all in the block function, changed by under 5%.

## Emulating the target with qemu-arm

`qemu-arm` (user mode, version 10.0) runs these binaries with the SDK sysroot
(`qemu-arm -cpu max -L <sysroot>`), which allows a byte-for-byte check of outputs before
any device is available (`scripts/r4_pi02w_qemu_check.sh`). Traps:

- **There is no Cortex-A53 model for 32-bit user mode.** The ARMv7 models do not run
  these binaries: under `-cpu cortex-a15` a `pq_bench` build stops with SIGILL in the
  dynamic loader, before `main`. Use `-cpu max`.
- **`max` reports the SHA-256 instructions**, which the A53 in the BCM2710A1 lacks, so
  libcrypto takes its ARMv8 path under emulation (the probe prints
  `OPENSSL_armcap_P=0x3d`). Set `OPENSSL_armcap=1` to make it take the NEON path.
- **Count jobs that produced nothing.** A row-by-row comparison with the host reference
  passes a build whose processes all fail, if failed jobs leave no rows behind: it sees
  nothing to reject. Count the jobs without output separately and treat any as a failure
  (`scripts/r4_pi02w_qemu_check.sh` lists them in `failed-jobs.txt`).
- **Emulated times do not transfer, not even as a ranking.** Thread creation is expensive
  under emulation: Jade's two-core SLH-DSA signing with one new thread per helper task
  took about twice the one-core time under qemu, while on the Pi Zero 2 W it took 0.57
  times the one-core time. Only outputs are meaningful there.

## Lattice libraries have no 32-bit ARM code paths

- mldsa-native v2.0.0 ships native arithmetic for AArch64 and x86_64 only, and FIPS-202
  backends for AArch64, x86_64, and Armv8.1-M with MVE (an M-profile extension, disabled
  by default as experimental). On an A-profile core in AArch32 state the portable C code
  runs.
- c-fn-dsa uses hardware floating point only with SSE2 on x86, NEON on 64-bit ARM, and
  RV64D. Its NEON code works on `float64x2_t` vectors, which AArch32 NEON does not
  provide, and its Cortex-M4 assembly is guarded by `__ARM_ARCH_7EM__`. On 32-bit ARM
  hard-float it runs its integer floating-point emulation, as on the Pi Zero W and the
  ESP32 boards.

## Jade's two-core paths on Linux

Jade's `slh_dsa.c` and `wots_c.c` contain two-core code behind `#define
CONFIG_FREERTOS_UNICORE 1` lines. Removing those lines from build copies and supplying
POSIX-thread versions of the FreeRTOS calls they use (`harness/linux/shim_dualcore/`) runs
that code unchanged on Linux. Points to keep in mind when reading its timings:

- **CPU time counts both threads.** `CLOCK_PROCESS_CPUTIME_ID` covers every thread of the
  process, so a two-core run's CPU time exceeds its wall time, and wall time minus CPU
  time no longer measures time taken by other processes.
- **Jade creates a helper task for every unit of parallel work** (every WOTS key in an
  XMSS tree, every FORS signature, every grinding search) and waits for it before
  creating the next. A literal mapping (one new thread per task) pays thread creation and
  wake-up each time; a persistent worker thread pays only the wake-up. Both are offered
  (`DUAL_CORE=1`, `DUAL_CORE=pool`) and must be named with any figure. On the Pi Zero 2 W,
  SLH-DSA signing used 4.24 s of CPU time on one core, 4.67 s on two cores with a thread
  per task (wall time 2.43 s), and 4.34 s with a persistent worker (wall time 2.24 s);
  SHRINCS signing, with fewer and longer tasks, differed by 1.4% between the forms.
- **Jade's task functions end with `vTaskDelete(NULL)`.** A persistent worker must turn
  that call into a return to its loop (the stand-in uses `longjmp`); a thread-per-task
  mapping can end the thread there.
- **Two-core SHRINCS output can differ from one-core output.** The grinding split by
  counter parity can find a different valid counter, so signatures differ in bytes and
  must be checked by verification rather than against a one-core reference.
