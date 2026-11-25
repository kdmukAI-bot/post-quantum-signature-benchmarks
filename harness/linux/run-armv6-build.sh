#!/bin/bash
# Runs make for the Pi Zero (TARGET=armv6) inside the seedsigner-raspi-lvgl sdk-armv6
# image, which holds the cross-compiler and the sysroot (OpenSSL 3.4.1 headers,
# libcrypto.so, and libcrypto.a). The repository is mounted at /work and the build runs as
# the calling user, so build directories stay owned by that user.
#
#   harness/linux/run-armv6-build.sh [make arguments...]
#   harness/linux/run-armv6-build.sh COMPRESS=asmrev SHA_API=native OPT=nossp cbench
set -euo pipefail
IMAGE="${PQB_SDK_IMAGE:-ghcr.io/kdmukai-bot/seedsigner-raspi-lvgl/sdk-armv6:ss-os-0.8.0-81-gbfbd791}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT:/work" -w /work/harness/linux "$IMAGE" \
    make TARGET=armv6 -j"$(nproc)" "$@"
