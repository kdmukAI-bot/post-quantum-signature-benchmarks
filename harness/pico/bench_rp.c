/*
 * Pico SDK entry point for the shared benchmark (harness/common) on the Waveshare RP2350
 * Touch LCD 2, a port of harness/esp-idf/main/bench_esp.c with the same console protocol,
 * job sets, and CSV columns, so the ESP32 run scripts, scripts/check_r2.py, and the
 * analysis read its logs unchanged. The console is the SDK's stdio over USB CDC. After
 * boot the app prints "#ready: send 'run <set> [n]'" once a second and waits for a
 * command line; it then runs that job set, prints CSV, prints "#done", and waits for the
 * next command.
 *
 * Job sets (n defaults to PQB_RUNS): r1, verify, stateless, lattice, smoke, as in
 * bench_esp.c; microbenchmark builds (PQB_MICROBENCH) add "microbench" and "mbops".
 *
 * Each run executes in a fresh FreeRTOS task pinned to core 0 (priority 5, as on the
 * ESP32 boards), so the task's stack high-water mark is that run's peak stack use;
 * printing happens in the console task. The task stack sizes are the ESP32 harness's, in
 * bytes.
 *
 * CSV columns: board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,
 *              stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind
 *   wall_s, cpu_s        time_us_64() around the library call (harness/common/common.c);
 *                        CPU time is reported equal to wall time, as on the ESP32 boards
 *   stack_peak_bytes     the run task's stack size minus its high-water mark (FreeRTOS
 *                        fills each new task's stack with a known byte)
 *   heap_peak_bytes      FreeRTOS heap free at the start of the run minus the lowest free
 *                        level during it (harness buffers and, in two-core builds, the
 *                        stacks and control blocks of Blockstream's helper tasks)
 *   heap_min_free_bytes  that lowest free level
 * Lines starting with '#' carry environment details.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "hardware/clocks.h"
#include "hardware/structs/qmi.h"
#include "hardware/structs/sysinfo.h"
#include "mbedtls/sha256.h"
#include "pico/stdlib.h"
#include "pico/version.h"

#include "common.h"
#include "pqb_rp_alloc.h"
#include "pqb_rp_fault.h"

#ifdef PQB_MICROBENCH
void pqb_microbench(const char* set);
#endif

#define STACK_HBS (48 * 1024)
/* The ESP32 harness's lattice stack sizes (bench_esp.c): host peaks plus a margin */
#define PQB_STACK_MLDSA44 (72 * 1024)
#define PQB_STACK_MLDSA65 (96 * 1024)
#define PQB_STACK_MLDSA87 (136 * 1024)
#define PQB_STACK_LOWRAM (40 * 1024)
#define PQB_STACK_FNDSA512 (52 * 1024)
#define PQB_STACK_FNDSA1024 (84 * 1024)

#if defined(SHRINCS_L)
#define PQB_SWN 140
#else
#define PQB_SWN 2040
#endif

#ifndef PQB_LTO
#define PQB_LTO 0
#endif

typedef struct {
    const char* op;
    uint32_t swn;
    uint32_t stack_bytes;
} job_t;

#if defined(SHRINCS_L)
static const job_t JOBS_R1[] = {
    { "shrincs_selftest", 140, STACK_HBS },
    { "shrincs_sign", 96, STACK_HBS },
    { "shrincs_sign", 140, STACK_HBS },
    { "shrincs_keygen", 0, STACK_HBS },
};
static const job_t JOBS_VERIFY[] = {
    { "shrincs_verify", PQB_SWN, STACK_HBS },
    { "shrincs_verify_stateless", PQB_SWN, STACK_HBS },
};
#else
static const job_t JOBS_R1[] = {
    { "shrincs_selftest", 2040, STACK_HBS },
    { "xmss_selftest", 0, STACK_HBS },
    { "slh_dsa_sign", 0, STACK_HBS },
    { "sphincs40_sign", 0, STACK_HBS },
    { "shrincs_sign", 2040, STACK_HBS },
    { "xmss_sign", 0, STACK_HBS },
    { "slh_dsa_keygen", 0, STACK_HBS },
    { "sphincs40_keygen", 0, STACK_HBS },
    { "shrincs_keygen", 0, STACK_HBS },
    { "xmss_keygen", 0, STACK_HBS },
};
static const job_t JOBS_VERIFY[] = {
    { "slh_dsa_verify", 0, STACK_HBS },
    { "sphincs40_verify", 0, STACK_HBS },
    { "shrincs_verify", PQB_SWN, STACK_HBS },
    { "shrincs_verify_stateless", PQB_SWN, STACK_HBS },
    { "xmss_verify", 0, STACK_HBS },
};
#endif

static const job_t JOBS_STATELESS[] = {
    { "shrincs_sign_stateless", PQB_SWN, STACK_HBS },
};

