/*
 * SHRINCS stateful signing and stateful-tree keygen, mirroring
 * third_party/jade-hbs/main/process/sign_shrincs.c. The variant (SHRINCS_B or SHRINCS_L)
 * is chosen at build time, as in the firmware.
 *
 * Round-2 ops use a consistent key: the SecretKey that shrincs_restore() derives from the
 * seed bytes 0, 1, ..., 47 (the shrincs_selftest seed for x = 0), computed by the host
 * and embedded as the vector record "shrincs_sk" (seed, prf, sf, sl, pk.seed, pk.root):
 *   shrincs_sign_stateless    shrincs_sign_stateless() on message x, then (untimed)
 *                             shrincs_verify_stateless() and the grinding counters
 *   shrincs_verify            shrincs_verify_stateful() on the host's stateful signature
 *                             of message x % PQB_VEC_N
 *   shrincs_verify_stateless  shrincs_verify_stateless() on the host's stateless
 *                             signature of message x % PQB_VEC_N
 * Both verify functions check WOTS+C digests against the variant's SWN constant, so the
 * signatures they check are made at swn = SWN (2040 for SHRINCS-B, 140 for SHRINCS-L).
 */
#include "common.h"

#include <mbedtls/sha512.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "shrincs/hash.h"
#include "shrincs/shrincs.h"
#include "shrincs/uxmss.h"

static const char* const SK_HEX =
    "0517400a7d4f5a532d4f34b077182caf1a79e406404e29a7feed94aa546330ac"
    "00ae2c282f33b319d83b705b4b5487c618311f77a5283cf39aabaf35dc3dfd79"
    "918fd17d889f34eb76a99a0c93a2015eda5a08dc47d1e05d0d4d816f72e78e27";

/* Jade always passes a progress callback and wots_sign() calls it without a NULL check,
 * so pass a do-nothing one (the firmware's version also redraws a progress bar). */
static void noop_progress(uint16_t current, void* userdata)
{
    (void)current;
    (void)userdata;
}

static void sk_from_bytes(const uint8_t* b, SecretKey* sk)
{
    memcpy(sk->seed, b, N);
    memcpy(sk->prf, b + N, N);
    memcpy(sk->sf, b + N * 2, N);
    memcpy(sk->sl, b + N * 3, N);
    memcpy(sk->pk.seed, b + N * 4, N);
    memcpy(sk->pk.root, b + N * 5, N);
}

