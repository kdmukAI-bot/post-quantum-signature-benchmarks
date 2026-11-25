/*
 * SLH-DSA-SHA2-128s and Blockstream's reduced "SPHINCS+ 2^40" set, mirroring
 * third_party/jade-hbs/main/process/sign_slh_dsa.c (same parameters, keys, and library
 * calls; no progress callback, no leaf cache, no NVS write).
 *
 * Verify ops (slh_dsa_verify, sphincs40_verify) time slh_verify() on the signature of
 * message x % PQB_VEC_N made by the host with the same key (embedded vectors). The
 * hard-coded keys are consistent (their PK.root matches SK.seed), so these verify.
 */
#include "common.h"

#include <mbedtls/sha512.h>
#include <stdlib.h>
#include <string.h>

#include "slh_dsa/slh_dsa.h"
#include "slh_dsa/slh_param.h"

static const char* const SK_STANDARD_HEX =
    "0fac4b7b966f29c3ecff665eb4ead66eee253a1a3d501c09d2cc0a7a5afad474"
    "7906277af176f5e3cf644f591fb353c5d12447a500c02be7d4c86bd1e29a84ab";
static const char* const SK_CUSTOM_HEX =
    "e39c0e870f7e0270c5e8bc4ecb8447f59acf02c625e6da1e2018140412e2c8d6"
    "9fc70fec2531104d439e8409a144308e99a230a89e6ccc8fd40855d7f519029d";

/* Jade passes a progress callback that redraws a progress bar; this one does nothing. */
static void noop_progress(uint16_t current, void* userdata)
{
    (void)current;
    (void)userdata;
}

static void get_params(int is_standard, slh_param_t* prm)
{
    if (is_standard) {
        *prm = slh_dsa_sha2_128s;
    } else {
        memcpy(prm, &slh_dsa_sha2_128s, sizeof(slh_param_t));
        prm->alg_id = "custom-slh-dsa";
        prm->h = 45;
        prm->d = 5;
        prm->hp = 9;
        prm->a = 13;
        prm->k = 10;
        prm->lg_w = 4;
    }
}

static int run_slh_verify(int is_standard, uint32_t x, op_result_t* r)
{
    slh_param_t prm;
    get_params(is_standard, &prm);
    uint8_t sk[64];
    hex_to_bytes(is_standard ? SK_STANDARD_HEX : SK_CUSTOM_HEX, sk, sizeof(sk));
    const int v = (int)(x % PQB_VEC_N);
    size_t sig_len = 0;
    uint8_t* sig = pqb_vec_copy(is_standard ? "slh_dsa_sig" : "sphincs40_sig", v, &sig_len);
    if (!sig || sig_len != slh_sig_sz(&prm)) {
        free(sig);
        return -1;
    }
    uint8_t in[32];
    run_input((uint32_t)v, in);
    op_timer_t t;

    timer_start(&t);
    pqb_core_begin();
    const int ok = slh_verify(in, 32, sig, sig_len, NULL, 0, sk + 2 * prm.n, &prm);
    pqb_core_end();
    timer_stop(&t, r);

    r->out = sig;
    r->out_len = sig_len;
    r->verified = ok ? 1 : 0;
    return 1;
}

int run_slh_op(const char* op, uint32_t x, op_result_t* r)
{
    int is_standard;
    int is_sign;
    if (!strcmp(op, "slh_dsa_verify")) {
        return run_slh_verify(1, x, r);
    } else if (!strcmp(op, "sphincs40_verify")) {
        return run_slh_verify(0, x, r);
    } else if (!strcmp(op, "slh_dsa_keygen")) {
        is_standard = 1, is_sign = 0;
    } else if (!strcmp(op, "slh_dsa_sign")) {
        is_standard = 1, is_sign = 1;
    } else if (!strcmp(op, "sphincs40_keygen")) {
        is_standard = 0, is_sign = 0;
    } else if (!strcmp(op, "sphincs40_sign")) {
        is_standard = 0, is_sign = 1;
    } else {
        return 0;
    }

    slh_param_t prm;
    get_params(is_standard, &prm);
    const size_t n = prm.n;
    uint8_t in[32];
    run_input(x, in);
    op_timer_t t;

    if (!is_sign) {
        uint8_t sha512_out[64];
        uint8_t sk[64];
        uint8_t pk[32];
        const size_t leaves_len = n + (n << prm.hp);
        uint8_t* leaves = malloc(leaves_len);

        timer_start(&t);
        mbedtls_sha512(in, 32, sha512_out, 0);
        pqb_core_begin();
        slh_keygen_internal(sk, pk, sha512_out, sha512_out + n, sha512_out + 2 * n, &prm,
                            leaves + n);
        pqb_core_end();
        timer_stop(&t, r);
        free(leaves);

        r->out_len = sizeof(sk);
        r->out = malloc(r->out_len);
        memcpy(r->out, sk, sizeof(sk));
        /* FIPS 205 sk = SK.seed || SK.prf || PK.seed || PK.root, and pk = PK.seed || PK.root */
        r->verified = !memcmp(sk + 2 * n, pk, 2 * n);
        return 1;
    }

    uint8_t sk[64];
    hex_to_bytes(is_standard ? SK_STANDARD_HEX : SK_CUSTOM_HEX, sk, sizeof(sk));
    const size_t sig_len = slh_sig_sz(&prm);
    uint8_t* sig = malloc(sig_len);

    timer_start(&t);
    pqb_core_begin();
    const size_t written =
        slh_sign(sig, in, 32, NULL, 0, sk, NULL, &prm, noop_progress, NULL, NULL);
    pqb_core_end();
    timer_stop(&t, r);

    r->out = sig;
    r->out_len = sig_len;
    r->verified = (written == sig_len) && slh_verify(in, 32, sig, sig_len, NULL, 0, sk + 2 * n, &prm);
    return 1;
}
