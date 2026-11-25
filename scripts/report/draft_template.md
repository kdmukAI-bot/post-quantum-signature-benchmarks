# Post-quantum signature benchmarks on SeedSigner-class hardware

{{DRAFT_STATUS}}

Provenance: the benchmark harness, the measurements, and this document were produced by an
AI agent (Claude) at the direction of GitHub user [kdmukai](https://github.com/kdmukai). The
results have not been independently reviewed.

## 1. Broad findings

This page times post-quantum signature schemes on five boards and compares them with the
hardware wallets in Blockstream's tests:

- **Pi Zero and Pi Zero 2 W:** SeedSigner runs on them today.
- **ESP32-P4:** the initial target for SeedSigner's port to MicroPython, now in progress.
- **ESP32-S3 and RP2350:** smaller chips for a possible stripped-down, ultra-low-cost
  SeedSigner.

**Table C1. Signing speed relative to the Jade Plus (approximate)**

{{C1}}

Averaged over two hash-based signature schemes. The wallet figures are Blockstream's, timed
differently from ours; Table H5 has the per-scheme times.

### SeedSigner's current and future hardware signs in seconds

{{DISC_SPEED}}

### Can the wallets go faster?

{{DISC_FASTER}}

The full results, with run counts and every measured figure, follow in section 3.

{{fndef:c1-method}} {{FN_C1_METHOD}}

{{fndef:tz-hw}} A Trezor developer wrote in trezor/trezor-firmware issue #6835 (2026-04-29)
that branch `cepetr/slh-dsa-hw-sha` reduced SLH-DSA-128 signing time to 20 seconds; the
branch notes record "Signed in 19.657 s" for the vendored SPHINCS+ SHA2-128s reference code
hashing through the STM32U5 HASH unit on a Trezor Safe 7, in Trezor's production-test
firmware with the stack protector off, in one run, and say that roughly 20 seconds "is not
the lower bound". The experiment differs from Blockstream's Safe 3 test in library,
firmware, model, and timing method, and covers one scheme; on production Safe 7 units the
HASH unit is not reachable by applications (`results/published/trezor-hw-sha_2025-12.csv`,
`docs/other-devices-hash-hardware.md`).

## 2. Boards and levels

### What was tested

| Item | Details |
|---|---|
| Boards | {{TESTED_BOARDS}} |
| Hash-based schemes and signature sizes | {{TESTED_HASH}} |
| Lattice schemes and signature sizes | {{TESTED_LATTICE}} |
| Operations | key generation<br>signing<br>verification<br>peak stack and heap |
| Settings | level 1: SHA-256 in portable C<br>level 2: each platform's SHA-256 acceleration<br>level 3: tuned SHA-256 code, compiler settings, and memory placement<br>one and two cores on the Pi Zero 2 W, the ESP32 boards, and the RP2350<br>each platform's default safeguards |

### 2.1 Processors and levels

{{BOARDS}}

| Level | Pi Zero 2 W | Pi Zero | ESP32 boards | RP2350 |
|---|---|---|---|---|
| 1, portable C | SHA-256 in plain C; gcc 13.3 -O2 | SHA-256 in plain C; gcc 13.3 -O2 | SHA-256 in plain C; ESP-IDF -O2 | SHA-256 in plain C; Pico SDK 2.3.1 -O2 |
| 2, platform acceleration | OpenSSL 3.4.1 through its public API, linked statically from the SDK; it selects its NEON SHA-256 code at run time | the system OpenSSL 3.4.1 through its public API | the SHA unit through ESP-IDF's driver functions | the SHA-256 accelerator through the SDK's hardware_sha256 driver functions |
| 3, tuned | a modified copy of OpenSSL 3.4.1's NEON SHA-256 code; a native-word-order SHA-256 API; -O3; LTO | a modified copy of OpenSSL 3.4.1's ARM assembly; a native-word-order SHA-256 API; -O3; LTO | register-level SHA unit access; hot hash-based code in IRAM; larger caches; -O3 | register-level accelerator access; hash-based and SHA-256 code in SRAM; -O3 |

- **Lattice schemes:** levels 1 and 3, one core{{fn:lattice-levels}}.
- **Two cores:** on the Pi Zero 2 W, the ESP32 boards, and the RP2350, every level also runs
  Blockstream's dual-core code paths for the hash-based schemes{{fn:pi2-dual}}{{fn:rp-dual}}.
- **Safeguards:** each platform's defaults{{fn:safeguards}}{{fn:watchpoint}}; other settings
  and their cost are in section 3.6.

Methods: [appendix](#appendix-methods-material-moves-to-methodshtml), until `methods.html`
exists.

## 3. Detailed results

### Signing time by scheme and board

Which rows matter:

- **A device that keeps no state between sessions** (SeedSigner, or any device restored
  from a seed backup): the stateless rows, plus key generation each session (section 3.1).
- **A device that keeps a counter it can never lose or reuse:** the stateful rows.
- **A device short on RAM:** [section 3.4](#34-peak-stack-and-heap).

Signing time at level 3 on one core, rounded to at most three significant figures;
full figures and statistics follow in sections 3.1 to 3.4.

**Table K1. Signing time per scheme on five boards: level 3, one core**

{{K1}}

{{K1_NOTE}}

Number format{{fn:number-format}}: one unit per table, seconds for hash-based signing and
key generation, milliseconds for verification and the lattice schemes.

### 3.1 Hash-based signing and key generation

{{HASH_TABLES}}

Level-1 time divided by level-3 time, one core, from Tables {{HASH_RANGE}}.

**Table D6. Hash-based operations on five boards: level-1 time divided by level-3 time, one core**

{{D6}}

SHRINCS stateless signing, expected value per message ± its standard error (seconds), from
a fit over messages 0 to 9 (n=10){{fn:stateless-fit}}{{fn:stateless-n}}. Fit coefficients:
{{CSV_STATELESS}}.

**Table D7. SHRINCS stateless signing on five boards, expected seconds per message, by level and cores**

{{D7}}

Level 3 against Blockstream's published figures (seconds): our second-round
figures, the ESP32 boards on two cores, against each wallet's own firmware timed on the host
over USB{{fn:swn96}}{{fn:merged-cell}}{{fn:sha1}}. Blockstream's figures, transcribed:
[`results/published/blockstream_2026-08-19.csv`](published/blockstream_2026-08-19.csv).

**Table H4. Our boards at level 3 against Blockstream's wallets: hash-based signing and key generation, seconds**

{{H4}}

How long each device takes to sign, for four schemes: our boards, and every device in the
other published reports we found. The sources used different code and timing methods, so
the comparison is approximate {{fn:h5-method}}.

**Table H5. Signing time on our boards (level 3, one core) and in other published reports: four schemes**

{{H5}}

- **Our boards:** level 3 (each board's tuned build, [section 2.1](#21-processors-and-levels)), one core, timed on the device.
- **Other reports:** figures as published; their code, run counts, and timing methods differ.
- **Hash hardware:** on the Jade Plus, Blockstream's SLH-DSA path hashes in portable C, and its SHRINCS and XMSS paths hash through mbedTLS and the ESP32-S3's SHA unit (Table D18); on the other three wallets the harness hashes in portable C. Of those wallets' chips, only the STM32U585 revision of the Safe 3 (a HASH unit that shipping firmware restricts to secure, privileged code) and the BitBox02 Nova's SAMD51 (its ICM) have SHA-256 hardware; the STM32F427 and the ST33K have none, and no device in any report has Keccak hardware ([`docs/other-devices-hash-hardware.md`](../docs/other-devices-hash-hardware.md)).
- **A dash:** the source did not measure that scheme.

{{fndef:h5-method}} Table H5 in detail. Figures are rounded to two significant figures. Our
boards' figures are level 3 on one core, as in Table K1, with ML-DSA as the expected value
per message. Other reports' figures are as published, converted to these units, from the
transcriptions in `results/published/`; chips and clocks as the chips footnote says.
Rows run fastest first by the geometric mean, over the schemes a row has, of its time
divided by the Pi Zero's. Run counts: Blockstream's figures are averages of 100
executions; pqm4's, of 10 (SLH-DSA) and 100 (ML-DSA) executions; Ledger Donjon's are
labeled averages, with no run count, and called preliminary; the Trezor Model T gist gives one
figure per cell, with no run count; ours are means or expected values over 10 or 100
messages (section 3). Timing: Blockstream timed each operation on the host over the
wallet's USB interface, which includes data transfer and any display work during the
operation (Jade's SLH-DSA signing draws a progress bar); ours time the scheme call on the
device, and pqm4 counts cycles on the device. Implementations: Blockstream ran the same
reference C libraries on every wallet, glued to each wallet's own hash functions; Ledger
Donjon used a plain C Falcon and a low-RAM ML-DSA; pqm4's rows are its portable C
implementations; the Trezor Model T ran PQClean's reference code, with PQClean's own SHA-2
and SHA-3. Hash hardware: at level 3 our ESP32 boards and the RP2350 hash with
the chip's SHA-256 hardware, while Jade's SLH-DSA path on the Jade Plus hashes in portable C; Table
D18 times Jade's own firmware on our ESP32-S3 board
([section 3.6](#36-reproducibility-cost-of-safeguards-and-jade-firmware-calibration)).

### 3.2 Verification

Verification by level on the Pi Zero 2 W and Pi Zero, one core
(milliseconds): means over host-made signatures, n=100{{fn:verify-cycle}}; Pi Zero 2 W round
4, Pi Zero round 3{{fn:r3}}. Lattice verification is in Tables D9a and D9b.

**Table D8a. Pi Zero 2 W (Cortex-A53, 1 GHz) and Pi Zero (ARM1176, 1 GHz): hash-based verification, mean ms, by level, one core**

{{D8a}}

Verification by level on the microcontrollers, one core (milliseconds): means over
host-made signatures, n=10; round 3{{fn:r3}}, the RP2350 round 4{{fn:verify-dc}}.

**Table D8b. ESP32-P4 (400 MHz), ESP32-S3 (240 MHz), and RP2350 (150 MHz): hash-based verification, mean ms, by level, one core**

{{D8b}}

### 3.3 Lattice schemes

Lattice key generation, signing, and verification at levels 1 and 3, one core
(milliseconds): means over inputs 0 to 99 (n=100), and ML-DSA signing as the expected value
per message ± its standard error, with the per-attempt time{{fn:mldsa-e}}{{fn:fndsa-sign}}{{fn:fndsa-standard}}{{fn:rp-cm4}}.
Round 3{{fn:r3}}; the Pi Zero 2 W and the RP2350 round 4.

**Table D9a. Pi Zero 2 W (Cortex-A53, 1 GHz) and Pi Zero (ARM1176, 1 GHz): lattice keygen, signing, and verification, ms, levels 1 and 3, one core**

{{D9a}}

**Table D9b. ESP32-P4 (400 MHz), ESP32-S3 (240 MHz), and RP2350 (150 MHz): lattice keygen, signing, and verification, ms, levels 1 and 3, one core**

{{D9b}}

FN-DSA key generation over seeds 0 to 99, one core (milliseconds): n=100;
round 3{{fn:r3}}, the Pi Zero 2 W and the RP2350 round 4{{fn:fndsa-seed}}.

**Table D10. FN-DSA key generation on five boards: milliseconds over seeds 0 to 99, levels 1 and 3, one core**

{{D10}}

Reduced RAM against default, ML-DSA signing at level 3, one core: the
reduced-RAM configuration's peak stack (Tables D13a and D13b) and expected signing time
(Tables D9a and D9b) divided by the default configuration's.

**Table D11a. Pi Zero 2 W (Cortex-A53, 1 GHz) and Pi Zero (ARM1176, 1 GHz): ML-DSA reduced RAM over default, ratios of stack and time, level 3, one core**

{{D11a}}

**Table D11b. ESP32-P4 (400 MHz), ESP32-S3 (240 MHz), and RP2350 (150 MHz): ML-DSA reduced RAM over default, ratios of stack and time, level 3, one core**

{{D11b}}

Lattice level-1 time divided by level-3 time, one core, from Tables D9a and
D9b{{fn:s3-lattice}}.

**Table D12. Lattice operations on five boards: level-1 time divided by level-3 time, one core**

{{D12}}

### 3.4 Peak stack and heap

Peak stack and heap per operation at level 3, one core unless stated (bytes),
second round, the Pi Zero 2 W and the RP2350 round 4{{fn:memory}}{{fn:pi2-mem}}.

**Table D13a. Pi Zero 2 W (Cortex-A53, 1 GHz) and Pi Zero (ARM1176, 1 GHz): peak stack and heap, bytes, level 3, one core**

{{D13a}}

**Table D13b. ESP32-P4 (400 MHz), ESP32-S3 (240 MHz), and RP2350 (150 MHz): peak stack and heap, bytes, level 3, one core unless stated**

{{D13b}}

Largest peak over all levels and core counts, with where it occurred (bytes;
L: level, c: cores).

**Table D14a. Pi Zero 2 W (Cortex-A53, 1 GHz) and Pi Zero (ARM1176, 1 GHz): largest peak stack and heap, bytes, any level**

{{D14a}}

**Table D14b. ESP32-P4 (400 MHz), ESP32-S3 (240 MHz), and RP2350 (150 MHz): largest peak stack and heap, bytes, any level or core count**

{{D14b}}

### 3.5 Two cores against one

One-core time divided by two-core time on the boards with a second core (the
Pi Zero 2 W and the microcontrollers), from Tables {{D15_FROM}}. XMSS 2^10 has no
two-core path: on the ESP32 boards and the RP2350 its row compares two builds of the same
code, and the Pi Zero 2 W ran it on one core only.

**Table D15a. Pi Zero 2 W (Cortex-A53, 1 GHz): one-core time over two-core time, by level**

{{D15a}}

**Table D15b. ESP32-P4 (400 MHz), ESP32-S3 (240 MHz), and RP2350 (150 MHz): one-core time over two-core time, by level**

{{D15b}}

### 3.6 Reproducibility, cost of safeguards, and Jade firmware calibration

These tables keep first-round figures: Tables D16a to D16c show
measured differences between the rounds, not corrections.

Pi Zero: second-round mean against first-round mean for the same
operation, level, and runs (percent change){{fn:r2-builds}}{{fn:selftests}}{{fn:restore}}.

**Table D16a. Pi Zero (ARM1176, 1 GHz): second round against first round, percent change of the mean, by level**

{{D16a}}

{{D16a_SUM}}

The Pi Zero's level-2 build runs at a speed that depends on the process, as a layout
diagnostic showed: {{D9_LAYOUT}} The SDK image randomizes the
address-space layout, and a 100-run job is one process, so its standard deviation leaves
this component out; most of the level-2 differences above are attributed to it. The cause
inside the layout (cache or TLB conflicts, for example) was not investigated.

ESP32-P4, as Table D16a, per level and core count (percent
change){{fn:p4-shift}}.

**Table D16b. ESP32-P4 (400 MHz): second round against first round, percent change of the mean, by level and cores**

{{D16b}}

{{D16b_SUM}}

ESP32-S3, as Table D16b (percent change).

**Table D16c. ESP32-S3 (240 MHz): second round against first round, percent change of the mean, by level and cores**

{{D16c}}

{{D16c_SUM}}

Cost of safeguards, Pi Zero level 3, first round: means of n=100 runs
(seconds), and in the last two columns the percent change from adding the stack protector
(static builds) and from moving to PIE with dynamic linking{{fn:pie}}.

**Table D17a. Pi Zero (ARM1176, 1 GHz): cost of safeguards at level 3, mean seconds and percent change, first round**

{{COST_PI}}

Cost of the ESP32 compiler stack protector (`-fstack-protector-strong`) at
level 3, first round (percent change against ESP-IDF's defaults){{fn:ssp}}{{fn:ssp-neg}}.

**Table D17b. ESP32-P4 and ESP32-S3: cost of the compiler stack protector at level 3, percent change, first round**

{{COST_SSP}}

Jade firmware calibration, first round: Blockstream's unmodified Jade firmware
on our ESP32-S3 board, timed on the host over USB as Blockstream timed it,
against Blockstream's published Jade Plus figures (seconds){{fn:sha1}}.

**Table D18. Jade firmware on our ESP32-S3 board (240 MHz) against Blockstream's Jade Plus figures, seconds**

{{CAL_JADE}}

## 4. Footnotes

{{FOOTNOTES}}

## 5. Not measured

- **ML-DSA with OpenSSL's Keccak assembly on the Pi Zero 2 W and Pi Zero:** it would add
  integration code of our own between mldsa-native and OpenSSL (mldsa-native's custom FIPS
  202 header hook), and c-fn-dsa has no such hook.
- **FN-DSA with native double precision on the Pi Zero 2 W and Pi Zero:** c-fn-dsa uses
  native floating point only on x86 with SSE2, 64-bit ARM with NEON, and 64-bit RISC-V with
  the D extension, so it has no native path on the Pi Zero 2 W in 32-bit mode or on the
  ARMv6 Pi Zero, and a native-precision figure would need a second implementation.
- **The Pi Zero 2 W in 64-bit mode, or on more than two cores:** SeedSigner OS runs it in
  32-bit mode, and Blockstream's dual-core code assumes one helper task.
- **Lattice code in IRAM on the ESP32 boards or in SRAM on the RP2350:** at level 3 the
  lattice code stays in flash, because IRAM placement would compete for internal RAM with
  the ML-DSA-87 task stack and the hash-based code already placed there; on the RP2350, a
  build with all code in SRAM leaves too little heap for the ML-DSA-87 job's stack.
- **ML-DSA in assembly on the RP2350:** mldsa-native v2.0.0's Arm code is for AArch64 NEON
  and Armv8.1-M MVE, neither of which the Cortex-M33 has.
- **Hedged signing:** ML-DSA and FN-DSA were timed with deterministic signing only; hedged
  signing adds one 32-byte random draw per signature outside the rejection loop.
- **Lattice schemes at level 2:** neither the ESP32 SHA units nor the RP2350's SHA-256
  accelerator computes SHAKE, and no
  OpenSSL-backed SHAKE path was built for the Pi Zero 2 W or Pi Zero, so a level-2 build
  would run the level-1 lattice code.
- **NIST's additional-signature candidates** (for example SQIsign, HAWK, and MAYO): not
  standardized, and their parameters still change between rounds.

## 6. Data and reproduction

- Summary table: `results/summary.csv`, one row per measured configuration, written by
  `scripts/report/fill.py` from the same run logs as the tables on this page. Our run
  logs are not published: checking a figure means rerunning it on the hardware.
- Generated fit tables: {{CSV_FILES}}.
- Board environments: `docs/environments/`, one file per board.
- To rerun: build a board's harness (`harness/linux/` for the Pi boards, `harness/esp-idf/`
  for the ESP32 boards, `harness/pico/` for the RP2350) and run its round's plans with the
  queue scripts in `scripts/`; the logs land under `results/raw/<device>/<round>/` (the
  Pi boards' fetch scripts copy them back from the board). Then run `scripts/report/fill.py` and `scripts/report/build_pages.py`. The generator
  checks every summary figure against its detail table and names any planned log that is
  missing.
- Scripts:
  - `scripts/grind_fit_r2.py`: expected values
  - `scripts/check_r2.py`: correctness gate
  - `scripts/summarize.py`: per-group statistics
  - `scripts/report/fill.py`: this page's generator, with `round2.py`, `levels2.py`,
    `numfmt.py`, and `draft_template.md`
  - `scripts/report/build_pages.py`: the HTML pages, from the generated Markdown
- Table labels: K1, C1, H4, and H5; the per-board tables D1 to D5
  in board order, fastest first; the tables after them in page order from D6, with a for
  the Pi boards and b for the microcontrollers where a table is split.

Run status:

{{STATUS}}

## 7. Corrections

None.

## Appendix: methods material (moves to methods.html)

### Safeguard settings

- **Pi Zero 2 W and Pi Zero:** each board's SDK compiler defaults (`sdk-pi02w`,
  `sdk-armv6`) at every level: `-fstack-protector-strong`, PIE, full RELRO, dynamic
  linking, except that the Pi Zero 2 W's level 2 links OpenSSL's libcrypto statically.
- **ESP32:** ESP-IDF's defaults, which also suit MicroPython firmware (it cannot use the
  compiler stack protector):
  - FreeRTOS task-stack canary check
  - the ESP32-P4 hardware stack guard
  - ESP32-S3 memory protection
  - assertions on
  - no compiler stack protector
  - task watchdog off, because the benchmark task runs for minutes without yielding
- **RP2350:** the Pico SDK's Release defaults, with no compiler stack protector, as on the
  ESP32 boards:
  - FreeRTOS's stack overflow check (method 2)
  - the port's per-task stack limit register
  - a hardware watchdog fed from the tick interrupt, with a fault handler that records
    the fault across the reboot (the counterpart of ESP-IDF's interrupt watchdog and
    panic handler)

### Levels

Every level runs Blockstream's scheme code (jade-hbs @ f5c90a5e) unmodified, with the same
keys and inputs. Levels differ only in how SHA-256 is computed, build settings, and memory
placement. On the Pi Zero 2 W, the ESP32 boards, and the RP2350, every level is also run with
Blockstream's dual-core code paths ("two cores"){{fn:pi2-dual}}{{fn:rp-dual}}; XMSS has no
dual-core path and runs on one core in both builds on the ESP32 boards and the RP2350, and
only in the one-core build on the Pi Zero 2 W.

- **Level 1, portable C:** SHA-256 in plain C for every scheme. Pi Zero 2 W and Pi Zero:
  gcc 13.3 -O2 from each board's SDK, which compiles for that board's CPU. ESP32: ESP-IDF performance optimization (-O2); with two cores, both compute in plain C.
  RP2350: Pico SDK 2.3.1 with GCC 14.2.1 at -O2, as on the other boards (the SDK's Release
  default is -O3), code run from flash; with two cores, both compute in plain C.
- **Level 2, platform acceleration:** documented platform facilities. Pi Zero 2 W:
  OpenSSL 3.4.1 through its public API, the SDK's libcrypto linked statically; libcrypto
  selects its NEON SHA-256 code at run time, as the CPU has no SHA-256 instructions. Pi
  Zero: system OpenSSL 3.4.1 through its public API. ESP32: the SHA unit through ESP-IDF's driver
  functions; with two cores, the second core computes in plain C while the first holds the
  SHA unit. RP2350: the SHA-256 accelerator through the SDK's `hardware_sha256` driver
  functions{{fn:rp-replay}}, code run from flash, -O2; with two cores, the second core
  computes in plain C while the first holds the accelerator.
- **Level 3, tuned:** Pi Zero 2 W: OpenSSL 3.4.1's NEON SHA-256 block function, called
  directly, with a big-endian single-block copy for SLH-DSA, a native-word-order SHA-256
  API for SHRINCS and XMSS, -O3, and LTO, chosen over the Pi Zero's integer code in a
  screen (`docs/knowledge/pi-zero-2w-a53-builds-and-sha256-paths.md`). Pi Zero: a modified copy of OpenSSL
  3.4.1's ARM assembly, the same native-word-order API, -O3, and LTO. ESP32: register-level
  SHA unit access that rewrites only the message words that changed (this relies on the
  unit keeping its message registers, verified on both chips but not documented by
  Espressif), hot code in IRAM, larger caches, and -O3. RP2350: register-level accelerator
  access, the hash-based and SHA-256 code in SRAM, -O3, and the ESP32 boards' SHA-256
  context code; with two cores, the second core hashes with the Pi Zero's level-3 assembly,
  assembled as Thumb-2. Chosen in a screen of the accelerator paths
  (`docs/knowledge/rp2350-sha256-accelerator-no-resume.md`) and of code placement.
- **Calibration:** Blockstream's unmodified Jade firmware on our ESP32-S3 board, timed on
  the host over USB, as Blockstream measured.
- **Lattice schemes:** ML-DSA and FN-DSA run at levels 1 and 3 with those levels' compiler
  settings (level 3: Pi Zero 2 W and Pi Zero -O3 and LTO; ESP32 -O3 and the larger
  caches, with the lattice code left in flash rather than IRAM; RP2350 -O3, with the
  lattice code left in flash), on one core: neither implementation has a dual-core path.
  Both hash with SHAKE, which neither the ESP32 SHA units nor the RP2350's accelerator
  computes, and on the Pi Zero 2 W and Pi Zero no OpenSSL-backed SHAKE path was built, so
  a level-2 build would run the level-1 lattice code; level 2 is not run for them.

### Implementations and inputs

- **Hash-based schemes:** Blockstream's code in the Jade fork (github.com/DmitriiKJ/Jade,
  branch `hash_based_signatures`, commit f5c90a5e), unmodified, in every round.
- **ML-DSA:** mldsa-native v2.0.0 (PQ Code Package, commit
  834a90d5e846ffa1e1611bd24e160bb2e9b86d35; Apache-2.0 OR ISC OR MIT), unmodified, portable
  C backend. Two configurations: the default, and `MLD_CONFIG_REDUCE_RAM` ("reduced RAM"),
  which recomputes data instead of keeping it and gives byte-identical outputs.
- **FN-DSA:** c-fn-dsa by Thomas Pornin (commit 1b858880dcac091b5e5f84f0e4d8617c35ba1392;
  Unlicense, a public-domain dedication), unmodified. It uses native floating point only on
  x86 with SSE2, 64-bit ARM with NEON, and 64-bit RISC-V with the D extension; none of the
  five boards is one of these (the Pi Zero 2 W's Cortex-A53 runs in 32-bit mode), so every
  FN-DSA row, the Pi Zero 2 W's and Pi Zero's included, runs the library's integer
  emulation of floating point.
- **Inputs:** run x uses the 32-byte input x (big-endian) as message or key-generation seed,
  as in the first round. Lattice signing uses the key pair generated from input 0, with an
  empty context string.

### Expected values

- SHRINCS-L stateful signing at swn=140: messages 0 to 9 need {{L140_M10}} WOTS+C attempts on
  average against the expectation of {{E_WOTS_L140}}, so a plain mean over them is not an
  estimate of the expected signing time. On the Pi Zero 2 W and Pi Zero the fit uses the
  swn=140 job alone; on the ESP32 boards and the RP2350 it pools the swn=96 and swn=140
  runs of one job set.
- SHRINCS stateless signing: the method is in the caption of Table D7; per-fit coefficients are in {{CSV_STATELESS}}.
- ML-DSA signing: see the text after Tables D9a and D9b; per-fit coefficients are in {{CSV_MLDSA}}.

### Correctness and independent verification

- Correctness, first round: every one-core output matches the Pi Zero level 2 output byte
  for byte (Pi Zero: four other first-round runs, 4,436 rows; ESP32: 32 job sets, 904
  one-core rows). Two-core outputs match too, except SHRINCS signatures, which can differ in
  bytes because the first valid counter found wins. Correctness of that path rests on the
  two-core self-test, which signs and verifies with a consistent key and passed in all 16
  two-core SHRINCS job sets.
- Correctness, rounds 2 to 4: {{CORRECTNESS}}
- Independent verification (host only, with `scripts/slh_dsa_openssl_verify.py`,
  `scripts/fips205_sha2_check.py`, `scripts/shrincs_cpp_verify.py`,
  `scripts/xmss_fixed_key_check.c`, and `scripts/check_mldsa_openssl.py`):
  - SLH-DSA-SHA2-128s: OpenSSL 3.5.7, in FIPS 205 pure mode with an empty context and
    deterministic signing, produces byte-identical keys and signatures for inputs 0 to 99
    and verifies its signatures; every first-round SLH-DSA row (1,109 signing, 957 key
    generation, including screening runs) equals OpenSSL's output, and {{OPENSSL_SLH}}, which every board's
    second-round output and the Pi Zero 2 W's and RP2350's round-4 outputs equal.
  - SPHINCS+ 2^40 (parameters OpenSSL cannot load): a FIPS 205 verifier written from the
    standard, and cross-checked against OpenSSL on SLH-DSA-SHA2-128s, verifies the
    signature of message 0 and reproduces every key generation output; signatures of
    messages 1 to 99 were not checked independently.
  - SHRINCS: shrincs-cpp (BlockstreamResearch, commit 7643d953; a second implementation
    from the same group, not independent authorship) fully verifies the self-test
    signatures and every SHRINCS-L signature at swn=140 (messages 0 to 99); signatures made
    with the fixed SHRINCS-B key pass every check short of the final root comparison;
    signatures at swn=96 cannot verify, because both verifiers check the fixed target sum
    140.
  - XMSS 2^10: no independent verifier exists for Jade's variant (WOTS+C in place of
    WOTS+, a new OID).
  - ML-DSA: {{OPENSSL_MLDSA}}.
  - FN-DSA: no independent check; c-fn-dsa's own self-tests pass on the host, with native
    floating point and with the emulation the boards use.
- In the second round, SHRINCS-L stateful signing at swn=140 checks each signature with
  Jade's verifier (its verified column reads 1, against -1 in the first round); its output
  bytes are unchanged.

### Other notes

- Pi Zero level 1, swn=140 (first round): run 19 lost 5.0 s of wall time to other
  processes (wall time minus CPU time). Excluding it moves the expected value by 0.2%, so
  all runs are kept.
- The FreeRTOS end-of-stack watchpoint: the checks that stay on cover most of what it
  detects: the ESP32-P4's hardware stack guard panics as soon as the stack pointer leaves
  the running task's stack, and FreeRTOS checks a canary at each context switch. The
  watchpoint adds detection of a store into the last 32 bytes of the stack while the stack
  pointer is still in bounds (`docs/knowledge/esp32-p4-stack-watchpoint-cost.md`).
- Knowledge notes:
  - comparison caveats (timing method, Jade build settings, mbedTLS overhead, SHA-1 in
    Jade's SHRINCS port): `docs/knowledge/jade-hbs-benchmark-notes.md`
  - grinding method: `docs/knowledge/shrincs-l-grinding-time-method.md`
  - ML-DSA attempts: `docs/knowledge/ml-dsa-signing-attempts.md`
  - ESP32 limits for the lattice schemes:
    `docs/knowledge/esp32-lattice-scheme-hardware-limits.md`
  - verifying Jade's signatures elsewhere:
    `docs/knowledge/verifying-jade-hbs-signatures-elsewhere.md`
  - level 3 methods: `docs/knowledge/esp32-sha-unit-register-costs.md`,
    `docs/knowledge/pi-zero-sha256-speed.md`,
    `docs/knowledge/pi-zero-2w-a53-builds-and-sha256-paths.md`, and
    `docs/knowledge/rp2350-sha256-accelerator-no-resume.md`
  - RP2350 port: `docs/knowledge/rp2350-pico-sdk-freertos-porting-traps.md` and
    `docs/knowledge/rp2350-unattended-fault-recovery.md`

{{fndef:fixed-keys}} Signing uses Blockstream's fixed keys from Jade's signing handlers, as
Jade's firmware does. The fixed SHRINCS key is consistent under SHRINCS-L and inconsistent
under SHRINCS-B, and the fixed XMSS key is inconsistent (its stored root differs from the
one its seeds produce), so SHRINCS-B and XMSS signatures made with them cannot be verified;
timing does not depend on this. Verification (Tables D8a and D8b) and the self-tests use keys
derived consistently from seeds: recomputing each fixed key's public parts from its seeds
(`scripts/xmss_fixed_key_check.c`) and verifying with shrincs-cpp
(`scripts/shrincs_cpp_verify.py`) showed the mismatches above.

{{fndef:deterministic}} Signing is deterministic: ML-DSA with rnd set to 32 zero bytes (FIPS
204 permits this; hedged signing is its default) and FN-DSA with a fixed 40-byte signing
seed, so outputs match across boards byte for byte. Hedged signing adds one 32-byte random
draw per signature outside the rejection loop and was not timed.

{{fndef:r3}} Round 3 reran verification on the Pi Zero and the ESP32 boards at every
level, and the lattice schemes at n=100 over inputs 0 to 99 on those boards at levels 1 and
3, with the second round's
builds unchanged apart from printing times to 1 µs instead of 0.1 ms. At 0.1 ms, operations under about 3 ms carry one or two significant figures,
and averaging does not remove the rounding for deterministic operations
(`docs/knowledge/benchmark-timing-resolution-and-untimed-work.md`); the second round's
ESP32 level-1 lattice runs also covered inputs 0 to 9 only (n=10). For operations of 3 ms
or more, round 3's means agree with the second round's within 0.52% on the ESP32-P4 and
within 0.30% on the ESP32-S3, apart from level-1 FN-DSA-512
verification (1.22%), where rounding each round-3 run to 0.1 ms reproduces the second
round's mean. On the Pi Zero, wall-time means differ between the rounds by up to 5.48%
(31 of 49 within 1%), while CPU-time means differ by at most 1.56% (48 of 49 within 1%):
the difference is time taken by other processes during some runs. The tables report wall
time on every board.

{{fndef:shrincs-q}} {{FN_SHRINCS_Q}}

{{fndef:fndsa-standard}} FN-DSA is not standardized: no FIPS 206 draft was found as of
2026-11-20, so c-fn-dsa implements its author's reading of the expected standard, its key and
signature formats may change, and its known-answer vectors are its own. Every FN-DSA figure,
the Pi Zero 2 W's and Pi Zero's included, uses c-fn-dsa's integer emulation of floating
point.

{{fndef:watchpoint}} The FreeRTOS end-of-stack watchpoint
(`CONFIG_FREERTOS_WATCHPOINT_END_OF_STACK`) is off in every build, as it is by ESP-IDF
default and in Jade's configuration. In separate runs it slowed signing on the ESP32-P4 by 12
to 31% at every level, plain C included, and changed no time on the ESP32-S3 by more than
0.2% (`docs/knowledge/esp32-p4-stack-watchpoint-cost.md`).

{{fndef:number-format}} At most four significant figures. The last digit shown is no finer
than the leading digit of the figure's standard error (of a mean: the standard deviation of
the runs divided by the square root of n; of an expected value: the fit's) or of the print
resolution of its timings (0.1 ms in rounds 1 and 2, 1 µs in rounds 3 and 4), whichever is
coarser. Expected values carry their standard error after ±, to one significant figure; it
covers the fit only, not the spread of the per-message work around its expectation. Ratios
have three significant figures; percent changes are given to 0.01 or 0.1 points. Tables
K1 and C1 round the detail-table figures further (half up), and `scripts/report/fill.py`
checks every such figure against the detail table, and C1's figures from other reports
against their transcriptions in `results/published/`.

{{fndef:grinding}} SHRINCS-L stateful signing grinds a WOTS+C counter until the digit sum
reaches swn=140, a message-dependent number of attempts, so its figure is the expected time
per message from a least-squares fit of time against attempts (counters from each run's
grind column), evaluated at the exact expectation of {{E_WOTS_L140}} attempts
(`docs/knowledge/shrincs-l-grinding-time-method.md`, `scripts/grind_fit_r2.py`). The
appendix gives the attempt counts of messages 0 to 9.

{{fndef:layout}} {{FN_LAYOUT}}

{{fndef:sha512}} In every Pi Zero 2 W and Pi Zero build, the one SHA-512 call per key
generation (seed
derivation, inside the timed section of every hash-based key generation) goes through
OpenSSL 3.4.1 (`harness/linux/shim/sha512_openssl.c` at levels 1 and 3,
the OpenSSL-backed shim at level 2), so the levels differ in SHA-256 only. Its cost was not
measured separately.

{{fndef:stateless-n}} n=10 on the Pi Zero 2 W and Pi Zero
 as well (n=100 for their other operations), because each run takes minutes. On the RP2350, where one run takes 9 to 37 minutes, n=10 holds at
level 3 on one core only; the other counts are n=6 at level 3 on two cores and at level 2,
n=5 at level 1 on one core, and n=3 at level 1 on two cores, too few runs for the two-core
fit, so those two cells read n/a (`scripts/r4_plans/rp2350-stateless.plan`).

{{fndef:merged-cell}} Blockstream's key generation table gives one figure per wallet for
SLH-DSA-SHA2-128s and SPHINCS+ 2^40 together (one table cell spans both rows), so both rows
carry the same published figures.

{{fndef:sha1}} Jade's SHRINCS port leaves its mbedTLS SHA-256 contexts unstarted, which on
ESP hardware hashes with SHA-1 (`docs/knowledge/esp-idf-mbedtls-unstarted-sha256-context.md`).
The benchmark builds start every context as SHA-256, so Jade's firmware SHRINCS rows in
Table D18 time different hash computations from ours; the material examined does not state
which build produced Blockstream's published figures
(`docs/knowledge/jade-hbs-benchmark-notes.md`).

{{fndef:verify-cycle}} The Pi Zero 2 W and Pi Zero verify the ten embedded signatures in
turn (run x verifies message x mod 10), so their n=100 is ten passes over the same ten
signatures; the
ESP32 boards and the RP2350 verify each once.

{{fndef:mldsa-e}} ML-DSA signing repeats a rejection-sampling loop a message-dependent number
of times. The expected values use mldsa-native's key-averaged expectations ({{MLDSA_E}}
attempts for ML-DSA-44, -65, and -87) rather than the benchmark key's own mean, because a
reader's key is not the benchmark key (`docs/knowledge/ml-dsa-signing-attempts.md`).
Attempts per message come from the host counting build of `harness/linux/`; outputs are
deterministic, so the counts hold on every board. {{FN_MLDSA_NOTE}}

{{fndef:fndsa-seed}} FN-DSA key generation time depends on the seed, and c-fn-dsa exposes no
attempt counter, so the figure is a mean over seeds 0 to 99 on every board, without a scaling
model. {{FN_FNDSA_SEED}}

{{fndef:s3-lattice}} {{FN_S3_LATTICE}}

{{fndef:memory}} On the ESP32 boards and the RP2350 each figure is the largest over the n
timing runs of the per-run task's stack high-water mark and of the drop in free heap during
the run (internal heap on the ESP32 boards, the FreeRTOS heap on the RP2350). On the Pi Zero 2 W and Pi Zero the figures come from separate memory builds: each run in a new thread
on a stack filled with a known byte beforehand, and the largest number of bytes outstanding
through the `malloc` family, counted by wrappers linked into the benchmark (allocations
inside libc and libcrypto are not counted; the schemes allocate nothing themselves). Those
builds ran n=10 for verification and the lattice operations, n=3 for the hash-based signing
and key generation, and n=1 for SHRINCS-L stateful signing at swn=140 and for stateless
signing; every run of an operation gave the same peak. On both platforms the window is the
whole operation call, including the harness's untimed copies of keys and inputs and its
verification of new signatures; the heap figures include the harness's buffers and, on two
ESP32 cores, the helper tasks' stacks. Self-tests are omitted. Method:
`docs/knowledge/peak-memory-measurement.md`.

{{fndef:selftests}} Self-tests: the ESP32 boards ran each self-test once in the first round
and n=10 in the second, so the comparison uses run 0; the Pi Zero ran them n=3 in both
rounds. Only the signature is timed.

{{fndef:restore}} Each SHRINCS self-test first restores a consistent key from its seed
(`shrincs_restore()`, untimed), which rebuilds the stateful tree and a whole hypertree layer;
on the ESP32 boards this makes a SHRINCS-B self-test take minutes of wall time per run
(`docs/knowledge/benchmark-timing-resolution-and-untimed-work.md`).

{{fndef:p4-shift}} {{FN_P4_SHIFT}}

{{fndef:lattice-levels}} Both lattice implementations hash with SHAKE, which neither the
ESP32 SHA units nor the RP2350's SHA-256 accelerator computes, and no OpenSSL-backed SHAKE path was built for the Pi Zero 2 W or Pi Zero,
 so a level-2
build would run the level-1 lattice code; neither implementation has a two-core path.

{{fndef:safeguards}} Pi Zero 2 W and Pi Zero: their SDK compilers' stack protector, PIE,
and full RELRO.
ESP32 boards: ESP-IDF's FreeRTOS stack canary, the ESP32-P4 hardware stack guard, and
ESP32-S3 memory protection. RP2350: FreeRTOS's stack overflow check, the per-task stack
limit register, and a hardware watchdog. Details: the appendix.

{{fndef:stateless-fit}} The fit is time = fixed + k_pors
x (PORS+FP attempts) + k_wots x (WOTS+C attempts, both layers) + k_tree x (PORS+FP tree hash
calls), with a key derived consistently from a seed, evaluated at {{D7_E_PORS}} PORS+FP
attempts, {{D7_E_WOTS_B}} (SHRINCS-B, swn=2040) or {{D7_E_WOTS_L}} (SHRINCS-L, swn=140)
WOTS+C attempts per layer, and {{D7_E_TREE}} tree hash calls; on two cores the WOTS+C
attempts are split by counter parity. Without the tree-work term the largest residual of a
one-core fit is {{D7_R3}} s; with it, the largest over all fits is {{D7_R4}} s
(`scripts/grind_fit_r2.py`; the tree work per message comes from the host build of
`scripts/pors_work.c`).

{{fndef:swn96}} SHRINCS-L at swn=96 appears only in Table H4, to match Blockstream's table:
it is a mean over the same inputs, and 140 is the scheme's specified target sum.

{{fndef:verify-dc}} {{FN_VERIFY_DC}}

{{fndef:fndsa-sign}} {{FN_FNDSA_SIGN}}

{{fndef:r2-builds}} The second-round builds compile the hash-based code with the first
round's options and add the lattice code and the embedded verification vectors; on the ESP32
boards they also run one task per run and handle console commands. None of it runs inside a
timed section.

{{fndef:pie}} SHRINCS-L at swn=140 is an expected value. Where PIE with dynamic linking is
faster than the static build, the cause was not investigated.

{{fndef:ssp}} `CONFIG_COMPILER_STACK_CHECK_MODE_STRONG`, as in Jade's build configuration.
Only native ESP-IDF projects can use it: it breaks MicroPython's setjmp/longjmp exception
handling.

{{fndef:ssp-neg}} {{COST_SSP_NOTE}}

{{fndef:pi2-clock}} {{FN_PI2_CLOCK}}

{{fndef:pi2-dual}} On the Pi Zero 2 W, Blockstream's dual-core code paths run over a stand-in
for the FreeRTOS task calls they use, built on POSIX threads: one persistent worker thread
runs the second core's tasks, and Linux places the threads on the board's four cores
(`harness/linux/shim_dualcore/`).

{{fndef:pi2-mem}} The Pi Zero 2 W's level-2 memory figures come from builds that link the
board's shared OpenSSL library, as on the Pi Zero. Level-2 memory builds that link it
statically abort at process exit, because the heap counters then also wrap libcrypto's own
allocation calls (`docs/knowledge/peak-memory-measurement.md`); the level-2 timing builds
link it statically.

{{fndef:rp-dual}} On the RP2350, FreeRTOS runs on both cores (its SMP kernel), so
Blockstream's dual-core code paths run with the kernel's own task calls; one header maps
ESP-IDF's `xTaskCreatePinnedToCore` onto the kernel. The tick is 100 Hz, as in ESP-IDF,
because Blockstream's grinding loops wait one tick at a time
(`docs/knowledge/rp2350-pico-sdk-freertos-porting-traps.md`).

{{fndef:rp-replay}} The RP2350's SHA-256 accelerator cannot load a saved state: writes to
its result registers are ignored, and the next block continues from the accelerator's own
state (`docs/knowledge/rp2350-sha256-accelerator-no-resume.md`). At levels 2 and 3 the
code rebuilds a precomputed state, such as SLH-DSA's state after the PK.seed block, by
replaying the block that produced it, and computes any state it has not seen in software.
In SLH-DSA-SHA2-128s and SHRINCS-B signing nearly every compression is a replay, and in the
signing operations counted none ran in software
(`docs/knowledge/rp2350-sha256-accelerator-no-resume.md`).

{{fndef:rp-l2-dc}} {{FN_RP_L2DC}}

{{fndef:rp-cm4}} {{FN_RP_CM4}}

{{fndef:boards}} The board names in this report stand for these boards. Pi Zero: a Pi Zero
W, with the Pi Zero's BCM2835 at 1 GHz and 512 MB of RAM; the W adds a wireless chip, for
which SeedSigner OS's Pi Zero image builds no driver (its kernel configuration,
`opt/pi0/board/kernel.config` in seedsigner-os, leaves out Wi-Fi and Bluetooth support).
The scripts and `results/summary.csv` identify this board as `pi0w`. Pi Zero 2 W: a Pi Zero 2 W, which
SeedSigner's releases support, though it is less common than the Pi Zero. ESP32-P4: a
Waveshare ESP32-P4 WiFi6 Touch LCD 4.3. ESP32-S3: a Waveshare ESP32-S3 Touch LCD 2.
RP2350: a Waveshare RP2350 Touch LCD 2.

{{fndef:chips}} Our boards' chips and clocks are our own records (section 2.1). The other
devices' chips and clocks come from vendor and certification documents, and the Jade Plus's
from Jade's build configuration, not from the reports themselves
(`docs/other-devices-hash-hardware.md`, `docs/knowledge/jade-hbs-benchmark-notes.md`).
The Trezor Safe 3 has two hardware revisions, and Blockstream does not say which it timed.

{{fndef:comp-gist}} The gist holds the results table of trezor/trezor-firmware pull request
#4901 (closed without merging), which states: "All the benchmarks were run on a Trezor T."
Neither names the clock; each figure is one value with the RAM used, with no run count
(`results/published/onvej-sl-gist_2025-04.csv`).

{{fndef:comp-donjon}} Ledger Donjon's post gives memory figures measured on the ST33K secure
element and a separate table of execution times, labeled averages, without naming the device
that ran them. Its FN-DSA-512 figure is for Falcon-512 ("a non optimized, plain C version"),
and its ML-DSA-44 figure is for ZKNox's low-RAM implementation
(`results/published/ledger-donjon_2026-02-26.csv`).

{{fndef:comp-pqm4}} pqm4 publishes cycle counts; the times here are its average divided by
the clock its results pages state (20 MHz on the NUCLEO-L4R5ZI, a Cortex-M4 board).
SLH-DSA-SHA2-128s uses its `ref` implementation and ML-DSA-44 its portable `clean` one, the
closest to ours; its Cortex-M4 assembly (`m4f`) signs ML-DSA-44 in about half the cycles.
Its FN-DSA figures are left out: they appear only in `benchmarks.md`, whose clock the README
gives as 24 MHz (`results/published/pqm4_2026-11-24.csv`).
