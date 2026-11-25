/*
 * XMSS with Blockstream's 2^10 parameter set (OID 0xff), mirroring
 * third_party/jade-hbs/main/process/sign_xmss.c. Uses xmss_core.c (no tree caching), as
 * the firmware's amalgamated build does.
 *
 * xmss_verify times xmss_core_sign_open() on the host's signature of message x %
 * PQB_VEC_N, made with the consistent key of xmss_selftest for x = 0 (embedded vectors
 * "xmss_pk" and "xmss_sig/<i>").
 */
#include "common.h"

#include <mbedtls/sha512.h>
#include <stdlib.h>
#include <string.h>

#include "xmss/params.h"
#include "xmss/xmss_core.h"

static const char* const SK_HEX =
    "000000ff00000000b809496f05c121c581b0c7d570a9f7212230654732ee3738"
    "6867f889755ce3dc2eee098dfb7b52a4042220ab6ff8a702829765a3d900a635"
    "9204ef3d352c6023";

/* Jade passes a progress callback that redraws a progress bar; this one does nothing. */
static void noop_progress(uint32_t current, uint32_t total, void* userdata)
{
    (void)current;
    (void)total;
    (void)userdata;
}

/* Consistent key pair of xmss_selftest for x = 0 (used by gen_vectors.c). */
int pqb_xmss_consistent_key(uint8_t** pk, size_t* pk_len, uint8_t** sk)
{
    xmss_params xp;
    if (xmss_parse_oid(&xp, 0x000000ff)) {
        return 0;
    }
    uint8_t in[32];
    run_input(0, in);
    uint8_t seed[64];
    mbedtls_sha512(in, 32, seed, 0);
    *sk = malloc(xp.sk_bytes);
    *pk = malloc(xp.pk_bytes);
    *pk_len = xp.pk_bytes;
    xmssmt_core_seed_keypair(&xp, *pk, *sk, seed, noop_progress, NULL);
    return 1;
}

/* Signs msg with sk (advancing its index) and writes the bare signature. */
int pqb_xmss_sign(uint8_t* sk, const uint8_t* msg, uint8_t* sig, size_t* sig_len)
{
    xmss_params xp;
    if (xmss_parse_oid(&xp, 0x000000ff)) {
        return 0;
    }
    unsigned long long smlen = 0;
    uint8_t* sm = malloc((size_t)xp.sig_bytes + 32);
    const int ret = xmss_core_sign(&xp, sk, sm, &smlen, msg, 32, noop_progress, NULL);
    memcpy(sig, sm, xp.sig_bytes);
    *sig_len = xp.sig_bytes;
    free(sm);
    return !ret;
}

size_t pqb_xmss_sig_len(void)
{
    xmss_params xp;
    return xmss_parse_oid(&xp, 0x000000ff) ? 0 : xp.sig_bytes;
}

static int run_xmss_verify(uint32_t x, op_result_t* r)
{
    xmss_params xp;
    if (xmss_parse_oid(&xp, 0x000000ff)) {
        return -1;
    }
    const int v = (int)(x % PQB_VEC_N);
    size_t pk_len = 0;
    size_t sig_len = 0;
    uint8_t* pk = pqb_vec_copy("xmss_pk", -1, &pk_len);
    uint8_t* sig = pqb_vec_copy("xmss_sig", v, &sig_len);
    if (!pk || !sig || pk_len != xp.pk_bytes || sig_len != xp.sig_bytes) {
        free(pk);
        free(sig);
        return -1;
    }
    uint8_t in[32];
    run_input((uint32_t)v, in);
    /* xmss_core_sign_open() takes the signed message: signature || message */
    const unsigned long long smlen = (unsigned long long)sig_len + 32;
    uint8_t* sm = malloc((size_t)smlen);
    memcpy(sm, sig, sig_len);
    memcpy(sm + sig_len, in, 32);
    uint8_t* m = malloc((size_t)smlen);
    unsigned long long mlen = 0;
    op_timer_t t;

    timer_start(&t);
    pqb_mbedtls_core_begin();
    const int ret = xmss_core_sign_open(&xp, m, &mlen, sm, smlen, pk);
    pqb_mbedtls_core_end();
    timer_stop(&t, r);

    r->verified = !ret && mlen == 32 && !memcmp(m, in, 32);
    r->out = sig;
    r->out_len = sig_len;
    free(m);
    free(sm);
    free(pk);
    return 1;
}

