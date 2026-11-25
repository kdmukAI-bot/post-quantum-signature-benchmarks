/*
 * Round 4, Pi Zero 2 W: reports which SHA-256 block function OpenSSL 3.4.1's libcrypto
 * selects at run time on this CPU. libcrypto's sha256_block_data_order reads
 * OPENSSL_armcap_P on every call and jumps to the ARMv8 cryptographic-extension code if
 * bit ARMV8_SHA256 (1 << 4) is set, else to the NEON code if bit ARMV7_NEON (1 << 0) is
 * set, else runs the integer code. OPENSSL_armcap_P is filled once at library
 * initialization from the kernel's hardware capability words (or from the OPENSSL_armcap
 * environment variable, which overrides them).
 *
 * The variable is hidden in libcrypto.so, so this program links the SDK's libcrypto.a
 * (the same OpenSSL 3.4.1 build as libcrypto.so) statically. It prints the auxiliary
 * vector's AT_HWCAP and AT_HWCAP2 with the bits that matter here, and the value of
 * OPENSSL_armcap_P after initialization.
 *
 * Build (scripts/r4_pi02w_build_all.sh probe): arm-Buildroot-linux-gnueabihf-gcc -O2
 * r4_pi02w_armcap_probe.c -Wl,-Bstatic -lcrypto -Wl,-Bdynamic -ldl -pthread
 */
#include <openssl/crypto.h>
#include <openssl/sha.h>
#include <stdio.h>
#include <sys/auxv.h>

extern unsigned int OPENSSL_armcap_P;

int main(void)
{
    OPENSSL_init_crypto(0, NULL);
    unsigned char d[32];
    SHA256((const unsigned char*)"abc", 3, d);
    const unsigned long hwcap = getauxval(AT_HWCAP), hwcap2 = getauxval(AT_HWCAP2);
    printf("AT_HWCAP=0x%lx neon=%d vfpv4=%d idiva=%d\n", hwcap, !!(hwcap & (1ul << 12)),
           !!(hwcap & (1ul << 16)), !!(hwcap & (1ul << 17)));
    printf("AT_HWCAP2=0x%lx aes=%d pmull=%d sha1=%d sha2=%d crc32=%d\n", hwcap2,
           !!(hwcap2 & 1ul), !!(hwcap2 & 2ul), !!(hwcap2 & 4ul), !!(hwcap2 & 8ul),
           !!(hwcap2 & 16ul));
    const unsigned int cap = OPENSSL_armcap_P;
    printf("OPENSSL_armcap_P=0x%x ARMV7_NEON=%d ARMV8_SHA256=%d -> sha256 block function: %s\n",
           cap, !!(cap & 1u), !!(cap & 16u),
           (cap & 16u) ? "ARMv8 (sha256h)" : (cap & 1u) ? "NEON" : "integer");
    printf("OpenSSL %s\n", OpenSSL_version(OPENSSL_VERSION));
    return 0;
}
