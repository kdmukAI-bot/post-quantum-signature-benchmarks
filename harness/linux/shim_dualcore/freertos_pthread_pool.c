/* Variant of freertos_pthread.c for the two-core Linux builds made with DUAL_CORE=pool:
 * the task function runs on one persistent worker thread instead of a new thread per
 * xTaskCreatePinnedToCore() call. Everything else is as in freertos_pthread.c (see
 * freertos/task.h for the mapping).
 *
 * Jade creates its helper task, does its own share of the work, and waits for the
 * helper's notification before it creates the next one, so one worker suffices. The
 * worker is started on first use and then blocks on a condition variable between tasks.
 * Jade's task functions end with vTaskDelete(NULL); on the worker, that call returns
 * control to the worker loop (longjmp) instead of ending the thread. A new task may be
 * queued while the worker is still returning from the previous one (after that task's
 * notification); the worker takes it next. If a queued task has not been taken yet when
 * another is created (Jade does not do this), the call returns pdFAIL, and Jade then
 * does the whole job on the calling core, as it does on an ESP32 when task creation
 * fails. */
#include <pthread.h>
#include <setjmp.h>
#include <stdlib.h>

#include "freertos/task.h"

struct pqb_task {
    pthread_mutex_t lock;
    pthread_cond_t cond;
    uint32_t notify_count;
    int ready;
};

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

static pthread_mutex_t pool_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t pool_cond = PTHREAD_COND_INITIALIZER;
static int pool_started;
static TaskFunction_t pool_fn; /* queued task, NULL once the worker has taken it */
static void* pool_arg;
static __thread int on_worker;
static __thread jmp_buf worker_return;

static void* worker(void* unused)
{
    (void)unused;
    on_worker = 1;
    for (;;) {
        pthread_mutex_lock(&pool_lock);
        while (pool_fn == NULL) {
            pthread_cond_wait(&pool_cond, &pool_lock);
        }
        const TaskFunction_t fn = pool_fn;
        void* const arg = pool_arg;
        pool_fn = NULL;
        pthread_mutex_unlock(&pool_lock);
        if (setjmp(worker_return) == 0) {
            fn(arg);
        }
    }
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
    pthread_mutex_lock(&pool_lock);
    if (!pool_started) {
        pthread_t thread;
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
        if (pthread_create(&thread, &attr, worker, NULL) != 0) {
            pthread_attr_destroy(&attr);
            pthread_mutex_unlock(&pool_lock);
            return pdFAIL;
        }
        pthread_attr_destroy(&attr);
        pool_started = 1;
    }
    if (pool_fn != NULL) {
        pthread_mutex_unlock(&pool_lock);
        return pdFAIL;
    }
    pool_fn = fn;
    pool_arg = arg;
    pthread_cond_signal(&pool_cond);
    pthread_mutex_unlock(&pool_lock);
    return pdPASS;
}

void vTaskDelete(TaskHandle_t task)
{
    if (task == NULL && on_worker) {
        longjmp(worker_return, 1);
    }
    if (task == NULL) {
        pthread_exit(NULL);
    }
}
