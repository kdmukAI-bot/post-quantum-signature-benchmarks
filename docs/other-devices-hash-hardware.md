# Hash hardware on the other devices in published post-quantum signing reports

For each device that other published reports timed, this note asks whether the chip has
hash hardware that the published benchmark did not use and whether that hardware could
plausibly change the timings. The hash-based schemes in Blockstream's post (2026-08-19)
spend nearly all their time in SHA-256 compressions, so for them the question is SHA-256
hardware. The two lattice reports (the Trezor gist of 2025-04 and Ledger Donjon's post of
2026-02-26) hash with SHAKE, so for them it is Keccak hardware. For comparison, on the
Jade Plus's ESP32-S3 this benchmark found that the SLH-DSA path in Blockstream's harness
hashes in portable C and that the chip's SHA unit makes SLH-DSA-SHA2-128s signing 3.80
times faster ([jade-notes] "Where the gap comes from").

Labels used throughout: **[source]** a document states it; **[code]** read in source code
at the commit named; **[inferred]** reasoning from the other two. Researched by reading
code, data sheets, and certification documents; nothing was built or run on these devices.
Where a vendor page could not be fetched (st.com timed out for RM0456 and the ST33 data
briefs), the note says so and uses another document.

## Capability matrix

| Device (report) | Chip, core, clock | SHA-256 hardware | Keccak hardware | Used by the published benchmark | Rough headroom | Evidence |
|---|---|---|---|---|---|---|
| Jade Plus (Blockstream), for reference | ESP32-S3, Xtensa LX7, 240 MHz | SHA unit | none | SLH-DSA: no, portable C. SHRINCS and XMSS: yes, through mbedTLS (SHRINCS hashes SHA-1 there, a port defect) | SLH-DSA-SHA2-128s signing 3.80x with the SHA unit (measured here) | [jade-notes] |
| Trezor Safe 3 rev A, T2B1 (Blockstream) | STM32F427, Cortex-M4F, 180 MHz | none | none | software: slhdsa-c portable C (SLH-DSA), trezor-crypto `sha2.c` (SHRINCS, XMSS) | none from hash hardware | [tz-models], [tz-f4clock], [cmsis-f427] |
| Trezor Safe 3 rev B, T3B1, and Safe 5, T3T1 (Blockstream column "Safe 3/5/7") | STM32U585, Cortex-M33, 160 MHz | HASH peripheral: SHA-1, SHA-224, SHA-256, MD5; 66 cycles per 512-bit block; DMA; context save and restore. Secure and privileged only; driver only in the kernel | none | no: same software as rev A, run in the unprivileged MicroPython application | about 3x, indicative only: a Trezor developer measured 19.657 s for SPHINCS+ SHA2-128s signing with the HASH unit (Safe 7, privileged test firmware, other library) against Blockstream's 65.31 s in software. Needs kernel changes in a custom firmware | [u5-hal], [st-u5-slides], [tz-tz], [tz-6835], [tz-hwsha] |
| Trezor Safe 7, T3W1 | STM32U5G9, Cortex-M33, 160 MHz | as above; owned by the secure monitor, TrustZone settings locked until reset | none | no | same measurement as above (made on this model); not reachable on production units, which only run a production-signed secure monitor | [tz-6835], [tz-hwsha], [tz-tz] |
| Ledger Nano S Plus and Nano Gen5 (Blockstream, one column) | ST33K1M5C (S Plus); ST33K1M5, suffix not given (Gen5); two Cortex-M35P in lockstep; 70 or 75 MHz for the C variant | none listed: the engines are AES, Triple DES, NESCRYPT LLP (public key), SM4, MIFARE, and CRC | none listed | not applicable: in-app portable C for all three schemes. BOLOS `cx_sha256` is itself plain C in Ledger's SDK, reached through a trampoline into OS code | none from hash hardware; only software changes remain | [ldg-hw], [ldg-gen5], [st33-c-pst], [neslib-c], [ldg-sdk], [ldg-apps] |
| BitBox02 Nova (Blockstream) | ATSAMD51J20A, Cortex-M4F, 120 MHz | ICM: SHA-1, SHA-224, SHA-256; 72 + 2 cycles per block; DMA bus master; software-set initial hash value. The firmware already enables and uses it | none | no: portable C for all three schemes | not established. The engine's 74 cycles per block are about 1.4% of the roughly 5,400 cycles per compression implied by the published SLH-DSA time; per-call setup cost unmeasured | [samd5x-ds], [bb-icm], [bb-fork] |
| Trezor Model T, T2T1 (Trezor gist, 2025-04) | STM32F427, Cortex-M4F, 180 MHz | none | none | software: PQClean reference code with PQClean's own SHA-2 and Keccak | none from hash hardware | [tz-4901], [cmsis-f427] |
| ST33K secure element (Ledger Donjon, 2026-02-26) | ST33K1M5 family, variant not stated; Cortex-M35P in lockstep; 63 to 75 MHz by variant | none listed | none listed | not applicable: the post states the algorithms ran fully in software | none from hash hardware | [donjon], [st33-c-pst], [st33-am-pst] |

