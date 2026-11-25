#!/usr/bin/env bash
# Round 4: copies the Pi Zero 2 W queue results (<dir>/results/, or <dir>/RESULTS_SUB)
# into results/raw/pi02w/r4/ (OUT_SUB below it, if given), except lines still in
# progress (*.partial). Never overwrites a file that already exists locally
# (tar --skip-old-files); the queue log is copied as queue-<time>.log each time.
# Adapted from scripts/r3_pi_fetch.sh.
#
#   r4_pi02w_fetch.sh [RESULTS_SUB [OUT_SUB]]     (defaults: results, none)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOST="${PI_HOST:-pi02w}"
DIR="${PI02W_DIR:-/mnt/data/pq-bench/r4}"
SUB="${1:-results}"
OUT="$ROOT/results/raw/pi02w/r4${2:+/$2}"
mkdir -p "$OUT"
ssh -o BatchMode=yes "$HOST" \
    "cd $DIR/$SUB && tar cf - \$(ls | grep -v -e '\.partial\$' -e '^queue.log\$')" \
    | tar xf - -C "$OUT" --skip-old-files
ssh -o BatchMode=yes "$HOST" "cat $DIR/$SUB/queue.log" \
    > "$OUT/queue-$(date +%Y%m%d_%H%M%S).log" || true
ls -la "$OUT" | tail -5
