/*
 * ESP-IDF entry point for the shared benchmark (harness/common). After boot it prints
 * "#ready: send 'run <set> [n]'" once a second and waits for a command line on the
 * console; it then runs that job set, prints CSV, prints "#done", and waits for the next
 * command. An empty line runs the round-1 set with PQB_RUNS runs per op.
 *
 * Job sets (n defaults to PQB_RUNS):
 *   r1         the round-1 job list of this build's SHRINCS variant (self-tests, signing,
 *              key generation)
 *   verify     verification: SHRINCS stateful and stateless; in SHRINCS-B builds also
 *              SLH-DSA-SHA2-128s, SPHINCS+ 2^40, and XMSS 2^10
 *   stateless  SHRINCS stateless signing at swn = SWN
 *   lattice    ML-DSA-44/65/87 (default and reduced-RAM builds of mldsa-native) and
 *              FN-DSA-512/1024: key generation, signing, verification
 *   smoke      every op of verify, lattice, and stateless, one run each
 *
 * Each run executes in a fresh task, so the task's stack high-water mark is that run's
 * peak stack use, and the printing (which uses stack of its own) happens in app_main.
 *
 * CSV columns: board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,
 *              stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind
 *   stack_peak_bytes     peak stack of the run's task (task stack size minus high-water
 *                        mark): the op, the harness's untimed work around it, and the
 *                        task's own frame
 *   heap_peak_bytes      internal-RAM heap free at the start of the run minus the lowest
 *                        free level during it (includes the harness's buffers and, in
 *                        dual-core builds, the stacks of Blockstream's helper tasks)
 *   heap_min_free_bytes  that lowest free level
 * Lines starting with '#' carry environment details.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_chip_info.h"
#include "esp_clk_tree.h"
#include "esp_heap_caps.h"
#include "esp_idf_version.h"
#include "esp_private/esp_clk.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "sdkconfig.h"
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#else
#include "driver/uart.h"
#include "driver/uart_vfs.h"
#endif

#include "common.h"
#ifdef PQB_MICROBENCH
#include "sha256_mb.h"
#endif

/* Task stack per run. 48 KiB for the hash-based ops, as in round 1. The lattice ops get
 * what their peak use on the host needs plus a margin. */
#define STACK_HBS (48 * 1024)
/* Measured on the x86-64 host (harness/linux MEM=1 build, -O2): ML-DSA-44/65/87 signing
 * 52.4, 75.8, 113.6 KiB; reduced-RAM signing at most 23.0 KiB; FN-DSA-512/1024 signing
 * 33.2 and 63.5 KiB. Each size adds about 16 KiB or more for other compilers, -O3, and
 * frames. */
#ifndef PQB_STACK_MLDSA44
#define PQB_STACK_MLDSA44 (72 * 1024)
#endif
#ifndef PQB_STACK_MLDSA65
#define PQB_STACK_MLDSA65 (96 * 1024)
#endif
#ifndef PQB_STACK_MLDSA87
#define PQB_STACK_MLDSA87 (136 * 1024)
#endif
#ifndef PQB_STACK_LOWRAM
#define PQB_STACK_LOWRAM (40 * 1024)
#endif
#ifndef PQB_STACK_FNDSA512
#define PQB_STACK_FNDSA512 (52 * 1024)
#endif
#ifndef PQB_STACK_FNDSA1024
#define PQB_STACK_FNDSA1024 (84 * 1024)
#endif

#if defined(SHRINCS_L)
#define PQB_SWN 140
#else
#define PQB_SWN 2040
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
    c->heap_free_before = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    heap_caps_monitor_local_minimum_free_size_start();
    c->handled = run_op(c->job->op, c->x, c->job->swn, &c->r);
    c->heap_min_free = heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL);
    heap_caps_monitor_local_minimum_free_size_stop();
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

static void console_init(void)
{
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    usb_serial_jtag_driver_install(&cfg);
    usb_serial_jtag_vfs_use_driver();
#else
    uart_driver_install(CONFIG_ESP_CONSOLE_UART_NUM, 512, 0, 0, NULL, 0);
    uart_vfs_dev_use_driver(CONFIG_ESP_CONSOLE_UART_NUM);
#endif
}

static int console_read(uint8_t* c, int timeout_ms)
{
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
    return usb_serial_jtag_read_bytes(c, 1, pdMS_TO_TICKS(timeout_ms));
#else
    return uart_read_bytes(CONFIG_ESP_CONSOLE_UART_NUM, c, 1, pdMS_TO_TICKS(timeout_ms));
#endif
}

/* Prints the ready prompt once a second until a full line arrives, then discards any
 * further pending input (the host repeats the command until the run starts). */
static void read_command(char* line, size_t len)
{
    size_t n = 0;
    int64_t last_prompt = -1000000;
    for (;;) {
        const int64_t now = esp_timer_get_time();
        if (now - last_prompt >= 1000000) {
            printf("#ready: send 'run <r1|verify|stateless|lattice|smoke> [n]'\n");
            fflush(stdout);
            last_prompt = now;
        }
        uint8_t c = 0;
        if (console_read(&c, 100) != 1) {
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
    uint8_t c;
    while (console_read(&c, 200) == 1) {
    }
}

static void print_env(const char* set, int runs)
{
    esp_chip_info_t chip;
    esp_chip_info(&chip);
    printf("#env,target=%s,chip_rev=v%d.%d,cores=%d,cpu_mhz=%d,idf=%s,variant=%s,runs=%d,"
           "jade_sha_semantics=%d,opt=%s,set=%s,heap_free_internal=%u,heap_largest_internal=%u\n",
           CONFIG_IDF_TARGET, chip.revision / 100, chip.revision % 100, chip.cores,
           esp_clk_cpu_freq() / 1000000, esp_get_idf_version(), PQB_VARIANT, runs,
#ifdef PQB_JADE_SHA_SEMANTICS
           1,
#else
           0,
#endif
#if CONFIG_COMPILER_OPTIMIZATION_PERF
           "O2",
#elif CONFIG_COMPILER_OPTIMIZATION_SIZE
           "Os",
#else
           "other",
#endif
           set, (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
           (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));
    printf("board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,"
           "stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind\n");
    fflush(stdout);
}

void app_main(void)
{
    console_init();
    SemaphoreHandle_t done = xSemaphoreCreateBinary();
    const char* board = CONFIG_IDF_TARGET;

#ifdef PQB_MICROBENCH
    vTaskDelay(pdMS_TO_TICKS(3000));
    print_env("microbench", 0);
    pqb_microbench(); /* microbenchmark build: no benchmark jobs */
    printf("#done\n");
    fflush(stdout);
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
#endif

    for (;;) {
        char line[160];
        read_command(line, sizeof(line));
        char set[24] = "r1";
        int runs = PQB_RUNS;
        if (line[0]) {
            /* Before the host's serial library takes the port, the host tty may echo the
             * prompt back, so parse from the last "run " in the line. */
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
