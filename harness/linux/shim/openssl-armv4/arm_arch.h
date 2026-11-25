/*
 * Stand-in for OpenSSL's crypto/arm_arch.h, so that sha256-armv4.S (generated from
 * OpenSSL 3.4.1's crypto/sha/asm/sha256-armv4.pl with the linux32 flavour) assembles on
 * its own, outside an OpenSSL build.
 *
 * Only the integer code path is assembled. __ARM_MAX_ARCH__ stays below 7, which leaves
 * out the NEON and ARMv8 code and the run-time capability check (OPENSSL_armcap_P).
 *
 * __ARM_ARCH__ selects how the integer path loads message words:
 *   6 (the default for the Pi Zero's ARMv6 target): four byte loads per word. With this
 *     setting the assembled .text is identical to sha256_block_data_order in the SDK's
 *     libcrypto.a (OpenSSL 3.4.1).
 *   7 (set with -D__ARM_ARCH__=7): one word load plus a rev instruction per word. Both
 *     are ARMv6 instructions, and the ARMv7 integer path uses nothing else beyond ARMv6,
 *     so the result still runs on the ARM1176. Its word loads may be unaligned; ARMv6
 *     Linux enables unaligned word access, as GCC's default -munaligned-access for this
 *     target also assumes.
 */
#ifndef PQB_OPENSSL_ARM_ARCH_STANDIN_H
#define PQB_OPENSSL_ARM_ARCH_STANDIN_H

#ifndef __ARM_ARCH__
#define __ARM_ARCH__ __ARM_ARCH
#endif

#define __ARM_MAX_ARCH__ 6

#endif
