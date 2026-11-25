/* OpenSSL implementation of the mbedTLS SHA-256/512 shim; see mbedtls/sha256.h. */
#include <openssl/sha.h>
#include <string.h>

#include "mbedtls/sha256.h"
#include "mbedtls/sha512.h"

_Static_assert(sizeof(((mbedtls_sha256_context*)0)->s256) >= sizeof(SHA256_CTX),
               "s256 storage too small for SHA256_CTX");
_Static_assert(sizeof(((mbedtls_sha256_context*)0)->s1) >= sizeof(SHA_CTX),
               "s1 storage too small for SHA_CTX");

enum { SHIM_UNSTARTED = 0, SHIM_SHA256 = 1, SHIM_SHA224 = 2, SHIM_SHA1 = 3 };

#define S256(c) ((SHA256_CTX*)(void*)(c)->s256)
#define S1(c) ((SHA_CTX*)(void*)(c)->s1)

void mbedtls_sha256_init(mbedtls_sha256_context* c) { memset(c, 0, sizeof(*c)); }

void mbedtls_sha256_free(mbedtls_sha256_context* c) { (void)c; }

void mbedtls_sha256_clone(mbedtls_sha256_context* dst, const mbedtls_sha256_context* src)
{
    *dst = *src;
}

int mbedtls_sha256_starts(mbedtls_sha256_context* c, int is224)
{
    memset(c, 0, sizeof(*c));
    if (is224) {
        c->mode = SHIM_SHA224;
        SHA224_Init(S256(c));
    } else {
        c->mode = SHIM_SHA256;
        SHA256_Init(S256(c));
    }
    return 0;
}

static void autostart(mbedtls_sha256_context* c)
{
    if (c->mode != SHIM_UNSTARTED) {
        return;
    }
#ifdef SHIM_EMULATE_ESP_UNSTARTED_SHA1
    c->mode = SHIM_SHA1;
    SHA1_Init(S1(c));
#else
    c->mode = SHIM_SHA256;
    SHA256_Init(S256(c));
#endif
}

int mbedtls_sha256_update(mbedtls_sha256_context* c, const unsigned char* in, size_t len)
{
    autostart(c);
    if (c->mode == SHIM_SHA1) {
        SHA1_Update(S1(c), in, len);
    } else {
        SHA256_Update(S256(c), in, len);
    }
    return 0;
}

int mbedtls_sha256_finish(mbedtls_sha256_context* c, unsigned char* out)
{
    autostart(c);
    if (c->mode == SHIM_SHA1) {
        unsigned char d[SHA_DIGEST_LENGTH];
        SHA1_Final(d, S1(c));
        memcpy(out, d, sizeof(d));
        memset(out + sizeof(d), 0, 32 - sizeof(d));
    } else if (c->mode == SHIM_SHA224) {
        SHA224_Final(out, S256(c));
    } else {
        SHA256_Final(out, S256(c));
    }
    return 0;
}

/* mbedTLS implements the one-shot as init + starts + update + finish, so it is always a
 * standard digest, on ESP hardware too. OpenSSL 3's own one-shot SHA256()/SHA512() look the
 * algorithm up on every call (EVP_Q_digest), which is slow for the many tiny inputs XMSS
 * hashes, so use the low-level calls instead. */
int mbedtls_sha256(const unsigned char* in, size_t len, unsigned char* out, int is224)
{
    SHA256_CTX c;
    if (is224) {
        SHA224_Init(&c);
        SHA224_Update(&c, in, len);
        SHA224_Final(out, &c);
    } else {
        SHA256_Init(&c);
        SHA256_Update(&c, in, len);
        SHA256_Final(out, &c);
    }
    return 0;
}

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
