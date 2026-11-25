/* Stand-in for FreeRTOS's task.h in the two-core Linux builds (make DUAL_CORE=1). It
 * provides the task calls that Blockstream's two-core code paths make (slh_dsa.c and
 * wots_c.c, with their single-core defines removed from the build copies), implemented
 * over POSIX threads in freertos_pthread.c:
 *
 *   xTaskCreatePinnedToCore  starts a detached thread that runs the task function. The
 *                            core argument is not mapped to a Linux CPU: the Linux
 *                            scheduler places the threads (the Pi Zero 2 W has four
 *                            cores, and with the SeedSigner app stopped at least three
 *                            are idle). Stack size and priority are ignored.
 *   vTaskDelete(NULL)        ends the calling thread (the task functions end this way)
 *   xTaskGetCurrentTaskHandle, xTaskNotifyGive, ulTaskNotifyTake
 *                            a notification count per thread, guarded by a mutex and a
 *                            condition variable; ulTaskNotifyTake waits until the count
 *                            is nonzero (the timeout is ignored: Jade passes
 *                            portMAX_DELAY), so the mutex orders the secondary's writes
 *                            before the primary's reads, as FreeRTOS does
 *   vTaskDelay               no operation, as in the one-core stand-in: Jade calls it to
 *                            let the ESP32 idle task feed the watchdog, which a Linux
 *                            process does not need
 */
#ifndef PQB_SHIM_DUALCORE_TASK_H
#define PQB_SHIM_DUALCORE_TASK_H

#include "freertos/FreeRTOS.h"

typedef struct pqb_task* TaskHandle_t;
typedef void (*TaskFunction_t)(void*);

BaseType_t xTaskCreatePinnedToCore(TaskFunction_t fn, const char* name, uint32_t stack_bytes,
                                   void* arg, UBaseType_t priority, TaskHandle_t* created,
                                   BaseType_t core);
void vTaskDelete(TaskHandle_t task);
TaskHandle_t xTaskGetCurrentTaskHandle(void);
BaseType_t xTaskNotifyGive(TaskHandle_t task);
uint32_t ulTaskNotifyTake(BaseType_t clear_on_exit, TickType_t ticks_to_wait);

static inline void vTaskDelay(TickType_t ticks) { (void)ticks; }

#endif
