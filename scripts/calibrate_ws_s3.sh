#!/usr/bin/env bash
# Calibration pass on the Waveshare ESP32-S3 Touch LCD 2 running Blockstream's SHRINCS-B
# build of the Jade benchmark firmware. Reproduces the Jade Plus rows of Blockstream's table
# (10 runs each instead of 100). SHRINCS-L rows need a separate -DSHRINCS_L build.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/../.venv/bin/python"
PORT="${PORT:-/dev/serial/by-id/usb-Waveshare_S3_Touch_LCD_2_123456-if00}"
BUILD="${BUILD:-jade-hbs f5c90a5e shrincs-b stackcheck-strong}"
RUNS="${RUNS:-10}"

"$PY" -u "$HERE/wait_for_jade.py" --port "$PORT" --max-wait 300

for op in shrincs_sign slh_dsa_sign sphincs40_sign xmss_sign \
          shrincs_keygen slh_dsa_keygen sphincs40_keygen xmss_keygen; do
    echo "=== $op ($RUNS runs)"
    "$PY" -u "$HERE/run_jade_bench.py" --port "$PORT" --board ws_s3_lcd2 \
        --build "$BUILD" --op "$op" --swn 2040 -n "$RUNS" | grep -vE "aioitertools|BLE scanning"
done
echo "=== done"
