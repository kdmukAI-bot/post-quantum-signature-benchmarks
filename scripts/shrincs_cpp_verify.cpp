/*
 * Checks SHRINCS stateful signatures produced by the benchmark (Blockstream's Jade port,
 * third_party/jade-hbs/main/shrincs) with BlockstreamResearch/shrincs-cpp, a separate C++
 * implementation of the same scheme by the same group, linked unmodified.
 *
 * Built once per variant by scripts/shrincs_cpp_verify.py (-DSHRINCS_B or -DSHRINCS_L,
 * linked against shrincs-cpp's sources and OpenSSL's libcrypto).
 *
 * Modes (messages are run x's input, x.to_bytes(32, "big"), as in
 * harness/common/common.c):
 *
 *   selftest SIG X
 *     The harness's shrincs_selftest op: seed[i] = i + X for i < 3N,
 *     shrincs_restore(seed), q = 1. shrincs-cpp restores the key from the same seed and
 *     must accept the signature with shrincs_verify_stateful. Controls that must be
 *     rejected: the next message, one flipped bit in a WOTS+C chain value, and one
 *     flipped bit in the SL root prefix.
 *
 *   fixedkey SKHEX SIG X
 *     The harness's shrincs_sign op, which signs with Blockstream's fixed test key
 *     (seed, prf, sf, sl, pk.seed, pk.root). shrincs-cpp restores sf, sl, and root from
 *     the key's seeds and reports which stored parts match. The signature check then
 *     covers everything except the final root comparison: the signature's SL prefix must
 *     equal the stored sl, and the stateful root rebuilt from the signature
 *     (uxmss_pk_from_sig, whose message hash binds the stored pk.root, as signing did)
 *     must equal the sf that shrincs-cpp derives from the seed. Controls: the next
 *     message and one flipped chain bit must not rebuild that root.
 *
 * Output: one line per call, "key=value" fields; exit status 0 if the expected results
 * hold, 1 otherwise.
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "shrincs.h"

using namespace SHRINCS;

static std::vector<unsigned char> read_file(const char* path)
{
    std::ifstream f(path, std::ios::binary);
    return std::vector<unsigned char>(std::istreambuf_iterator<char>(f), {});
}

static std::vector<unsigned char> message(uint32_t x)
{
    std::vector<unsigned char> m(32, 0);
    m[28] = (unsigned char)(x >> 24);
    m[29] = (unsigned char)(x >> 16);
    m[30] = (unsigned char)(x >> 8);
    m[31] = (unsigned char)x;
    return m;
}

static std::vector<unsigned char> from_hex(const char* hex)
{
    std::vector<unsigned char> out;
    size_t len = strlen(hex);
    for (size_t i = 0; i + 1 < len; i += 2) {
        unsigned int b;
        sscanf(hex + i, "%2x", &b);
        out.push_back((unsigned char)b);
    }
    return out;
}

static bool verify(const std::vector<unsigned char>& m,
                   const std::vector<unsigned char>& sig, PublicKey& pk)
{
    try {
        return shrincs_verify_stateful(m, sig.data(), (uint32_t)sig.size(), pk);
    } catch (const std::exception&) {
        return false;
    }
}

/* The base hash context every SHRINCS hash starts from:
 * SHA-256(PK.seed || 48 zero bytes). */
static SHA256_CTX base_ctx(const unsigned char* pk_seed)
{
    unsigned char zeros[48] = { 0 };
    SHA256_CTX c;
    SHA256_Init(&c);
    SHA256_Update(&c, pk_seed, N);
    SHA256_Update(&c, zeros, 48);
    return c;
}

/* Stateful root rebuilt from the signature, or empty if the WOTS+C digest is rejected. */
static std::vector<unsigned char> sf_from_sig(const std::vector<unsigned char>& m,
                                              const std::vector<unsigned char>& sig,
                                              const unsigned char* pk_seed,
                                              const unsigned char* pk_root)
{
    const uint32_t q = (uint32_t)((sig.size() - N - WOTS_SIGN_LEN) / N);
    unsigned char adrs[32] = { 0 };
    try {
        unsigned char* node = UXMSS::uxmss_pk_from_sig(
            sig.data() + N, sig.data() + N + WOTS_SIGN_LEN, m.data(), (uint32_t)m.size(),
            pk_root, base_ctx(pk_seed), adrs, q);
        std::vector<unsigned char> out(node, node + N);
        delete[] node;
        return out;
    } catch (const std::exception&) {
        return {};
    }
}

