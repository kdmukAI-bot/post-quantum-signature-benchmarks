/* Direct SHA-256 context API; see shim_direct/mbedtls/sha256.h. SHA-224 is not used by the
 * scheme code and is rejected. */
#include <stdlib.h>
#include <string.h>

#include "mbedtls/sha256.h"

void mbedtls_sha256_init(mbedtls_sha256_context* c) { memset(c, 0, sizeof(*c)); }

void mbedtls_sha256_free(mbedtls_sha256_context* c) { (void)c; }

void mbedtls_sha256_clone(mbedtls_sha256_context* dst, const mbedtls_sha256_context* src)
{
    *dst = *src;
}

int mbedtls_sha256_starts(mbedtls_sha256_context* c, int is224)
{
    if (is224) {
        abort();
    }
    sha2_256_init(&c->s);
    c->started = 1;
    return 0;
}

static void autostart(mbedtls_sha256_context* c)
{
    if (!c->started) {
        sha2_256_init(&c->s);
        c->started = 1;
    }
}

int mbedtls_sha256_update(mbedtls_sha256_context* c, const unsigned char* in, size_t len)
{
    autostart(c);
    sha2_256_update(&c->s, in, len);
    return 0;
}

int mbedtls_sha256_finish(mbedtls_sha256_context* c, unsigned char* out)
{
    autostart(c);
    sha2_256_final(&c->s, out);
    return 0;
}

int mbedtls_sha256(const unsigned char* in, size_t len, unsigned char* out, int is224)
{
    if (is224) {
        abort();
    }
    sha2_256(out, in, len);
    return 0;
}
