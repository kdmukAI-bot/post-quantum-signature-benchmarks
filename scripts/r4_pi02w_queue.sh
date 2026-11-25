#!/bin/bash
# Round 4: resumable run queue for the Pi Zero 2 W. Adapted from scripts/r3_pi_queue.sh
# (Pi Zero W); the changes:
#   - it works in its own directory (where scripts/r4_pi02w_deploy.sh puts it), strips
#     the "r4-pi02w-" prefix from build directories in result names, and passes
#     --board pi02w;
#   - the clock check runs compress_bench from the level-3 build deployed with the queue
#     (CLOCK_BIN), and it also records the CPU frequency, governor, temperature, and the
#     firmware's throttling flags where the image exposes them;
#   - each queue.log start line carries the same hardware state (sysfs reads, and the
#     firmware's ARM clock and temperature through vcgencmd where present; images without
#     cpufreq or a thermal zone show "na" for those fields);
#   - while the queue runs, the cpufreq governor is set to GOVERNOR (default
#     "performance") on every core that has one, and the previous governors are restored
#     at the end ("keep" leaves them alone); with "performance" every run starts at the
#     full clock instead of at the governor's idle step.
# Start it under nohup:
#
#   cd <dir> && nohup sh ./r4_pi02w_queue.sh plans/pi02w.plan > queue.out 2>&1 < /dev/null &
#
# Results go to results/ (RESULTS=<dir> for another directory, used for the screen).
#
# PLAN_FILE has one job per line, fields separated by '|':
#   <build dir under bin/>|<build label for the CSV>|<op>|<n>[|<swn>]
# The label names the level and SHRINCS variant (for example "r4-L3 shrincs-B ..."); the
# correctness gate matches SHRINCS rows by "shrincs-B" / "shrincs-L" in it, and treats
# rows whose label contains "dual-core" as two-core output. Blank lines and lines
# starting with '#' are skipped.
#
# Each line writes, with <level> the label's first word and <build> the build dir minus
# its "r4-pi02w-" prefix,
#   results/pi02w-<level>-<build>-<op>[-swn<swn>]-n<n>-<stamp>.csv
# (round-2 columns, with a header), first as .partial, renamed when the line completes;
# the line is then appended to <plan>.done. A rerun skips lines listed there, so the queue
# can be killed and restarted; a .partial file left by an interrupted line is renamed
# .aborted and the line runs again. A line whose pq_bench fails is renamed .failed and
# not retried within the same pass. Two further ops, for screening: "cbench" runs the
# build's compress_bench with n compressions per item ("cbench-armcap0" the same with
# OPENSSL_armcap=0), and "probe" runs bin/<build>/armcap_probe (with and without
# OPENSSL_armcap=0); both write .txt files.
#
# Throttling: with STOP_ON_THROTTLE=1 (the default), the queue reads the firmware's
# get_throttled flags before and after every line. A nonzero value before a line stops the
# queue; after a line it also renames that line's output to .throttled (not added to the
# done-list, so it runs again on a restart). Each done line carries the hardware state at
# its end.
#
# The SeedSigner app is stopped (APP_STOP) for the whole queue and started again
# (APP_START) when the queue ends, however it ends (EXIT trap).
set -u
cd "$(dirname "$0")"
PLAN="$1"
DONE="$PLAN.done"
CLOCK_BIN="${CLOCK_BIN:-bin/clock/compress_bench}"
APP_STOP="${APP_STOP:-seedsigner stop}"
APP_START="${APP_START:-seedsigner start}"
GOVERNOR="${GOVERNOR:-performance}"
STOP_ON_THROTTLE="${STOP_ON_THROTTLE:-1}"
RES="${RESULTS:-results}"
mkdir -p "$RES"
touch "$DONE"
LOG="$RES/queue.log"
CLOCK_LOG="$RES/clock_checks.txt"
HDR="board,build,op,swn,run,wall_s,cpu_s,out_bytes,out_sha256,verified,stack_peak_bytes,heap_peak_bytes,heap_min_free_bytes,grind"
THROTTLED=/sys/devices/platform/soc/soc:firmware/get_throttled

rd() { cat "$1" 2>/dev/null || echo na; }

# The firmware's throttling flags (hex): bits 0 to 3 are current under-voltage, frequency
# capping, throttling, and soft temperature limit; bits 16 to 19 record the same since
# boot. Prints the value, or nothing on an image without the interface.
throttle_flags() {
    [ -r "$THROTTLED" ] && cat "$THROTTLED" 2>/dev/null
}

hw() {
    local f="" g=""
    for c in /sys/devices/system/cpu/cpu[0-9]*; do
        f="$f$(rd "$c/cpufreq/scaling_cur_freq"),"
        g="$g$(rd "$c/cpufreq/scaling_governor"),"
    done
    local arm="na" vt="na"
    if command -v vcgencmd > /dev/null 2>&1; then
        arm="$(vcgencmd measure_clock arm 2>/dev/null | cut -d= -f2)"
        vt="$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2)"
    fi
    echo "khz=${f%,} gov=${g%,} temp_mC=$(rd /sys/class/thermal/thermal_zone0/temp) throttled=$(rd "$THROTTLED") arm_hz=$arm vc_temp=$vt"
}

