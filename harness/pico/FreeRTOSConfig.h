/*
 * FreeRTOS configuration for harness/pico (FreeRTOS SMP on both Cortex-M33 cores of the
 * RP2350, raspberrypi/FreeRTOS-Kernel's RP2350_ARM_NTZ port). Based on pico-examples'
 * FreeRTOSConfig_examples_common.h; where the ESP32 harness relies on an ESP-IDF default
 * that affects the benchmark, the same value is used here:
 *
 *   tick rate 100 Hz            ESP-IDF CONFIG_FREERTOS_HZ=100. Jade's grinding loops
 *                               call vTaskDelay(1) every 100,000 attempts, which waits
 *                               for the next tick, so the tick rate is part of the
 *                               measured time.
 *   stack overflow check 2      ESP-IDF's default canary check
 *                               (CONFIG_FREERTOS_CHECK_STACKOVERFLOW_CANARY). The port
 *                               also sets each task's PSPLIM, so the Cortex-M33 faults
 *                               when a task's stack pointer leaves its stack.
 *   trace facility on           as the ESP32 harness's sdkconfig.defaults
 *
 * Heap: heap_4 over a static array of PQB_HEAP_KB KiB. Task stacks and the harness's
 * buffers come from it (pqb_rp_alloc.h); traceMALLOC records the lowest free level for
 * the per-run heap peak, as ESP-IDF's heap_caps_monitor_local_minimum_free_size does.
 */
#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

/* Scheduler */
#define configUSE_PREEMPTION 1
#define configUSE_TICKLESS_IDLE 0
#define configUSE_IDLE_HOOK 0
#define configUSE_TICK_HOOK 1 /* feeds the hardware watchdog (pqb_rp_fault.c) */
#define configTICK_RATE_HZ ((TickType_t)100)
#define configMAX_PRIORITIES 25
#define configMINIMAL_STACK_SIZE ((configSTACK_DEPTH_TYPE)512)
#define configUSE_16_BIT_TICKS 0
#define configIDLE_SHOULD_YIELD 1

/* Synchronization */
#define configUSE_MUTEXES 1
#define configUSE_RECURSIVE_MUTEXES 1
#define configUSE_APPLICATION_TASK_TAG 0
#define configUSE_COUNTING_SEMAPHORES 1
#define configQUEUE_REGISTRY_SIZE 8
#define configUSE_QUEUE_SETS 1
#define configUSE_TIME_SLICING 1
#define configUSE_NEWLIB_REENTRANT 0
#define configENABLE_BACKWARD_COMPATIBILITY 1
#define configNUM_THREAD_LOCAL_STORAGE_POINTERS 5

/* System */
#define configSTACK_DEPTH_TYPE uint32_t
#define configMESSAGE_BUFFER_LENGTH_TYPE size_t

/* Memory */
#define configSUPPORT_STATIC_ALLOCATION 0
#define configSUPPORT_DYNAMIC_ALLOCATION 1
#ifndef PQB_HEAP_KB
#define PQB_HEAP_KB 400
#endif
#define configTOTAL_HEAP_SIZE ((size_t)PQB_HEAP_KB * 1024)
#define configAPPLICATION_ALLOCATED_HEAP 0

/* Hooks */
#define configCHECK_FOR_STACK_OVERFLOW 2
#define configUSE_MALLOC_FAILED_HOOK 1
#define configUSE_DAEMON_TASK_STARTUP_HOOK 0

/* Statistics */
#define configGENERATE_RUN_TIME_STATS 0
#define configUSE_TRACE_FACILITY 1
#define configUSE_STATS_FORMATTING_FUNCTIONS 0

#define configUSE_CO_ROUTINES 0
#define configMAX_CO_ROUTINE_PRIORITIES 1

/* The port's pico_sync interoperation pends work to the timer task
 * (xEventGroupSetBitsFromISR), so the timer task exists; priority 1 and 10 queue entries
 * as ESP-IDF's defaults. No software timers are used. */
#define configUSE_TIMERS 1
#define configTIMER_TASK_PRIORITY 1
#define configTIMER_QUEUE_LENGTH 10
#define configTIMER_TASK_STACK_DEPTH 512

/* SMP port */
#if FREE_RTOS_KERNEL_SMP
#ifndef configNUMBER_OF_CORES
#define configNUMBER_OF_CORES 2
#endif
#define configNUM_CORES configNUMBER_OF_CORES
#define configTICK_CORE 0
#define configRUN_MULTIPLE_PRIORITIES 1
#if configNUMBER_OF_CORES > 1
#define configUSE_CORE_AFFINITY 1
#endif
#define configUSE_PASSIVE_IDLE_HOOK 0
#endif

/* RP2xxx SDK interoperation */
#define configSUPPORT_PICO_SYNC_INTEROP 1
#define configSUPPORT_PICO_TIME_INTEROP 1

#ifndef __ASSEMBLER__
void pqb_rtos_assert_failed(const char* file, int line);
void pqb_heap_note(void);
#endif
#define configASSERT(x)                                                                  \
    do {                                                                                 \
        if (!(x)) {                                                                      \
            pqb_rtos_assert_failed(__FILE__, __LINE__);                                  \
        }                                                                                \
    } while (0)
#define traceMALLOC(pvAddress, uiSize) pqb_heap_note()

#define INCLUDE_vTaskPrioritySet 1
#define INCLUDE_uxTaskPriorityGet 1
#define INCLUDE_vTaskDelete 1
#define INCLUDE_vTaskSuspend 1
#define INCLUDE_vTaskDelayUntil 1
#define INCLUDE_vTaskDelay 1
#define INCLUDE_xTaskGetSchedulerState 1
#define INCLUDE_xTaskGetCurrentTaskHandle 1
#define INCLUDE_uxTaskGetStackHighWaterMark 1
#define INCLUDE_xTaskGetIdleTaskHandle 1
#define INCLUDE_eTaskGetState 1
#define INCLUDE_xTimerPendFunctionCall 1
#define INCLUDE_xTaskAbortDelay 1
#define INCLUDE_xTaskGetHandle 1
#define INCLUDE_xTaskResumeFromISR 1
#define INCLUDE_xQueueGetMutexHolder 1

/* RP2350 Arm, secure only (the SDK's default image type) */
#define configENABLE_MPU 0
#define configENABLE_TRUSTZONE 0
#define configRUN_FREERTOS_SECURE_ONLY 1
#define configENABLE_FPU 1
#define configMAX_SYSCALL_INTERRUPT_PRIORITY 16

#endif /* FREERTOS_CONFIG_H */
