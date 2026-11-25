#!/usr/bin/env bash
# Round 2: configure and build every ESP32 build of the run matrix
# with scripts/esp_opt_build.sh. Build directories:
# harness/esp-idf/build-<s3|p4>-r2-L<level>-<B|L>-dc<0|1>. Re-running rebuilds
# incrementally in the same directories.
#
#   r2_esp_build_all.sh <s3|p4|both> [level ...]      (levels default to 1 2 3)
#
# Level flags (the same as the round-1 builds of each level; see methods.html, Levels):
#   L1  plain-C SHA-256 (soft), direct SHA-256 API, ESP-IDF -O2
#       (CONFIG_COMPILER_OPTIMIZATION_PERF)
#   L2  SHA unit through ESP-IDF's driver functions (hw), direct SHA-256 API, -O2
#   L3  register-level SHA unit access with message-register reuse (hwshadow), the leaner
#       direct API (PQB_DIRECT_FAST), hash-based scheme code in IRAM (PQB_IRAM), -O3
#       (PQB_COPTS), larger caches (sdkconfig.opt-cache)
# Lattice code is compiled into every build with the build's flags and stays in flash.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WHICH="$1"
shift
LEVELS="${*:-1 2 3}"
case "$WHICH" in
    s3) TARGETS="s3" ;;
    p4) TARGETS="p4" ;;
    both) TARGETS="s3 p4" ;;
    *) echo "usage: $0 <s3|p4|both> [level ...]"; exit 2 ;;
esac

status=0
for t in $TARGETS; do
    idf_target="esp32$t"
    for lvl in $LEVELS; do
        for v in B L; do
            for dc in 0 1; do
                b="build-$t-r2-L$lvl-$v-dc$dc"
                common=(-DPQB_SHRINCS=$v -DPQB_SHA_API=direct -DPQB_DUAL_CORE=$dc -DPQB_RUNS=10)
                case "$lvl" in
                    1) extra=(-DPQB_SLH_COMPRESS=soft -DPQB_TAG=r2-L1) ;;
                    2) extra=(-DPQB_SLH_COMPRESS=hw -DPQB_TAG=r2-L2) ;;
                    3) extra=(-DPQB_SLH_COMPRESS=hwshadow -DPQB_DIRECT_FAST=1 -DPQB_IRAM=1
                              -DPQB_COPTS=-O3 -DPQB_TAG=r2-L3-opt-iram-cache-fast-O3
                              "-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.opt-cache") ;;
                    *) echo "unknown level $lvl"; exit 2 ;;
                esac
                echo "=== $(date +%T) $b"
                bash "$HERE/esp_opt_build.sh" "$b" "$idf_target" "${common[@]}" "${extra[@]}" \
                    || status=1
            done
        done
    done
done
exit $status