clock() {
    [ -s "$CLOCK_LOG" ] || echo "# compress_bench columns: item,n,reps,ns_per_op_median,ns_per_op_min,cycles_per_op_median,mhz,check" > "$CLOCK_LOG"
    local before res after
    before="$(hw)"
    if [ -x "$CLOCK_BIN" ]; then
        res="$("$CLOCK_BIN" 20000 3 | grep -E '^(# perf|compress|compress_soft|asm_blocks),?' | tr '\n' ' ')"
    else
        res="$CLOCK_BIN not found"
    fi
    after="$(hw)"
    echo "$(date '+%F %T') clock check ($1, app stopped, load $(cut -d' ' -f1-3 /proc/loadavg)): $res| before: $before | after: $after" >> "$CLOCK_LOG"
}

SAVED_GOV=""
set_governor() {
    [ "$GOVERNOR" = keep ] && return
    for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
        [ -w "$c/scaling_governor" ] || continue
        SAVED_GOV="$SAVED_GOV $c=$(cat "$c/scaling_governor")"
        echo "$GOVERNOR" > "$c/scaling_governor"
    done
}
restore_governor() {
    for e in $SAVED_GOV; do
        echo "${e#*=}" > "${e%%=*}/scaling_governor"
    done
}

for f in "$RES"/*.partial; do
    [ -e "$f" ] && mv "$f" "${f%.partial}.aborted"
done

$APP_STOP
trap 'clock "queue end"; restore_governor; $APP_START; echo "$(date "+%F %T") queue exit, governors restored, app started; $(hw)" >> "$LOG"' EXIT
set_governor
sleep 2
clock "queue start"
echo "$(date '+%F %T') queue start plan=$PLAN governor=$GOVERNOR saved=[${SAVED_GOV# }] $(hw)" >> "$LOG"

while IFS='|' read -r bin label op n swn; do
    case "$bin" in ''|'#'*) continue ;; esac
    line="$bin|$label|$op|$n${swn:+|$swn}"
    if grep -qxF "$line" "$DONE"; then
        continue
    fi
    tf="$(throttle_flags)"
    if [ "$STOP_ON_THROTTLE" = 1 ] && [ -n "$tf" ] && [ "$tf" != 0 ]; then
        echo "$(date '+%F %T') THROTTLED before $line (get_throttled=$tf); queue stopped" >> "$LOG"
        exit 3
    fi
    stamp="$(date +%Y%m%d_%H%M%S)"
    out="$RES/pi02w-${label%% *}-${bin#r4-pi02w-}-$op${swn:+-swn$swn}-n$n-$stamp.csv"
    echo "$(date '+%F %T') start $line load=$(cut -d' ' -f1-3 /proc/loadavg) $(hw)" >> "$LOG"
    case "$op" in
    cbench|cbench-armcap0)
        # compress_bench of the build, n compressions per item, 5 repetitions; the
        # armcap0 form sets OPENSSL_armcap=0, so libcrypto runs its integer code
        out="${out%.csv}.txt"
        if [ "$op" = cbench-armcap0 ]; then
            OPENSSL_armcap=0 ./bin/"$bin"/compress_bench "$n" 5 > "$out.partial" 2>> "$LOG" < /dev/null
        else
            ./bin/"$bin"/compress_bench "$n" 5 > "$out.partial" 2>> "$LOG" < /dev/null
        fi
        status=$? ;;
    probe)
        out="${out%.csv}.txt"
        { ./bin/"$bin"/armcap_probe && OPENSSL_armcap=0 ./bin/"$bin"/armcap_probe; } \
            > "$out.partial" 2>> "$LOG" < /dev/null
        status=$? ;;
    *)
        echo "$HDR" > "$out.partial"
        ./bin/"$bin"/pq_bench --board pi02w --build "$label" --op "$op" --swn "${swn:-2040}" \
            -n "$n" >> "$out.partial" 2>> "$LOG" < /dev/null
        status=$? ;;
    esac
    tf="$(throttle_flags)"
    if [ "$STOP_ON_THROTTLE" = 1 ] && [ -n "$tf" ] && [ "$tf" != 0 ]; then
        mv "$out.partial" "$out.throttled"
        echo "$(date '+%F %T') THROTTLED during $line (get_throttled=$tf) -> $out.throttled; queue stopped $(hw)" >> "$LOG"
        exit 3
    fi
    if [ "$status" -eq 0 ]; then
        mv "$out.partial" "$out"
        echo "$line" >> "$DONE"
        echo "$(date '+%F %T') done $line -> $out $(hw)" >> "$LOG"
    else
        mv "$out.partial" "${out}.failed"
        echo "$(date '+%F %T') FAILED $line (exit status $status) -> $out.failed" >> "$LOG"
    fi
done < "$PLAN"
echo "$(date '+%F %T') queue end $(hw)" >> "$LOG"
