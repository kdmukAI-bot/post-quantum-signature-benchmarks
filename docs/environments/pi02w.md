# Environment: Pi Zero 2 W

Recorded by `scripts/r4_pi02w_env.sh` over the board's USB network link, before and after
the run.

- **Board:** Raspberry Pi Zero 2 W Rev 1.0 (revision 902120), BCM2710A1, four Cortex-A53
  cores. The 32-bit kernel reports "ARMv7 Processor rev 4 (v7l)" with Features `half thumb
  fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt vfpd32 lpae evtstrm crc32`: NEON, and
  no aes, pmull, sha1, or sha2. AT_HWCAP2 agrees (0x10, crc32 only). 440,588 KiB of RAM
  visible to Linux, no swap.
- **OS:** a development build of SeedSigner OS: Linux 5.15.92-v7 (#1 SMP, built
  2025-04-22), glibc 2.40, and OpenSSL 3.4.1 (11 Feb 2025). `randomize_va_space` is 2. The
  SeedSigner app was stopped during the run and started again afterwards.
- **Toolchain:** GCC 13.3.0 (Buildroot 2024.11.4, its wrapper adding
  `-mcpu=cortex-a53 -mfpu=neon-vfpv4 -mfloat-abi=hard -marm`) in the Docker image
  `ghcr.io/kdmukai-bot/seedsigner-raspi-lvgl/sdk-pi02w:ss-os-0.8.0-81-gbfbd791`, with
  glibc 2.40 and OpenSSL 3.4.1 in its sysroot, run through
  `scripts/r4_pi02w_build_all.sh`.
- **Clock:** without changes the image runs the processor at its 600 MHz minimum: it has
  no cpufreq interface, `config.txt` sets neither `arm_freq` nor `force_turbo`, and
  `vcgencmd measure_clock arm` reads 600 MHz idle and under load. With `force_turbo=1`
  the clock reads 1,000 MHz at a core voltage of 1.275 V (1.25 V at 600 MHz). The CPU
  cycle counter read 1,000 MHz at each of the run's clock checks (`compress_bench`), and
  the record taken after the run still shows 1 GHz.
- **Throttling:** throttling flags 0 in each environment record (`get_throttled`).
