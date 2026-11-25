#!/usr/bin/env bash
# Wait for the Waveshare ESP32-S3 to appear in ROM download mode (Espressif USB-Serial/JTAG),
# then flash and run every harness/esp-idf ESP32-S3 build in turn.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/.."
PORT="${PORT:?set PORT to the ESP32-S3 port, /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_MAC-if00}"
mkdir -p "$ROOT/results/raw/esp32s3"

echo "$(date +%T) waiting for $PORT"
until [ -e "$PORT" ]; do sleep 1; done
echo "$(date +%T) found it"

for s in B L; do
    for v in soft-dc0 hw-dc0 hw-dc1; do
        b="build-s3-$s-$v-direct-r10"
        echo "=== $(date +%T) $b"
        CONSOLE=usj bash "$HERE/esp_flash_and_run.sh" "$b" "$PORT" \
            "$ROOT/results/raw/esp32s3/${b#build-}.log" 5400 || echo "FAILED: $b"
    done
done
echo "=== $(date +%T) all done"
