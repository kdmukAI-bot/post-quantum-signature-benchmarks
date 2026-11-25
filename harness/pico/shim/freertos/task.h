/*
 * ESP-IDF style path to the FreeRTOS task header, plus the one ESP-IDF task function that
 * Jade's two-core code calls and the upstream kernel lacks.
 *
 * xTaskCreatePinnedToCore() is ESP-IDF's API. ESP-IDF's FreeRTOS measures task stacks in
 * bytes, the upstream kernel in StackType_t words (4 bytes on the Cortex-M33), so the
 * byte count is converted: Jade's helper tasks get the same 2,048 and 4,096 bytes as on
 * the ESP32 boards. The core number becomes an affinity mask of one core (FreeRTOS SMP,
 * configUSE_CORE_AFFINITY). Everything else Jade calls (xTaskGetCurrentTaskHandle,
 * xTaskNotifyGive, ulTaskNotifyTake, vTaskDelete, vTaskDelay) is the kernel's own.
 */
#pragma once
#include <FreeRTOS.h>
#include <task.h>

static inline BaseType_t xTaskCreatePinnedToCore(TaskFunction_t fn, const char* name,
                                                 uint32_t stack_bytes, void* arg,
                                                 UBaseType_t prio, TaskHandle_t* handle,
                                                 BaseType_t core)
{
    const configSTACK_DEPTH_TYPE words =
        (configSTACK_DEPTH_TYPE)((stack_bytes + sizeof(StackType_t) - 1) / sizeof(StackType_t));
#if configNUMBER_OF_CORES > 1
    return xTaskCreateAffinitySet(fn, name, words, arg, prio, (UBaseType_t)1 << core, handle);
#else
    (void)core;
    return xTaskCreate(fn, name, words, arg, prio, handle);
#endif
}