static uint32_t be32(const uint8_t* p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

/* Stateless signature layout (shrincs.c, constants.h): sf (N), PORS+FP signature (R, K
 * secret values, M_MAX authentication nodes), then D hypertree layers of XMSS_SIGN_LEN,
 * each starting with a WOTS+C signature (R, 4-byte big-endian counter, L chains). */
#define SL_WOTS_CTR_OFFSET(layer) (N + PORS_SIGN_LEN + (layer) * XMSS_SIGN_LEN + R_LEN)

/* The PORS+FP grinding counter is not stored in the signature; it is the ctr for which
 * prf_msg(..., is_ctr = 1, ctr, ...) reproduces the signature's R (pors_fp.c,
 * pors_grind()). Returns UINT32_MAX if no counter below the limit matches. */
static uint32_t pors_counter(const SecretKey* sk, const uint8_t* msg, uint32_t msg_len,
                             const uint8_t* sig)
{
    uint8_t r[R_LEN];
    for (uint32_t ctr = 0; ctr < (1u << 24); ctr++) {
        prf_msg(sk->prf, sk->pk.seed, sk->pk.seed, msg, msg_len, 1, ctr, R_LEN, r);
        if (!memcmp(r, sig + N, R_LEN)) {
            return ctr;
        }
    }
    return UINT32_MAX;
}

void pqb_shrincs_stateless_grind(const SecretKey* sk, const uint8_t* msg, uint32_t msg_len,
                                 const uint8_t* sig, char* out, size_t out_len)
{
    snprintf(out, out_len, "pors=%lu;wots0=%lu;wots1=%lu",
             (unsigned long)pors_counter(sk, msg, msg_len, sig),
             (unsigned long)be32(sig + SL_WOTS_CTR_OFFSET(0)),
             (unsigned long)be32(sig + SL_WOTS_CTR_OFFSET(1)));
}

/* Consistent key from the shrincs_selftest seed for x = 0 (used by gen_vectors.c). */
void pqb_shrincs_consistent_key(SecretKey* sk, PublicKey* pk)
{
    uint8_t seed[3 * N];
    for (size_t i = 0; i < sizeof(seed); i++) {
        seed[i] = (uint8_t)i;
    }
    State state;
    shrincs_restore(seed, pk, sk, &state, NULL);
}

size_t pqb_shrincs_sf_sig_len(void) { return N + WOTS_SIGN_LEN + 1 * N; }
size_t pqb_shrincs_sl_sig_len(void) { return SL_SIZE; }
uint32_t pqb_shrincs_swn(void) { return SWN; }

/* Stateful signature with q = 1, as the shrincs_sign op makes, with the given key. */
int pqb_shrincs_sign_sf(SecretKey* sk, const uint8_t* msg, uint32_t swn, uint8_t* sig)
{
    State state;
    state.q = 0;
    state.valid = 1;
    return (int)shrincs_sign_stateful(msg, 32, sk, &state, swn, sig, noop_progress, NULL, NULL);
}

/* shrincs_sign_stateless() writes only the PORS+FP authentication nodes it needs, and
 * shrincs_verify_stateless() rejects a signature whose unused node slots are not all
 * zero, so the caller zeroes the buffer first (Jade's firmware has no handler that calls
 * it). */
int pqb_shrincs_sign_sl(SecretKey* sk, const uint8_t* msg, uint32_t swn, uint8_t* sig)
{
    memset(sig, 0, SL_SIZE);
    return (int)shrincs_sign_stateless(msg, 32, sk, swn, sig, noop_progress, NULL);
}

static int load_consistent_key(SecretKey* sk, PublicKey* pk)
{
    size_t len = 0;
    const uint8_t* b = pqb_vec("shrincs_sk", -1, &len);
    if (!b || len != 6 * N) {
        return 0;
    }
    sk_from_bytes(b, sk);
    memcpy(pk->seed, sk->pk.seed, N);
    memcpy(pk->root, sk->pk.root, N);
    return 1;
}

static int run_shrincs_verify(int stateless, uint32_t x, op_result_t* r)
{
    SecretKey sk;
    PublicKey pk;
    if (!load_consistent_key(&sk, &pk)) {
        return -1;
    }
    const int v = (int)(x % PQB_VEC_N);
    size_t sig_len = 0;
    uint8_t* sig = pqb_vec_copy(stateless ? "shrincs_sl_sig" : "shrincs_sf_sig", v, &sig_len);
    const size_t want = stateless ? pqb_shrincs_sl_sig_len() : pqb_shrincs_sf_sig_len();
    if (!sig || sig_len != want) {
        free(sig);
        return -1;
    }
    uint8_t in[32];
    run_input((uint32_t)v, in);
    op_timer_t t;

    timer_start(&t);
    pqb_mbedtls_core_begin();
    const uint32_t ok = stateless ? shrincs_verify_stateless(in, 32, sig, &pk)
                                  : shrincs_verify_stateful(in, 32, sig, (uint32_t)sig_len, &pk);
    pqb_mbedtls_core_end();
    timer_stop(&t, r);

    r->out = sig;
    r->out_len = sig_len;
    r->verified = ok ? 1 : 0;
    return 1;
}

int run_shrincs_op(const char* op, uint32_t x, uint32_t swn, op_result_t* r)
{
    uint8_t in[32];
    run_input(x, in);
    op_timer_t t;

    if (!strcmp(op, "shrincs_verify")) {
        return run_shrincs_verify(0, x, r);
    }
    if (!strcmp(op, "shrincs_verify_stateless")) {
        return run_shrincs_verify(1, x, r);
    }
    if (!strcmp(op, "shrincs_sign_stateless")) {
        SecretKey sk;
        PublicKey pk;
        if (!load_consistent_key(&sk, &pk)) {
            return -1;
        }
        const size_t sig_len = SL_SIZE;
        uint8_t* sig = calloc(1, sig_len); /* unused authentication slots must be zero */

        timer_start(&t);
        pqb_mbedtls_core_begin();
        const uint32_t ok =
            shrincs_sign_stateless(in, 32, &sk, swn, sig, noop_progress, NULL);
        pqb_mbedtls_core_end();
        timer_stop(&t, r);

        r->out = sig;
        r->out_len = sig_len;
        if (ok) {
            /* Verification checks WOTS+C digests against SWN: only swn = SWN verifies */
            r->verified = swn == SWN ? (int)shrincs_verify_stateless(in, 32, sig, &pk) : -1;
            pqb_shrincs_stateless_grind(&sk, in, 32, sig, r->grind, sizeof(r->grind));
        } else {
            r->verified = 0;
        }
        return 1;
    }

    if (!strcmp(op, "shrincs_keygen")) {
        uint8_t sha512_out[64];
        const size_t leaves_len = N + (HSF + 1) * N;
        uint8_t* leaves = malloc(leaves_len);
        uint8_t adrs[32] = { 0 };
        uint8_t pk_sf[N];
        SHA256_CTX hash_ctx;

        timer_start(&t);
        mbedtls_sha512(in, 32, sha512_out, 0);
        mbedtls_sha256_init(&hash_ctx); /* no starts(), exactly as in the Jade handler */
        pqb_mbedtls_core_begin();
        sha256_add_to_ctx(&hash_ctx, sha512_out + 2 * N, N);
        sha256_add_to_ctx(&hash_ctx, adrs, 32);
        sha256_add_to_ctx(&hash_ctx, adrs, 16);
        uxmss_root(sha512_out, &hash_ctx, adrs, pk_sf, leaves + N);
        pqb_mbedtls_core_end();
        timer_stop(&t, r);
        free(leaves);

        r->out_len = N;
        r->out = malloc(N);
        memcpy(r->out, pk_sf, N);
        r->verified = -1; /* no independent check for a bare stateful-tree root */
        return 1;
    }

    if (!strcmp(op, "shrincs_selftest")) {
        /* Correctness only: a key derived consistently from a fixed seed, then sign the run's
         * message and verify it. Times the signature. */
        uint8_t seed[3 * N];
        for (size_t i = 0; i < sizeof(seed); i++) {
            seed[i] = (uint8_t)(i + x);
        }
        PublicKey pk;
        SecretKey sk;
        State state;
        shrincs_restore(seed, &pk, &sk, &state, NULL);
        state.q = 0;
        state.valid = 1;
        const size_t sig_len = N + WOTS_SIGN_LEN + (state.q + 1) * N;
        uint8_t* sig = malloc(sig_len);

        timer_start(&t);
        pqb_mbedtls_core_begin();
        const uint32_t ok =
            shrincs_sign_stateful(in, 32, &sk, &state, swn, sig, noop_progress, NULL, NULL);
        pqb_mbedtls_core_end();
        timer_stop(&t, r);

        r->out = sig;
        r->out_len = sig_len;
        r->verified = ok ? (int)shrincs_verify_stateful(in, 32, sig, (uint32_t)sig_len, &pk) : 0;
        snprintf(r->grind, sizeof(r->grind), "wots=%lu", (unsigned long)be32(sig + N + R_LEN));
        return 1;
    }

    if (strcmp(op, "shrincs_sign")) {
        return 0;
    }

    uint8_t sk_bytes[96];
    hex_to_bytes(SK_HEX, sk_bytes, sizeof(sk_bytes));
    SecretKey sk;
    memcpy(sk.seed, sk_bytes, N);
    memcpy(sk.prf, sk_bytes + N, N);
    memcpy(sk.sf, sk_bytes + N * 2, N);
    memcpy(sk.sl, sk_bytes + N * 3, N);
    memcpy(sk.pk.seed, sk_bytes + N * 4, N);
    memcpy(sk.pk.root, sk_bytes + N * 5, N);

    State state;
    state.q = 0;
    state.valid = 1;
    const size_t sig_len = N + WOTS_SIGN_LEN + (state.q + 1) * N;
    uint8_t* sig = malloc(sig_len);

    timer_start(&t);
    pqb_mbedtls_core_begin();
    const uint32_t ok =
        shrincs_sign_stateful(in, 32, &sk, &state, swn, sig, noop_progress, NULL, NULL);
    pqb_mbedtls_core_end();
    timer_stop(&t, r);

    r->out = sig;
    r->out_len = sig_len;
    /* Blockstream's hard-coded test key is consistent under SHRINCS-L (its pk.root
     * matches its seeds, shown by independent verification with shrincs-cpp) but not
     * under SHRINCS-B, whose signatures cannot verify even when correct (the Jade handler
     * never verifies). So SHRINCS-L signatures are verified here when swn = SWN (the only
     * target the verifier accepts); SHRINCS-B correctness comes from byte-identical
     * output across platforms plus the shrincs_selftest op. */
#if defined(SHRINCS_L)
    if (ok && swn == SWN) {
        PublicKey pk;
        memcpy(pk.seed, sk.pk.seed, N);
        memcpy(pk.root, sk.pk.root, N);
        r->verified = (int)shrincs_verify_stateful(in, 32, sig, (uint32_t)sig_len, &pk);
    } else {
        r->verified = ok ? -1 : 0;
    }
#else
    r->verified = ok ? -1 : 0;
#endif
    snprintf(r->grind, sizeof(r->grind), "wots=%lu", (unsigned long)be32(sig + N + R_LEN));
    return 1;
}
