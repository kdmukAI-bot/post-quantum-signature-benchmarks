#!/usr/bin/env bash
# Round 4: resumable run queue for the Waveshare RP2350 Touch LCD 2 (host side), the
# RP2350 counterpart of scripts/r2_esp_queue.sh with the same plan format and bookkeeping.
#
#   r4_rp2350_queue.sh <plan_file> [out_dir]
#
# PLAN_FILE has one job per line, fields separated by '|':
#   <build dir under harness/pico/>|<job set>|<n>
# Blank lines and lines starting with '#' are skipped. Lines run in order. Each completed
# line is appended to <plan_file>.rp2350.done, and a rerun of the queue skips lines listed
# there. A line whose capture fails (timeout, '#error', no '#done') goes to
# <plan_file>.rp2350.failed and the queue moves on; rerunning the queue retries it.
# Consecutive lines on the same build flash once; the first line after a (re)start always
# flashes. Flashing needs no button press (scripts/r4_rp2350_flash.sh).
#
# Logs: <out_dir>/rp2350-<build minus "build-">-<set>-n<n>-<YYYYmmdd_HHMMSS>.log (default
# out_dir: results/raw/rp2350/r4). The queue's own progress goes to
# <out_dir>/queue-rp2350.log.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PLAN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
OUT="${2:-$ROOT/results/raw/rp2350/r4}"
DONE="$PLAN.rp2350.done"
FAILED="$PLAN.rp2350.failed"
mkdir -p "$OUT"
touch "$DONE"
QLOG="$OUT/queue-rp2350.log"

last_build=""
while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    if grep -qxF "$line" "$DONE"; then
        continue
    fi
    IFS='|' read -r build set n <<< "$line"
    if [ ! -f "$ROOT/harness/pico/$build/pqb_rp.uf2" ]; then
        echo "$(date '+%F %T') MISSING BUILD $build ($line)" | tee -a "$QLOG"
        echo "$line" >> "$FAILED"
        continue
    fi
    flash=1
    [ "$build" = "$last_build" ] && flash=0
    echo "$(date '+%F %T') start: $line (flash=$flash)" | tee -a "$QLOG"
    if FLASH=$flash bash "$HERE/r4_rp2350_run.sh" "$build" "$OUT" "$set:$n" >> "$QLOG" 2>&1 < /dev/null; then
        echo "$line" >> "$DONE"
        echo "$(date '+%F %T') done: $line" | tee -a "$QLOG"
        last_build="$build"
    else
        echo "$line" >> "$FAILED"
        echo "$(date '+%F %T') FAILED: $line (see $QLOG)" | tee -a "$QLOG"
        last_build=""
    fi
done < "$PLAN"
echo "$(date '+%F %T') queue finished: $(grep -cv '^\s*\(#\|$\)' "$PLAN") lines in plan, $(wc -l < "$DONE") done" | tee -a "$QLOG"
