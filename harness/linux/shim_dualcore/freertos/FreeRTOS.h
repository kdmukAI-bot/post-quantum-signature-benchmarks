/* Stand-in for FreeRTOS.h in the two-core Linux builds (make DUAL_CORE=1): the types and
 * constants that Blockstream's two-core code paths use. The calls are declared in
 * freertos/task.h and implemented over POSIX threads in freertos_pthread.c. The
 * one-core builds use shim/freertos/task.h instead, which this directory shadows. */
#ifndef PQB_SHIM_DUALCORE_FREERTOS_H
#define PQB_SHIM_DUALCORE_FREERTOS_H

#include <stdbool.h>
#include <stdint.h>

typedef int BaseType_t;
typedef unsigned int UBaseType_t;
typedef uint32_t TickType_t;

#define pdTRUE 1
#define pdFALSE 0
#define pdPASS 1
#define pdFAIL 0
#define portMAX_DELAY ((TickType_t)0xffffffffu)
#define tskIDLE_PRIORITY ((UBaseType_t)0)

#endif
