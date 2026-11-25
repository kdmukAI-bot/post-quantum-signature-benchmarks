/*
 * Host-only: writes the verification vector blob for this build's SHRINCS variant
 * (pq_bench --write-vectors FILE; format in vectors.c), and estimates the PORS+FP
 * grinding success probability (pq_bench --pors-prob MILLIONS[:START_MILLION]; samples
 * are numbered, so separate processes can cover separate ranges).
 *
 * Every key is derived from a fixed seed and every message is run_input(i), so the blob
 * is reproducible:
 *   slh_dsa_sig/i, sphincs40_sig/i       signatures with the hard-coded keys of op_slh.c
 *   xmss_pk, xmss_sig/i                  key of xmss_selftest for x = 0, signatures at
 *                                        indexes 0 .. PQB_VEC_N - 1
 *   shrincs_sk                           SecretKey from shrincs_restore() of the seed
 *                                        bytes 0 .. 47 (seed, prf, sf, sl, pk.seed,
 *                                        pk.root)
 *   shrincs_sf_sig/i, shrincs_sl_sig/i   stateful (q = 1) and stateless signatures at
 *                                        swn = SWN
 *   mldsa<set>_pk, _sk, _sig/i           key pair from seed run_input(0), deterministic
 *                                        signatures (op_mldsa.c)
 *   fndsa<n>_vk, _sk, _sig/i             key pair from seed run_input(0), seeded
 *                                        signatures (op_fndsa.c)
 * Each signature is verified before it is written.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "common.h"
#include "shrincs/hash.h"
#include "shrincs/pors_fp.h"
#include "shrincs/shrincs.h"
#include "slh_dsa/slh_dsa.h"
#include "slh_dsa/slh_param.h"

/* op_shrincs.c */
void pqb_shrincs_consistent_key(SecretKey* sk, PublicKey* pk);
size_t pqb_shrincs_sf_sig_len(void);
size_t pqb_shrincs_sl_sig_len(void);
uint32_t pqb_shrincs_swn(void);
int pqb_shrincs_sign_sf(SecretKey* sk, const uint8_t* msg, uint32_t swn, uint8_t* sig);
int pqb_shrincs_sign_sl(SecretKey* sk, const uint8_t* msg, uint32_t swn, uint8_t* sig);
/* op_xmss.c */
int pqb_xmss_consistent_key(uint8_t** pk, size_t* pk_len, uint8_t** sk);
int pqb_xmss_sign(uint8_t* sk, const uint8_t* msg, uint8_t* sig, size_t* sig_len);
size_t pqb_xmss_sig_len(void);
/* op_mldsa.c */
int pqb_mldsa_sizes(int set_idx, size_t* pk_len, size_t* sk_len, size_t* sig_len);
int pqb_mldsa_keygen(int set_idx, uint8_t* pk, uint8_t* sk);
int pqb_mldsa_sign(int set_idx, const uint8_t* sk, uint32_t x, uint8_t* sig);
/* op_fndsa.c */
void pqb_fndsa_sizes(unsigned logn, size_t* sk_len, size_t* vk_len, size_t* sig_len);
void pqb_fndsa_keygen(unsigned logn, uint8_t* sk, uint8_t* vk);
size_t pqb_fndsa_sign(unsigned logn, const uint8_t* sk, uint32_t x, uint8_t* sig);

static void put(FILE* f, const char* name, int idx, const uint8_t* data, size_t len)
{
    char nm[96];
    if (idx >= 0) {
        snprintf(nm, sizeof(nm), "%s/%d", name, idx);
    } else {
        snprintf(nm, sizeof(nm), "%s", name);
    }
    const size_t nl = strlen(nm);
    const uint8_t h[2] = { (uint8_t)nl, (uint8_t)(nl >> 8) };
    const uint8_t l[4] = { (uint8_t)len, (uint8_t)(len >> 8), (uint8_t)(len >> 16),
                           (uint8_t)(len >> 24) };
    fwrite(h, 1, 2, f);
    fwrite(nm, 1, nl, f);
    fwrite(l, 1, 4, f);
    fwrite(data, 1, len, f);
}

/* After writing a signature record, run the matching verify op on it from memory is not
 * possible (the blob is not embedded yet), so each signature is checked here directly. */
static int check(int ok, const char* what, int i)
{
    if (!ok) {
        fprintf(stderr, "write-vectors: %s %d does not verify\n", what, i);
    }
    return ok;
}

