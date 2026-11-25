#!/usr/bin/env bash
# Round 4: build one harness/pico configuration for the Waveshare RP2350 Touch LCD 2 in
# the pinned Docker image (harness/pico/docker/Dockerfile).
#
#   r4_rp2350_build.sh <name> [-DPQB_...=... ...]
#
# Output: harness/pico/build-<name>/ (pqb_rp.elf, pqb_rp.uf2, pqb_rp.elf.map). The
# workspace is mounted at its own path, so the paths in CMake's cache and in the ELF are
# the host's. The build runs as the calling user, at nice 10 with 4 jobs (other builds
# share the host).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
IMAGE="${PQB_RP_IMAGE:-pqb-rp2350:sdk2.3.1-gcc14.2}"
NAME="$1"
shift
B="$ROOT/harness/pico/build-$NAME"
mkdir -p "$B"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$ROOT:$ROOT" -w "$B" "$IMAGE" \
    bash -c "cmake -G Ninja -S '$ROOT/harness/pico' -B '$B' $* > '$B/configure.log' 2>&1 \
             || { tail -30 '$B/configure.log'; exit 1; }; \
             nice -n 10 cmake --build '$B' -j 4 > '$B/build.log' 2>&1 \
             || { grep -E 'error|Error' '$B/build.log' | head -40; exit 1; }; \
             arm-none-eabi-size '$B/pqb_rp.elf'"