static const job_t JOBS_LATTICE[] = {
    { "mldsa44_keygen", 0, PQB_STACK_MLDSA44 },
    { "mldsa44_sign", 0, PQB_STACK_MLDSA44 },
    { "mldsa44_verify", 0, PQB_STACK_MLDSA44 },
    { "mldsa65_keygen", 0, PQB_STACK_MLDSA65 },
    { "mldsa65_sign", 0, PQB_STACK_MLDSA65 },
    { "mldsa65_verify", 0, PQB_STACK_MLDSA65 },
    { "mldsa87_keygen", 0, PQB_STACK_MLDSA87 },
    { "mldsa87_sign", 0, PQB_STACK_MLDSA87 },
    { "mldsa87_verify", 0, PQB_STACK_MLDSA87 },
    { "mldsa44_lowram_keygen", 0, PQB_STACK_LOWRAM },
    { "mldsa44_lowram_sign", 0, PQB_STACK_LOWRAM },
    { "mldsa44_lowram_verify", 0, PQB_STACK_LOWRAM },
    { "mldsa65_lowram_keygen", 0, PQB_STACK_LOWRAM },
    { "mldsa65_lowram_sign", 0, PQB_STACK_LOWRAM },
    { "mldsa65_lowram_verify", 0, PQB_STACK_LOWRAM },
    { "mldsa87_lowram_keygen", 0, PQB_STACK_LOWRAM },
    { "mldsa87_lowram_sign", 0, PQB_STACK_LOWRAM },
    { "mldsa87_lowram_verify", 0, PQB_STACK_LOWRAM },
    { "fndsa512_keygen", 0, PQB_STACK_FNDSA512 },
    { "fndsa512_sign", 0, PQB_STACK_FNDSA512 },
    { "fndsa512_verify", 0, PQB_STACK_FNDSA512 },
    { "fndsa1024_keygen", 0, PQB_STACK_FNDSA1024 },
    { "fndsa1024_sign", 0, PQB_STACK_FNDSA1024 },
    { "fndsa1024_verify", 0, PQB_STACK_FNDSA1024 },
};

typedef struct {
    const char* name;
    const job_t* jobs;
    size_t count;
} job_set_t;

#define SET(name, arr) { name, arr, sizeof(arr) / sizeof(arr[0]) }
static const job_set_t SETS[] = {
    SET("r1", JOBS_R1),
    SET("verify", JOBS_VERIFY),
    SET("stateless", JOBS_STATELESS),
    SET("lattice", JOBS_LATTICE),
};

typedef struct {
    const job_t* job;
    uint32_t x;
    op_result_t r;
    int handled;
    unsigned stack_peak;
    size_t heap_free_before;
    size_t heap_min_free;
    SemaphoreHandle_t done;
} run_ctx_t;

static void run_task(void* arg)
{
    run_ctx_t* c = (run_ctx_t*)arg;
    pqb_current_op = c->job->op;
    c->heap_free_before = pqb_heap_free();
    pqb_heap_monitor_start();
    c->handled = run_op(c->job->op, c->x, c->job->swn, &c->r);
    c->heap_min_free = pqb_heap_monitor_min_free();
    c->stack_peak = c->job->stack_bytes
        - (unsigned)uxTaskGetStackHighWaterMark(NULL) * sizeof(StackType_t);
    xSemaphoreGive(c->done);
    vTaskDelete(NULL);
}

static void run_job(const job_t* job, int runs, const char* board, SemaphoreHandle_t done)
{
    for (int x = 0; x < runs; x++) {
        run_ctx_t c;
        memset(&c, 0, sizeof(c));
        c.job = job;
        c.x = (uint32_t)x;
        c.done = done;
        if (xTaskCreatePinnedToCore(run_task, "pqb_run", job->stack_bytes, &c, 5, NULL, 0)
            != pdPASS) {
            printf("#error,task creation failed (stack %u bytes),%s\n",
                   (unsigned)job->stack_bytes, job->op);
            return;
        }
        xSemaphoreTake(done, portMAX_DELAY);
        vTaskDelay(pdMS_TO_TICKS(50)); /* let the idle task free the finished task */
        if (c.handled != 1) {
            printf("#error,unknown op or failure,%s\n", job->op);
            free(c.r.out);
            return;
        }

        uint8_t h[32];
        mbedtls_sha256(c.r.out, c.r.out_len, h, 0);
        char hex[65];
        for (int i = 0; i < 32; i++) {
            sprintf(hex + 2 * i, "%02x", h[i]);
        }
        char swn_col[16] = "";
        if (op_uses_swn(job->op)) {
            snprintf(swn_col, sizeof(swn_col), "%u", (unsigned)job->swn);
        }
        const size_t heap_peak =
            c.heap_free_before > c.heap_min_free ? c.heap_free_before - c.heap_min_free : 0;
        printf("%s,%s,%s,%s,%d,%.6f,%.6f,%u,%s,%d,%u,%u,%u,%s\n", board, PQB_VARIANT, job->op,
               swn_col, x, c.r.wall_s, c.r.cpu_s, (unsigned)c.r.out_len, hex, c.r.verified,
               c.stack_peak, (unsigned)heap_peak, (unsigned)c.heap_min_free, c.r.grind);
        fflush(stdout);
        free(c.r.out);
    }
}