## Conclusions

1. **Unused SHA-256 hardware exists only on the STM32U5 Trezors and the BitBox02 Nova.**
   The Trezor Safe 3 rev B, Safe 5, and Safe 7 have ST's HASH peripheral and the BitBox02
   Nova has Microchip's ICM; Blockstream's harness hashes in portable C on all of them
   [code]. The Trezor Safe 3 rev A, the Trezor Model T, and the Ledger ST33K parts have no
   SHA-256 engine at all [code for the STM32F427, source for the ST33K]. Blockstream does
   not say which Safe 3 hardware revision it timed [source], so its Trezor column may come
   from a chip with no hash hardware [inferred].
2. **No device in these reports has Keccak hardware** [source and code]. The lattice
   figures in the Trezor gist (Model T) and Ledger Donjon's post (ST33K) therefore have no
   unused hash hardware to tap.
3. **On the Trezor STM32U5 models the scheme code cannot reach the hardware.** A Trezor
   developer's experiment signed SPHINCS+ SHA2-128s in 19.657 s with the HASH unit on a
   Safe 7, in privileged test firmware [source]; Blockstream's software figure is 65.31 s
   [source]. The ratio, about 3.3, is indicative only: the library, firmware context, and
   timing method all differ [inferred]. In shipping firmware the HASH unit is secure and
   privileged, the MicroPython application that runs the schemes is unprivileged, and no
   syscall reaches the unit [code]. Trezor developers state that on the Safe 7 only a
   production-signed secure monitor could change this, and that a call per hash through
   smcalls or syscalls may cost more than the unit saves unless the chunks are large
   [source].
4. **Ledger's hash path has no hardware behind it.** In Ledger's SDK, `cx_sha256_*` and
   the SHA-3 functions are plain C reached through a trampoline into OS-resident code,
   while only AES and NESCRYPT operations have hardware syscalls [code]. ST's
   certification documents for the ST33K1M5 list no SHA-2 or Keccak engine [source].
   Blockstream's in-app SHA-256 therefore gave up no hardware [inferred]; remaining
   headroom on Ledger is in software only, and its size is not established.
5. **The BitBox02 Nova's ICM is reachable and suits these schemes, but its gain is not
   established.** The ICM takes a chaining value from software and the firmware already
   enables and calls it [source and code], so no access change is needed [inferred]. Its
   per-call cost is neither documented nor measured.

## Cycles per compression implied by the published SLH-DSA times

[inferred] Published SLH-DSA-SHA2-128s signing time multiplied by the clock, divided by
2,220,338 compressions, the count this benchmark measured for slhdsa-c's SLH-DSA-SHA2-128s
signing on the RP2350 ([rp-sha]). Every cost in the published time is charged to
compressions, including the rest of the scheme, USB transfer, and display work, so these
are upper bounds on the cost of one compression.

| Device | Published time | Clock | Cycles per compression |
|---|---|---|---|
| Jade Plus | 52.85 s | 240 MHz | 5,713 |
| Trezor Safe 3 | 65.31 s | 160 MHz (rev B) or 180 MHz (rev A) | 4,706 or 5,295 |
| Ledger Nano gen5/S+ | 120.12 s | 70 or 75 MHz | 3,787 or 4,057 |
| BitBox02 Nova | 100.1 s | 120 MHz | 5,410 |

