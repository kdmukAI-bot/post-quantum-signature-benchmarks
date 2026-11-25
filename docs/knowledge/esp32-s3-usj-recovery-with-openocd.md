# ESP32-S3: recovering a board that esptool cannot reset over USB-Serial-JTAG

## Rule

When esptool fails on an ESP32-S3's USB-Serial-JTAG port with "Write timeout" and the USB
device does not re-enumerate after the RTS reset sequence, reset the chip through the JTAG
interface of the same USB device with OpenOCD. No button press or replug is needed, and the
next esptool command then works as usual.

## Symptoms

- The port stays enumerated (`303a:1001`, `/dev/serial/by-id/usb-Espressif_USB_JTAG_...`) but
  writes time out.
- Toggling RTS with DTR released, or esptool's own USB-JTAG reset sequence, leaves the
  by-id symlink's timestamp unchanged: the chip has not reset.
- Seen with Jade firmware (Waveshare config, `CONFIG_ESP_SYSTEM_PANIC_PRINT_HALT`) after it
  stopped answering, once after printing an abort. After another abort of a similar build the
  ordinary esptool reset still worked, so the condition does not follow from every panic halt;
  its cause is not known.

## Recovery

Find the device node by the chip's serial number (the MAC address in the by-id name, set
as `SERIAL` below) and run OpenOCD's built-in-JTAG board config from an ESP-IDF image.
Docker's `--device` gives the container access to the USB device node, which is root-owned
on the host:

```sh
for d in /sys/bus/usb/devices/*; do
    [ "$(cat "$d/serial" 2>/dev/null)" = "$SERIAL" ] || continue
    bus=$(printf '%03d' "$(cat "$d/busnum")"); dev=$(printf '%03d' "$(cat "$d/devnum")")
    docker run --rm --device="/dev/bus/usb/$bus/$dev" <esp-idf image> bash -lc \
        "source <idf>/export.sh >/dev/null; openocd -f board/esp32s3-builtin.cfg \
         -c 'init; reset run; shutdown'"
done
```

OpenOCD reports "requesting target halt and executing a soft reset" and "Reset cause (3)
(Software core reset)". The second core's examination may fail ("Unexpected OCD_ID"); the
reset still takes effect. Afterwards esptool connects and flashes normally, so a flashing
script can fall back to this when an esptool flash fails.

## Related trap: Jade over USB-Serial-JTAG aborts on early host data

With `CONFIG_JADE_USE_USB_JTAG_SERIAL`, the USB port is live from power-on, before Jade's
boot finishes. Jade starts its serial reader before its idle timer; data that arrives in
between reaches `idletimer_register_activity()`, whose `JADE_ASSERT(last_activity_mutex)`
aborts. Wait several seconds after a reset before sending the first request (15 s was enough
on the Waveshare ESP32-S3 Touch LCD 2). With TinyUSB CDC the port appears only once Jade has
started it and the host has enumerated it, which probably narrows the window (not tested).
