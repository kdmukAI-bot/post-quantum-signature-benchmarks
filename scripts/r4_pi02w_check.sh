#!/usr/bin/env bash
# Round 4 correctness gate for the Pi Zero 2 W: runs scripts/check_r2.py (unchanged) over
# the round-4 result files against the round-2 host reference, as scripts/check_r3.sh
# does per board. Rows whose build label contains "dual-core" may differ from the host
# in SHRINCS signing output (Blockstream's two-core grinding can return another valid
# counter) and must still verify where check_r2.py requires it. Exit status 0 only if
# every row passes. Output: <raw_dir>/check_r4-pi02w.txt.
#
#   r4_pi02w_check.sh [raw_dir]          (default results/raw/pi02w/r4)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RAW="${1:-$ROOT/results/raw/pi02w/r4}"
REF="$ROOT/results/raw/host/r2"
files=( "$RAW"/pi02w-r4-*.csv )
if [ ! -e "${files[0]}" ]; then
    echo "Pi Zero 2 W: no result files in $RAW"
    exit 1
fi
out="$RAW/check_r4-pi02w.txt"
"$ROOT/.venv/bin/python" -I "$HERE/check_r2.py" --ref "$REF/reference-B.csv" \
    --ref "$REF/reference-L.csv" "${files[@]}" > "$out" 2>&1
status=$?
echo "Pi Zero 2 W (${#files[@]} files): $(tail -1 "$out")"
exit $status
