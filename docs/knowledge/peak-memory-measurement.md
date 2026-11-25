# Measuring peak stack and heap per operation

How the benchmark measures peak memory on each platform, and the traps that make the
obvious methods report the wrong number.

## ESP32 (FreeRTOS)

Method (`harness/esp-idf/main/bench_esp.c`): each run of each operation executes in a task
created for that run alone. FreeRTOS fills a new task's stack with a known byte, and
`uxTaskGetStackHighWaterMark()` at the end of the run gives the unused part; the stack
size minus that is the run's peak. Heap: internal-RAM free bytes at the start of the run
minus the lowest free level during it (`heap_caps_monitor_local_minimum_free_size_start()`
and `heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL)`). Results are printed by
`app_main`, after the run's task has ended.

Traps:

- **Printing in the measured task.** A task that runs an operation several times and
  prints a CSV line after each run reports a high-water mark that includes `printf()`,
  which with floating-point formatting can use more stack than a small operation does.
  One task per run, printing elsewhere, avoids this.
- **Helper tasks.** Blockstream's dual-core paths create short-lived tasks on the second
  core (2 KiB and 4 KiB stacks). Their stacks come from the heap, so they appear in the
  heap peak, not in the stack peak.
- **Task stack size.** The task must be created with room for the largest operation;
  mldsa-native's ML-DSA-87 signing peaked at 113,300 to 114,000 bytes on all three boards,
  so the benchmark gives that job a 136 KiB stack. On the Waveshare ESP32-S3 Touch LCD 2
  with the scheme code in internal RAM (level 3) the largest free internal block at boot
  was about 264 KiB, which leaves little room for anything larger.

## Linux (Pi Zero W)

Method (`harness/common/mem_linux.c`, memory builds only: `make MEM=1`):

- Stack: each run executes in a new thread on a 4 MiB stack allocated with `mmap()` and
  filled with 0xA5 first (`pthread_attr_setstack()`). The thread records the address of a
  local variable on entry; after it ends, the lowest byte that is no longer 0xA5 marks the
  deepest point. The peak is the distance between the two.
- Heap: the binary is linked with `-Wl,--wrap=malloc,--wrap=free,--wrap=calloc,
  --wrap=realloc`; the wrappers keep a size header and count bytes outstanding. The peak
  is the highest count during the run, above the count at its start.

Traps:

- **Thread descriptor at the top of the stack.** With a caller-supplied stack, glibc
  places the thread descriptor and static TLS at the top of that memory. Measuring from
  the top of the mapping would count them; measuring from the entry frame does not.
- **What `--wrap` sees.** Only calls made from objects linked with the option are counted:
  the benchmark and the scheme code, not allocations inside libc or libcrypto. The schemes
  benchmarked here allocate nothing themselves except through the harness, so this covers
  them; an OpenSSL-backed hash that allocated internally would not be counted.
- **A statically linked library comes under `--wrap` too.** Linking libcrypto statically
  (`libcrypto.a`) puts its `malloc` and `free` calls behind the wrappers, while memory
  that libc allocates for itself is not. On the Pi Zero 2 W, memory builds linked that way
  printed every row and then aborted at process exit with "free(): invalid pointer"
  (glibc's check on a pointer it did not hand out), in every operation, including ones
  that never call OpenSSL. Link libraries dynamically in memory builds, as the Pi Zero W
  builds do, and expect the counts to exclude the library's own allocations.
- **Timing.** The thread start, the stack fill, and the wrappers cost time, so memory
  builds are a separate pass and their times are not reported.

## What the numbers cover

On both platforms the window is the whole operation call: the timed library call plus
the harness's untimed work around it (copying keys and signatures from flash or the
binary into RAM, and verifying a new signature). The checks that run after an operation
use less stack than the operation (for example, ML-DSA verification against signing), so
they do not raise the stack peak; key generation runs no check for that reason. The heap
peak includes the harness's own buffers (the output signature or key, and copies of the
inputs), which an application would also need.
