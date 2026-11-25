/*
 * FN-DSA-512 and FN-DSA-1024 with Thomas Pornin's c-fn-dsa (third_party/c-fn-dsa, used
 * unmodified). c-fn-dsa follows its author's reading of the expected FIPS 206 draft; no
 * FIPS 206 draft had been published when it was pinned, so its key and signature formats
 * are not final. On the three boards it uses its integer emulation of floating point
 * (native floating point is only compiled for x86 SSE2, 64-bit ARM NEON, and 64-bit
 * RISC-V with the D extension). Temporary buffers are on the stack (the non-_temp API).
 *
 *   fndsa<512|1024>_keygen   fndsa_keygen_seeded() from the 32-byte seed run_input(x);
 *                            output vk || sk
 *   fndsa<512|1024>_sign     fndsa_sign_seeded(): raw message run_input(x), empty
 *                            context, and a fixed 40-byte seed of zeros for the signer's
 *                            PRNG, so the signature is a deterministic function of the
 *                            message (normal use seeds it from the system RNG). Key: the
 *                            key pair from seed run_input(0), embedded as vectors
 *                            "fndsa<n>_sk" and "fndsa<n>_vk". Verified afterwards,
 *                            untimed.
 *   fndsa<512|1024>_verify   fndsa_verify() on the host's signature of message
 *                            x % PQB_VEC_N (vector "fndsa<n>_sig/<i>").
 */
#include "common.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fndsa.h"

static const uint8_t SIGN_SEED[40] = { 0 };

static int parse(const char* op, unsigned* logn, const char** kind)
{
    if (!strncmp(op, "fndsa512_", 9)) {
        *logn = FNDSA_LOGN_512;
        *kind = op + 9;
    } else if (!strncmp(op, "fndsa1024_", 10)) {
        *logn = FNDSA_LOGN_1024;
        *kind = op + 10;
    } else {
        return 0;
    }
    return !strcmp(*kind, "keygen") || !strcmp(*kind, "sign") || !strcmp(*kind, "verify");
}

void pqb_fndsa_sizes(unsigned logn, size_t* sk_len, size_t* vk_len, size_t* sig_len)
{
    *sk_len = FNDSA_SIGN_KEY_SIZE(logn);
    *vk_len = FNDSA_VRFY_KEY_SIZE(logn);
    *sig_len = FNDSA_SIGNATURE_SIZE(logn);
}

void pqb_fndsa_keygen(unsigned logn, uint8_t* sk, uint8_t* vk)
{
    uint8_t seed[32];
    run_input(0, seed);
    fndsa_keygen_seeded(logn, seed, sizeof(seed), sk, vk);
}

size_t pqb_fndsa_sign(unsigned logn, const uint8_t* sk, uint32_t x, uint8_t* sig)
{
    uint8_t in[32];
    run_input(x, in);
    return fndsa_sign_seeded(sk, FNDSA_SIGN_KEY_SIZE(logn), NULL, 0, FNDSA_HASH_ID_RAW, in,
                             32, SIGN_SEED, sizeof(SIGN_SEED), sig,
                             FNDSA_SIGNATURE_SIZE(logn));
}

int run_fndsa_op(const char* op, uint32_t x, op_result_t* r)
{
    unsigned logn = 0;
    const char* kind = NULL;
    if (!parse(op, &logn, &kind)) {
        return 0;
    }
    const size_t sk_len = FNDSA_SIGN_KEY_SIZE(logn);
    const size_t vk_len = FNDSA_VRFY_KEY_SIZE(logn);
    const size_t sig_len = FNDSA_SIGNATURE_SIZE(logn);
    const unsigned n = 1u << logn;
    char rec[32];
    uint8_t in[32];
    op_timer_t t;

    if (!strcmp(kind, "keygen")) {
        uint8_t seed[32];
        run_input(x, seed);
        uint8_t* out = malloc(vk_len + sk_len);

        timer_start(&t);
        fndsa_keygen_seeded(logn, seed, sizeof(seed), out + vk_len, out);
        timer_stop(&t, r);

        r->out = out;
        r->out_len = vk_len + sk_len;
        /* keygen_seeded cannot fail; correctness comes from the library's self-tests and
         * KATs and from output hashes against the host */
        r->verified = -1;
        return 1;
    }

    size_t got = 0;
    snprintf(rec, sizeof(rec), "fndsa%u_vk", n);
    uint8_t* vk = pqb_vec_copy(rec, -1, &got);
    if (!vk || got != vk_len) {
        free(vk);
        return -1;
    }

    if (!strcmp(kind, "sign")) {
        snprintf(rec, sizeof(rec), "fndsa%u_sk", n);
        uint8_t* sk = pqb_vec_copy(rec, -1, &got);
        if (!sk || got != sk_len) {
            free(sk);
            free(vk);
            return -1;
        }
        run_input(x, in);
        uint8_t* sig = malloc(sig_len);

        timer_start(&t);
        const size_t written =
            fndsa_sign_seeded(sk, sk_len, NULL, 0, FNDSA_HASH_ID_RAW, in, 32, SIGN_SEED,
                              sizeof(SIGN_SEED), sig, sig_len);
        timer_stop(&t, r);

        r->out = sig;
        r->out_len = sig_len;
        r->verified = written == sig_len
            && fndsa_verify(sig, sig_len, vk, vk_len, NULL, 0, FNDSA_HASH_ID_RAW, in, 32);
        free(sk);
        free(vk);
        return 1;
    }

    /* verify */
    const int v = (int)(x % PQB_VEC_N);
    snprintf(rec, sizeof(rec), "fndsa%u_sig", n);
    uint8_t* sig = pqb_vec_copy(rec, v, &got);
    if (!sig || got != sig_len) {
        free(sig);
        free(vk);
        return -1;
    }
    run_input((uint32_t)v, in);

    timer_start(&t);
    const int ok = fndsa_verify(sig, sig_len, vk, vk_len, NULL, 0, FNDSA_HASH_ID_RAW, in, 32);
    timer_stop(&t, r);

    r->out = sig;
    r->out_len = sig_len;
    r->verified = ok ? 1 : 0;
    free(vk);
    return 1;
}
