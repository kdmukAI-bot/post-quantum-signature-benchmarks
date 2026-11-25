/*
 * Microbenchmark of single SHA-256 compressions and of the SHA-256 API paths the schemes
 * use, built against the same objects as pq_bench in the same build directory
 * (make ... cbench). Each item runs N chained calls; the result of every call feeds the
 * next, so calls cannot overlap or be skipped. Time comes from CLOCK_MONOTONIC and, where
 * the kernel exposes the CPU's cycle counter (perf_event_open), from the cycle count.
 *
 * Items:
 *   compress           sha2_256_compress() as linked into pq_bench for this COMPRESS
 *   compress_soft      slhdsa-c's plain-C compression (sha2_256_compress_soft)
 *   ossl_transform     OpenSSL's SHA256_Transform() on a native-order SHA256_CTX
 *   asm_blocks         pqb_sha256_blocks(), 1 block per call (assembly builds only)
 *   asm_blocks_x4      the same, 4 blocks per call, reported per block
 *   asm_blocks_unal    the same as asm_blocks with the block at an odd address
 *   api_chain_step     one SHRINCS WOTS chain step through the mbedTLS-style API linked
 *                      here: init, clone, update(32), update(16), finish
 *   api_oneshot_52     mbedtls_sha256() over 52 bytes (an XMSS PRF or H input)
 *   api_sweep          untimed check: lengths 0 to 300, one-shot and incremental
 *
 * Checks: every compression item must end in the same state, and the API items must match
 * OpenSSL's SHA256() over the same bytes. Exit status 1 if any check fails.
 *
 * Usage: compress_bench [N] [REPS]   (defaults 200000 and 5)
 */
#include <linux/perf_event.h>
#include <openssl/sha.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#include <mbedtls/sha256.h>

void sha2_256_compress(void* v);
void sha2_256_compress_soft(void* v);
__attribute__((weak)) void pqb_sha256_blocks(uint32_t state[8], const void* in, size_t num);

static int perf_fd = -1;

static void perf_open(void)
{
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof(pe));
    pe.type = PERF_TYPE_HARDWARE;
    pe.size = sizeof(pe);
    pe.config = PERF_COUNT_HW_CPU_CYCLES;
    perf_fd = (int)syscall(__NR_perf_event_open, &pe, 0, -1, -1, 0);
}

static uint64_t cycles_now(void)
{
    uint64_t v = 0;
    if (perf_fd < 0 || read(perf_fd, &v, sizeof(v)) != (ssize_t)sizeof(v)) {
        return 0;
    }
    return v;
}

static double now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}

static int cmp_double(const void* a, const void* b)
{
    const double x = *(const double*)a, y = *(const double*)b;
    return (x > y) - (x < y);
}

#define MAX_REPS 21

typedef struct {
    double ns[MAX_REPS];
    double cyc[MAX_REPS];
} samples_t;

static void report(const char* item, long n, int reps, samples_t* s, const char* check)
{
    qsort(s->ns, reps, sizeof(double), cmp_double);
    qsort(s->cyc, reps, sizeof(double), cmp_double);
    const double ns_med = s->ns[reps / 2] / n, ns_min = s->ns[0] / n;
    const double cyc_med = s->cyc[reps / 2] / n;
    const double mhz = (s->cyc[reps / 2] > 0) ? 1e3 * s->cyc[reps / 2] / s->ns[reps / 2] : 0;
    printf("%s,%ld,%d,%.1f,%.1f,%.0f,%.0f,%s\n", item, n, reps, ns_med, ns_min, cyc_med, mhz,
           check);
    fflush(stdout);
}

/* Runs BODY n times per rep, reps times, recording wall time and cycles. The cycle count
 * is taken from the same interval as the wall time, so MHz = cycles / time. */
#define TIME_ITEM(samples, n, reps, BODY)                                       \
    for (int r_ = 0; r_ < (reps); r_++) {                                       \
        const uint64_t c0_ = cycles_now();                                      \
        const double t0_ = now_ns();                                            \
        for (long i_ = 0; i_ < (n); i_++) {                                     \
            BODY;                                                               \
        }                                                                       \
        const double t1_ = now_ns();                                            \
        const uint64_t c1_ = cycles_now();                                      \
        (samples).ns[r_] = t1_ - t0_;                                           \
        (samples).cyc[r_] = (double)(c1_ - c0_);                                \
    }

static const uint32_t IV_BE_WORDS[8] = {
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
};

/* slhdsa-c layout: 8 big-endian state words, then the 64-byte block. */
static void be_buf_init(uint32_t v[24])
{
    for (int i = 0; i < 8; i++) {
        v[i] = __builtin_bswap32(IV_BE_WORDS[i]);
    }
    uint8_t* m = (uint8_t*)(v + 8);
    for (int i = 0; i < 64; i++) {
        m[i] = (uint8_t)(i * 7 + 1);
    }
}

