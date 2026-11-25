/* Direct SHA-256 context API over slhdsa-c's incremental SHA-256; see
 * shim_direct/mbedtls/sha256.h. Clones copy only the live part of the context
 * (sha2_256_copy()), not the whole 64-byte buffer. */
#include <stdlib.h>

#include <mbedtls/sha256.h> /* angle brackets: the SHA_API header dir, not shim/mbedtls */

void mbedtls_sha256_init(mbedtls_sha256_context* c)
{
    c->started = 0;
    c->s.i = 0;
    c->s.len = 0;
}

void mbedtls_sha256_free(mbedtls_sha256_context* c) { (void)c; }

void mbedtls_sha256_clone(mbedtls_sha256_context* dst, const mbedtls_sha256_context* src)
{
    dst->started = src->started;
    sha2_256_copy(&dst->s, &src->s);
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
