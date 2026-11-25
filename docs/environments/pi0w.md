# Environment: Pi Zero (a Pi Zero W)

All rounds ran on one board with the same OS image and toolchain.

- **Device:** Raspberry Pi Zero W Rev 1.1 (`/proc/cpuinfo`: BCM2835, ARMv6 processor rev 7,
  CPU part 0xb76, ARM1176JZF-S), 475,896 KiB of RAM visible to Linux (`free`), no swap.
- **OS:** a development build of SeedSigner OS: Buildroot 2024.11.4, Linux 5.15.92 (built
  2025-04-22), glibc 2.40, OpenSSL 3.4.1 (11 Feb 2025, `/usr/lib/libcrypto.so.3`). The
  SeedSigner app was stopped during every timed job and started again afterwards.
- **Toolchain:** GCC 13.3.0 (Buildroot 2024.11.4) in the Docker image
  `ghcr.io/kdmukai-bot/seedsigner-raspi-lvgl/sdk-armv6:ss-os-0.8.0-81-gbfbd791`, run
  through `harness/linux/run-armv6-build.sh`. Every binary is a PIE with full RELRO
  (BIND_NOW and a GNU_RELRO segment) and calls `__stack_chk_fail` (stack protector),
  checked with `readelf`; each links dynamically against libcrypto, libm, and libc.
- **Deployment:** the binaries' SHA-256 on the device equal the host's.
- **Clock:** `force_turbo=1` in `config.txt` holds the ARM clock at 1 GHz, as SeedSigner OS's
  Pi Zero image sets it; the image has no cpufreq or thermal interface. The run's clock
  checks (`compress_bench` from the level-3 build: the CPU cycle counter against wall
  time, run with the app stopped) read 997 to 1,001 MHz. During a run, CPU
  time is the clock evidence: CPU times of the same binaries agree across rounds, which a
  clock change would have shifted in proportion.
- **Load:** the load average at job starts was 0.80 to 1.14; the benchmark process alone
  gives 1.0.
