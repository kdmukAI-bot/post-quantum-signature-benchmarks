/* POSIX-thread implementation of the FreeRTOS task calls declared in freertos/task.h, for
 * the two-core Linux builds (make DUAL_CORE=1). See freertos/task.h for the mapping. */
#include <pthread.h>
#include <stdlib.h>

#include "freertos/task.h"

struct pqb_task {
    pthread_mutex_t lock;
    pthread_cond_t cond;
    uint32_t notify_count;
    int ready;
};

/* One record per thread. Only the thread that waits (the primary) ever needs one; it is
 * set up on first use. */
static __thread struct pqb_task self_task;

TaskHandle_t xTaskGetCurrentTaskHandle(void)
{
    struct pqb_task* t = &self_task;
    if (!t->ready) {
        pthread_mutex_init(&t->lock, NULL);
        pthread_cond_init(&t->cond, NULL);
        t->notify_count = 0;
        t->ready = 1;
    }
    return t;
}

BaseType_t xTaskNotifyGive(TaskHandle_t task)
{
    pthread_mutex_lock(&task->lock);
    task->notify_count++;
    pthread_cond_signal(&task->cond);
    pthread_mutex_unlock(&task->lock);
    return pdPASS;
}

uint32_t ulTaskNotifyTake(BaseType_t clear_on_exit, TickType_t ticks_to_wait)
{
    (void)ticks_to_wait;
    struct pqb_task* t = xTaskGetCurrentTaskHandle();
    pthread_mutex_lock(&t->lock);
    while (t->notify_count == 0) {
        pthread_cond_wait(&t->cond, &t->lock);
    }
    const uint32_t value = t->notify_count;
    t->notify_count = clear_on_exit ? 0 : value - 1;
    pthread_mutex_unlock(&t->lock);
    return value;
}

typedef struct {
    TaskFunction_t fn;
    void* arg;
} start_t;

static void* task_start(void* p)
{
    const start_t s = *(start_t*)p;
    free(p);
    s.fn(s.arg);
    return NULL;
}

BaseType_t xTaskCreatePinnedToCore(TaskFunction_t fn, const char* name, uint32_t stack_bytes,
                                   void* arg, UBaseType_t priority, TaskHandle_t* created,
                                   BaseType_t core)
{
    (void)name;
    (void)stack_bytes;
    (void)priority;
    (void)core;
    if (created) {
        *created = NULL;
    }
    start_t* s = malloc(sizeof(*s));
    if (!s) {
        return pdFAIL;
    }
    s->fn = fn;
    s->arg = arg;
    pthread_attr_t attr;
    pthread_t thread;
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    const int err = pthread_create(&thread, &attr, task_start, s);
    pthread_attr_destroy(&attr);
    if (err) {
        free(s);
        return pdFAIL;
    }
    return pdPASS;
}

void vTaskDelete(TaskHandle_t task)
{
    if (task == NULL) {
        pthread_exit(NULL);
    }
}
