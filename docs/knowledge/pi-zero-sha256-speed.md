# SHA-256 speed for hash-based signatures on the Pi Zero W

The Pi Zero W (BCM2835, ARM1176JZF-S at 1 GHz) has no NEON unit and no SHA instructions, so
SHA-256 runs as integer code. SLH-DSA, SHRINCS, and XMSS spend most of their time in SHA-256
compressions of single 64-byte blocks (SLH-DSA-SHA2-128s signing performs about 2.22 million of
them). This note records what limits the speed of that work on this CPU and the traps met when
measuring and reducing it. Build options named here are those of `harness/linux/Makefile`.

## The compression function is the floor

OpenSSL 3.4.1's integer SHA-256 (`crypto/sha/asm/sha256-armv4.pl`), assembled with word loads
(next section), executes about 1,922 instructions per block and takes about 1,926 cycles per
block on the ARM1176 (measured with the CPU cycle counter, 4 blocks per call). It therefore
runs at one instruction per cycle, without stalls, at about 30 instructions per round on
average. Rescheduling does not help on this single-issue core; only fewer instructions would.
After the changes below, a sampling profile of SLH-DSA-128s signing puts about 86% of the time
inside this function.

## OpenSSL's ARMv6 build loads message words one byte at a time

The perlasm source has two integer variants, selected by `__ARM_ARCH__` when the generated `.S`
file is assembled. Below 7, each message word takes four `ldrb` plus shifts and ORs. At 7 or
above, it takes one `ldr` and one `rev`. Both are ARMv6 instructions, and the ARMv7 integer
path uses nothing else beyond ARMv6, so it runs on the ARM1176. Per block: 2,079 cycles with
byte loads, 1,945 with word loads (6.4% fewer).

Rules:

- OpenSSL's own `arm_arch.h` rejects `__ARM_ARCH__` 7 with `__ARM_MAX_ARCH__` below 7, and
  `__ARM_MAX_ARCH__` 7 pulls in the NEON path and a run-time CPU capability check. Assembling
  the word-load path for ARMv6 needs a stand-in header (`harness/linux/shim/openssl-armv4/arm_arch.h`).
- The word loads may be unaligned. ARMv6 Linux enables unaligned word access, which GCC's
  default `-munaligned-access` for this target also assumes; the word-load variant gave correct
  results with the block at an odd address on the Pi Zero W.
- Assembled with `__ARM_ARCH__` 6, the generated file reproduces the `.text` of
  `sha256_block_data_order` in the SDK's `libcrypto.a` byte for byte, which is a simple check
  that the generation matches the shipped library.
- Mark the assembled object `--noexecstack`; the generated file has no `.note.GNU-stack`.

## Costs around the compression

slhdsa-c keeps the chaining state as big-endian bytes and calls `sha2_256_compress(void *v)`
once per block. An adapter to a native-word-order block function must swap eight words in and
out. Measured costs per call on the ARM1176:

| Path | Cycles per compression |
|---|---|
| slhdsa-c plain C | 2,610 |
| C adapter plus `SHA256_Transform()` in the shared libcrypto, -O2 | 2,266 |
| `SHA256_Transform()` alone, native-order state | 2,085 |
| C adapter (unrolled swaps) plus word-load assembly | 2,005 |
| Word-load assembly with the swaps fused in (no adapter) | 1,970 |

Traps:

- **GCC at -O2 does not unroll an eight-iteration swap loop.** Each iteration then waits on its
  load (load-use latency) and the loop costs about 8 cycles per word. Unroll it explicitly
  (`#pragma GCC unroll 8`).
- **Link-time optimization can make an adapter slower.** With `-flto`, GCC inlined the adapter
  into slhdsa-c's WOTS chain loop, where few registers were free, and the sixteen swaps became
  a serial load, `rev`, store sequence through one register. SLH-DSA signing took 1.7% more CPU
  time than with a call. Keep such an adapter `noinline`.
- **Linking libcrypto statically does not help.** The call into the shared library is not where
  the time goes.

## The mbedTLS-style API dominates SHRINCS and XMSS overhead

Jade's SHRINCS and XMSS code hash through `mbedtls_sha256_*`. On Linux, backing that API with
OpenSSL's `SHA256_Init/Update/Final` makes a one-block hash cost 2,983 cycles for a SHRINCS
chain step (clone, two updates, finish) and 2,591 cycles for a 52-byte one-shot (an XMSS hash),
against 2,079 cycles for the block function OpenSSL uses inside. Backing it with a
native-word-order context over the word-load assembly (1,945 cycles per block), with the
small-input case inlined, brings these to 2,146 and 2,128 cycles. Rules for such a context:

