#!/usr/bin/env bash
# Round 3 correctness gate: runs scripts/check_r2.py (unchanged) over the round-3 result
# files of each board against the round-2 host reference (outputs do not depend on the
# print format), and prints one pass count per board. Exit status 0 only if every board
# passes.
#
#   check_r3.sh [raw_dir]          (default results/raw)
#
# Files read: <raw_dir>/pi0w/r3/pi0w-r3-*.csv, <raw_dir>/esp32p4/r3/p4-r3-*.log, and
# <raw_dir>/esp32s3/r3/s3-r3-*.log (queue logs and clock checks are not result files). The
# full check_r2.py output per board goes to <raw_dir>/<board>/r3/check_r3-<board>.txt.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RAW="${1:-$ROOT/results/raw}"
REF="$ROOT/results/raw/host/r2"
PY="$ROOT/.venv/bin/python"
status=0
for spec in "pi0w:pi0w/r3/pi0w-r3-*.csv:Pi Zero W" "esp32p4:esp32p4/r3/p4-r3-*.log:ESP32-P4" \
        "esp32s3:esp32s3/r3/s3-r3-*.log:Waveshare ESP32-S3 Touch LCD 2"; do
    IFS=: read -r board pattern name <<< "$spec"
    files=( $RAW/$pattern )
    if [ ! -e "${files[0]}" ]; then
        echo "$name: no result files"
        status=1
        continue
    fi
    out="$RAW/$board/r3/check_r3-$board.txt"
    "$PY" -I "$HERE/check_r2.py" --ref "$REF/reference-B.csv" --ref "$REF/reference-L.csv" \
        "${files[@]}" > "$out" 2>&1 || status=1
    echo "$name (${#files[@]} files): $(tail -1 "$out")"
done
exit $status
