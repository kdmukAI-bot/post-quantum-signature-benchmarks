# Porting ESP-IDF FreeRTOS code to the RP2350 with the Pico SDK: traps

Notes from building Blockstream's Jade hash-based signature code and two lattice libraries
for the RP2350's Cortex-M33 cores with Pico SDK 2.3.1, Arm GNU Toolchain 14.2.rel1, and
FreeRTOS SMP (`harness/pico/`). Each item is a behavior that compiles or links without
complaint, or fails with a message that does not point at the cause.

## FreeRTOS

- **Where the RP2350 port is.** The upstream FreeRTOS-Kernel releases V11.2.0 and V11.3.3
  have only the RP2040 port under `portable/ThirdParty/GCC`. Raspberry Pi's fork
  (github.com/raspberrypi/FreeRTOS-Kernel, main) adds `RP2350_ARM_NTZ` and
  `RP2350_RISC-V`; pico-examples' FreeRTOS import script looks for them there or under a
  `Community-Supported-Ports` path.
- **The timer task is required.** With `configUSE_TIMERS 0` the link fails with an
  undefined `xEventGroupSetBitsFromISR` in the port's `port.c`: the port's pico_sync
  interoperation (on by default when `pico_sync` is linked) pends work to the timer task.
  Set `configUSE_TIMERS 1` and `INCLUDE_xTimerPendFunctionCall 1`.
- **Stack sizes are in words, not bytes.** ESP-IDF's FreeRTOS takes task stack sizes in
  bytes (`xTaskCreatePinnedToCore(fn, name, 4096, ...)` is 4 KiB); the upstream kernel
  takes `StackType_t` words (4 bytes on the M33). Code written for ESP-IDF and passed
  through unchanged gets four times the stack it asked for, which hides overflows and
  changes heap use. `xTaskCreatePinnedToCore` itself does not exist upstream; the
  equivalent is `xTaskCreateAffinitySet` with a one-core mask (`configUSE_CORE_AFFINITY`).
- **The tick rate is part of the measured time** when code calls `vTaskDelay(1)` inside
  long loops (Jade's grinding loops do, every 100,000 attempts, including the single-core
  loop because Jade passes a progress callback): each call waits for the next tick.
  ESP-IDF defaults to 100 Hz, pico-examples' configuration to 1000 Hz.
- **Per-task stack limit.** The RP2350_ARM_NTZ port sets each task's PSPLIM, so a task
  that overruns its stack faults at once (UsageFault STKOF, escalated to HardFault)
  instead of corrupting memory; FreeRTOS's own check (`configCHECK_FOR_STACK_OVERFLOW`)
  runs only at context switches.

## Memory placement

- **`copy_to_ram` copies the constant data too.** The SDK's copy-to-RAM linker script puts
  all of `.rodata` in SRAM, and only sections named `.flashdata*` stay in flash. A large
  embedded table (here a 320 to 345 KB test-vector blob) must be emitted into a
  `.flashdata` section, or the image does not fit; code in SRAM also takes heap from
  everything else (about 300 KB of code and constants left about 150 KiB of the 512 KB).
- **Placing chosen objects in SRAM without source changes.** Pico SDK 2.x builds its
  linker script from small include files and lets a project override them
  (`pico_add_linker_script_override_path`). Excluding object files in the overriding
  `default_text_excludes.incl` and `default_rodata_excludes.incl` moves them into `.data`,
  which the boot code copies to SRAM. Object names are CMake's (`*sha2_256.c.o`).
  File-based placement does not survive LTO: the linker then sees LTRANS objects.
- **LTO across the SDK fails to assemble.** With `-flto` on every source, one LTRANS unit
  failed with "offset out of range" (a literal-pool or branch range in SDK or FreeRTOS
  assembly). Applying `-flto` to the application's own sources only links.
- **The flash clock divider read back as 3.** With the SDK's defaults and the `pico2`
  board header (whose `PICO_FLASH_SPI_CLKDIV` is 2), the QMI divider read at run time was
  3: a 50 MHz flash clock at the 150 MHz system clock. Why the header's value does not
  apply was not established (the boot ROM sets up the QMI on the RP2350). Code running in
  place from flash pays for it on every XIP cache miss; read the divider rather than
  assume it.

## Two cores running different code from flash

The two Cortex-M33 cores share one 16 KB XIP cache in front of the flash. When both run
the same small loop from flash (portable-C SHA-256 on both cores), neither slows down
measurably. When they run different code, the two working sets can evict each other, and
the effect depends on where the linker happened to place the code: in this benchmark's
level-2 build for SHRINCS-B (core 0 driving the SHA-256 accelerator, core 1 hashing in
portable C, all code in flash), Blockstream's two-core SLH-DSA-SHA2-128s signing took
20.75 s against 12.90 s on one core, and the same configuration with the hash-based and
SHA-256 objects placed in SRAM took 11.14 s. A microbenchmark build of the same
configuration, whose code sits at other addresses, showed no slowdown (12.11 s on two
cores). Rule: before trusting a two-core speedup with code in flash, compare against a
build with the hot code in SRAM; on two cores, place code that both cores execute
concurrently in SRAM.

## Heaps

- **`pico_malloc` already wraps `malloc`.** The SDK links `malloc`, `calloc`, `realloc`,
  and `free` through `-Wl,--wrap` (`pico_malloc`, part of `pico_runtime`), so a second
  wrap for counting is not possible. To measure an application's heap use, route its
  allocations to the FreeRTOS heap (heap_4) and record the lowest free size from
  `traceMALLOC`; every file that frees such memory must use the same route
  (`rp2350-unattended-fault-recovery.md`).

## Console

- **USB CDC drops output while no host has the port open** (the SDK's default connect
  wait, `PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS`, is 0). A program that prints once at
  boot loses that line; repeat a prompt until a command arrives, and keep the port open
  for the whole run.
- `stdio_usb_init()` must run on the core that owns the default alarm pool (core 0 at
  boot); call `stdio_init_all()` before starting the scheduler.

## c-fn-dsa's Cortex-M4 assembly on the M33

- c-fn-dsa (commit 1b858880) enables its assembly with `FNDSA_ASM_CORTEXM4=1` and checks
  `__ARM_ARCH_7EM__ && __ARM_FEATURE_DSP`. GCC defines `__ARM_ARCH_8M_MAIN__` and
  `__ARM_FEATURE_DSP` for the M33, so the check fails although the M33 with its DSP
  extension executes every ARMv7E-M instruction; defining `__ARM_ARCH_7EM__` for
  c-fn-dsa's sources only satisfies it without a source change.
- Its `.s` files begin with `.cpu cortex-m4`, which leaves the assembler without an FPU,
  and they use FPU registers as scratch storage (`vmov s3, r3`): assemble them with
  `-Wa,-mfpu=fpv5-sp-d16` (the M33's single-precision FPU).