- Keep `clone` proportional to the buffered bytes; SHRINCS clones a context for every hash.
- An unstarted context must hash as SHA-256 (Jade's SHRINCS port updates contexts without
  `starts()`; see `esp-idf-mbedtls-unstarted-sha256-context.md`).
- Small `memcpy` and `memset` calls through the PLT cost more than the bytes they move.
  Straight-line word stores for the padding, and an inline fast path for updates that fit in
  the partial block, remove most of them. Under LTO, the scheme's constant-length updates then
  compile to inline copies.
- If a header used by the scheme sources carries inline code, the scheme objects must depend on
  that header in the build; otherwise a header change silently leaves stale objects.

## Compiler defaults of the SDK toolchain

The Buildroot toolchain wrapper in the seedsigner-raspi-lvgl sdk-armv6 image adds
`-mcpu=arm1176jzf-s -mfpu=vfp -marm -fstack-protector-strong -fPIE -pie` to every compilation.
The CPU flags are already right for the Pi Zero. The other two have a measurable cost on this
workload and must be stated with any timing: with the native API and word-load assembly,
`-fno-stack-protector` reduced signing CPU time by 0.8% for SLH-DSA-128s, 2.5% for SHRINCS-B,
and 3.6% for XMSS. A fully static link (`-static`, which also implies no PIE) removes the PLT
stub from slhdsa-c's frequent `memcpy` calls; it reduced SLH-DSA signing by 1.7% relative to
`-O3 -fno-stack-protector` with the default PIE link. `-O3` matters most for XMSS: with
link-time optimization, XMSS signing took 8% less CPU time at `-O3` than at `-O2`.

## Measuring on the dev SeedSigner OS image

- The image has no `vcgencmd`, no cpufreq sysfs, no thermal zone, and no `/dev/vcio`, so
  neither the ARM clock nor the temperature can be read the usual way. The kernel does expose
  the ARM1176 cycle counter through `perf_event_open()` (there is no `perf` tool), and cycles
  divided by wall time gives the effective clock (999 to 1,000 MHz when undisturbed).
  Preemption lowers this ratio the same way a lower clock would, so it cannot exclude a brief
  clock change by itself. Process CPU time can: for an unchanged binary it stayed within 0.1%
  across passes, which a clock change would have shifted in proportion.
- Wall time includes preemption by other tasks even with the SeedSigner app stopped. Single
  runs occasionally lost up to 0.8 s. For screening, compare process CPU time
  (`CLOCK_PROCESS_CPUTIME_ID`, the `cpu_s` column), which typically repeats within 0.1% between
  runs of one process and, for most builds, between processes (a preempted run can still show
  slightly more; see the next point for an exception); report wall time over many runs.
- The address-space layout can change a process's speed. The image randomizes it
  (`/proc/sys/kernel/randomize_va_space` is 2). With the OpenSSL-backed build (dynamic
  libcrypto, level 2), XMSS 2^10 key generation took 5.42 to 5.62 s of CPU time in six
  processes of the same binary, and signing (the same tree computation) took 5.38 s in six
  processes but 5.51 s in another, while runs within one process agreed within 0.3%. With
  randomization off (busybox `setarch linux32 -R`), three processes all took 5.56 to
  5.57 s. The tuned build (level 3) and older binaries varied by under 0.05% between
  processes. Rule: a 100-run job is one process with one layout, so its standard deviation
  leaves this out. Before reading a difference of a few percent between builds or between
  measurement rounds as a code effect, repeat the operation in several processes, or fix
  the layout with `setarch linux32 -R`.
- Host-side ssh activity is preemption too. An ssh login, a tar of the result files, or a
  grep through a large file on the Pi takes CPU from the benchmark: one result fetch during
  a 100-run job of 8 ms operations raised that job's mean wall time by 19% (ten runs lost up
  to 36 ms each), while its CPU time changed by under 1%. Rule: keep ssh away from timed
  jobs of short operations. Poll the queue log over one long-lived connection (OpenSSH
  `ControlMaster`) at long intervals, and fetch results during untimed passes or after the
  queue.
- A `SIGPROF` sampling profile (`harness/common/sigprof.c`) collects about 100 samples per second of
  CPU time on this kernel, one per scheduler tick.
