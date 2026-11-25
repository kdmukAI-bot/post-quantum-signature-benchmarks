#!/usr/bin/env bash
# Round 4 correctness gate for the Waveshare RP2350 Touch LCD 2: runs scripts/check_r2.py
# (unchanged) over the round-4 result logs against the round-2 host reference, as
# scripts/check_r3.sh does for round 3, and prints the pass count. Exit status 0 only if
# every row passes.
#
#   check_r4_rp2350.sh [raw_dir]          (default results/raw/rp2350/r4)
#
# Files read: <raw_dir>/rp2350-r4-*.log (the queue log and the microbenchmark logs are not
# result files). Full check_r2.py output: <raw_dir>/check_r4-rp2350.txt.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RAW="${1:-$ROOT/results/raw/rp2350/r4}"
REF="$ROOT/results/raw/host/r2"
files=( "$RAW"/rp2350-r4-*.log )
if [ ! -e "${files[0]}" ]; then
    echo "Waveshare RP2350 Touch LCD 2: no result files"
    exit 1
fi
out="$RAW/check_r4-rp2350.txt"
"$ROOT/.venv/bin/python" -I "$HERE/check_r2.py" --ref "$REF/reference-B.csv" \
    --ref "$REF/reference-L.csv" "${files[@]}" > "$out" 2>&1
status=$?
echo "Waveshare RP2350 Touch LCD 2 (${#files[@]} files): $(tail -1 "$out")"
exit $status
