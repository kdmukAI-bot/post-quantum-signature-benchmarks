#!/usr/bin/env bash
# Configure and build one harness/esp-idf variant in Docker (ESP-IDF v5.5.5).
# Usage: esp_opt_build.sh <build_dir_name> <esp32s3|esp32p4> [-DNAME=VALUE ...]
# The -D options go to idf.py unchanged, e.g.
#   esp_opt_build.sh build-s3-opt-B-hwreg-dc0-r1 esp32s3 -DPQB_SHRINCS=B \
#       -DPQB_SLH_COMPRESS=hwreg -DPQB_SHA_API=direct -DPQB_RUNS=1
# The build directory is created under harness/esp-idf/ and keeps its own sdkconfig.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BUILD="$1"
TARGET="$2"
shift 2
IMAGE="ghcr.io/kdmukai-bot/seedsigner-micropython-builder-base:idf-v5.5.5"

mkdir -p "$ROOT/var"  # build logs (not committed)
ARGS=""
for a in "$@"; do
    ARGS="$ARGS $(printf '%q' "$a")"
done

mkdir -p "$ROOT/build"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$ROOT:/work" \
    -w /work/harness/esp-idf "$IMAGE" bash -lc "source /opt/toolchains/esp-idf/export.sh >/dev/null 2>&1 && \
    idf.py -B $BUILD -DIDF_TARGET=$TARGET -DSDKCONFIG=$BUILD/sdkconfig $ARGS build" \
    > "$ROOT/build/esp-$BUILD.log" 2>&1 || {
    tail -40 "$ROOT/build/esp-$BUILD.log"
    echo "BUILD FAILED: $BUILD"
    exit 1
}
grep -E "binary size|Project build complete" "$ROOT/build/esp-$BUILD.log" | head -3
