#!/bin/bash
# Full benchmark pass on the Pi Zero W (dev SeedSigner OS image). Copy to
# /mnt/data/pq-bench next to the pq_bench_* binaries and run inside tmux.
# Stops the SeedSigner app for clean timing and restarts it at the end.
set -u
cd /mnt/data/pq-bench
N="${N:-100}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="results_${STAMP}.csv"
LOG="results_${STAMP}.log"
TOOLCHAIN="gcc13.3 -O2 openssl3.4.1"

temp() { cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null; }
run() {
    local bin="$1" build="$2" op="$3" n="$4" swn="${5:-2040}"
    echo "$(date +%T) $build $op swn=$swn n=$n temp=$(temp)" >> "$LOG"
    "./pq_bench_$bin" --board pi0w --build "$build; $TOOLCHAIN" --op "$op" --swn "$swn" \
        -n "$n" --save sigs >> "$OUT"
}

seedsigner stop
mkdir -p sigs
echo "board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified" > "$OUT"
echo "start $(date) temp=$(temp) $(grep -m1 BogoMIPS /proc/cpuinfo)" > "$LOG"

B=armv6-shrincsB-openssl
L=armv6-shrincsL-openssl
S=armv6-shrincsB-soft

# Correctness first: consistent keys, sign, verify
run "$B" "shrincs-b openssl" shrincs_selftest 3
run "$L" "shrincs-l openssl" shrincs_selftest 3 140
run "$B" "openssl" xmss_selftest 3

# Blockstream's table rows (same keys, inputs, and parameter sets as the Jade firmware)
run "$B" "openssl" slh_dsa_sign "$N"
run "$B" "openssl" sphincs40_sign "$N"
run "$L" "shrincs-l openssl" shrincs_sign "$N" 96
run "$L" "shrincs-l openssl" shrincs_sign "$N" 140
run "$B" "shrincs-b openssl" shrincs_sign "$N" 2040
run "$B" "openssl" xmss_sign "$N"
run "$B" "openssl" slh_dsa_keygen "$N"
run "$B" "openssl" sphincs40_keygen "$N"
run "$L" "shrincs-l openssl" shrincs_keygen "$N"
run "$B" "shrincs-b openssl" shrincs_keygen "$N"
run "$B" "openssl" xmss_keygen "$N"

# How much OpenSSL's ARM assembly SHA-256 helps SLH-DSA (plain-C compression instead)
run "$S" "plain-c compress" slh_dsa_sign 10
run "$S" "plain-c compress" sphincs40_sign 10

echo "end $(date) temp=$(temp)" >> "$LOG"
seedsigner start
echo "done: $OUT" >> "$LOG"
