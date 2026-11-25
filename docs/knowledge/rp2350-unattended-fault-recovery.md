# RP2350: a fault silences USB and needs a button, unless the app recovers itself

A Pico SDK application that runs unattended on an RP2350 board with a USB CDC console can
end up in a state that only a button press or a power cycle clears: the console stops, and
`picotool reboot -f -u` (the SDK's USB reset interface) has no effect. This note explains
why, and the two small additions that turn such a fault into an automatic reboot with a
report.

## Why the board goes silent

- The SDK's default HardFault handler (`isr_hardfault` in `pico_crt0`) is a breakpoint.
  With no debugger attached, a breakpoint inside the HardFault handler cannot be taken,
  and the Cortex-M33 enters lockup. The SDK's `panic()` also ends in a breakpoint.
- USB on the RP2350 is serviced by the CPU: TinyUSB runs from the USB controller's
  interrupt and from a low-priority software interrupt. In a HardFault or in lockup no
  interrupt of lower priority runs, so the CDC console stops answering and so does the
  vendor reset interface that `picotool reboot -f -u` and the 1200-baud reset use.
- The board stays enumerated: the host still lists the device (2e8a:0009), opening the
  serial port succeeds, and writes to it block. That looks like a slow run rather than a
  dead one.
- The watchdog is off unless the application starts it, and the host cannot power-cycle a
  USB port without root access to the hub.

By contrast, a task stuck in a loop with interrupts enabled is harmless in this respect:
the USB interrupt still runs, and `picotool reboot -f -u` sends the board to BOOTSEL.

## The additions (harness/pico/pqb_rp_fault.c)

1. **Watchdog fed from the tick interrupt.** Start the hardware watchdog at boot
   (`watchdog_enable(5000, true)`) and call `watchdog_update()` from the FreeRTOS tick
   hook (`configUSE_TICK_HOOK 1`, `vApplicationTickHook`), which runs in the SysTick
   interrupt on the tick core. Long computations in tasks never starve it; it fires only
   when the tick core stops taking interrupts: a fault, lockup, or a deadlock with
   interrupts masked. The cost is one register write per tick.
2. **A HardFault handler that records and reboots.** Replace `isr_hardfault` with a short
   handler that saves the stacked PC, LR, and xPSR, the fault status registers (CFSR,
   HFSR, MMFAR, BFAR), the core number, and the name of the running operation into a
   variable in `__uninitialized_ram()` (not cleared at boot), then calls
   `watchdog_reboot(0, 0, 10)`. Do the same in the FreeRTOS hooks for stack overflow,
   assertion failure, and allocation failure. After the reboot, the application prints the
   record until the host sends a command, and `watchdog_caused_reboot()` tells a watchdog
   reboot from a power-on.

With both in place, a fault ends the current job set (the capture sees the USB device
disappear) and the board comes back at its prompt, ready for the next job, with the cause
in the log.

## Reading a record

The CFSR bits say what kind of fault it was. Two common cases:

- `cfsr=0x00008200`: a precise bus fault (PRECISERR) with BFAR valid; BFAR holds the
  address that was accessed. An address outside the memory map, such as one in 0xa0000000,
  usually comes from a corrupted pointer.
- `cfsr` bit 20 (STKOF, value 0x00100000): a stack overflow caught by the stack limit
  register (PSPLIM), which the FreeRTOS RP2350_ARM_NTZ port sets for every task.

`arm-none-eabi-addr2line -f -e <elf> <pc>` names the faulting function.

## A fault that looks like this: two allocators

A precise bus fault inside newlib's `_free_r()` (the record's PC), with BFAR outside the
memory map, is what releasing memory to the wrong heap produces: newlib's `free()` given a
block from the FreeRTOS heap (`pvPortMalloc()`) reads a chunk header that is not there.
Without the handler above, the same mistake locks the board with no record. An application
that routes some allocations to the FreeRTOS heap (for example with a force-included
header that redefines `malloc` and `free`) must do so in every file that frees that
memory. The SDK already wraps `malloc` through the linker (`pico_malloc`), so a second
`--wrap` cannot do it.