For scale: the STM32U5 HASH engine takes 66 cycles per block and the SAMD51 ICM 72 + 2
[source]. What these engines would deliver is set by the cost of each call around them,
which the next sections discuss per device.

## Per-device notes

### Trezor Safe 3, Safe 5, and Safe 7

**Models and chips.** [source] Trezor's build documentation names T2T1 the Model T, T2B1
the Safe 3 rev.A, T3B1 the Safe 3 rev.B, T3T1 the Safe 5, and T3W1 the Safe 7
(`docs/common/reproducible-build.md:38-43` in [tz-fork]). [code] The board files select
STM32F427xx with `-mcpu=cortex-m4` for T2B1
(`core/site_scons/models/T2B1/trezor_r_v10.py:28,37`), STM32U585xx with `-mcpu=cortex-m33`
for T3B1 (`.../T3B1/trezor_t3b1_revB.py:28,39`) and T3T1
(`.../T3T1/trezor_t3t1_revE.py:30`), and STM32U5G9xx for T3W1
(`.../T3W1/trezor_t3w1_revC.py:19`). [code] Clocks: 180 MHz for STM32F427 and F429 models
other than the Model T (`core/embed/sys/startup/stm32f4/startup_init.c:60-73`), with the
Model T raised to 180 MHz by the kernel (`core/embed/sys/task/stm32/system.c:62`); 160 MHz
for STM32U5 models (`core/embed/sys/startup/stm32u5/startup_init.c:60`). [source]
`core/embed/models/T3T1/Clocks_T3T1_revE.md` states a 160 MHz system clock for the Safe 5.

**HASH peripheral.** [code] ST's device headers define `HASH_BASE` and `HASH_TypeDef` for
the STM32U585 and STM32U5G9 and not for the STM32F427 ([cmsis-f427], [cmsis-u5]). [code]
ST's STM32U5 HAL offers only SHA-1, MD5, SHA-224, and SHA-256 as algorithm selections
(`Inc/stm32u5xx_hal_hash.h:190-193`) and supports suspending a computation and saving and
restoring the peripheral context (`Src/stm32u5xx_hal_hash.c:104-111`) ([u5-hal]). There is
no SHA-3 or SHA-512. [source] ST's STM32U5 HASH training slides give 66 cycles per 512-bit
block for SHA-224 and SHA-256, 82 for SHA-1, and 66 for MD5, and list DMA support (slide
2) [st-u5-slides]. Search excerpts of RM0456 give the same 66 and 82 cycles; RM0456 itself
could not be fetched.

**What Blockstream's harness used.** [code] Branch `feature/shrincs` of [tz-fork] (seven
commits on upstream main of 2026-05-04) adds the three schemes to the MicroPython
`trezorcrypto` module (`core/SConscript.firmware:208-231`). SLH-DSA hashes with slhdsa-c's
`crypto/slh_dsa/sha2_256.c`, the "Portable C Implementation" (line 6), byte for byte the
same file as in the Ledger and BitBox02 harnesses, called through `slh_sign`
(`core/embed/upymod/modtrezorcrypto/modtrezorcrypto-slh-dsa.h:55`). SHRINCS hashes through
trezor-crypto's `sha256_Update` (`crypto/shrincs/hash.c:5`) and XMSS through `sha256_Raw`
(`crypto/xmss/hash.c:34`); both end in the plain C `sha256_Transform` of `crypto/sha2.c`
(lines 723 and 780). The MicroPython application runs unprivileged: the kernel "is used to
start the unprivileged application code" (`core/embed/sys/task/stm32/systask.c:131`),
under MPU mode `MPU_MODE_APP` (`core/embed/sys/mpu/inc/sys/mpu.h:49`).

