#!/usr/bin/env bash
# Flash and run several harness/esp-idf builds in turn on one board, one log per build.
# Usage: esp_opt_run.sh <s3|p4> <out_dir> <build_dir_name>...
# Log names drop the leading "build-" from the build directory name.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BOARD="$1"
OUT="$2"
shift 2
mkdir -p "$OUT"
if [ "$BOARD" = "s3" ]; then
    PORT="${PORT:-$(ls /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_*-if00 2>/dev/null | head -n 1)}"
    export CONSOLE=usj
else
    PORT="${PORT:-$(ls /dev/serial/by-id/usb-1a86_USB_Single_Serial_*-if00 2>/dev/null | head -n 1)}"
    export CONSOLE=uart
fi
for b in "$@"; do
    echo "=== $(date +%T) $b"
    bash "$HERE/esp_flash_and_run.sh" "$b" "$PORT" "$OUT/${b#build-}.log" 7200 || echo "FAILED: $b"
done
echo "=== $(date +%T) all done"