/* Prints the ready prompt once a second until a full line arrives, then discards any
 * further pending input (the host repeats the command until the run starts). */
static void read_command(char* line, size_t len)
{
    size_t n = 0;
    uint64_t last_prompt = 0;
    int prompted = 0;
    for (;;) {
        const uint64_t now = time_us_64();
        if (!prompted || now - last_prompt >= 1000000) {
            pqb_fault_print();
            printf("#ready: send 'run <r1|verify|stateless|lattice|smoke> [n]'\n");
            fflush(stdout);
            last_prompt = now;
            prompted = 1;
        }
        const int c = getchar_timeout_us(100000);
        if (c == PICO_ERROR_TIMEOUT || c < 0) {
            continue;
        }
        if (c == '\n' || c == '\r') {
            line[n] = 0;
            break;
        }
        if (n + 1 < len) {
            line[n++] = (char)c;
        }
    }
    while (getchar_timeout_us(200000) >= 0) {
    }
    pqb_fault_clear();
}

static void print_env(const char* set, int runs)
{
    const unsigned pkg = sysinfo_hw->package_sel & 1u;
    const unsigned clkdiv =
        (qmi_hw->m[0].timing & QMI_M0_TIMING_CLKDIV_BITS) >> QMI_M0_TIMING_CLKDIV_LSB;
    printf("#env,target=rp2350,chip_rev=A%u,package=%s,cores=2,cpu_mhz=%u,"
           "sdk=%s,freertos=%s,tick_hz=%u,flash_clkdiv=%u,variant=%s,runs=%d,opt=%s,lto=%d,"
           "placement=%s,wdt_ms=%d,boot_after_watchdog=%d,set=%s,heap_free_internal=%u,"
           "heap_largest_internal=%u\n",
           (unsigned)rp2350_chip_version(), pkg ? "QFN60" : "QFN80",
           (unsigned)(clock_get_hz(clk_sys) / 1000000), PICO_SDK_VERSION_STRING,
           tskKERNEL_VERSION_NUMBER, (unsigned)configTICK_RATE_HZ, clkdiv, PQB_VARIANT, runs,
           PQB_OPT_STR, PQB_LTO, PQB_PLACEMENT_STR, PQB_WDT_MS, pqb_fault_watchdog_reboot(),
           set, (unsigned)pqb_heap_free(),
           (unsigned)pqb_heap_largest_free_block());
    printf("board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,"
           "stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind\n");
    fflush(stdout);
}

static void main_task(void* arg)
{
    (void)arg;
    SemaphoreHandle_t done = xSemaphoreCreateBinary();
    const char* board = "rp2350";

    for (;;) {
        char line[160];
        read_command(line, sizeof(line));
        char set[24] = "r1";
        int runs = PQB_RUNS;
        if (line[0]) {
            /* parse from the last "run " in the line (the host tty may echo the
             * prompt) */
            const char* cmd = line;
            for (const char* p = strstr(line, "run "); p; p = strstr(p + 1, "run ")) {
                cmd = p;
            }
            char word[8] = "";
            int n = 0;
            const int got = sscanf(cmd, "%7s %23s %d", word, set, &n);
            if (got < 2 || strcmp(word, "run")) {
                printf("#error,bad command,%s\n", line);
                continue;
            }
            if (got == 3 && n > 0) {
                runs = n;
            }
        }
#ifdef PQB_MICROBENCH
        if (!strncmp(set, "mb", 2) || !strcmp(set, "microbench")) {
            print_env(set, 0);
            pqb_microbench(set);
            printf("#done\n");
            fflush(stdout);
            continue;
        }
#endif
        const int smoke = !strcmp(set, "smoke");
        int found = smoke;
        print_env(set, smoke ? 1 : runs);
        for (size_t s = 0; s < sizeof(SETS) / sizeof(SETS[0]); s++) {
            const job_set_t* js = &SETS[s];
            if (smoke ? !strcmp(js->name, "r1") : strcmp(js->name, set)) {
                continue;
            }
            found = 1;
            for (size_t i = 0; i < js->count; i++) {
                run_job(&js->jobs[i], smoke ? 1 : runs, board, done);
            }
        }
        if (!found) {
            printf("#error,unknown job set,%s\n", set);
        }
        printf("#done\n");
        fflush(stdout);
    }
}

int main(void)
{
    stdio_init_all();
    pqb_fault_boot();
    /* The console task runs on core 0 at priority 1, as ESP-IDF's main task does. */
    xTaskCreatePinnedToCore(main_task, "pqb_main", 8192, NULL, 1, NULL, 0);
    vTaskStartScheduler();
    for (;;) {
    }
}
