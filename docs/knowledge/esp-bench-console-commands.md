# Sending commands to an ESP32 benchmark app over its serial console

The round-2 harness/esp-idf app (`harness/esp-idf/main/bench_esp.c`) prints
`#ready: send 'run <set> [n]'` once a second and waits for a command line; the host
script (`scripts/esp_capture.py --command`) sends it. Two traps apply to any app that
reads commands from the console this way.

## The host tty echoes the ESP32's output back to it

Before a serial library configures the port, a Linux tty is in its default line mode with
`ECHO` on. Bytes the ESP32 sends in that window (for example right after `esptool.py`
releases the port, while the app is already printing its prompt) are echoed back to the
ESP32, which then reads its own prompt text as input. The first command line the app
receives can be `#ready: send 'rurun verify 10` instead of `run verify 10`.

Rule: the app parses from the last occurrence of the command keyword in the line, and the
host repeats its command until the app confirms that it started (the `#env` line), so a
garbled first line costs one prompt interval.

## Consoles differ in how the ESP32 can be reset

- ESP32-P4 board (CH343 USB-to-UART bridge, `CONSOLE=uart`): the host resets the chip
  through RTS, and the app reads commands with ESP-IDF's UART driver
  (`uart_driver_install()` plus `uart_vfs_dev_use_driver()`) and a read timeout.
- Waveshare ESP32-S3 Touch LCD 2 (the chip's USB-Serial/JTAG port, `CONSOLE=usj`): the
  port disappears and re-enumerates on every chip reset, so the host cannot reset and
  keep reading in one step. The app returns to its prompt after each job set, so several
  sets can run after one flash without a reset.

The app discards pending input after accepting a command, so repeated copies of the same
command do not start a second run.
