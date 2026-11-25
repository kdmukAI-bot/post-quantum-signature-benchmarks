#!/usr/bin/env bash
# Round 4: build the level builds for the Waveshare RP2350 Touch LCD 2 (harness/pico), one
# per level, SHRINCS variant, and core count, into
# harness/pico/build-r4-L<level>-<B|L>-dc<0|1>, plus the labeled lattice variation
# build-r4-L3cm4-B-dc0 (c-fn-dsa's Cortex-M4 assembly).
#
#   r4_rp2350_build_all.sh [name ...]     (default: every build)
#
# Level options (methods.html, Levels):
#   L1  portable C (soft), code in flash, -O2
#   L2  accelerator through the SDK's hardware_sha256 functions (sdk), code in flash, -O2
#   L3  see L3_OPTS below
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
L1_OPTS="-DPQB_SLH_COMPRESS=soft -DPQB_TAG=r4-L1"
L2_OPTS="-DPQB_SLH_COMPRESS=sdk -DPQB_TAG=r4-L2"
L3_OPTS="${L3_OPTS:?set L3_OPTS to the screened level-3 options}"
L3_DC1_OPTS="${L3_DC1_OPTS:-$L3_OPTS}"

build() {  # name, options
    echo "== $1"
    bash "$HERE/r4_rp2350_build.sh" "$1" $2 | tail -1
}

names=("$@")
for lvl in 1 2 3; do
    for v in B L; do
        for dc in 0 1; do
            n="r4-L$lvl-$v-dc$dc"
            if [ ${#names[@]} -gt 0 ] && [[ ! " ${names[*]} " == *" $n "* ]]; then
                continue
            fi
            case $lvl in
                1) o="$L1_OPTS" ;;
                2) o="$L2_OPTS" ;;
                3) if [ $dc = 1 ]; then o="$L3_DC1_OPTS"; else o="$L3_OPTS"; fi ;;
            esac
            build "$n" "-DPQB_SHRINCS=$v -DPQB_DUAL_CORE=$dc -DPQB_RUNS=10 $o"
        done
    done
done
n="r4-L3cm4-B-dc0"
if [ ${#names[@]} -eq 0 ] || [[ " ${names[*]} " == *" $n "* ]]; then
    build "$n" "-DPQB_SHRINCS=B -DPQB_DUAL_CORE=0 -DPQB_RUNS=10 -DPQB_FNDSA_CM4=1 ${L3_OPTS/-DPQB_TAG=/-DPQB_TAG=fndsa-cm4-}"
fi
