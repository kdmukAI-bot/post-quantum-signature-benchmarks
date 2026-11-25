#!/usr/bin/env bash
# Round 2: resumable run queue for one ESP32 board (host side).
#
#   r2_esp_queue.sh <s3|p4> <plan_file> [out_dir]
#
# PLAN_FILE has one job per line, fields separated by '|':
#   <build dir under harness/esp-idf/>|<job set>|<n>
# (job sets: r1, verify, stateless, lattice, smoke; see harness/esp-idf/main/bench_esp.c).
# Blank lines and lines starting with '#' are skipped. Lines run in order. Each completed
# line is appended to <plan_file>.<board>.done, and a rerun of the queue skips lines
# listed there, so the queue can be stopped (Ctrl-C, or kill) and restarted. A line whose
# capture fails (timeout, '#error', a reset) goes to <plan_file>.<board>.failed and the
# queue moves on; rerunning the queue retries it. Consecutive lines on the same build
# flash once; the first line after a (re)start always flashes.
#
# Logs: <out_dir>/<build minus "build-">-<set>-n<n>-<YYYYmmdd_HHMMSS>.log (default
# out_dir: results/raw/esp32<board>/r2). The queue's own progress goes to
# <out_dir>/queue-<board>.log.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BOARD="$1"
PLAN="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
OUT="${3:-$ROOT/results/raw/esp32$BOARD/r2}"
DONE="$PLAN.$BOARD.done"
FAILED="$PLAN.$BOARD.failed"
mkdir -p "$OUT"
touch "$DONE"
QLOG="$OUT/queue-$BOARD.log"

last_build=""
while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    if grep -qxF "$line" "$DONE"; then
        continue
    fi
    IFS='|' read -r build set n <<< "$line"
    if [ ! -d "$ROOT/harness/esp-idf/$build" ]; then
        echo "$(date '+%F %T') MISSING BUILD $build ($line)" | tee -a "$QLOG"
        echo "$line" >> "$FAILED"
        continue
    fi
    flash=1
    [ "$build" = "$last_build" ] && flash=0
    echo "$(date '+%F %T') start: $line (flash=$flash)" | tee -a "$QLOG"
    if FLASH=$flash bash "$HERE/r2_esp_run.sh" "$BOARD" "$build" "$OUT" "$set:$n" >> "$QLOG" 2>&1 < /dev/null; then
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
