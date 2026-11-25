/* OpenSSL-backed mbedtls_sha512() for builds whose SHA-256 API is not the OpenSSL shim
 * (SHA_API=direct or native). Same code as in shim/mbedtls_shim.c, so SHA-512 (one call
 * per key generation) is computed identically in every build. */
#include <openssl/sha.h>

#include "mbedtls/sha512.h"

int mbedtls_sha512(const unsigned char* in, size_t len, unsigned char* out, int is384)
{
    SHA512_CTX c;
    if (is384) {
        SHA384_Init(&c);
        SHA384_Update(&c, in, len);
        SHA384_Final(out, &c);
    } else {
        SHA512_Init(&c);
        SHA512_Update(&c, in, len);
        SHA512_Final(out, &c);
    }
    return 0;
}
