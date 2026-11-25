#ifndef PQ_BENCH_COMMON_H
#define PQ_BENCH_COMMON_H

#include <stddef.h>
#include <stdint.h>

/* One benchmarked operation. Only the core library call is timed; key decoding and
 * verification happen outside the timed section. */
typedef struct {
    double wall_s;
    double cpu_s;
    uint8_t* out; /* malloc'd; the bytes Jade would return for the same RPC */
    size_t out_len;
    int verified; /* 1 = verified, 0 = verification FAILED, -1 = not applicable */
    /* Grinding counters read from the output, outside the timed section, for the
     * per-message expected-value fits ("" if none). Semicolon-separated key=value pairs:
     * wots=C (SHRINCS stateful: the WOTS+C counter found), pors=C;wots0=C;wots1=C
     * (SHRINCS stateless: the PORS+FP counter and the two hypertree layers' WOTS+C
     * counters), attempts=A (ML-DSA signing in the host counting build only). */
    char grind[64];
} op_result_t;

typedef struct {
    double wall0, cpu0;
} op_timer_t;

/* Called just before and after the core library call of SLH-DSA operations, inside the
 * timed section. No-ops by default; the ESP hardware-SHA build uses them to hold the SHA
 * engine for the whole operation instead of locking it per compression. */
void pqb_core_begin(void);
void pqb_core_end(void);
/* The same, around the core calls of SHRINCS and XMSS operations (which hash through the
 * mbedTLS SHA-256 API). Used only by ESP builds that replace mbedTLS with direct SHA. */
void pqb_mbedtls_core_begin(void);
void pqb_mbedtls_core_end(void);

void timer_start(op_timer_t* t);
void timer_stop(const op_timer_t* t, op_result_t* r);
void hex_to_bytes(const char* hex, uint8_t* out, size_t out_len);
/* Jade's test script uses x.to_bytes(32, "big") for both messages and keygen seeds. */
void run_input(uint32_t x, uint8_t out[32]);

/* Each returns 1 if it handled the op, 0 if the op is not one of its own, -1 on error. */
int run_slh_op(const char* op, uint32_t x, op_result_t* r);
int run_shrincs_op(const char* op, uint32_t x, uint32_t swn, op_result_t* r);
int run_xmss_op(const char* op, uint32_t x, op_result_t* r);
int run_mldsa_op(const char* op, uint32_t x, op_result_t* r);
int run_fndsa_op(const char* op, uint32_t x, op_result_t* r);
/* Tries every module above; same return convention. */
int run_op(const char* op, uint32_t x, uint32_t swn, op_result_t* r);
/* 1 if the op's swn column is filled (SHRINCS signing and verification). */
int op_uses_swn(const char* op);

/* Verification inputs (keys and signatures) made by the host harness (gen_vectors.c) and
 * embedded in every build (vectors.c, vectors_blob.c). Verify ops for run x use message
 * x % PQB_VEC_N. */
#define PQB_VEC_N 10
/* The record named name, or the record name/idx when idx >= 0. Returns NULL (and an error
 * on stderr) if the build has no vectors or no such record. */
const uint8_t* pqb_vec(const char* name, int idx, size_t* len);
/* A malloc'd copy of the same record (so timed code reads RAM, not flash), or NULL. */
uint8_t* pqb_vec_copy(const char* name, int idx, size_t* len);
/* Writes the vector blob for this build's SHRINCS variant (host builds only). */
int pqb_write_vectors(const char* path);

#endif
