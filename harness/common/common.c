#include "common.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef ESP_PLATFORM
#include "esp_timer.h"

/* No per-process CPU clock on FreeRTOS; the benchmark task is the only busy task, so CPU
 * time is reported equal to wall time. */
void timer_start(op_timer_t* t)
{
    t->wall0 = (double)esp_timer_get_time() * 1e-6;
    t->cpu0 = t->wall0;
}

void timer_stop(const op_timer_t* t, op_result_t* r)
{
    r->wall_s = (double)esp_timer_get_time() * 1e-6 - t->wall0;
    r->cpu_s = r->wall_s;
}
#else
#include <time.h>

static double clock_s(clockid_t id)
{
    struct timespec ts;
    clock_gettime(id, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

void timer_start(op_timer_t* t)
{
    t->cpu0 = clock_s(CLOCK_PROCESS_CPUTIME_ID);
    t->wall0 = clock_s(CLOCK_MONOTONIC);
}

void timer_stop(const op_timer_t* t, op_result_t* r)
{
    r->wall_s = clock_s(CLOCK_MONOTONIC) - t->wall0;
    r->cpu_s = clock_s(CLOCK_PROCESS_CPUTIME_ID) - t->cpu0;
}
#endif

__attribute__((weak)) void pqb_core_begin(void) { }
__attribute__((weak)) void pqb_core_end(void) { }
__attribute__((weak)) void pqb_mbedtls_core_begin(void) { }
__attribute__((weak)) void pqb_mbedtls_core_end(void) { }

void hex_to_bytes(const char* hex, uint8_t* out, size_t out_len)
{
    if (strlen(hex) != 2 * out_len) {
        fprintf(stderr, "hex_to_bytes: expected %u hex chars\n", (unsigned)(2 * out_len));
        abort();
    }
    for (size_t i = 0; i < out_len; i++) {
        unsigned int b;
        sscanf(hex + 2 * i, "%2x", &b);
        out[i] = (uint8_t)b;
    }
}

void run_input(uint32_t x, uint8_t out[32])
{
    memset(out, 0, 32);
    out[28] = (uint8_t)(x >> 24);
    out[29] = (uint8_t)(x >> 16);
    out[30] = (uint8_t)(x >> 8);
    out[31] = (uint8_t)x;
}

int run_op(const char* op, uint32_t x, uint32_t swn, op_result_t* r)
{
    int handled = run_slh_op(op, x, r);
    if (!handled) {
        handled = run_shrincs_op(op, x, swn, r);
    }
    if (!handled) {
        handled = run_xmss_op(op, x, r);
    }
    if (!handled) {
        handled = run_mldsa_op(op, x, r);
    }
    if (!handled) {
        handled = run_fndsa_op(op, x, r);
    }
    return handled;
}

int op_uses_swn(const char* op)
{
    return !strcmp(op, "shrincs_sign") || !strcmp(op, "shrincs_sign_stateless")
        || !strcmp(op, "shrincs_verify") || !strcmp(op, "shrincs_verify_stateless");
}
