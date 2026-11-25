/* Replaces Jade's jade_tasks.h in the two-core Linux builds (make DUAL_CORE=1 copies this
 * file into the build's generated source directory). Values as in Jade's own header for
 * a two-core configuration. */
#ifndef JADE_TASKS_H_
#define JADE_TASKS_H_

#include "freertos/FreeRTOS.h"

#define JADE_CORE_PRIMARY 0
#define JADE_CORE_SECONDARY 1
#define JADE_TASK_PRIO_TEMPORARY (tskIDLE_PRIORITY + 1)

#endif
