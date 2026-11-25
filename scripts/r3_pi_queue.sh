#!/bin/bash
# Round 3: resumable run queue for the Pi Zero W. A copy of scripts/r2_pi_queue.sh with
# three changes: it works in /mnt/data/pq-bench/r3, strips the "r3-armv6-" prefix from
# build directories in result names, and runs the round-1 clock check (compress_bench
# from the round-1 level-3 build, CPU cycle counter against wall time) right after the
# app stops and again before it starts, appending both readings to
# results/clock_checks.txt. Runs on the Pi with each build's binary in
# bin/<build dir>/pq_bench (copied from harness/linux/build/). Start it under nohup or
# tmux:
#
#   cd /mnt/data/pq-bench/r3 && nohup ./r3_pi_queue.sh plans/pi0w.plan > queue.out 2>&1 &
#
# PLAN_FILE has one job per line, fields separated by '|':
#   <build dir under bin/>|<build label for the CSV>|<op>|<n>[|<swn>]
# The label should name the level and the SHRINCS variant (for example
# "r3-L3 shrincs-B asmrevbe-apinative-opto3-lto"); the correctness gate matches SHRINCS
# rows by "shrincs-B" / "shrincs-L" in it. Blank lines and lines starting with '#' are
# skipped.
#
# Each line writes, with <level> the label's first word (for example r3-L3) and <build>
# the build dir minus its "r3-armv6-" prefix,
#   results/pi0w-<level>-<build>-<op>[-swn<swn>]-n<n>-<stamp>.csv
# (round-2 columns, with a header), first as .partial, renamed when the line completes;
# the line is then appended to <plan>.done. A rerun skips lines listed there, so the queue
# can be killed and restarted; a .partial file left by an interrupted line is renamed
# .aborted and the line runs again. results/queue.log records each line's start and end,
# the load average, and BogoMIPS (this image has no cpufreq or thermal interface).
#
# The SeedSigner app is stopped for the whole queue and started again when the queue
# ends, however it ends (EXIT trap).
set -u
cd /mnt/data/pq-bench/r3
PLAN="$1"
DONE="$PLAN.done"
CLOCK_BIN="${CLOCK_BIN:-/mnt/data/pq-bench/opt/bin/armv6-shrincsB-asmrevbe-apinative-opto3-lto/compress_bench}"
mkdir -p results
touch "$DONE"
LOG=results/queue.log
CLOCK_LOG=results/clock_checks.txt
HDR="board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind"

clock() {
    [ -s "$CLOCK_LOG" ] || echo "# compress_bench columns: item,n,reps,ns_per_op_median,ns_per_op_min,cycles_per_op_median,mhz,check" > "$CLOCK_LOG"
    if [ -x "$CLOCK_BIN" ]; then
        echo "$(date '+%F %T') clock check ($1, app stopped, load $(cut -d' ' -f1-3 /proc/loadavg)): $("$CLOCK_BIN" 20000 3 \
            | grep -E '^(compress|compress_soft),' | tr '\n' ' ')" >> "$CLOCK_LOG"
    else
        echo "$(date '+%F %T') clock check ($1): $CLOCK_BIN not found" >> "$CLOCK_LOG"
    fi
}

for f in results/*.partial; do
    [ -e "$f" ] && mv "$f" "${f%.partial}.aborted"
done

seedsigner stop
trap 'clock "queue end"; seedsigner start; echo "$(date "+%F %T") queue exit, app started" >> "$LOG"' EXIT
sleep 2
clock "queue start"
echo "$(date '+%F %T') queue start plan=$PLAN $(grep -m1 BogoMIPS /proc/cpuinfo)" >> "$LOG"

while IFS='|' read -r bin label op n swn; do
    case "$bin" in ''|'#'*) continue ;; esac
    line="$bin|$label|$op|$n${swn:+|$swn}"
    if grep -qxF "$line" "$DONE"; then
        continue
    fi
    stamp="$(date +%Y%m%d_%H%M%S)"
    out="results/pi0w-${label%% *}-${bin#r3-armv6-}-$op${swn:+-swn$swn}-n$n-$stamp.csv"
    echo "$(date '+%F %T') start $line load=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$LOG"
    echo "$HDR" > "$out.partial"
    ./bin/"$bin"/pq_bench --board pi0w --build "$label" --op "$op" --swn "${swn:-2040}" \
        -n "$n" >> "$out.partial" 2>> "$LOG" < /dev/null
    status=$?
    if [ "$status" -eq 0 ]; then
        mv "$out.partial" "$out"
        echo "$line" >> "$DONE"
        echo "$(date '+%F %T') done $line -> $out" >> "$LOG"
    else
        mv "$out.partial" "${out}.failed"
        echo "$(date '+%F %T') FAILED $line (exit status $status) -> $out.failed" >> "$LOG"
    fi
done < "$PLAN"
echo "$(date '+%F %T') queue end" >> "$LOG"
