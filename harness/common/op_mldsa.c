/*
 * ML-DSA-44, -65, and -87 (FIPS 204) with mldsa-native (third_party/mldsa-native, used
 * unmodified; configuration in lattice/pqb_mldsa_config.h). Two builds of the library are
 * linked: the default one (ops mldsa<set>_*) and the one with MLD_CONFIG_REDUCE_RAM, the
 * library's reduced-RAM option (ops mldsa<set>_lowram_*). Both produce identical bytes.
 *
 *   mldsa<set>_keygen   ML-DSA.KeyGen_internal (keypair_internal) from the seed
 *                       run_input(x); output pk || sk
 *   mldsa<set>_sign     ML-DSA.Sign with an empty context and the deterministic variant
 *                       (rnd = 32 zero bytes, which FIPS 204 permits; the FIPS 204
 *                       default is hedged signing with fresh randomness): the 2-byte
 *                       prefix 0x00 || 0x00 is formed outside the timed section, then
 *                       signature_internal() is timed. Message: run_input(x). Key: the
 *                       key pair from seed run_input(0), embedded as vectors
 *                       "mldsa<set>_sk" and "mldsa<set>_pk". Verified afterwards,
 *                       untimed.
 *   mldsa<set>_verify   ML-DSA.Verify (verify(), empty context) on the host's signature
 *                       of message x % PQB_VEC_N (vector "mldsa<set>_sig/<i>").
 *
 * Signing repeats a rejection-sampling loop a message-dependent number of times. In the
 * host counting build (PQB_MLDSA_COUNT) a signing hook records the attempts, which go to
 * the grind column ("attempts=A"); outputs are deterministic, so those counts hold for
 * every board.
 */
#include "common.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    const char* name; /* "44", "65", "87" */
    size_t pk_len, sk_len, sig_len;
    int (*keypair)(uint8_t* pk, uint8_t* sk, const uint8_t seed[32]);
    int (*sign)(uint8_t* sig, const uint8_t* m, size_t mlen, const uint8_t* pre, size_t prelen,
                const uint8_t rnd[32], const uint8_t* sk, int externalmu);
    int (*verify)(const uint8_t* sig, const uint8_t* m, size_t mlen, const uint8_t* ctx,
                  size_t ctxlen, const uint8_t* pk);
} mldsa_impl_t;

#define PQB_MLDSA_DECL(p)                                                                   \
    int p##_keypair_internal(uint8_t* pk, uint8_t* sk, const uint8_t seed[32]);             \
    int p##_signature_internal(uint8_t* sig, const uint8_t* m, size_t mlen,                 \
                               const uint8_t* pre, size_t prelen, const uint8_t rnd[32],    \
                               const uint8_t* sk, int externalmu);                          \
    int p##_verify(const uint8_t* sig, const uint8_t* m, size_t mlen, const uint8_t* ctx,   \
                   size_t ctxlen, const uint8_t* pk);

PQB_MLDSA_DECL(mldsa44)
PQB_MLDSA_DECL(mldsa65)
PQB_MLDSA_DECL(mldsa87)
PQB_MLDSA_DECL(mldsalr44)
PQB_MLDSA_DECL(mldsalr65)
PQB_MLDSA_DECL(mldsalr87)

/* Sizes from FIPS 204, Table 2 */
static const mldsa_impl_t IMPLS[2][3] = {
    {
        { "44", 1312, 2560, 2420, mldsa44_keypair_internal, mldsa44_signature_internal,
          mldsa44_verify },
        { "65", 1952, 4032, 3309, mldsa65_keypair_internal, mldsa65_signature_internal,
          mldsa65_verify },
        { "87", 2592, 4896, 4627, mldsa87_keypair_internal, mldsa87_signature_internal,
          mldsa87_verify },
    },
    {
        { "44", 1312, 2560, 2420, mldsalr44_keypair_internal, mldsalr44_signature_internal,
          mldsalr44_verify },
        { "65", 1952, 4032, 3309, mldsalr65_keypair_internal, mldsalr65_signature_internal,
          mldsalr65_verify },
        { "87", 2592, 4896, 4627, mldsalr87_keypair_internal, mldsalr87_signature_internal,
          mldsalr87_verify },
    },
};

/* Set by the signing hook in the host counting build (lattice/pqb_mldsa_config.h). */
volatile uint32_t pqb_mldsa_last_attempt = UINT32_MAX;

#ifndef PQB_MLDSA_COUNT
/* The randomized API (keypair(), signature()) is compiled in but never called; it needs
 * this symbol. No randomness is used anywhere in the benchmark. */
int randombytes(uint8_t* out, size_t outlen);
int randombytes(uint8_t* out, size_t outlen)
{
    memset(out, 0, outlen);
    return -1;
}
#endif

/* Pure ML-DSA with an empty context: M' = 0x00 || 0x00 || M (FIPS 204, Algorithm 2) */
static const uint8_t PREFIX[2] = { 0, 0 };
static const uint8_t RND_ZERO[32] = { 0 };