int run_xmss_op(const char* op, uint32_t x, op_result_t* r)
{
    if (!strcmp(op, "xmss_verify")) {
        return run_xmss_verify(x, r);
    }
    const int is_keygen = !strcmp(op, "xmss_keygen");
    const int is_selftest = !strcmp(op, "xmss_selftest");
    if (!is_keygen && !is_selftest && strcmp(op, "xmss_sign")) {
        return 0;
    }

    uint8_t in[32];
    run_input(x, in);
    op_timer_t t;

    if (is_selftest) {
        /* Correctness only: keygen from a fixed seed, sign the run's message, verify it.
         * Times the signature. */
        xmss_params xp;
        if (xmss_parse_oid(&xp, 0x000000ff)) {
            return -1;
        }
        uint8_t seed[64];
        mbedtls_sha512(in, 32, seed, 0);
        uint8_t* sk = malloc(xp.sk_bytes);
        uint8_t* pk = malloc(xp.pk_bytes);
        xmssmt_core_seed_keypair(&xp, pk, sk, seed, noop_progress, NULL);

        const size_t sm_max = (size_t)xp.sig_bytes + 32;
        unsigned long long smlen = 0;
        uint8_t* sm = malloc(sm_max);
        timer_start(&t);
        pqb_mbedtls_core_begin();
        const int ret = xmss_core_sign(&xp, sk, sm, &smlen, in, 32, noop_progress, NULL);
        pqb_mbedtls_core_end();
        timer_stop(&t, r);

        uint8_t* m = malloc(sm_max);
        unsigned long long mlen = 0;
        r->verified = !ret && !xmss_core_sign_open(&xp, m, &mlen, sm, smlen, pk) && mlen == 32
            && !memcmp(m, in, 32);
        r->out_len = xp.sig_bytes;
        r->out = malloc(r->out_len);
        memcpy(r->out, sm, r->out_len);
        free(m);
        free(sm);
        free(sk);
        free(pk);
        return 1;
    }

    if (is_keygen) {
        const uint32_t oid = 0x000000ff;
        xmss_params xp;
        if (xmss_parse_oid(&xp, oid)) {
            return -1;
        }
        uint8_t sha512_out[64];
        const size_t sk_total = XMSS_OID_LEN + (size_t)xp.sk_bytes;
        const size_t pk_total = XMSS_OID_LEN + (size_t)xp.pk_bytes;
        uint8_t* sk = malloc(sk_total);
        uint8_t* pk = malloc(pk_total);
        for (unsigned int i = 0; i < XMSS_OID_LEN; i++) {
            pk[XMSS_OID_LEN - i - 1] = (oid >> (8 * i)) & 0xFF;
            sk[XMSS_OID_LEN - i - 1] = (oid >> (8 * i)) & 0xFF;
        }

        timer_start(&t);
        mbedtls_sha512(in, 32, sha512_out, 0);
        pqb_mbedtls_core_begin();
        xmssmt_core_seed_keypair(&xp, pk + XMSS_OID_LEN, sk + XMSS_OID_LEN, sha512_out,
                                 noop_progress, NULL);
        pqb_mbedtls_core_end();
        timer_stop(&t, r);

        r->out = sk;
        r->out_len = sk_total;
        /* pk = root || PUB_SEED, which the core sk also carries after idx, SK_SEED, SK_PRF */
        r->verified = !memcmp(pk + XMSS_OID_LEN,
                              sk + XMSS_OID_LEN + xp.index_bytes + 2 * xp.n, 2 * xp.n);
        free(pk);
        return 1;
    }

    uint8_t sk[72];
    hex_to_bytes(SK_HEX, sk, sizeof(sk));
    uint32_t oid = 0;
    for (int i = 0; i < XMSS_OID_LEN; i++) {
        oid |= (uint32_t)sk[XMSS_OID_LEN - i - 1] << (i * 8);
    }
    xmss_params xp;
    if (xmss_parse_oid(&xp, oid)) {
        return -1;
    }
    const size_t sm_max = (size_t)xp.sig_bytes + 32;
    unsigned long long smlen = 0;
    uint8_t* sm = malloc(sm_max);

    timer_start(&t);
    pqb_mbedtls_core_begin();
    const int ret = xmss_core_sign(&xp, sk + XMSS_OID_LEN, sm, &smlen, in, 32, noop_progress,
                                   NULL);
    pqb_mbedtls_core_end();
    timer_stop(&t, r);

    r->out_len = xp.sig_bytes; /* Jade replies with the signature only */
    r->out = malloc(r->out_len);
    memcpy(r->out, sm, r->out_len);

    /* Blockstream's hard-coded test key stores a root that does not match its own seeds (the
     * Jade handler never verifies), so its signatures cannot verify even when correct.
     * Correctness for this op comes from byte-identical output across platforms plus the
     * xmss_selftest op. */
    r->verified = ret ? 0 : -1;
    free(sm);
    return 1;
}
