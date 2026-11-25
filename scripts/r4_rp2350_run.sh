#!/usr/bin/env bash
# Round 4: flash one harness/pico build onto the Waveshare RP2350 Touch LCD 2 and run job
# sets on it, one log per set (the RP2350 counterpart of scripts/r2_esp_run.sh).
#
#   r4_rp2350_run.sh <build dir under harness/pico/> <out_dir> <set>[:n] [<set>[:n] ...]
#
# Sets: r1, verify, stateless, lattice, smoke (harness/pico/bench_rp.c), and microbench,
# mbops, mbops_<mode> in microbenchmark builds; n overrides the build's run count. Logs,
# with the build name minus its "build-" prefix and "rp2350-" in front:
#   <out_dir>/rp2350-<build>-<set>-n<n>-<YYYYmmdd_HHMMSS>.log
# FLASH=0 skips flashing (the board must already hold the build). MAX_S caps each set's
# capture time (default 43200 s). The console is USB CDC: the app is not reset between
# sets and takes the next command at its prompt, as on the Waveshare ESP32-S3 Touch LCD 2.
# Exit status 1 if any set did not reach '#done' or printed an error.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BUILD="$1"
OUT="$2"
shift 2
MAX_S="${MAX_S:-43200}"
mkdir -p "$OUT"

if [ "${FLASH:-1}" != "0" ]; then
    echo "=== $(date +%T) flash $BUILD"
    PORT="$(bash "$HERE/r4_rp2350_flash.sh" "$BUILD" | tail -1)" || { echo "flash failed"; exit 1; }
    sleep 2
else
    PORT=""
    for p in /dev/serial/by-id/usb-Raspberry_Pi_*-if00; do
        [ -e "$p" ] && udevadm info -q property -n "$p" | grep -qx 'ID_VENDOR_ID=2e8a' && PORT="$p"
    done
fi
case "$PORT" in /dev/serial/by-id/*) ;; *) echo "no RP2350 console ($PORT)"; exit 1 ;; esac

status=0
for spec in "$@"; do
    set_name="${spec%%:*}"
    n=""
    [ "$spec" != "$set_name" ] && n="${spec#*:}"
    cmd="run $set_name${n:+ $n}"
    log="$OUT/rp2350-${BUILD#build-}-$set_name-n${n:-default}-$(date +%Y%m%d_%H%M%S).log"
    echo "=== $(date +%T) $BUILD: $cmd -> $log"
    "$ROOT/.venv/bin/python" -I "$HERE/esp_capture.py" "$PORT" "$log" --max-seconds "$MAX_S" \
        --no-reset --command "$cmd" || status=1
    if ! grep -q '^#done' "$log"; then
        echo "WARNING: no #done in $log"
        status=1
    fi
    if grep -qE "^#error|PANIC|panic|Out of memory" "$log"; then
        echo "WARNING: errors in $log"
        grep -nE "^#error|PANIC|panic|Out of memory" "$log" | head -5
        status=1
    fi
done
echo "=== $(date +%T) done ($BUILD)"
exit $status
