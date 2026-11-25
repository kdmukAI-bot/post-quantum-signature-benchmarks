#!/bin/bash
# Round 2: resumable run queue for the Pi Zero W. Runs on the Pi from
# /mnt/data/pq-bench/r2, with each build's binary in bin/<build dir>/pq_bench (copied from
# harness/linux/build/). Start it under nohup or tmux:
#
#   cd /mnt/data/pq-bench/r2 && nohup ./r2_pi_queue.sh plans/pi0w.plan > queue.out 2>&1 &
#
# PLAN_FILE has one job per line, fields separated by '|':
#   <build dir under bin/>|<build label for the CSV>|<op>|<n>[|<swn>]
# The label should name the level and the SHRINCS variant (for example
# "r2-L3 shrincs-B asmrevbe-apinative-opto3-lto"); the correctness gate matches SHRINCS
# rows by "shrincs-B" / "shrincs-L" in it. Blank lines and lines starting with '#' are
# skipped.
#
# Each line writes, with <level> the label's first word (for example r2-L3 or r2-L3-mem)
# and <build> the build dir minus its "r2-armv6-" prefix,
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
cd /mnt/data/pq-bench/r2
PLAN="$1"
DONE="$PLAN.done"
mkdir -p results
touch "$DONE"
LOG=results/queue.log
HDR="board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind"

for f in results/*.partial; do
    [ -e "$f" ] && mv "$f" "${f%.partial}.aborted"
done

seedsigner stop
trap 'seedsigner start; echo "$(date "+%F %T") queue exit, app started" >> "$LOG"' EXIT
sleep 2
echo "$(date '+%F %T') queue start plan=$PLAN $(grep -m1 BogoMIPS /proc/cpuinfo)" >> "$LOG"

while IFS='|' read -r bin label op n swn; do
    case "$bin" in ''|'#'*) continue ;; esac
    line="$bin|$label|$op|$n${swn:+|$swn}"
    if grep -qxF "$line" "$DONE"; then
        continue
    fi
    stamp="$(date +%Y%m%d_%H%M%S)"
    out="results/pi0w-${label%% *}-${bin#r2-armv6-}-$op${swn:+-swn$swn}-n$n-$stamp.csv"
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
