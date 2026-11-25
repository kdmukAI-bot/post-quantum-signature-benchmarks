/*
 * Native benchmark of Blockstream's Jade hash-based signature code (jade-hbs) and of the
 * lattice schemes (mldsa-native, c-fn-dsa), for Linux hosts and the Pi Zero. Op names,
 * keys, and inputs of the hash-based ops match scripts/run_jade_bench.py, so the output
 * hashes can be compared byte for byte against the Jade firmware's replies.
 *
 * Usage: pq_bench --board B --build S --op OP [-n RUNS] [--swn SWN] [--save DIR]
 *                 [--save-all] [--header]
 *        pq_bench --write-vectors FILE   (host: write the verification vector blob)
 *        pq_bench --pors-prob M[:S]      (host: PORS+FP grinding success probability
 *                                         from M million samples starting at S million)
 * --save writes run 0's output to DIR; --save-all writes every run's output.
 *
 * CSV columns (round 2, the same on every platform):
 *   board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,
 *   stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind
 * On Linux the three memory columns are empty except in memory builds (make MEM=1), which
 * run each op in a fresh thread with a painted stack and count heap use through
 * -Wl,--wrap=malloc (mem_linux.c); heap_min_free_bytes stays empty on Linux. Memory
 * builds are for the memory pass only, not for timing.
 */
#include <getopt.h>
#include <openssl/sha.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "common.h"

#ifdef PQB_MEM
#include "mem_linux.h"
#endif

int pqb_pors_prob(unsigned long millions, unsigned long start_million);

static void usage(void)
{
    fprintf(stderr,
            "usage: pq_bench --board B --build S --op OP [-n RUNS] [--swn SWN] "
            "[--save DIR] [--save-all] [--header]\n"
            "       pq_bench --write-vectors FILE | --pors-prob MILLIONS\n"
            "ops: slh_dsa_{keygen,sign,verify} sphincs40_{keygen,sign,verify} "
            "shrincs_{keygen,sign,selftest,verify,sign_stateless,verify_stateless} "
            "xmss_{keygen,sign,selftest,verify} mldsa{44,65,87}[_lowram]_{keygen,sign,verify} "
            "fndsa{512,1024}_{keygen,sign,verify}\n");
    exit(2);
}

int main(int argc, char** argv)
{
    const char* board = NULL;
    const char* build = NULL;
    const char* op = NULL;
    const char* save_dir = NULL;
    const char* vectors_out = NULL;
    unsigned long pors_millions = 0;
    unsigned long pors_start = 0;
    int runs = 1;
    unsigned long swn = 2040;
    int header = 0;
    int save_all = 0;

    static const struct option opts[] = {
        { "board", required_argument, 0, 'b' },  { "build", required_argument, 0, 'B' },
        { "op", required_argument, 0, 'o' },     { "swn", required_argument, 0, 's' },
        { "save", required_argument, 0, 'S' },   { "header", no_argument, 0, 'h' },
        { "save-all", no_argument, 0, 'A' },     { "write-vectors", required_argument, 0, 'W' },
        { "pors-prob", required_argument, 0, 'P' },
        { 0, 0, 0, 0 },
    };
    int c;
    while ((c = getopt_long(argc, argv, "n:", opts, NULL)) != -1) {
        switch (c) {
        case 'b': board = optarg; break;
        case 'B': build = optarg; break;
        case 'o': op = optarg; break;
        case 's': swn = strtoul(optarg, NULL, 10); break;
        case 'S': save_dir = optarg; break;
        case 'h': header = 1; break;
        case 'A': save_all = 1; break;
        case 'W': vectors_out = optarg; break;
        case 'P': {
            char* end = NULL;
            pors_millions = strtoul(optarg, &end, 10);
            if (end && *end == ':') {
                pors_start = strtoul(end + 1, NULL, 10);
            }
            break;
        }
        case 'n': runs = atoi(optarg); break;
        default: usage();
        }
    }
    if (vectors_out) {
        return pqb_write_vectors(vectors_out) ? 0 : 1;
    }
    if (pors_millions) {
        return pqb_pors_prob(pors_millions, pors_start) ? 0 : 1;
    }
    if (!board || !build || !op || runs < 1) {
        usage();
    }
    if (header) {
        printf("board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,"
               "stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind\n");
    }

    int failures = 0;
    for (int x = 0; x < runs; x++) {
        op_result_t r;
        memset(&r, 0, sizeof(r));
        char stack_col[24] = "";
        char heap_col[24] = "";
#ifdef PQB_MEM
        pqb_mem_t mem;
        const int handled = pqb_mem_run(op, (uint32_t)x, (uint32_t)swn, &r, &mem);
        snprintf(stack_col, sizeof(stack_col), "%lu", (unsigned long)mem.stack_peak);
        snprintf(heap_col, sizeof(heap_col), "%lu", (unsigned long)mem.heap_peak);
#else
        const int handled = run_op(op, (uint32_t)x, (uint32_t)swn, &r);
#endif
        if (handled != 1) {
            fprintf(stderr, "unknown op or error: %s\n", op);
            return 2;
        }

        uint8_t h[SHA256_DIGEST_LENGTH];
        SHA256(r.out, r.out_len, h);
        char hex[2 * SHA256_DIGEST_LENGTH + 1];
        for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
            sprintf(hex + 2 * i, "%02x", h[i]);
        }
        const int has_swn = op_uses_swn(op);
        char swn_col[16] = "";
        if (has_swn) {
            snprintf(swn_col, sizeof(swn_col), "%lu", swn);
        }
        printf("%s,%s,%s,%s,%d,%.6f,%.6f,%zu,%s,%d,%s,%s,,%s\n", board, build, op, swn_col, x,
               r.wall_s, r.cpu_s, r.out_len, hex, r.verified, stack_col, heap_col, r.grind);
        fflush(stdout);
        if (r.verified == 0) {
            failures++;
        }

        if (save_dir && (x == 0 || save_all)) {
            char path[512];
            if (has_swn) {
                snprintf(path, sizeof(path), "%s/%s_swn%lu_run%d.bin", save_dir, op, swn, x);
            } else {
                snprintf(path, sizeof(path), "%s/%s_run%d.bin", save_dir, op, x);
            }
            FILE* f = fopen(path, "wb");
            if (f) {
                fwrite(r.out, 1, r.out_len, f);
                fclose(f);
            }
        }
        free(r.out);
    }
    return failures ? 1 : 0;
}
