#!/usr/bin/env bash
# Round 4, Pi Zero 2 W: correctness check of the r4-pi02w builds on the host, under
# qemu-arm user-mode emulation (CPU model "max", an ARMv8-A core in AArch32 state; qemu
# has no Cortex-A53 model for 32-bit user mode). The SDK sysroot (glibc, libcrypto) is
# copied out of the sdk-pi02w image once. OPENSSL_armcap=1 makes libcrypto take its NEON
# SHA-256 path, as it does on the Pi Zero 2 W (qemu's "max" core also reports the SHA-256
# instructions, which the Pi Zero 2 W does not have). Times under emulation mean nothing;
# only the outputs are checked: scripts/check_r2.py against the host reference.
#
#   r4_pi02w_qemu_check.sh BUILD_DIR...      (directory names under harness/linux/build/)
#
# Per build: verification ops n=10; lattice ops n=3 (one-core builds); SLH-DSA, SPHINCS+,
# SHRINCS, and XMSS key generation and signing at n=1 or 2; self-tests n=1; SHRINCS
# stateless signing n=1 (skipped for memory builds). Results: build/pi02w-qemu/<build>.csv
# and build/pi02w-qemu/check.txt; jobs whose emulation failed (no output) are listed in
# build/pi02w-qemu/failed-jobs.txt and make the exit status nonzero. Runs PQB_QEMU_JOBS
# emulations at a time (default 4).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
IMAGE="${PQB_SDK_IMAGE:-ghcr.io/kdmukai-bot/seedsigner-raspi-lvgl/sdk-pi02w:ss-os-0.8.0-81-gbfbd791}"
OUT="$ROOT/build/pi02w-qemu"
SYSROOT="$ROOT/build/pi02w-qemu-sysroot"
JOBS="${PQB_QEMU_JOBS:-4}"
mkdir -p "$OUT" "$OUT/parts"
if [ ! -e "$SYSROOT/lib/ld-linux-armhf.so.3" ]; then
    mkdir -p "$SYSROOT"
    docker run --rm --user "$(id -u):$(id -g)" -v "$SYSROOT:/out" "$IMAGE" sh -c \
        'cd /output/host/arm-Buildroot-linux-gnueabihf/sysroot && tar cf - lib usr/lib/libcrypto.so* | tar xf - -C /out'
fi

VERIFY_B="slh_dsa_verify sphincs40_verify xmss_verify shrincs_verify shrincs_verify_stateless"
VERIFY_L="shrincs_verify shrincs_verify_stateless"
LATTICE=""
for ps in 44 65 87; do for var in "" _lowram; do for k in keygen sign verify; do
    LATTICE="$LATTICE mldsa${ps}${var}_$k"; done; done; done
for n in 512 1024; do for k in keygen sign verify; do LATTICE="$LATTICE fndsa${n}_$k"; done; done

jobs_for() {   # build -> lines "build|label|op|n|swn"
    local b="$1" v label swn
    case "$b" in *shrincsB*) v=B; swn=2040 ;; *shrincsL*) v=L; swn=140 ;; esac
    label="qemu shrincs-$v ${b#r4-pi02w-shrincs?-}"
    case "$b" in *-dc1*) label="$label dual-core" ;; esac
    if [ "$v" = B ]; then
        for op in $VERIFY_B; do echo "$b|$label|$op|10|$swn"; done
        case "$b" in *-dc1*) ;; *) for op in $LATTICE; do echo "$b|$label|$op|3|"; done ;; esac
        for op in slh_dsa_sign sphincs40_sign; do echo "$b|$label|$op|2|"; done
        for op in slh_dsa_keygen sphincs40_keygen shrincs_keygen xmss_keygen xmss_sign \
                xmss_selftest; do echo "$b|$label|$op|1|"; done
        echo "$b|$label|shrincs_sign|2|2040"
        echo "$b|$label|shrincs_selftest|1|2040"
    else
        for op in $VERIFY_L; do echo "$b|$label|$op|10|$swn"; done
        echo "$b|$label|shrincs_keygen|1|"
        echo "$b|$label|shrincs_sign|2|96"
        echo "$b|$label|shrincs_sign|2|140"
        echo "$b|$label|shrincs_selftest|1|140"
    fi
    case "$b" in *-mem) ;; *) echo "$b|$label|shrincs_sign_stateless|1|$swn" ;; esac
}

run_one() {
    IFS='|' read -r b label op n swn <<< "$1"
    local part="$OUT/parts/$b--$op${swn:+-swn$swn}.csv"
    [ -s "$part" ] && return 0
    OPENSSL_armcap=1 qemu-arm -cpu max -L "$SYSROOT" "$ROOT/harness/linux/build/$b/pq_bench" \
        --board qemu --build "$label" --op "$op" --swn "${swn:-2040}" -n "$n" \
        > "$part.tmp" 2> "$part.err" && mv "$part.tmp" "$part"
}
export -f run_one
export OUT SYSROOT ROOT

for b in "$@"; do jobs_for "$b"; done | xargs -d '\n' -P "$JOBS" -I{} bash -c 'run_one "$@"' _ {}
files=()
for b in "$@"; do
    cat "$OUT"/parts/"$b"--*.csv > "$OUT/$b.csv" 2>/dev/null
    files+=("$OUT/$b.csv")
done
REF="$ROOT/results/raw/host/r2"
"$ROOT/.venv/bin/python" -I "$HERE/check_r2.py" --ref "$REF/reference-B.csv" \
    --ref "$REF/reference-L.csv" "${files[@]}" > "$OUT/check.txt" 2>&1
status=$?
# A job whose emulation failed leaves no part file, so the gate never sees its rows: count
# those jobs separately (their stderr is kept in parts/*.err).
failed=0
for b in "$@"; do
    while IFS= read -r job; do
        IFS='|' read -r jb label op n swn <<< "$job"
        [ -s "$OUT/parts/$jb--$op${swn:+-swn$swn}.csv" ] || { echo "FAILED JOB $job"; failed=$((failed + 1)); }
    done < <(jobs_for "$b")
done | tee "$OUT/failed-jobs.txt" | tail -5
failed=$(grep -c '^FAILED JOB' "$OUT/failed-jobs.txt")
tail -1 "$OUT/check.txt"
echo "emulated jobs without output: $failed"
[ "$failed" -eq 0 ] || status=1
exit $status
