#!/usr/bin/env bash
# Flash one harness/esp-idf build and capture its benchmark output.
# Usage: esp_flash_and_run.sh <build_dir_name> <port> <out_file> [max_seconds]
# CONSOLE=usj for boards whose console is the chip's USB-Serial/JTAG port (ESP32-S3 here):
# the app is started by sending a newline after boot instead of by an RTS reset.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/.."
BUILD="$1"
PORT="$2"
OUT="$3"
MAX="${4:-3600}"
CONSOLE="${CONSOLE:-uart}"
IMAGE="ghcr.io/kdmukai-bot/seedsigner-micropython-builder-base:idf-v5.5.5"
DEV="$(readlink -f "$PORT")"

if [ "$CONSOLE" = "usj" ]; then
    # A plain RTS reset does not leave download mode on the ESP32-S3 when download mode was
    # entered with the BOOT strap (the strap is latched); a watchdog reset re-samples it.
    AFTER=watchdog_reset
else
    AFTER=no_reset
fi

docker run --rm --device="$DEV" -v "$ROOT/harness/esp-idf/$BUILD:/workspace" -w /workspace "$IMAGE" \
    bash -lc "source /opt/toolchains/esp-idf/export.sh >/dev/null 2>&1 && \
    esptool.py --chip auto -p $DEV -b 460800 --before default_reset --after $AFTER \
    write_flash @flash_args" | grep -E "Chip is|Hash of data verified" | tail -2

if [ "$CONSOLE" = "usj" ]; then
    sleep 3
    "$ROOT/.venv/bin/python" -I "$HERE/esp_capture.py" "$PORT" "$OUT" --max-seconds "$MAX" \
        --send-start
else
    "$ROOT/.venv/bin/python" -I "$HERE/esp_capture.py" "$PORT" "$OUT" --max-seconds "$MAX"
fi
