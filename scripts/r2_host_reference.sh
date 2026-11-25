#!/usr/bin/env bash
# Round 2: host (x86-64) reference outputs for the cross-board correctness gate
# (scripts/check_r2.py) and the attempt counts for the expected-value fits
# (scripts/grind_fit_r2.py). Builds the host binaries if needed (harness/linux/Makefile;
# the lattice code runs its integer floating-point emulation path, as on the boards), then
# writes
#   <out_dir>/reference-B.csv, reference-L.csv  every op, n=100 (self-tests n=10)
#   <out_dir>/mldsa-attempts.csv                ML-DSA signing attempts, messages 0 to
#                                               19999 (COUNT=1 build; same outputs)
#   <out_dir>/pors-fp-prob.txt                  exact PORS+FP acceptance probability
#
#   r2_host_reference.sh <out_dir>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$(mkdir -p "$1" && cd "$1" && pwd)"
mkdir -p "$OUT"
cd "$ROOT/harness/linux"
make SHRINCS=B -j"$(nproc)" >/dev/null
make SHRINCS=L -j"$(nproc)" >/dev/null
make SHRINCS=B COUNT=1 -j"$(nproc)" >/dev/null
HDR="board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind"

ref() {
    local v="$1" bin="build/r2-host-shrincs$1-openssl/pq_bench" out="$OUT/reference-$1.csv"
    local swn
    if [ "$v" = B ]; then swn=2040; else swn=140; fi
    echo "$HDR" > "$out.partial"
    run() { "$bin" --board host --build "host-r2 shrincs-$v" --op "$1" --swn "$2" -n "$3" >> "$out.partial"; }
    run shrincs_selftest "$swn" 10
    if [ "$v" = B ]; then
        run xmss_selftest 0 10
        for op in slh_dsa_sign sphincs40_sign xmss_sign slh_dsa_keygen sphincs40_keygen \
                  xmss_keygen slh_dsa_verify sphincs40_verify xmss_verify; do
            run "$op" 0 100
        done
        run shrincs_sign 2040 100
        for ps in 44 65 87; do
            for kind in keygen sign verify; do
                run "mldsa${ps}_$kind" 0 100
                run "mldsa${ps}_lowram_$kind" 0 100
            done
        done
        for n in 512 1024; do
            for kind in keygen sign verify; do run "fndsa${n}_$kind" 0 100; done
        done
    else
        run shrincs_sign 96 100
        run shrincs_sign 140 100
    fi
    run shrincs_keygen 0 100
    run shrincs_verify "$swn" 100
    run shrincs_verify_stateless "$swn" 100
    run shrincs_sign_stateless "$swn" 100
    mv "$out.partial" "$out"
}

ref B &
ref L &
(
    echo "$HDR" > "$OUT/mldsa-attempts.csv.partial"
    for ps in 44 65 87; do
        build/r2-host-shrincsB-openssl-count/pq_bench --board host --build host-r2-count \
            --op "mldsa${ps}_sign" -n 20000 >> "$OUT/mldsa-attempts.csv.partial"
    done
    mv "$OUT/mldsa-attempts.csv.partial" "$OUT/mldsa-attempts.csv"
) &
"$ROOT/.venv/bin/python" -I "$HERE/pors_fp_prob.py" > "$OUT/pors-fp-prob.txt"
wait
echo "done: $OUT"
