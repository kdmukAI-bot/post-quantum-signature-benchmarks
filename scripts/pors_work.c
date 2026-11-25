/*
 * PORS+FP authentication-path work per message, for the SHRINCS stateless-signing fit
 * (scripts/grind_fit_r2.py). Links the host build's objects; changes no shared code.
 *
 * shrincs_sign_stateless() computes every PORS+FP authentication node with
 * pors_treehash(), which rebuilds the node's whole subtree. The subtrees of the Octopus
 * set cover every leaf of the "stop subtree" except the K revealed ones, where the stop
 * subtree is the whole tree unless pors_octopus() stops early (all K leaves under the
 * leftmost node of a lower level). So this work depends on the message.
 *
 * Reads lines "x ctr" (message index, PORS+FP grinding counter from the grind column) on
 * stdin. For each: R = prf_msg(..., ctr) as pors_grind() makes it (checked against the
 * embedded host signature for x < PQB_VEC_N), the message digest, the indices
 * (pors_msg_to_indices()), and the Octopus set (pors_octopus()). Prints
 *   x,ctr,accepted,a_len,max_index,stop_level,leaves_hashed,tree_hashes,r_check
 * leaves_hashed: leaves under the authentication nodes (each costs two hashes: secret
 * value and leaf); tree_hashes: leaf and internal-node hash calls that pors_auth_path()
 * makes (2 per leaf, 1 per internal node). r_check: "ok", "differs", or "-" (no vector).
 *
 * Build and run (host, from the repository root, per variant S = B or L; the host build
 * comes from scripts/r2_host_reference.sh). common.o dispatches to every scheme's
 * operations, so every scheme's objects are linked, though only SHRINCS code runs:
 *   O=harness/linux/build/r2-host-shrincsS-openssl/obj
 *   gcc -O2 -DSHRINCS_S -DPQB_HAVE_VECTORS -Iharness/linux/shim \
 *       -Iharness/linux/build/r2-host-shrincsS-openssl/src -Iharness/common \
 *       scripts/pors_work.c $O/shrincs/*.o $O/slh_dsa/*.o $O/xmss/*.o $O/fndsa/*.o \
 *       $O/lattice/*.o $O/linux/shim/*.o $O/common/common.o $O/common/op_*.o \
 *       $O/common/vectors.o $O/common/vectors_blob.o -lcrypto -lm -o pors_work_S
 *   grep ',shrincs_sign_stateless,' results/raw/host/r2/reference-S.csv \
 *       | awk -F, '{ split($14, g, "[=;]"); print $5, g[2] }' \
 *       | ./pors_work_S > results/raw/host/r2/pors-work-S.csv
 * Checked 2026-11-21: for both variants the output equals, byte for byte, the files the
 * round-2 fits used (messages 0 to 99, r_check "ok" for 0 to 9).
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "common.h"
#include "shrincs/address.h"
#include "shrincs/constants.h"
#include "shrincs/hash.h"
#include "shrincs/pors_fp.h"
#include "shrincs/shrincs.h"

/* Leaves under node (lvl, idx) as pors_treehash() counts them. */
static uint64_t leaves_under(uint32_t lvl, uint32_t idx)
{
    const uint64_t s = T - (1u << (B - 1));
    if (lvl == 0) {
        return 1;
    }
    /* level-1 nodes covered: [idx << (lvl - 1), (idx + 1) << (lvl - 1)) */
    const uint64_t lo = (uint64_t)idx << (lvl - 1);
    const uint64_t hi = (uint64_t)(idx + 1) << (lvl - 1);
    uint64_t two = 0; /* level-1 nodes below s have two leaves */
    if (lo < s) {
        two = (hi < s ? hi : s) - lo;
    }
    return (hi - lo) + two;
}

int main(void)
{
    size_t len = 0;
    const uint8_t* b = pqb_vec("shrincs_sk", -1, &len);
    if (!b || len != 6 * N) {
        fprintf(stderr, "no shrincs_sk vector\n");
        return 1;
    }
    SecretKey sk;
    memcpy(sk.seed, b, N);
    memcpy(sk.prf, b + N, N);
    memcpy(sk.sf, b + N * 2, N);
    memcpy(sk.sl, b + N * 3, N);
    memcpy(sk.pk.seed, b + N * 4, N);
    memcpy(sk.pk.root, b + N * 5, N);

    printf("x,ctr,accepted,a_len,max_index,stop_level,leaves_hashed,tree_hashes,r_check\n");
    unsigned long x, ctr;
    while (scanf("%lu %lu", &x, &ctr) == 2) {
        uint8_t msg[32];
        run_input((uint32_t)x, msg);

        /* as shrincs_sign_stateless() */
        uint8_t adrs[32] = { 0 };
        SHA256_CTX hash_ctx;
        mbedtls_sha256_init(&hash_ctx);
        sha256_add_to_ctx(&hash_ctx, sk.pk.seed, N);
        sha256_add_to_ctx(&hash_ctx, adrs, 32);
        sha256_add_to_ctx(&hash_ctx, adrs, 16);

        /* as pors_sign() and pors_grind() for this counter */
        uint8_t opt_rand[N];
        memcpy(opt_rand, sk.pk.seed, N);
        uint8_t r[R_LEN];
        prf_msg(sk.prf, sk.pk.seed, opt_rand, msg, 32, 1, (uint32_t)ctr, R_LEN, r);

        const char* rc = "-";
        if (x < PQB_VEC_N) {
            size_t sl = 0;
            const uint8_t* sig = pqb_vec("shrincs_sl_sig", (int)x, &sl);
            rc = (sig && sl == SL_SIZE && !memcmp(sig + N, r, R_LEN)) ? "ok" : "differs";
        }

        setTypeAndClear(adrs, SL_H_MSG);
        SHA256_CTX ctx;
        mbedtls_sha256_init(&ctx);
        mbedtls_sha256_clone(&ctx, &hash_ctx);
        sha256_add_to_ctx(&ctx, adrs, 32);
        sha256_add_to_ctx(&ctx, r, R_LEN);
        sha256_add_to_ctx(&ctx, sk.pk.root, N);
        sha256_add_to_ctx(&ctx, msg, 32);
        uint8_t digest[32];
        sha256_finalize_32(&ctx, digest);

        uint32_t indices[K];
        uint8_t xof_out[xof_block_idx * 32];
        pors_msg_to_indices(digest, adrs, &hash_ctx, indices, xof_out);

        Tuple32_t A[M_MAX];
        uint32_t a_len = 0;
        const uint32_t ok = pors_octopus(indices, A, &a_len);

        uint64_t leaves = 0, hashes = 0;
        uint32_t top = 0;
        for (uint32_t i = 0; i < a_len; i++) {
            const uint64_t n = leaves_under(A[i].a, A[i].b);
            leaves += n;
            hashes += 2 * n + (n - 1);
            if (A[i].a > top) {
                top = A[i].a;
            }
        }
        uint32_t mx = 0;
        for (uint32_t i = 0; i < K; i++) {
            if (indices[i] > mx) {
                mx = indices[i];
            }
        }
        /* stop level: the lowest level whose leftmost node holds every chosen leaf */
        uint32_t stop = B;
        for (uint32_t h = 1; h <= B; h++) {
            if ((uint64_t)mx < leaves_under(h, 0)) {
                stop = h;
                break;
            }
        }
        printf("%lu,%lu,%u,%u,%u,%u,%llu,%llu,%s\n", x, ctr, ok, a_len, mx, stop,
               (unsigned long long)leaves, (unsigned long long)hashes, rc);
    }
    return 0;
}