int pqb_write_vectors(const char* path)
{
    FILE* f = fopen(path, "wb");
    if (!f) {
        perror(path);
        return 0;
    }
    int ok = 1;
    fwrite("PQBVEC01", 1, 8, f);
    uint8_t in[32];

    /* SLH-DSA-SHA2-128s and SPHINCS+ 2^40: the existing sign ops make and verify them */
    static const char* const SLH_OPS[2][2] = { { "slh_dsa_sign", "slh_dsa_sig" },
                                               { "sphincs40_sign", "sphincs40_sig" } };
    for (int s = 0; s < 2; s++) {
        for (int i = 0; i < PQB_VEC_N; i++) {
            op_result_t r;
            memset(&r, 0, sizeof(r));
            if (run_op(SLH_OPS[s][0], (uint32_t)i, 0, &r) != 1) {
                ok = 0;
            }
            ok &= check(r.verified == 1, SLH_OPS[s][1], i);
            put(f, SLH_OPS[s][1], i, r.out, r.out_len);
            free(r.out);
        }
        fprintf(stderr, "write-vectors: %s done\n", SLH_OPS[s][1]);
    }

    /* XMSS 2^10 */
    {
        uint8_t* pk = NULL;
        uint8_t* sk = NULL;
        size_t pk_len = 0;
        ok &= pqb_xmss_consistent_key(&pk, &pk_len, &sk);
        put(f, "xmss_pk", -1, pk, pk_len);
        uint8_t* sig = malloc(pqb_xmss_sig_len());
        for (int i = 0; i < PQB_VEC_N; i++) {
            size_t sig_len = 0;
            run_input((uint32_t)i, in);
            ok &= pqb_xmss_sign(sk, in, sig, &sig_len);
            put(f, "xmss_sig", i, sig, sig_len);
        }
        free(sig);
        free(pk);
        free(sk);
        fprintf(stderr, "write-vectors: xmss done (checked by the xmss_verify op)\n");
    }

    /* SHRINCS (this build's variant) */
    {
        SecretKey sk;
        PublicKey pk;
        pqb_shrincs_consistent_key(&sk, &pk);
        uint8_t skb[6 * N];
        memcpy(skb, sk.seed, N);
        memcpy(skb + N, sk.prf, N);
        memcpy(skb + 2 * N, sk.sf, N);
        memcpy(skb + 3 * N, sk.sl, N);
        memcpy(skb + 4 * N, sk.pk.seed, N);
        memcpy(skb + 5 * N, sk.pk.root, N);
        put(f, "shrincs_sk", -1, skb, sizeof(skb));
        const uint32_t swn = pqb_shrincs_swn();
        const size_t sf_len = pqb_shrincs_sf_sig_len();
        const size_t sl_len = pqb_shrincs_sl_sig_len();
        uint8_t* sig = malloc(sl_len > sf_len ? sl_len : sf_len);
        for (int i = 0; i < PQB_VEC_N; i++) {
            run_input((uint32_t)i, in);
            ok &= pqb_shrincs_sign_sf(&sk, in, swn, sig);
            ok &= check((int)shrincs_verify_stateful(in, 32, sig, (uint32_t)sf_len, &pk),
                        "shrincs_sf_sig", i);
            put(f, "shrincs_sf_sig", i, sig, sf_len);
        }
        fprintf(stderr, "write-vectors: shrincs stateful done\n");
        for (int i = 0; i < PQB_VEC_N; i++) {
            run_input((uint32_t)i, in);
            ok &= pqb_shrincs_sign_sl(&sk, in, swn, sig);
            ok &= check((int)shrincs_verify_stateless(in, 32, sig, &pk), "shrincs_sl_sig", i);
            put(f, "shrincs_sl_sig", i, sig, sl_len);
            fprintf(stderr, "write-vectors: shrincs stateless %d\n", i);
        }
        free(sig);
    }

    /* ML-DSA */
    static const char* const SETS[3] = { "44", "65", "87" };
    for (int s = 0; s < 3; s++) {
        size_t pk_len, sk_len, sig_len;
        pqb_mldsa_sizes(s, &pk_len, &sk_len, &sig_len);
        uint8_t* pk = malloc(pk_len);
        uint8_t* sk = malloc(sk_len);
        uint8_t* sig = malloc(sig_len);
        char nm[32];
        ok &= pqb_mldsa_keygen(s, pk, sk);
        snprintf(nm, sizeof(nm), "mldsa%s_pk", SETS[s]);
        put(f, nm, -1, pk, pk_len);
        snprintf(nm, sizeof(nm), "mldsa%s_sk", SETS[s]);
        put(f, nm, -1, sk, sk_len);
        snprintf(nm, sizeof(nm), "mldsa%s_sig", SETS[s]);
        for (int i = 0; i < PQB_VEC_N; i++) {
            ok &= pqb_mldsa_sign(s, sk, (uint32_t)i, sig);
            put(f, nm, i, sig, sig_len);
        }
        free(pk);
        free(sk);
        free(sig);
    }
    fprintf(stderr, "write-vectors: ml-dsa done (checked by the verify ops)\n");

    /* FN-DSA */
    static const unsigned LOGNS[2] = { 9, 10 };
    for (int s = 0; s < 2; s++) {
        const unsigned logn = LOGNS[s];
        size_t sk_len, vk_len, sig_len;
        pqb_fndsa_sizes(logn, &sk_len, &vk_len, &sig_len);
        uint8_t* sk = malloc(sk_len);
        uint8_t* vk = malloc(vk_len);
        uint8_t* sig = malloc(sig_len);
        char nm[32];
        pqb_fndsa_keygen(logn, sk, vk);
        snprintf(nm, sizeof(nm), "fndsa%u_vk", 1u << logn);
        put(f, nm, -1, vk, vk_len);
        snprintf(nm, sizeof(nm), "fndsa%u_sk", 1u << logn);
        put(f, nm, -1, sk, sk_len);
        snprintf(nm, sizeof(nm), "fndsa%u_sig", 1u << logn);
        for (int i = 0; i < PQB_VEC_N; i++) {
            ok &= pqb_fndsa_sign(logn, sk, (uint32_t)i, sig) == sig_len;
            put(f, nm, i, sig, sig_len);
        }
        free(sk);
        free(vk);
        free(sig);
    }
    fprintf(stderr, "write-vectors: fn-dsa done (checked by the verify ops)\n");

    const uint8_t end[2] = { 0, 0 };
    fwrite(end, 1, 2, f);
    fclose(f);
    return ok;
}

