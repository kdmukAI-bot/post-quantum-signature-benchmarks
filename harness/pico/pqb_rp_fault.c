/*
 * Fault recovery for unattended runs on the Waveshare RP2350 Touch LCD 2, the counterpart
 * of ESP-IDF's default panic handler and interrupt watchdog on the ESP32 boards:
 *
 *   - The hardware watchdog (5 s) is fed from the FreeRTOS tick hook, which runs in the
 *     tick interrupt on core 0. A busy task never starves it; it fires only when core 0
 *     stops taking interrupts (a fault, a lockup, or a deadlock with interrupts masked).
 *     The board then reboots into the app, so no button press is needed. A loop with
 *     interrupts enabled keeps the USB reset interface working (picotool reboot -f -u).
 *   - The HardFault handler and the FreeRTOS failure hooks (stack overflow, assertion,
 *     allocation failure) record what happened in RAM that the boot code does not clear,
 *     and reboot through the watchdog at once. After the reboot the app prints the record
 *     as a "#fault" line with every "#ready" prompt until it receives a command.
 *
 * Cost during timed code: one register write per 10 ms tick.
 */
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "hardware/structs/m33.h"
#include "hardware/watchdog.h"
#include "pico/platform.h"
#include "pico/stdlib.h"

#include "pqb_rp_fault.h"

#define PQB_FAULT_MAGIC 0x50514246u /* "PQBF" */

typedef struct {
    uint32_t magic;
    uint32_t kind;
    uint32_t core;
    uint32_t pc, lr, psr, sp;
    uint32_t cfsr, hfsr, mmfar, bfar;
    char op[40];
    char text[64];
} pqb_fault_t;

static pqb_fault_t __uninitialized_ram(s_fault);
static pqb_fault_t s_last; /* the record found at boot, printed until the first command */
static int s_have_last;
static int s_wdt_reboot;

volatile const char* pqb_current_op = "";

static const char* const KIND[] = { "none", "hardfault", "stack_overflow", "rtos_assert",
                                    "malloc_failed" };

static void copy_str(char* dst, size_t n, const volatile char* src)
{
    size_t i = 0;
    if (src) {
        for (; i + 1 < n && src[i]; i++) {
            dst[i] = src[i];
        }
    }
    dst[i] = 0;
}

static void __attribute__((noreturn)) record_and_reboot(uint32_t kind, const char* text)
{
    s_fault.kind = kind;
    s_fault.core = get_core_num();
    copy_str(s_fault.op, sizeof(s_fault.op), pqb_current_op);
    copy_str(s_fault.text, sizeof(s_fault.text), text);
    s_fault.magic = PQB_FAULT_MAGIC;
    __dsb();
    watchdog_reboot(0, 0, 10);
    for (;;) {
        __nop();
    }
}

void __attribute__((used, noreturn)) pqb_hardfault_c(uint32_t* frame)
{
    s_fault.pc = frame[6];
    s_fault.lr = frame[5];
    s_fault.psr = frame[7];
    s_fault.sp = (uint32_t)frame;
    s_fault.cfsr = m33_hw->cfsr;
    s_fault.hfsr = m33_hw->hfsr;
    s_fault.mmfar = m33_hw->mmfar;
    s_fault.bfar = m33_hw->bfar;
    record_and_reboot(1, "");
}

/* Replaces the SDK's default (a breakpoint): passes the stacked frame to the C
 * handler. */
void __attribute__((naked)) isr_hardfault(void)
{
    __asm volatile("tst lr, #4\n"
                   "ite eq\n"
                   "mrseq r0, msp\n"
                   "mrsne r0, psp\n"
                   "b pqb_hardfault_c\n");
}

void vApplicationStackOverflowHook(TaskHandle_t task, char* name)
{
    (void)task;
    memset(&s_fault, 0, sizeof(s_fault));
    record_and_reboot(2, name);
}

void pqb_rtos_assert_failed(const char* file, int line)
{
    char t[64];
    snprintf(t, sizeof(t), "%s:%d", file, line);
    memset(&s_fault, 0, sizeof(s_fault));
    record_and_reboot(3, t);
}

void vApplicationMallocFailedHook(void)
{
    char t[64];
    snprintf(t, sizeof(t), "free %u", (unsigned)xPortGetFreeHeapSize());
    memset(&s_fault, 0, sizeof(s_fault));
    record_and_reboot(4, t);
}

void vApplicationTickHook(void) { watchdog_update(); }

void pqb_fault_boot(void)
{
    s_wdt_reboot = watchdog_caused_reboot();
    if (s_fault.magic == PQB_FAULT_MAGIC) {
        s_last = s_fault;
        s_have_last = 1;
    }
    memset(&s_fault, 0, sizeof(s_fault));
    watchdog_enable(PQB_WDT_MS, true);
}

void pqb_fault_print(void)
{
    if (!s_have_last) {
        return;
    }
    const pqb_fault_t* f = &s_last;
    printf("#fault,kind=%s,core=%u,op=%s,text=%s,pc=0x%08x,lr=0x%08x,psr=0x%08x,sp=0x%08x,"
           "cfsr=0x%08x,hfsr=0x%08x,mmfar=0x%08x,bfar=0x%08x,watchdog_reboot=%d\n",
           f->kind < 5 ? KIND[f->kind] : "?", (unsigned)f->core, f->op, f->text,
           (unsigned)f->pc, (unsigned)f->lr, (unsigned)f->psr, (unsigned)f->sp,
           (unsigned)f->cfsr, (unsigned)f->hfsr, (unsigned)f->mmfar, (unsigned)f->bfar,
           s_wdt_reboot);
}

void pqb_fault_clear(void) { s_have_last = 0; }

int pqb_fault_watchdog_reboot(void) { return s_wdt_reboot; }