**Who may use the HASH unit.** [code] The driver is built for every STM32U5 model
(`core/site_scons/models/stm32u5_common.py:97`; `USE_HASH_PROCESSOR` at
`.../T3B1/trezor_t3b1_revB.py:109`, `.../T3T1/trezor_t3t1_revE.py:142`, and
`.../T3W1/trezor_t3w1_revC.py:298`) but only under `SECURE_MODE`
(`core/embed/sec/hash_processor/stm32u5/hash_processor.c:20`). The kernel initializes it
on models without a secure monitor (`core/embed/projects/kernel/main.c:146-147`) and the
secure monitor does on the Safe 7 (`core/embed/projects/secmon/main.c:114`). Without a
secure monitor, `tz_init` makes every peripheral secure and privileged
(`core/embed/sec/trustzone/stm32u5/tz_init.c:219-221`); with one, it leaves peripherals
non-secure by default and marks HASH secure and privileged (lines 247-265). The only
hash-related syscalls are `SYSCALL_FIRMWARE_HASH_START` and `_CONTINUE`
(`core/embed/sys/syscall/inc/sys/syscall_numbers.h:128-129`), which the issue below
describes as the BLAKE2s firmware-image hash. In the tree the HASH unit serves firmware
image hashing (`core/embed/sec/image/inc/sec/image_hash_conf.h:29-36`).

**Trezor's statements** [source], issue #6835 ([tz-6835], 2026-04-27 to 2026-05-04, closed
as not planned). The reporter describes the Safe 7 case: HASH secure-only, the TrustZone
controller's lock bit set at the end of `tz_init`, and no secure-monitor call for it. A
Trezor developer replied (2026-04-29) that this was "an intentional decision though not
from security reasons" and that sharing the unit with the secure monitor is the open
problem. On 2026-04-30 the same developer wrote: "Adding smcalls and syscalls could be a
way, but it adds overhead and unless the chunks are large enough this will negate the
effect of accelerator", that a custom secure monitor "is only accepted with production
signature", and that on the Safe 5, which has no secure monitor, "you will be able to use
the hash processor there". [code] The Safe 3 rev B board file, like the Safe 5's, has no
`secmon_layout` option. [inferred] So the same likely holds for the Safe 3 rev B.

**The hardware experiment** [source and code]. Another Trezor developer linked branch
`cepetr/slh-dsa-hw-sha` of trezor/trezor-firmware ([tz-hwsha], five commits dated
2025-12-09 to 2025-12-11). Its `branch-notes.md` records a test command in prodtest,
Trezor's production-test firmware, on a T3W1, signing with the vendored sphincsplus
reference code patched to hash through the HASH unit: 7,856-byte signatures, "Signed in
19.657 s", 2,186,238 hash finalize calls, stack protector disabled. The notes say that
restoring the roughly 160-byte hardware context was "significantly slower than recomputing
the first block every time", which is why the code replays the PK.seed block for each
hash, and that 20 seconds "is not the lower bound". [code] The file
`core/embed/sec/hash_processor/stm32u5/xsha256.c` on that branch feeds words to
`HASH->DIN` from the CPU and polls status flags; it uses no DMA. Prodtest itself runs in
secure mode: it calls `hash_processor_init` and `tz_init`
(`core/embed/projects/prodtest/main.c:175,229` in [tz-fork]), and the driver exists only
under `SECURE_MODE`. [inferred] 19.657 s at 160 MHz over 2,186,238 calls is about 1,440
cycles per hash, all costs included. On the RP2350, whose SHA engine is also fed word by
word from the CPU and takes no state input, this benchmark's register path replays a block
in about 484 cycles ([rp-sha]), which supports the notes' view that 19.7 s is not a
floor.

**Headroom** [inferred]. Blockstream's 65.31 s against the experiment's 19.657 s gives
about 3.3, but the two differ in library (slhdsa-c against sphincsplus), firmware context
(MicroPython application against prodtest), stack protector, timing (host over USB against
on the device), and possibly model. For SHRINCS and XMSS, which hash through
trezor-crypto's general SHA-256 API, no hardware measurement exists. Using the unit in a
Blockstream-style harness on a Safe 3 rev B or Safe 5 means a custom firmware whose kernel
either runs the hashing or maps the unit to the application.