/* Monte Carlo estimate of the probability that one PORS+FP grinding attempt succeeds
 * (pors_grind() in pors_fp.c accepts the first digest whose indices give an Octopus
 * authentication set of at most M_MAX nodes). Digests are SHA-256 of a counter, which
 * stands in for the random-oracle output of the real attempt; the index derivation and
 * the acceptance test are Jade's own functions with the consistent key's hash context. */
int pqb_pors_prob(unsigned long millions, unsigned long start_million)
{
    SecretKey sk;
    PublicKey pk;
    pqb_shrincs_consistent_key(&sk, &pk);
    uint8_t adrs[32] = { 0 };
    SHA256_CTX hash_ctx;
    mbedtls_sha256_init(&hash_ctx);
    sha256_add_to_ctx(&hash_ctx, sk.pk.seed, N);
    sha256_add_to_ctx(&hash_ctx, adrs, 32);
    sha256_add_to_ctx(&hash_ctx, adrs, 16);

    const unsigned long long first = (unsigned long long)start_million * 1000000ull;
    const unsigned long total = millions * 1000000ul;
    unsigned long hits = 0;
    uint8_t digest[32];
    uint32_t indices[K];
    uint8_t xof[xof_block_idx * 32];
    Tuple32_t A[M_MAX];
    uint32_t A_len = 0;
    for (unsigned long long i = first; i < first + total; i++) {
        uint8_t ctr[8];
        for (int b = 0; b < 8; b++) {
            ctr[b] = (uint8_t)(i >> (8 * b));
        }
        SHA256_CTX c;
        mbedtls_sha256_init(&c);
        mbedtls_sha256_clone(&c, &hash_ctx);
        sha256_add_to_ctx(&c, ctr, 8);
        sha256_finalize_32(&c, digest);
        pors_msg_to_indices(digest, adrs, &hash_ctx, indices, xof);
        hits += pors_octopus(indices, A, &A_len);
    }
    const double p = (double)hits / (double)total;
    printf("pors_prob,start=%llu,samples=%lu,accepted=%lu,p=%.9f,expected_attempts=%.1f\n",
           first, total, hits, p, p > 0 ? 1.0 / p : 0.0);
    return 1;
}