static int selftest(const char* path, uint32_t x)
{
    std::vector<unsigned char> sig = read_file(path);
    unsigned char seed[3 * N];
    for (uint32_t i = 0; i < 3 * N; i++) {
        seed[i] = (unsigned char)(i + x);
    }
    PublicKey pk;
    SecretKey sk;
    State st;
    shrincs_restore(seed, pk, sk, st);

    const bool ok = verify(message(x), sig, pk);
    const bool wrong_msg = verify(message(x + 1), sig, pk);
    std::vector<unsigned char> chain_flip = sig;
    chain_flip[N + R_LEN + 4] ^= 0x01;
    const bool chain_ok = verify(message(x), chain_flip, pk);
    std::vector<unsigned char> sl_flip = sig;
    sl_flip[0] ^= 0x01;
    const bool sl_ok = verify(message(x), sl_flip, pk);

    const bool pass = ok && !wrong_msg && !chain_ok && !sl_ok;
    printf("mode=selftest variant=%s run=%u bytes=%zu verify=%d wrong_msg=%d "
           "chain_flip=%d sl_flip=%d result=%s\n",
           L == 64 ? "L" : "B", x, sig.size(), ok, wrong_msg, chain_ok, sl_ok,
           pass ? "PASS" : "FAIL");
    return pass ? 0 : 1;
}

static int fixedkey(const char* skhex, const char* path, uint32_t x)
{
    std::vector<unsigned char> k = from_hex(skhex);
    if (k.size() != 6 * N) {
        fprintf(stderr, "key must be %u bytes\n", 6 * N);
        return 2;
    }
    const unsigned char* s_seed = k.data();
    const unsigned char* s_sf = k.data() + 2 * N;
    const unsigned char* s_sl = k.data() + 3 * N;
    const unsigned char* s_pkseed = k.data() + 4 * N;
    const unsigned char* s_root = k.data() + 5 * N;

    unsigned char seed[3 * N];
    memcpy(seed, s_seed, N);
    memcpy(seed + N, k.data() + N, N);
    memcpy(seed + 2 * N, s_pkseed, N);
    PublicKey pk;
    SecretKey sk;
    State st;
    shrincs_restore(seed, pk, sk, st);

    const bool sf_match = !memcmp(sk.sf.data(), s_sf, N);
    const bool sl_match = !memcmp(sk.sl.data(), s_sl, N);
    const bool root_match = !memcmp(pk.root.data(), s_root, N);

    std::vector<unsigned char> sig = read_file(path);
    const bool prefix = sig.size() > N && !memcmp(sig.data(), s_sl, N);
    std::vector<unsigned char> sf = sf_from_sig(message(x), sig, s_pkseed, s_root);
    const bool rebuilt = sf.size() == N && !memcmp(sf.data(), sk.sf.data(), N);
    std::vector<unsigned char> sf_wrong =
        sf_from_sig(message(x + 1), sig, s_pkseed, s_root);
    const bool wrong_msg =
        sf_wrong.size() == N && !memcmp(sf_wrong.data(), sk.sf.data(), N);
    std::vector<unsigned char> flip = sig;
    flip[N + R_LEN + 4] ^= 0x01;
    std::vector<unsigned char> sf_flip = sf_from_sig(message(x), flip, s_pkseed, s_root);
    const bool chain_ok = sf_flip.size() == N && !memcmp(sf_flip.data(), sk.sf.data(), N);

    PublicKey stored;
    memcpy(stored.seed.data(), s_pkseed, N);
    memcpy(stored.root.data(), s_root, N);
    const bool full_stored = verify(message(x), sig, stored);

    const bool pass = prefix && rebuilt && !wrong_msg && !chain_ok;
    printf("mode=fixedkey variant=%s run=%u bytes=%zu key_sf_matches_seed=%d "
           "key_sl_matches_seed=%d key_root_matches_seed=%d sig_sl_prefix=%d "
           "rebuilt_sf_matches_seed=%d wrong_msg=%d chain_flip=%d "
           "full_verify_stored_key=%d result=%s\n",
           L == 64 ? "L" : "B", x, sig.size(), sf_match, sl_match, root_match, prefix,
           rebuilt, wrong_msg, chain_ok, full_stored, pass ? "PASS" : "FAIL");
    return pass ? 0 : 1;
}

int main(int argc, char** argv)
{
    if (argc == 4 && !strcmp(argv[1], "selftest")) {
        return selftest(argv[2], (uint32_t)strtoul(argv[3], NULL, 10));
    }
    if (argc == 5 && !strcmp(argv[1], "fixedkey")) {
        return fixedkey(argv[2], argv[3], (uint32_t)strtoul(argv[4], NULL, 10));
    }
    fprintf(stderr, "usage: %s selftest SIG RUN | fixedkey SKHEX SIG RUN\n", argv[0]);
    return 2;
}