**Which Safe 3.** [source] Blockstream's key generation table says "Trezor Safe 3" and its
signing table "Trezor Safe 3/5/7"; the hardware revision is not stated. [code] The fork's
interface changes touch the `layout_caesar` layout (both Safe 3 revisions) and
`layout_delizia` (Safe 5), not `layout_eckhart` (Safe 7)
(`core/embed/models/*/config.mk`).

### Ledger Nano S Plus and Nano Gen5

**Chips.** [source] Ledger's developer documentation pairs the Nano S Plus with an
STM32F042 MCU and an ST33K1M5C secure element; Stax and Flex also use the ST33K1M5C, the
Nano X an ST33J2M0 [ldg-hw]. The Nano Gen5 is not in that table; Ledger's shop lists its
secure element as "ST33K1M5" [ldg-gen5]. Ledger's porting guide gives `apex_p` as the Nano
Gen5's target name [ldg-gen5-port]. [code] All three Ledger harnesses build their C code
with `-mcpu=cortex-m35p+nodsp` for `nanosplus`, `stax`, `flex`, and `apex_p` and at `-O3`
(`ledger_slh_dsa/build.rs:47,73` in [ldg-apps]).

**Hash engines.** [source] ST's platform security target for the ST33K1M5C and ST33K1M5T
(C02, Rev C02.1, August 2024), sections 1.5 and 1.6.1, paragraphs 28 to 40 [st33-c-pst]:
two Cortex-M35P CPUs in lockstep, "Cadenced at 70 or 75 MHz"; a CRC calculation block; AES
and Triple DES (EDES+) accelerators; the NESCRYPT LLP public-key accelerator; and SM4 and
MIFARE accelerators outside the evaluation. No hash engine is listed. The ST33K1M5A and
ST33K1M5M target (B03) lists the same engines at 63 MHz [st33-am-pst]. ST's NesLib library
targets state, section by section, which engine each algorithm uses: EDES+ for DES, the
AES accelerator for AES, and NESCRYPT for RSA, ECC, and Diffie-Hellman; the SHA-1 and
SHA-2 section (7.1.12) and the Keccak and SHA-3 section (7.1.13) name none, and the PQC
add-on "does not use such hardware accelerators" (section 3.3, paragraphs 81 and 82, and
sections 7.1.12 and 7.1.13 in [neslib-c], for the ST33K1M5C C03). [inferred] SHA-2 and
Keccak on the ST33K run on the CPU, in ST's own library as well as Ledger's.

**What Blockstream's harnesses used.** [source] Blockstream's post says Ledger apps can
call the OS's cryptographic functions and that "we noticed significant syscall overhead
and decided to use a custom SHA-256 implementation in the app to speed this up".
[code] In [ldg-apps], `ledger_slh_dsa` compiles slhdsa-c's portable `slh_dsa/sha2_256.c`
(`build.rs:76`) and calls no `cx_` function from its C code; `ledger_shrincs` compiles
`shrincs/sha256_impl.c` (`build.rs:81`), a plain C SHA-256, while its BOLOS wrapper
`sha256_bolos.c` is not compiled and has its three functions commented out (lines 8 to
26); `ledger-xmss` compiles `xmss/sha256.c` (`build.rs:80`), reached through `sha256_Raw`
(`xmss/hash.c:34`).

**Is BOLOS `cx_sha256` hardware-backed?** [code] In Ledger's SDK [ldg-sdk] (commit
796c64e3, 2026-11-17), the SHA-256 compression `cx_sha256_block` is plain C
(`lib_cxng/src/cx_sha256.c:119`), as is the Keccak permutation `cx_sha3_block`
(`lib_cxng/src/cx_sha3.c:234`). An application reaches `cx_sha256_init_no_throw`,
`cx_sha256_update`, and `cx_sha256_final` through `CX_TRAMPOLINE` stubs
(`src/cx_stubs.S:8-17,131-133`) that branch to a shared trampoline at a fixed OS address
(`src/cx_stubs.S:166-168`; `include/shared_trampoline.h`, 0x00808001 for Nano S Plus,
Stax, Flex, and Apex P). The hardware engines are reached differently, through SVC
syscalls with `_hw` names: `cx_aes_set_key_hw` and `cx_aes_block_hw`
(`src/syscalls.c:185-205`) and the `cx_bn_*` NESCRYPT calls (from line 213). No hash
function has a `_hw` call. [inferred] The OS-side SHA-256 is the same plain C (the OS
binary was not examined), so routing hashes through the OS added call overhead without
adding hardware. The cost per call is not documented publicly, and Blockstream gives no
figure.

