/*
 * Does Blockstream's fixed XMSS 2^10 test key
 * (third_party/jade-hbs/main/process/sign_xmss.c; SK_HEX in harness/common/op_xmss.c)
 * store the root that its own seeds produce?
 *
 * There is no independent implementation of this XMSS variant (WOTS+C, n = 16, OID 0xff),
 * so this uses Jade's own XMSS code, unmodified and read in place, with the benchmark's
 * OpenSSL-backed mbedTLS shim (harness/linux/shim/mbedtls_shim.c). It first reproduces
 * the harness's xmss_keygen output for run 0 (seed = SHA-512(32 zero bytes)), so the
 * build is known to match the benchmark, then recomputes the fixed key's root from its
 * seeds.
 *
 * Build and run (from the repository root):
 *   X=third_party/jade-hbs/main/xmss
 *   cc -O2 -Iharness/linux/shim -I$X scripts/xmss_fixed_key_check.c $X/fips202.c \
 *      $X/hash_address.c $X/hash.c $X/params.c $X/randombytes.c $X/utils.c $X/wots.c \
 *      $X/xmss_commons.c $X/xmss_core.c harness/linux/shim/mbedtls_shim.c -lcrypto \
 *      -o build/independent-verification/xmss_fixed_key_check
 *   build/independent-verification/xmss_fixed_key_check \
 *      results/raw/host/r1/host-sigs/xmss_keygen_run0.bin
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <mbedtls/sha512.h>

#include "params.h"
#include "xmss_core.h"

static const char* const SK_HEX =
    "000000ff00000000b809496f05c121c581b0c7d570a9f7212230654732ee3738"
    "6867f889755ce3dc2eee098dfb7b52a4042220ab6ff8a702829765a3d900a635"
    "9204ef3d352c6023";

static void noop_progress(uint32_t current, uint32_t total, void* userdata)
{
    (void)current;
    (void)total;
    (void)userdata;
}

static void hex(const char* label, const unsigned char* b, size_t n)
{
    printf("%s=", label);
    for (size_t i = 0; i < n; i++) {
        printf("%02x", b[i]);
    }
    printf("\n");
}

int main(int argc, char** argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s XMSS_KEYGEN_RUN0_FILE\n", argv[0]);
        return 2;
    }
    xmss_params p;
    if (xmss_parse_oid(&p, 0x000000ff)) {
        return 2;
    }
    const size_t n = p.n;
    unsigned char sk[4 + 256];
    unsigned char pk[64];

    /* 1. Reproduce the harness's xmss_keygen output for run 0. */
    unsigned char in[32] = { 0 };
    unsigned char seed[64];
    mbedtls_sha512(in, 32, seed, 0);
    memset(sk, 0, sizeof(sk));
    sk[3] = 0xff;
    xmssmt_core_seed_keypair(&p, pk, sk + 4, seed, noop_progress, NULL);
    unsigned char saved[4 + 256];
    FILE* f = fopen(argv[1], "rb");
    if (!f) {
        perror(argv[1]);
        return 2;
    }
    const size_t saved_len = fread(saved, 1, sizeof(saved), f);
    fclose(f);
    const int build_ok = saved_len == 4 + p.sk_bytes && !memcmp(saved, sk, saved_len);
    printf("build_reproduces_harness_keygen_run0=%d\n", build_ok);

    /* 2. The fixed key: OID(4) || idx(4) || SK_SEED || SK_PRF || root || PUB_SEED. */
    unsigned char fixed[72];
    for (size_t i = 0; i < sizeof(fixed); i++) {
        unsigned int b;
        sscanf(SK_HEX + 2 * i, "%2x", &b);
        fixed[i] = (unsigned char)b;
    }
    const unsigned char* core = fixed + 4 + p.index_bytes;
    unsigned char s[48];
    memcpy(s, core, 2 * n);                  /* SK_SEED || SK_PRF */
    memcpy(s + 2 * n, core + 3 * n, n);      /* PUB_SEED */
    xmssmt_core_seed_keypair(&p, pk, sk + 4, s, noop_progress, NULL);
    const int root_ok = !memcmp(pk, core + 2 * n, n);
    hex("stored_root", core + 2 * n, n);
    hex("root_from_seeds", pk, n);
    printf("fixed_key_root_matches_seeds=%d\n", root_ok);
    return build_ok ? 0 : 1;
}
