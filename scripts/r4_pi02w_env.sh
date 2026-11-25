#!/usr/bin/env bash
# Round 4: records the Pi Zero 2 W's environment over one ssh session (run it before or
# after a queue, never during one) and compares the board's C library and libcrypto with
# the sdk-pi02w image the binaries were built against. Output:
# results/raw/pi02w/r4/environment-<stamp>.txt (path printed at the end).
#
#   r4_pi02w_env.sh [label]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOST="${PI_HOST:-pi02w}"
DIR="${PI02W_DIR:-/mnt/data/pq-bench/r4}"
IMAGE="${PQB_SDK_IMAGE:-ghcr.io/kdmukai-bot/seedsigner-raspi-lvgl/sdk-pi02w:ss-os-0.8.0-81-gbfbd791}"
OUT="$ROOT/results/raw/pi02w/r4"
mkdir -p "$OUT"
F="$OUT/environment-$(date +%Y%m%d_%H%M%S)${1:+-$1}.txt"
{
echo "# Pi Zero 2 W environment, $(date '+%F %T %Z') (host clock), ssh alias $HOST"
ssh -o BatchMode=yes "$HOST" 'sh -s' <<'REMOTE'
sec() { echo; echo "## $*"; }
rd() { for f in "$@"; do [ -e "$f" ] && echo "$f: $(cat "$f" 2>/dev/null | tr '\0\n' ' ')"; done; }
sec date; date -u '+%F %T UTC'; uptime
sec uname; uname -a
sec os-release; cat /etc/os-release 2>/dev/null
sec device-tree model; tr -d '\0' < /proc/device-tree/model 2>/dev/null; echo
sec cpuinfo; cat /proc/cpuinfo
sec memory; free 2>/dev/null; grep -E 'MemTotal|SwapTotal' /proc/meminfo
sec cpufreq
for c in /sys/devices/system/cpu/cpu[0-9]*; do
  rd $c/cpufreq/scaling_driver $c/cpufreq/scaling_governor $c/cpufreq/scaling_available_governors \
     $c/cpufreq/scaling_cur_freq $c/cpufreq/cpuinfo_min_freq $c/cpufreq/cpuinfo_max_freq \
     $c/cpufreq/scaling_min_freq $c/cpufreq/scaling_max_freq $c/cpufreq/scaling_available_frequencies
done
ls /sys/devices/system/cpu/cpufreq 2>/dev/null
sec thermal and throttling
rd /sys/class/thermal/thermal_zone*/type /sys/class/thermal/thermal_zone*/temp \
   /sys/devices/platform/soc/soc:firmware/get_throttled
for h in /sys/class/hwmon/hwmon*; do rd $h/name $h/in0_lcrit_alarm; done
command -v vcgencmd && for a in get_throttled "measure_clock arm" measure_temp "measure_volts core" \
  "get_config arm_freq" "get_config over_voltage" "get_config force_turbo"; do echo "vcgencmd $a: $(vcgencmd $a 2>&1)"; done
sec kernel settings; rd /proc/sys/kernel/randomize_va_space /proc/sys/kernel/perf_event_paranoid /proc/cmdline
ls /sys/bus/event_source/devices 2>/dev/null
sec libraries
ls -l /lib/libc.so* /lib/ld-linux* /usr/lib/libcrypto.so* /usr/lib/libssl.so* 2>/dev/null
sha256sum /lib/libc.so.6 /lib/ld-linux-armhf.so.3 /usr/lib/libcrypto.so.3 2>/dev/null
/lib/libc.so.6 2>&1 | head -1
command -v openssl && openssl version -a 2>&1 | head -3
strings /usr/lib/libcrypto.so.3 2>/dev/null | grep -m1 '^OpenSSL 3' 
sec processes; ps 2>/dev/null | head -40 || ps -ef | head -40
sec seedsigner app; command -v seedsigner; seedsigner status 2>&1 | head -5
sec storage
df -h / /mnt/data 2>/dev/null; mount | grep -E ' / | /mnt/data ' 
sec shell and tools; ls -l /bin/sh; command -v bash tar sha256sum nohup taskset setarch
REMOTE
echo
echo "## sdk-pi02w image ($IMAGE)"
docker run --rm "$IMAGE" sh -c 'cd /output/host/arm-Buildroot-linux-gnueabihf/sysroot && sha256sum lib/libc.so.6 lib/ld-linux-armhf.so.3 usr/lib/libcrypto.so.3' 2>&1
} > "$F" 2>&1
echo "$F"