**Lattice path.** [code] The SDK's ML-DSA (`lib_cxng/src/cx_mldsa_*.c`) hashes through
`cx_shake256_hash` and related calls (`lib_cxng/src/cx_mldsa_util.c:27-34`), the same
plain C Keccak. [source] Ledger's post on the SDK's ML-DSA and ML-KEM (page dated
07/06/2026) says both "reuse the existing Ledger SDK" SHAKE and SHA3 primitives [ldg-pqc].

**Headroom** [inferred]. None from hash hardware. Software changes remain, such as an
assembly SHA-256; on the RP2350's Cortex-M33 this benchmark measured OpenSSL's ARMv4
assembly, assembled as Thumb-2, at 2,329 cycles per compression against 2,952 for portable
C ([rp-sha]). Whether a similar gain carries over to the lockstep Cortex-M35P against
Ledger's `-O3` build is not established.

### BitBox02 Nova

**Chip.** [code] Every firmware build targets the ATSAMD51J20A with `-mcpu=cortex-m4`
(`CMakeLists.txt:147-148` in [bb-fork]); the Nova is a variant of the same firmware (for
example `src/rust/bitbox02-rust/src/communication_mode.rs:3`). The configured CPU clock is
120 MHz (`external/asf4-drivers/Config/peripheral_clk_config.h:52`).

**ICM.** [source] SAM D5x/E5x data sheet DS60001507G [samd5x-ds]: the feature list names
AES, a TRNG, the PUKCC public-key controller, and an "Integrity Check Module (ICM) based
on Secure Hash Algorithm (SHA1, SHA224, SHA256), DMA assisted" (page 3); section 26.2
gives a run time of 72 or 194 cycles for SHA-256 (page 626); section 26.6.4.2 gives the
shortest period as "72 clock cycles + 2 clock cycles for start command synchronization"
(pages 639 and 640); section 26.8.11 says that with `CFG.UIHASH` set "the Initial Hash
Value is user-programmable" (page 659). The descriptor area must be 64-byte aligned and
the hash area 128-byte aligned (section 26.8). No SHA-3. [code] Microchip's ASF4 driver in
the firmware tree, `_sha_sync_sha256_process`
(`external/asf4-drivers/hpl/icm/hpl_icm.c:204-224`), writes the eight `UIHVAL` registers
from the context before each run, points a one-region descriptor in RAM at the data,
enables the ICM, and polls for completion; it takes whole 64-byte blocks only. The ICM
writes the digest back to RAM in its own byte order (the driver's initial values are
byte-swapped). [inferred] So the ICM can compress from any chaining value, which lets
slhdsa-c's precomputed PK.seed state be reused without the block replay that the RP2350
and the Trezor experiment need.

**The firmware already uses it.** [code] `system_init` enables the ICM at boot
(`src/platform/driver_init.c:52-58`, called at line 367); firmware code hashes with it
through `pukcc_sha256_compute` (`src/pukcc/pukcc.c:198-210`, called from
`src/memory/memory_spi.c:39`), as does the bootloader
(`src/bootloader/bootloader.c:441-444`). [inferred] Nothing in the firmware's structure
keeps scheme code from it.

**What Blockstream's harness used.** [code] Branch `feature/hash-based-signatures` of
[bb-fork] (one commit on upstream master of 2026-06-16) compiles slhdsa-c's portable
`sha2_256.c` (`src/rust/bitbox-slh-dsa/build.rs:4`, the same file as in the Ledger
harness), a plain C `sha256_impl.c` for SHRINCS (`src/rust/bitbox-shrincs/build.rs:6`),
and a plain C `sha256.c` for XMSS (`src/rust/bitbox-xmss/build.rs:9`). These build scripts
set no optimization flag, so the C code takes the `cc` crate's default for the Rust
profile, which is `opt-level = 'z'` (`src/rust/Cargo.toml:77`); the flag the `cc` crate
passes for it was not checked. The same commit enables the SAMD51's 4 KB cache controller
at boot (`src/platform/driver_init.c:349-350`); no other code under `src/` enables it.

