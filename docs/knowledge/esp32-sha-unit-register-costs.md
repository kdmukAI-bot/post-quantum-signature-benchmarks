# Where a SHA-256 compression's time goes on the ESP32-S3 and ESP32-P4 SHA units

Companion to `esp32-sha-unit-raw-compression.md`, which covers how the benchmark reaches
the SHA unit at all. This note covers what one compression costs once it does, and the
rules that follow for code that compresses millions of single blocks (hash-based
signatures).

All figures are CPU cycles per compression, measured with the cycle counter over 20,000
compressions of one buffer held in internal RAM, with the unit held (the microbenchmark in
`harness/esp-idf/main/microbench_esp.c`, build options `PQB_MICROBENCH=1
PQB_SLH_COMPRESS=mb`). ESP32-S3 at 240 MHz, ESP32-P4 (chip revision v3.2) at 400 MHz,
ESP-IDF v5.5.5, -O2, code in flash and default caches. The signing times quoted later are
single screening runs. Neither the microbenchmark's logs nor the screening logs are part of
this repository's data; the microbenchmark builds from the sources named above.

## The unit is fast; reaching it is not

| Step | ESP32-S3 | ESP32-P4 |
|---|---|---|
| Write the 8 state words (H_MEM) and 16 block words (M_MEM) | 360 (15 per write) | 720 (30 per write) |
| Start, then poll SHA_BUSY_REG until idle (4 polls on both chips) | 141 | 170 |
| Read the 8 state words back | 198 (25 per read) | 230 (29 per read) |
| One SHA_BUSY_REG read | 18 | 25 |
| Whole compression, register accesses only | 684 | 1,111 |
| Whole compression through ESP-IDF's `sha_core.h` calls | 796 | 1,201 |
| Plain C (slhdsa-c's portable compression) | 3,863 | 4,156 |

The engine finishes a block in roughly the time of four status reads. Each register access
costs 15 to 30 CPU cycles, and a compression needs 33 of them, so about 80% (ESP32-S3) and
85% (ESP32-P4) of the time goes to moving words across the peripheral bus. The ESP32-P4
pays twice the ESP32-S3's cycles per register write, which is why its SHA-unit path takes
more cycles per compression than the ESP32-S3's despite its faster core.

## Rules that follow

1. **Set the mode once per acquisition, not per block.** `esp_sha_acquire_hardware()`
   resets the unit, so set the mode after acquiring; it then stays set. ESP-IDF's
   `esp_sha_set_mode()` also waits for idle; per block it costs about 57 cycles on both
   chips.
2. **The unit keeps M_MEM after hashing a block.** On both chips, reading M_MEM back after
   1,000 blocks showed no changed word. Code that keeps a copy of what it last wrote can
   skip the words that did not change. In slhdsa-c's WOTS+ chain loop only 5 of the 16
   block words change between steps, and this alone cuts a compression from 684 to 507
   cycles (ESP32-S3) and from 1,111 to 854 cycles (ESP32-P4).
3. **H_MEM must be rewritten unless the block continues the previous one.** The unit
   overwrites H_MEM with each result. Hash-based signature code mostly restarts every
   block from the same precomputed midstate, so the 8 state writes are needed for nearly
   every block. Two exceptions avoid them: a block whose input state is the SHA-256
   initial value (start with SHA_START_REG, which applies the initial value internally)
   and a block that continues from the previous output (start with SHA_CONTINUE_REG
   without rewriting H_MEM). Detecting these cases costs a compare and a copy of the
   output on every block (`sha256_hwmin.h`, the "min" path). On the ESP32-P4 it pays off
   for XMSS, whose one-shot hashes of 96 and 128 bytes make nearly every block either a
   first or a continuation block (XMSS signing 7.20 to 6.60 s), and costs 2.5 to 3% on one
   core for the other schemes (under 1% on two cores). On the ESP32-S3 it barely helped
   XMSS (9.54 to 9.50 s) and cost 3 to 4% elsewhere: in the microbenchmark a continuation
   block with one changed block word took 501 cycles, against 510 for a block with all 8
   state words and 5 block words written, so skipping writes there saves far less than
   single writes cost in isolation.
4. **Any copy of the register contents must be reset whenever the unit is acquired**,
   because acquisition resets the unit and other code (mbedTLS) may have used it in
   between.
5. **Memory barriers are not the bottleneck on the ESP32-S3.** Xtensa GCC emits a MEMW
   before every volatile access (`-mserialize-volatile` is its default). Writing the data
   registers through plain pointers with one barrier before and after the start write
   saved 24 of 684 cycles. On the ESP32-P4 the generated code is the same either way.
6. **The register path drops ESP-IDF's fault-injection check.**
   `esp_sha_read_digest_state()` aborts when the digest reads back as all zeros. Code that
   reads H_MEM directly does not get this check.

## What remains per compression in a signature

Whole signing operations divided by the number of compressions in the timed section
(single core, the same run 0 inputs as the benchmark, plain-C overhead from slhdsa-c's and
Blockstream's own code included):

| Operation (compressions) | Path | ESP32-S3 | ESP32-P4 |
|---|---|---|---|
| SLH-DSA-SHA2-128s sign (2,218,214) | plain C | 4,180 | 4,453 |
| | ESP-IDF calls | 1,108 | 1,486 |
| | registers | 1,006 | 1,401 |
| | registers, unchanged M_MEM words skipped | 830 | 1,164 |
| SHRINCS-B sign (580,725) | ESP-IDF calls | 1,570 | 1,922 |
| | registers, unchanged M_MEM words skipped | 1,249 | 1,595 |
| XMSS 2^10 sign (1,671,996) | ESP-IDF calls | 1,832 | 2,113 |
| | registers, unchanged M_MEM words skipped | 1,560 | 1,928 |

In SLH-DSA about 300 to 320 cycles per compression are the scheme's own work (copying
midstates and addresses, function calls), on both chips. SHRINCS and XMSS spend more per
compression outside the compression function, because they hash through a context API
(initialize, clone, update, and finish per hash) rather than compressing caller-held
blocks.

## Plain C on the ESP32-P4 is slower per cycle for instruction reasons, not memory

slhdsa-c's compression takes 4,156 cycles on the ESP32-P4 and 3,863 on the ESP32-S3.
Placing the code in internal RAM and enlarging the L2 cache from 128 KB to 256 KB changed
the ESP32-P4 figure by less than 0.1%, and running plain C on the second core at the same
time did not slow either core. The compiler's target for the ESP32-P4
(`rv32imafc_zicsr_zifencei_xesploop_xespv`) has no rotate instruction, so each of
SHA-256's rotations takes three instructions; on the ESP32-S3 a rotation takes two.

## On the ESP32-S3, code in flash slows down when both cores run it

ESP-IDF configures one instruction cache and one data cache for the whole ESP32-S3 (a
single size setting for each), which both cores use to run code from flash. With the
plain-C compression in flash, running it on core 1 while core 0 runs it too raised core
0's cost from 3,863 to 5,270 cycles per compression (36%) and core 1 ran at 4,735. With
the scheme code and the plain-C compression placed in internal RAM (linker fragment
`harness/esp-idf/main/pqb_iram.lf`, build option `PQB_IRAM=1`) and the larger caches, the
same test gave 3,911 and 3,901 cycles. This is the cause of the ESP32-S3 dual-core
slowdown recorded in `esp32-sha-unit-raw-compression.md`. The register path on core 0 was
not affected (684 against 690 cycles) because it runs from internal RAM and touches only
registers and internal RAM.

Placement matters more than cache size. Dual-core SLH-DSA-128s signing with the
M_MEM-skipping register path took 7.13 s with code in flash and the default caches, 6.98 s
with the larger caches (32 KB instruction, 64 KB data with 64-byte lines), 6.90 s with the
code in internal RAM, and 6.90 s with both. On one core neither change made a difference
(7.42 s in all four cases). Without the placement, a faster core 0 gains little from the
second core: 7.42 s on one core against 7.13 s on two.

## Sharing the unit between the cores costs a lock on every compression

Blockstream's dual-core code makes core 0 wait at the end of every WOTS+ key for core 1's
last chain, which core 1 computes in plain C under the hybrid rule. Letting core 1 use the
unit while core 0 is idle (`harness/esp-idf/main/sha256_compress_hwshare.c`) needs a lock
that core 0 also takes for each of its compressions, and core 0's copy of M_MEM must be
rewritten after core 1 has used the unit. A compare-and-swap lock cost about 33 cycles per
compression on the ESP32-S3 and about 80 on the ESP32-P4 (measured on XMSS, which has no
dual-core path and so gains nothing). On the ESP32-S3 the shorter wait outweighed that for
SLH-DSA-128s (dual-core signing 6.86 to 6.57 s) but not for SHRINCS-B or XMSS; on the
ESP32-P4 it did not pay off for SLH-DSA. Restricting the rule to SLH-DSA operations
through the existing begin hooks keeps most of the SLH-DSA gain (6.62 s) without the lock
elsewhere.

## A long silence before the first SHRINCS-B result is not a hang

The SHRINCS self-test calls `shrincs_restore()` before its timed section. It regenerates
the key with the SHA unit taken and released for every compression (nobody holds it
outside the timed section), at roughly 9 µs per compression on the ESP32-P4. With
SHRINCS-B the original hardware build printed nothing for more than 140 s on the ESP32-P4
after its header line, and the register-level builds behaved the same; a capture that
gives up after a minute or two reports a hang that is not there.
