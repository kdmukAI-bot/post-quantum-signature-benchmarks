#!/usr/bin/env bash
# Round 2: flash one harness/esp-idf build and run job sets on it, one log per set.
#
#   r2_esp_run.sh <s3|p4> <build_dir_name> <out_dir> <set>[:n] [<set>[:n] ...]
#
# Sets: r1, verify, stateless, lattice, smoke (harness/esp-idf/main/bench_esp.c); n
# overrides the build's run count. Logs, with the build name minus its "build-" prefix:
#   <out_dir>/<build>-<set>-n<n>-<YYYYmmdd_HHMMSS>.log
# FLASH=0 skips flashing (the ESP32 must already hold the build). MAX_S caps each set's
# capture time (default 43200 s: the level-1 stateless sets on the Waveshare ESP32-S3
# Touch LCD 2 take about 5 h, and a set cut off by the cap fails and reruns from its
# start). Exit status 1 if any set did not reach '#done'.
#
# The ESP32-P4 (UART console) is reset over RTS before each set; the Waveshare ESP32-S3
# Touch LCD 2 (USB-Serial/JTAG console) is not reset after flashing: the app returns to
# its prompt after each set and takes the next command.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BOARD="$1"
BUILD="$2"
OUT="$3"
shift 3
IMAGE="ghcr.io/kdmukai-bot/seedsigner-micropython-builder-base:idf-v5.5.5"
MAX_S="${MAX_S:-43200}"
if [ "$BOARD" = "s3" ]; then
    PORT="${PORT:-$(ls /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_*-if00 2>/dev/null | head -n 1)}"
    AFTER=watchdog_reset
    RESET_ARG="--no-reset"
else
    PORT="${PORT:-$(ls /dev/serial/by-id/usb-1a86_USB_Single_Serial_*-if00 2>/dev/null | head -n 1)}"
    AFTER=no_reset
    RESET_ARG=""
fi
DEV="$(readlink -f "$PORT")"
mkdir -p "$OUT"

if [ "${FLASH:-1}" != "0" ]; then
    echo "=== $(date +%T) flash $BUILD"
    docker run --rm --device="$DEV" -v "$ROOT/harness/esp-idf/$BUILD:/workspace" -w /workspace \
        "$IMAGE" bash -lc "source /opt/toolchains/esp-idf/export.sh >/dev/null 2>&1 && \
        esptool.py --chip auto -p $DEV -b 460800 --before default_reset --after $AFTER \
        write_flash @flash_args" | grep -E "Chip is|Hash of data verified" | tail -2
    sleep 3
fi

status=0
for spec in "$@"; do
    set_name="${spec%%:*}"
    n=""
    [ "$spec" != "$set_name" ] && n="${spec#*:}"
    cmd="run $set_name${n:+ $n}"
    log="$OUT/${BUILD#build-}-$set_name-n${n:-default}-$(date +%Y%m%d_%H%M%S).log"
    echo "=== $(date +%T) $BUILD: $cmd -> $log"
    "$ROOT/.venv/bin/python" -I "$HERE/esp_capture.py" "$PORT" "$log" --max-seconds "$MAX_S" \
        $RESET_ARG --command "$cmd" || status=1
    if grep -qE "^#error|Guru Meditation|abort\(\)|Backtrace:|rst:0x[0-9a-f]+ \((TG|RTC|SW_CPU|PANIC|WDT)" "$log"; then
        echo "WARNING: errors or resets in $log"
        grep -nE "^#error|Guru Meditation|abort\(\)|Backtrace:|rst:0x" "$log" | head -5
        status=1
    fi
done
echo "=== $(date +%T) done ($BUILD)"
exit $status