**Headroom.** Not established. [inferred] The engine's 74 cycles per block are about 1.4%
of the roughly 5,400 cycles per compression implied by the published time (table above).
Each call also pays for the register writes, the ICM's own fetches of descriptor and data
over the bus, polling, and the digest's byte order; none of this is documented as a cycle
count or measured. This benchmark's measurements on other chips bracket the outcome
without predicting it: on the RP2350 (one-core times in the report's Table D5 [report]),
SLH-DSA-SHA2-128s signing took 47.76 s in portable C, 12.90 s through the Pico SDK's SHA
functions (3.70x), and 9.737 s through registers at `-O3` (4.9x); on the
ESP32-S3 the SHA unit gave 3.80x [jade-notes]. In the other direction, Jade's mbedTLS
path, a general-purpose per-call hardware API, made SHRINCS-B signing slower than plain C
on the same board (16.20 s against 11.09 s) [jade-notes]. [code] ASF4's `sha_sync` layer
is of the general-purpose kind: it buffers input with `memcpy` and pads in software around
each engine run (`external/asf4-drivers/hal/src/hal_sha_sync.c:148-242`). [inferred] A
backend that serves single compressions straight from the registers, as this benchmark's
RP2350 and ESP32 backends do, would sit closer to the first case.

### Trezor Model T (the Trezor gist)

[source] The gist does not name its device, but the pull request it came from does:
trezor/trezor-firmware #4901, "Benchmark post-quantum signatures" (onvej-sl, opened
2025-04-09, closed without merging 2026-04-21) [tz-4901] states "All the benchmarks were
run on a Trezor T", that the table moved to the gist, that the signature code and its
SHA-2 and SHA-3 come from PQClean, and that "SLH-DSA would be significantly faster if
SHA-2 or SHA-3 were implemented using hardware acceleration". [code] At the pull request's
head (b98b919b), `core/SConscript.firmware:199-209` builds
`vendor/pqm4/mupq/pqclean/crypto_sign/<algorithm>/clean/` with
`crypto/pq_signature/sha2.c` (based on SUPERCOP's reference code) and
`crypto/pq_signature/fips202.c` (based on SUPERCOP and TweetFips202); the benchmark signs
10 times per measurement (`core/src/apps/benchmark/pq_signature_benchmark.py`). [code] The
Model T builds as STM32F427xx with `-mcpu=cortex-m4`
(`core/site_scons/models/T2T1/trezor_t.py:27,36` in [tz-fork]) and the kernel sets 180 MHz
(`core/embed/sys/task/stm32/system.c:62`, also present at the pull request's head). The
STM32F427 has no HASH peripheral [cmsis-f427] and no Keccak engine. No unused hash
hardware.

### ST33K secure element (Ledger Donjon)

[source] The post [donjon] gives memory results "on the ST33K Secure Element" and does not
say which device produced the time table. It states that "current Secure Elements do not
embed any PQC accelerator, so we implemented the tested algorithms fully in software",
with Falcon as "a non optimized, plain C version" and ML-DSA as "ZKNox's low ram
implementation". It does not say which Keccak code was used. [source] As above, ST's
documents for the ST33K1M5 family list no hash engine, and NesLib's Keccak section names
no accelerator [st33-c-pst], [st33-am-pst], [neslib-c]. [inferred] No unused Keccak
hardware; the AES and NESCRYPT engines do not compute hashes.

## Not covered

External secure chips that some of these wallets carry were not examined. The Ledger Nano
X (ST33J2M0) and the Trezor One were not in the reports. RM0456 (STM32U5 reference manual)
and the ST33K1M5 data briefs could not be fetched (st.com timed out); ST's certification
documents, its STM32U5 training slides, and ST's published device headers and HAL were
used instead.

## Sources

[jade-notes]: knowledge/jade-hbs-benchmark-notes.md
[rp-sha]: knowledge/rp2350-sha256-accelerator-no-resume.md
[report]: ../index.html
[tz-fork]: https://github.com/DmitriiKJ/trezor-firmware/tree/3348cdb4fadc55f2503483afc69c27c5ee3b09a6
[tz-models]: https://github.com/DmitriiKJ/trezor-firmware/blob/3348cdb4fadc55f2503483afc69c27c5ee3b09a6/docs/common/reproducible-build.md
[tz-f4clock]: https://github.com/DmitriiKJ/trezor-firmware/blob/3348cdb4fadc55f2503483afc69c27c5ee3b09a6/core/embed/sys/startup/stm32f4/startup_init.c#L60-L73
[tz-tz]: https://github.com/DmitriiKJ/trezor-firmware/blob/3348cdb4fadc55f2503483afc69c27c5ee3b09a6/core/embed/sec/trustzone/stm32u5/tz_init.c#L210-L265
[tz-6835]: https://github.com/trezor/trezor-firmware/issues/6835
[tz-hwsha]: https://github.com/trezor/trezor-firmware/blob/cepetr/slh-dsa-hw-sha/branch-notes.md
[tz-4901]: https://github.com/trezor/trezor-firmware/pull/4901
[cmsis-f427]: https://github.com/STMicroelectronics/cmsis-device-f4/blob/master/Include/stm32f427xx.h
[cmsis-u5]: https://github.com/STMicroelectronics/cmsis-device-u5/blob/main/Include/stm32u585xx.h
[u5-hal]: https://github.com/STMicroelectronics/stm32u5xx-hal-driver/blob/main/Inc/stm32u5xx_hal_hash.h
[st-u5-slides]: https://www.stmcu.jp/wp/wp-content/uploads/files/presentation-ja/STM32U5/STM32U5-Security-HASH%20and%20Random%20Number%20Generator%20(Hash%20&%20RNG)_Rev1.0.pdf
[ldg-hw]: https://developers.ledger.com/docs/device-app/explanation/ledger-os/hardware-architecture
[ldg-gen5]: https://shop.ledger.com/products/ledger-nano-gen5
[ldg-gen5-port]: https://developers.ledger.com/docs/device-app/explanation/gen5-porting
[ldg-apps]: https://github.com/DmitriiKJ/ledger_slh_dsa/tree/cbb92e083654cf492adcd1343df2bdc00b87829b
[ldg-sdk]: https://github.com/LedgerHQ/ledger-secure-sdk/tree/796c64e3a4afd19d57ad1aacb71aac49c3f54721
[ldg-pqc]: https://www.ledger.com/blog-post-quantum-cryptography-ledger-sdk
[st33-c-pst]: https://sec-certs.org/cc/34d1675a7a079459/target.pdf
[st33-am-pst]: https://sec-certs.org/cc/83fc6586c8ac42f5/target.pdf
[neslib-c]: https://sec-certs.org/cc/2652a6089216e714/target.pdf
[samd5x-ds]: https://ww1.microchip.com/downloads/en/DeviceDoc/SAM_D5x_E5x_Family_Data_Sheet_DS60001507G.pdf
[bb-icm]: https://github.com/DmitriiKJ/bitbox02-firmware/blob/df5d501a3661dba508d0757c15e8a825d42f9e6c/external/asf4-drivers/hpl/icm/hpl_icm.c#L204-L224
[bb-fork]: https://github.com/DmitriiKJ/bitbox02-firmware/tree/df5d501a3661dba508d0757c15e8a825d42f9e6c
[donjon]: https://ledger.com/blog-quantum-computing-threat-to-blockchain

Other harness commits read: `ledger_shrincs` at 197c36ef63aa069c190b3345f74308d382dd31cd
and `ledger-xmss` at a694602699f2c71a4351f78b2ffaa2625033aac2 (github.com/DmitriiKJ).
Blockstream's post: https://blog.blockstream.com/hardware-wallets-post-quantum-signatures/
(section "Implementation Details"; tables in "The Numbers"). The NesLib 6.11.6 target for
the ST33K1M5A and ST33K1M5M (https://sec-certs.org/cc/5bc7ac1ce69c77b4/target.pdf,
paragraphs 84 and 85, sections 7.1.12 and 7.1.13) matches [neslib-c] on every point used
here.
