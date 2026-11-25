#!/usr/bin/env bash
# Round 4: builds the Pi Zero 2 W binaries (harness/linux/build/r4-pi02w-*) inside the
# seedsigner-raspi-lvgl sdk-pi02w image, which holds the cross-compiler (GCC 13.3.0,
# Buildroot 2024.11.4, whose wrapper adds -mcpu=cortex-a53 -mfpu=neon-vfpv4
# -mfloat-abi=hard -marm) and the sysroot (glibc 2.40, OpenSSL 3.4.1 headers, libcrypto.so
# and libcrypto.a). Make options: harness/linux/Makefile header. The repository is mounted
# at /work and the build runs as the calling user. Builds run one after another with
# PQB_JOBS parallel jobs each (default 4), so other work on the host keeps some CPU.
#
#   r4_pi02w_build_all.sh SET...
#
# Sets (S is B and L):
#   levels    L1 r4-pi02w-shrincsS-soft-apidirect          COMPRESS=soft SHA_API=direct
#             L2 r4-pi02w-shrincsS-openssl                 (OpenSSL 3.4.1 through its API)
#             (each with compress_bench)
#   l3cand    the level-3 candidates, each with compress_bench (make ... cbench):
#             r4-pi02w-shrincsS-asmrevbe-apinative-opto3-lto   integer code (the Pi Zero W
#                                                              level-3 recipe)
#             r4-pi02w-shrincsS-asmneonbe-apinative-opto3-lto  NEON code, big-endian copy
#                                                              for SLH-DSA
#             r4-pi02w-shrincsB-asmneon-apinative-opto3-lto    NEON code, C wrapper for
#                                                              SLH-DSA (screen only)
#   dual      two-core builds of L1, L2, and the level-3 build named by the environment
#             variable L3 (default asmrevbe-apinative-opto3-lto): DUAL_CORE=1 (one
#             thread per Jade task, directory suffix -dc1), or with DUAL=pool,
#             DUAL_CORE=pool (one persistent worker thread, suffix -dc1pool)
#   mem       memory builds (MEM=1, suffix -mem) of L1, L2, and that level-3 build
#   l2static  level 2 with the SDK's libcrypto.a linked statically (OPT=static, directory
#             r4-pi02w-shrincsS-openssl-optstatic), for an image whose libcrypto.so.3
#             differs from the SDK's: one core, both two-core forms, and memory builds
#   probe     scripts/r4_pi02w_armcap_probe.c, linked with libcrypto.a, into
#             r4-pi02w-armcap-probe/armcap_probe
#   screen    extra screening builds: level-3 candidates at -O2 without LTO, the
#             integer candidate with -O3 only, and its two-core builds (both forms)
set -euo pipefail
IMAGE="${PQB_SDK_IMAGE:-ghcr.io/kdmukai-bot/seedsigner-raspi-lvgl/sdk-pi02w:ss-os-0.8.0-81-gbfbd791}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOBS="${PQB_JOBS:-4}"
L3="${L3:-asmrevbe-apinative-opto3-lto}"

mk() {
    echo "== make $*"
    docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT:/work" -w /work/harness/linux "$IMAGE" \
        make TARGET=pi02w ROUND=r4 -j"$JOBS" "$@"
}

# make arguments for a build-name suffix of the level-3 kind
l3args() {
    case "$1" in
        asmrevbe-apinative-opto3-lto) echo "COMPRESS=asmrevbe SHA_API=native OPT=o3-lto" ;;
        asmneonbe-apinative-opto3-lto) echo "COMPRESS=asmneonbe SHA_API=native OPT=o3-lto" ;;
        asmneon-apinative-opto3-lto) echo "COMPRESS=asmneon SHA_API=native OPT=o3-lto" ;;
        *) echo "unknown level-3 build: $1" >&2; exit 2 ;;
    esac
}

for set in "$@"; do
    case "$set" in
    levels)
        for s in B L; do
            mk SHRINCS=$s COMPRESS=soft SHA_API=direct cbench
            mk SHRINCS=$s cbench
        done ;;
    l3cand)
        for s in B L; do
            mk SHRINCS=$s $(l3args asmrevbe-apinative-opto3-lto) cbench
            mk SHRINCS=$s $(l3args asmneonbe-apinative-opto3-lto) cbench
        done
        mk SHRINCS=B $(l3args asmneon-apinative-opto3-lto) cbench ;;
    dual|mem)
        if [ "$set" = dual ]; then extra=DUAL_CORE=${DUAL:-1}; else extra=MEM=1; fi
        for s in B L; do
            mk SHRINCS=$s COMPRESS=soft SHA_API=direct $extra
            mk SHRINCS=$s $extra
            mk SHRINCS=$s $(l3args "$L3") $extra
        done ;;
    l2static)
        for s in B L; do
            mk SHRINCS=$s OPT=static cbench
            mk SHRINCS=$s OPT=static DUAL_CORE=1
            mk SHRINCS=$s OPT=static DUAL_CORE=pool
            mk SHRINCS=$s OPT=static MEM=1
        done ;;
    probe)
        echo "== armcap probe"
        mkdir -p "$ROOT/harness/linux/build/r4-pi02w-armcap-probe"
        docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT:/work" -w /work "$IMAGE" \
            /output/host/bin/arm-Buildroot-linux-gnueabihf-gcc -O2 -Wall \
            -o harness/linux/build/r4-pi02w-armcap-probe/armcap_probe scripts/r4_pi02w_armcap_probe.c \
            -Wl,-Bstatic -lcrypto -Wl,-Bdynamic -ldl -pthread ;;
    screen)
        mk SHRINCS=B COMPRESS=asmrevbe SHA_API=native cbench
        mk SHRINCS=B COMPRESS=asmneonbe SHA_API=native cbench
        mk SHRINCS=B COMPRESS=asmrevbe SHA_API=native OPT=o3 cbench
        mk SHRINCS=B $(l3args asmrevbe-apinative-opto3-lto) DUAL_CORE=1
        mk SHRINCS=B $(l3args asmrevbe-apinative-opto3-lto) DUAL_CORE=pool ;;
    *)
        echo "unknown set: $set" >&2; exit 2 ;;
    esac
done
