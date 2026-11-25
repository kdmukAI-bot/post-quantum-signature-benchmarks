# ESP32-S3 and ESP32-P4 hardware limits for lattice signature schemes

The hardware features that speed up the hash-based schemes on the ESP32 boards do little
for ML-DSA (FIPS 204) and FN-DSA (Falcon). Two chip facts decide this.

## The SHA unit has no SHA-3

Both chips' SHA accelerators support SHA-1, SHA-224, SHA-256, SHA-384, SHA-512, and the
SHA-512/t variants, and nothing else. ESP-IDF 5.5.1 lists the modes in
`components/soc/<chip>/include/soc/soc_caps.h` (`SOC_SHA_SUPPORT_*`); neither chip has a
SHA-3 or Keccak entry.

ML-DSA and FN-DSA hash with SHAKE (SHA-3's extendable-output functions), so their hashing
runs in software on these chips. The "platform acceleration" level used for the
SHA-256-based schemes (SLH-DSA-SHA2, SPHINCS+, SHRINCS, XMSS) has no counterpart for them.

## The FPU is single precision only

- ESP32-S3: `components/xtensa/esp32s3/include/xtensa/config/core-isa.h` has
  `XCHAL_HAVE_FP 1` (single precision) and `XCHAL_HAVE_DFP 0` (no double precision).
- ESP32-P4: ESP-IDF compiles with `-march=rv32imafc_zicsr_zifencei_xesppie -mabi=ilp32f`
  (`tools/cmake/toolchain-esp32p4.cmake`). The `f` extension is single precision; there
  is no `d`, so every `double` operation goes through software routines.
- Pi Zero W, for comparison: the ARM1176JZF-S has a VFPv2 floating-point unit (VFP11) that
  does double precision in hardware (ARM's documentation; not measured here).

FN-DSA signing (fast Fourier sampling) and parts of its key generation use
double-precision arithmetic.
On a chip without a double-precision FPU, an implementation either emulates it with
integer code (Falcon's reference implementation has a build option for this) or falls
back on the compiler's soft-float routines. Whether a chip with a double-precision FPU
uses it depends on the implementation: Thomas Pornin's c-fn-dsa (commit 1b858880) compiles
native floating point only for x86 with SSE2, 64-bit ARM with NEON, and 64-bit RISC-V with
the D extension, and uses its integer emulation everywhere else, the Pi Zero W's ARMv6
included. On an x86 host the emulation must be forced (`-DFNDSA_AVX2=0 -DFNDSA_SSE2=0`)
for the host to run the same code as these boards; both paths produce the same bytes.
Record which floating-point path each build uses: a comparison between a native and an
emulated build measures the FPU as much as the clock. FN-DSA verification uses integer
arithmetic only, so it is not affected.

ML-DSA uses integer arithmetic throughout (its number-theoretic transform works modulo a
23-bit prime), so the FPU question does not arise for it.
