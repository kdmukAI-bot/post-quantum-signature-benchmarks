#!/usr/bin/env bash
# Round 3: copy the Pi Zero W queue results (/mnt/data/pq-bench/r3/results/) into
# results/raw/pi0w/r3/, except lines still in progress (*.partial). A copy of
# scripts/r2_pi_fetch.sh with r2 replaced by r3. Never overwrites a file that already
# exists locally (tar --skip-old-files), so it can be run as often as needed during a
# queue; the queue log (queue.log) is copied as queue-<time>.log each time.
#
#   r3_pi_fetch.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOST="${PI_HOST:-seedsigner}"
OUT="$ROOT/results/raw/pi0w/r3"
mkdir -p "$OUT"
ssh -o BatchMode=yes "$HOST" \
    "cd /mnt/data/pq-bench/r3/results && tar cf - \$(ls | grep -v -e '\.partial\$' -e '^queue.log\$')" \
    | tar xf - -C "$OUT" --skip-old-files
ssh -o BatchMode=yes "$HOST" "cat /mnt/data/pq-bench/r3/results/queue.log" \
    > "$OUT/queue-$(date +%Y%m%d_%H%M%S).log" || true
ls -la "$OUT" | tail -5