/* Parses "mldsa<set>[_lowram]_<kind>". */
static const mldsa_impl_t* parse(const char* op, const char** kind)
{
    if (strncmp(op, "mldsa", 5) || strlen(op) < 8) {
        return NULL;
    }
    int idx;
    if (!strncmp(op + 5, "44", 2)) {
        idx = 0;
    } else if (!strncmp(op + 5, "65", 2)) {
        idx = 1;
    } else if (!strncmp(op + 5, "87", 2)) {
        idx = 2;
    } else {
        return NULL;
    }
    const char* rest = op + 7;
    int lowram = 0;
    if (!strncmp(rest, "_lowram", 7)) {
        lowram = 1;
        rest += 7;
    }
    if (strcmp(rest, "_keygen") && strcmp(rest, "_sign") && strcmp(rest, "_verify")) {
        return NULL;
    }
    *kind = rest + 1;
    return &IMPLS[lowram][idx];
}

/* Key pair from seed run_input(0) and signatures of messages 0 .. PQB_VEC_N - 1, for
 * gen_vectors.c. Writes into caller buffers sized by pqb_mldsa_sizes(). */
int pqb_mldsa_sizes(int set_idx, size_t* pk_len, size_t* sk_len, size_t* sig_len)
{
    if (set_idx < 0 || set_idx > 2) {
        return 0;
    }
    *pk_len = IMPLS[0][set_idx].pk_len;
    *sk_len = IMPLS[0][set_idx].sk_len;
    *sig_len = IMPLS[0][set_idx].sig_len;
    return 1;
}

int pqb_mldsa_keygen(int set_idx, uint8_t* pk, uint8_t* sk)
{
    uint8_t seed[32];
    run_input(0, seed);
    return !IMPLS[0][set_idx].keypair(pk, sk, seed);
}

int pqb_mldsa_sign(int set_idx, const uint8_t* sk, uint32_t x, uint8_t* sig)
{
    uint8_t in[32];
    run_input(x, in);
    return !IMPLS[0][set_idx].sign(sig, in, 32, PREFIX, sizeof(PREFIX), RND_ZERO, sk, 0);
}

int run_mldsa_op(const char* op, uint32_t x, op_result_t* r)
{
    const char* kind = NULL;
    const mldsa_impl_t* m = parse(op, &kind);
    if (!m) {
        return 0;
    }
    char rec[32];
    uint8_t in[32];
    op_timer_t t;

    if (!strcmp(kind, "keygen")) {
        uint8_t seed[32];
        run_input(x, seed);
        uint8_t* out = malloc(m->pk_len + m->sk_len);

        timer_start(&t);
        const int ret = m->keypair(out, out + m->pk_len, seed);
        timer_stop(&t, r);

        r->out = out;
        r->out_len = m->pk_len + m->sk_len;
        /* No independent check here (it would raise the peak stack above keygen's own);
         * correctness comes from the library's KATs and output hashes against the
         * host. */
        r->verified = ret ? 0 : -1;
        return 1;
    }

    size_t pk_len = 0;
    snprintf(rec, sizeof(rec), "mldsa%s_pk", m->name);
    uint8_t* pk = pqb_vec_copy(rec, -1, &pk_len);
    if (!pk || pk_len != m->pk_len) {
        free(pk);
        return -1;
    }

    if (!strcmp(kind, "sign")) {
        size_t sk_len = 0;
        snprintf(rec, sizeof(rec), "mldsa%s_sk", m->name);
        uint8_t* sk = pqb_vec_copy(rec, -1, &sk_len);
        if (!sk || sk_len != m->sk_len) {
            free(sk);
            free(pk);
            return -1;
        }
        run_input(x, in);
        uint8_t* sig = malloc(m->sig_len);
        pqb_mldsa_last_attempt = UINT32_MAX;

        timer_start(&t);
        const int ret = m->sign(sig, in, 32, PREFIX, sizeof(PREFIX), RND_ZERO, sk, 0);
        timer_stop(&t, r);

        r->out = sig;
        r->out_len = m->sig_len;
        r->verified = ret ? 0 : (m->verify(sig, in, 32, NULL, 0, pk) == 0);
        if (pqb_mldsa_last_attempt != UINT32_MAX) {
            snprintf(r->grind, sizeof(r->grind), "attempts=%lu",
                     (unsigned long)pqb_mldsa_last_attempt + 1);
        }
        free(sk);
        free(pk);
        return 1;
    }

    /* verify */
    const int v = (int)(x % PQB_VEC_N);
    size_t sig_len = 0;
    snprintf(rec, sizeof(rec), "mldsa%s_sig", m->name);
    uint8_t* sig = pqb_vec_copy(rec, v, &sig_len);
    if (!sig || sig_len != m->sig_len) {
        free(sig);
        free(pk);
        return -1;
    }
    run_input((uint32_t)v, in);

    timer_start(&t);
    const int ret = m->verify(sig, in, 32, NULL, 0, pk);
    timer_stop(&t, r);

    r->out = sig;
    r->out_len = sig_len;
    r->verified = ret == 0;
    free(pk);
    return 1;
}