static void be_state_bytes(const uint32_t v[8], uint8_t out[32]) { memcpy(out, v, 32); }

static void native_state_bytes(const uint32_t h[8], uint8_t out[32])
{
    for (int i = 0; i < 8; i++) {
        const uint32_t w = __builtin_bswap32(h[i]);
        memcpy(out + 4 * i, &w, 4);
    }
}

int main(int argc, char** argv)
{
    const long n = argc > 1 ? atol(argv[1]) : 200000;
    int reps = argc > 2 ? atoi(argv[2]) : 5;
    if (reps < 1) {
        reps = 1;
    }
    if (reps > MAX_REPS) {
        reps = MAX_REPS;
    }
    perf_open();
    printf("# perf cycle counter: %s\n", perf_fd >= 0 ? "yes" : "no");
    printf("item,n,reps,ns_per_op_median,ns_per_op_min,cycles_per_op_median,mhz,check\n");

    int failures = 0;
    samples_t s;
    uint8_t ref[32], got[32];
    /* The chained state after n compressions, from the plain-C reference. Every rep
     * starts from the same initial buffer, so every rep ends in the same state. */
    uint32_t v[24];

    be_buf_init(v);
    TIME_ITEM(s, n, reps, if (i_ == 0) be_buf_init(v); sha2_256_compress_soft(v));
    be_state_bytes(v, ref);
    report("compress_soft", n, reps, &s, "ref");

    TIME_ITEM(s, n, reps, if (i_ == 0) be_buf_init(v); sha2_256_compress(v));
    be_state_bytes(v, got);
    failures += memcmp(ref, got, 32) != 0;
    report("compress", n, reps, &s, memcmp(ref, got, 32) ? "MISMATCH" : "ok");

    {
        SHA256_CTX c;
        uint32_t init[24];
        be_buf_init(init);
        const uint8_t* block = (const uint8_t*)(init + 8);
        TIME_ITEM(s, n, reps,
                  if (i_ == 0) memcpy(c.h, IV_BE_WORDS, 32);
                  SHA256_Transform(&c, block));
        native_state_bytes(c.h, got);
        failures += memcmp(ref, got, 32) != 0;
        report("ossl_transform", n, reps, &s, memcmp(ref, got, 32) ? "MISMATCH" : "ok");
    }

    if (pqb_sha256_blocks) {
        uint32_t h[8];
        uint32_t init[24];
        be_buf_init(init);
        const uint8_t* block = (const uint8_t*)(init + 8);

        TIME_ITEM(s, n, reps, if (i_ == 0) memcpy(h, IV_BE_WORDS, 32);
                  pqb_sha256_blocks(h, block, 1));
        native_state_bytes(h, got);
        failures += memcmp(ref, got, 32) != 0;
        report("asm_blocks", n, reps, &s, memcmp(ref, got, 32) ? "MISMATCH" : "ok");

        /* 4 identical blocks per call: n/4 calls, so the end state matches n single
         * calls. */
        static uint8_t four[256];
        for (int k = 0; k < 4; k++) {
            memcpy(four + 64 * k, block, 64);
        }
        const long n4 = n / 4;
        TIME_ITEM(s, n4, reps, if (i_ == 0) memcpy(h, IV_BE_WORDS, 32);
                  pqb_sha256_blocks(h, four, 4));
        native_state_bytes(h, got);
        const int ok4 = (n % 4) || !memcmp(ref, got, 32);
        failures += !ok4;
        for (int r = 0; r < reps; r++) {
            s.ns[r] /= 4;
            s.cyc[r] /= 4;
        }
        report("asm_blocks_x4", n4, reps, &s, ok4 ? "ok" : "MISMATCH");

        static uint8_t unal[65 + 3];
        memcpy(unal + 1, block, 64);
        TIME_ITEM(s, n, reps, if (i_ == 0) memcpy(h, IV_BE_WORDS, 32);
                  pqb_sha256_blocks(h, unal + 1, 1));
        native_state_bytes(h, got);
        failures += memcmp(ref, got, 32) != 0;
        report("asm_blocks_unal", n, reps, &s, memcmp(ref, got, 32) ? "MISMATCH" : "ok");
    }

    /* SHRINCS WOTS chain step: base context holds one compressed 64-byte block (pk_seed
     * and padding), each step hashes adrs (32 bytes) and the 16-byte running value. */
    {
        uint8_t base_msg[64], adrs[32], val[16], d[32], expect[32];
        for (int i = 0; i < 64; i++) {
            base_msg[i] = (uint8_t)(3 * i + 5);
        }
        for (int i = 0; i < 32; i++) {
            adrs[i] = (uint8_t)(i ^ 0x5a);
        }
        mbedtls_sha256_context base;
        mbedtls_sha256_init(&base);
        mbedtls_sha256_starts(&base, 0);
        mbedtls_sha256_update(&base, base_msg, 64);

        TIME_ITEM(s, n, reps, if (i_ == 0) memset(val, 0x11, 16);
                  mbedtls_sha256_context c;
                  mbedtls_sha256_init(&c);
                  mbedtls_sha256_clone(&c, &base);
                  mbedtls_sha256_update(&c, adrs, 32);
                  mbedtls_sha256_update(&c, val, 16);
                  mbedtls_sha256_finish(&c, d);
                  mbedtls_sha256_free(&c);
                  memcpy(val, d, 16));
        /* Recompute the end value with OpenSSL. */
        uint8_t e[16], msg[112];
        memset(e, 0x11, 16);
        for (long i = 0; i < n; i++) {
            memcpy(msg, base_msg, 64);
            memcpy(msg + 64, adrs, 32);
            memcpy(msg + 96, e, 16);
            SHA256(msg, sizeof(msg), expect);
            memcpy(e, expect, 16);
        }
        const int ok = !memcmp(val, e, 16);
        failures += !ok;
        report("api_chain_step", n, reps, &s, ok ? "ok" : "MISMATCH");
    }

    {
        uint8_t in0[52], in[52], d[32], expect[32];
        for (int i = 0; i < 52; i++) {
            in0[i] = (uint8_t)(i + 9);
        }
        TIME_ITEM(s, n, reps, if (i_ == 0) memcpy(in, in0, 52); mbedtls_sha256(in, 52, d, 0);
                  memcpy(in, d, 16));
        uint8_t e[52];
        for (int i = 0; i < 52; i++) {
            e[i] = (uint8_t)(i + 9);
        }
        for (long i = 0; i < n; i++) {
            SHA256(e, 52, expect);
            memcpy(e, expect, 16);
        }
        const int ok = !memcmp(in, e, 52);
        failures += !ok;
        report("api_oneshot_52", n, reps, &s, ok ? "ok" : "MISMATCH");
    }

    /* Untimed sweep of the API linked here against OpenSSL: every length from 0 to 300
     * bytes, one-shot and incremental (several chunk sizes, with a clone part way). */
    {
        static uint8_t msg[300];
        for (int i = 0; i < 300; i++) {
            msg[i] = (uint8_t)(i * 13 + 7);
        }
        const size_t chunks[] = { 1, 3, 16, 31, 32, 55, 64, 65 };
        int bad = 0, cases = 0;
        for (size_t len = 0; len <= 300; len++) {
            uint8_t expect[32], d[32];
            SHA256(msg, len, expect);
            mbedtls_sha256(msg, len, d, 0);
            if (memcmp(d, expect, 32) && bad++ < 5) {
                printf("# api_sweep mismatch: one-shot len=%u\n", (unsigned)len);
            }
            cases++;
            for (size_t k = 0; k < sizeof(chunks) / sizeof(chunks[0]); k++) {
                mbedtls_sha256_context c, c2;
                mbedtls_sha256_init(&c);
                if (k & 1) {
                    /* even k: left unstarted, as Jade often does */
                    mbedtls_sha256_starts(&c, 0);
                }
                /* Hash the first half into c, clone c into c2, hash the rest into c2. */
                mbedtls_sha256_context* cur = &c;
                size_t off = 0;
                while (off < len) {
                    if (cur == &c && off >= len / 2) {
                        mbedtls_sha256_init(&c2);
                        mbedtls_sha256_clone(&c2, &c);
                        cur = &c2;
                    }
                    const size_t step = (len - off < chunks[k]) ? len - off : chunks[k];
                    mbedtls_sha256_update(cur, msg + off, step);
                    off += step;
                }
                if (cur == &c) {
                    mbedtls_sha256_init(&c2);
                    mbedtls_sha256_clone(&c2, &c);
                }
                mbedtls_sha256_finish(&c2, d);
                if (memcmp(d, expect, 32) && bad++ < 5) {
                    printf("# api_sweep mismatch: len=%u chunk=%u\n", (unsigned)len,
                           (unsigned)chunks[k]);
                }
                cases++;
            }
        }
        failures += bad != 0;
        printf("api_sweep,%d,0,0,0,0,0,%s\n", cases, bad ? "MISMATCH" : "ok");
    }

    printf("# checks: %s\n", failures ? "FAILED" : "all ok");
    return failures ? 1 : 0;
}
