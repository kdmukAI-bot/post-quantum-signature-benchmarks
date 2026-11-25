#!/bin/bash
# Benchmark pass for the Pi Zero W speed variants (harness/linux/Makefile COMPRESS=asm,
# asmrev, or asmrevbe; SHA_API; OPT). Runs on the Pi from /mnt/data/pq-bench/opt, with
# each build's binaries in bin/<build dir>/ (pq_bench and compress_bench). Run it under
# nohup or tmux.
#
#   pi_opt_run.sh PLAN_FILE [TAG]
#
# PLAN_FILE has one run per line, fields separated by '|':
#   <build dir under bin/>|<build label for the CSV>|<op>|<n>[|<swn>]
# Blank lines and lines starting with '#' are skipped.
#
# Writes results_<TAG>_<stamp>.csv (the pq_bench columns) and .log, and saves run 0's
# output of each op under sigs_<TAG>_<stamp>/<build dir>/. Stops the SeedSigner app for
# the pass and restarts it at the end. The log records the ARM clock at the start and end
# of the pass, measured by compress_bench from the CPU cycle counter (this image has no
# vcgencmd, no cpufreq, and no thermal zone, so the temperature cannot be read).
set -u
cd /mnt/data/pq-bench/opt
PLAN="$1"
TAG="${2:-run}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="results_${TAG}_${STAMP}.csv"
LOG="results_${TAG}_${STAMP}.log"
SIGS="sigs_${TAG}_${STAMP}"

clock() {
    local bin
    bin="$(grep -v '^#' "$PLAN" | grep -v '^$' | head -1 | cut -d'|' -f1)"
    echo "$(date +%T) clock check ($1): $(./bin/"$bin"/compress_bench 20000 3 \
        | grep -E '^(compress|compress_soft),' | tr '\n' ' ')" >> "$LOG"
}

seedsigner stop
sleep 2
mkdir -p "$SIGS"
echo "board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified" > "$OUT"
echo "start $(date) plan=$PLAN $(grep -m1 BogoMIPS /proc/cpuinfo)" > "$LOG"
echo "# compress_bench columns: item,n,reps,ns_per_op_median,ns_per_op_min,cycles_per_op_median,mhz,check" >> "$LOG"
clock start

while IFS='|' read -r bin label op n swn; do
    case "$bin" in ''|'#'*) continue ;; esac
    swn="${swn:-2040}"
    mkdir -p "$SIGS/$bin"
    echo "$(date +%T) $bin $op swn=$swn n=$n" >> "$LOG"
    ./bin/"$bin"/pq_bench --board pi0w --build "$label" --op "$op" --swn "$swn" -n "$n" \
        --save "$SIGS/$bin" >> "$OUT" 2>> "$LOG" < /dev/null
done < "$PLAN"

clock end
echo "end $(date)" >> "$LOG"
seedsigner start
echo "done: $OUT" >> "$LOG"
