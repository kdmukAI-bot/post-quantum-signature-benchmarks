/*
 * Replacement for slhdsa-c's sha2_256_compress() using OpenSSL's single-block transform,
 * which runs OpenSSL's assembly SHA-256 where one exists (ARMv4+ on the Pi Zero).
 *
 * Layout (from slh_dsa/sha2_256.c): v points to 8 state words then a 64-byte message block,
 * all stored as big-endian bytes. The state is updated in place.
 */
#include <stdint.h>
#include <openssl/sha.h>

static inline uint32_t ld_be32(const uint8_t* b)
{
    return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 8) | b[3];
}

static inline void st_be32(uint8_t* b, uint32_t x)
{
    b[0] = (uint8_t)(x >> 24);
    b[1] = (uint8_t)(x >> 16);
    b[2] = (uint8_t)(x >> 8);
    b[3] = (uint8_t)x;
}

void sha2_256_compress(void* v)
{
    uint8_t* s = (uint8_t*)v;
    SHA256_CTX c;
    for (int i = 0; i < 8; i++) {
        c.h[i] = ld_be32(s + 4 * i);
    }
    SHA256_Transform(&c, s + 32);
    for (int i = 0; i < 8; i++) {
        st_be32(s + 4 * i, c.h[i]);
    }
}
