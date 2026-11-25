#!/usr/bin/env bash
# Round 4: flash an harness/pico build onto the Waveshare RP2350 Touch LCD 2 without a
# button press, and wait for its USB CDC console.
#
#   r4_rp2350_flash.sh <build dir under harness/pico/>
#
# The board is found by USB vendor ID 2e8a only. If the app is running (2e8a:0009), it is
# sent to BOOTSEL through the SDK's USB reset interface (picotool reboot -f -u); then
# picotool loads the UF2, verifies it, and starts it. picotool runs in the pinned Docker
# image as the calling user with the plugdev group, the host's /dev/bus/usb, and access to
# USB character devices (major 189); the host's udev rule
# /etc/udev/rules.d/60-raspberrypi-usb.rules gives vendor 2e8a devices mode 0660, group
# plugdev. No block device is touched. Prints the console's /dev/serial/by-id path on
# success.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
IMAGE="${PQB_RP_IMAGE:-pqb-rp2350:sdk2.3.1-gcc14.2}"
BUILD="$ROOT/harness/pico/$1/pqb_rp.uf2"
[ -f "$BUILD" ] || { echo "missing $BUILD" >&2; exit 1; }
PT=(docker run --rm --user "$(id -u):$(id -g)" --group-add "$(getent group plugdev | cut -d: -f3)"
    -v /dev/bus/usb:/dev/bus/usb --device-cgroup-rule='c 189:* rmw'
    -v "$ROOT:$ROOT" "$IMAGE" picotool)

wait_usb() {  # $1 = product id, $2 = seconds
    for _ in $(seq 1 $(( $2 * 2 ))); do
        lsusb -d "2e8a:$1" > /dev/null 2>&1 && return 0
        sleep 0.5
    done
    return 1
}

console() {
    for p in /dev/serial/by-id/usb-Raspberry_Pi_*-if00; do
        [ -e "$p" ] || continue
        if udevadm info -q property -n "$p" 2>/dev/null | grep -qx 'ID_VENDOR_ID=2e8a'; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

if ! lsusb -d 2e8a:000f > /dev/null 2>&1; then
    if lsusb -d 2e8a: > /dev/null 2>&1; then
        timeout 60 "${PT[@]}" reboot -f -u > /dev/null 2>&1 || true
    fi
    wait_usb 000f 20 || { echo "board did not enter BOOTSEL (a button press may be needed)" >&2; exit 1; }
fi
timeout 300 "${PT[@]}" load -v -x "$BUILD" 2>&1 | tr '\r' '\n' | grep -E 'OK|ERROR|rebooted|differ' | tail -3
wait_usb 0009 20 || { echo "app did not enumerate" >&2; exit 1; }
for _ in $(seq 1 40); do
    if p="$(console)"; then
        echo "$p"
        exit 0
    fi
    sleep 0.5
done
echo "no console device" >&2
exit 1
