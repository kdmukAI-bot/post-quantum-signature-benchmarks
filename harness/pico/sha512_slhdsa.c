/*
 * mbedtls_sha512() for harness/pico, over slhdsa-c's portable SHA-512
 * (slh_dsa/sha2_512.c, compiled from Jade's sources). The Pi Zero W builds use OpenSSL
 * here and the ESP32 builds ESP-IDF's mbedTLS; every build hashes one 32-byte seed per
 * key generation with it, so the outputs are identical and the time is a few
 * microseconds.
 */
#include <stdlib.h>

#include "mbedtls/sha512.h"
#include "slh_dsa/sha2_api.h"

int mbedtls_sha512(const unsigned char* in, size_t len, unsigned char* out, int is384)
{
    if (is384) {
        abort(); /* not used by the scheme code */
    }
    sha2_512(out, in, len);
    return 0;
}
