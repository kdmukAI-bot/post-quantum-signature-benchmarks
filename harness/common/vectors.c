/*
 * Verification inputs embedded in the build (vectors_blob.c includes the blob made by the
 * host harness with pq_bench --write-vectors; see gen_vectors.c).
 *
 * Blob format, all integers little-endian:
 *   "PQBVEC01"                               8-byte magic
 *   repeated: u16 name_len, name, u32 data_len, data
 *   u16 0                                    end
 * Names are "<record>" or "<record>/<index>", for example "mldsa44_pk" or
 * "slh_dsa_sig/3".
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "common.h"

#ifdef PQB_HAVE_VECTORS
extern const uint8_t pqb_vectors_start[];
extern const uint8_t pqb_vectors_end[];
#endif

const uint8_t* pqb_vec(const char* name, int idx, size_t* len)
{
    char want[96];
    if (idx >= 0) {
        snprintf(want, sizeof(want), "%s/%d", name, idx);
    } else {
        snprintf(want, sizeof(want), "%s", name);
    }
#ifdef PQB_HAVE_VECTORS
    const uint8_t* p = pqb_vectors_start;
    const uint8_t* end = pqb_vectors_end;
    if (end - p < 8 || memcmp(p, "PQBVEC01", 8)) {
        fprintf(stderr, "pqb_vec: bad vector blob\n");
        return NULL;
    }
    p += 8;
    const size_t want_len = strlen(want);
    while (end - p >= 2) {
        const size_t nl = (size_t)p[0] | ((size_t)p[1] << 8);
        if (nl == 0 || (size_t)(end - p) < 2 + nl + 4) {
            break;
        }
        const uint8_t* nm = p + 2;
        const uint8_t* q = nm + nl;
        const size_t dl = (size_t)q[0] | ((size_t)q[1] << 8) | ((size_t)q[2] << 16)
            | ((size_t)q[3] << 24);
        const uint8_t* data = q + 4;
        if ((size_t)(end - data) < dl) {
            break;
        }
        if (nl == want_len && !memcmp(nm, want, nl)) {
            *len = dl;
            return data;
        }
        p = data + dl;
    }
    fprintf(stderr, "pqb_vec: no record %s\n", want);
#else
    fprintf(stderr, "pqb_vec: this build has no vectors (record %s)\n", want);
#endif
    *len = 0;
    return NULL;
}

uint8_t* pqb_vec_copy(const char* name, int idx, size_t* len)
{
    const uint8_t* src = pqb_vec(name, idx, len);
    if (!src) {
        return NULL;
    }
    uint8_t* dst = malloc(*len ? *len : 1);
    if (dst) {
        memcpy(dst, src, *len);
    }
    return dst;
}
