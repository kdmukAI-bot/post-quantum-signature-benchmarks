#!/usr/bin/env python3
"""
Hard-reset an ESP32 running harness/esp-idf over its serial port and capture the benchmark
output until the app prints '#done' (or a timeout passes).

Usage: esp_capture.py <port> <out_file> [--max-seconds N] [--no-reset] [--send-start]
                      [--command "run <set> [n]"]

The reset uses esptool's RTS sequence with DTR deasserted, so the chip boots normally (the
same method as esp-board-common/.claude/scripts/reset_and_capture.py). Use --no-reset for
USB-Serial/JTAG consoles, where the host cannot reset the chip this way; reset by hand.

--command (round-2 builds): send this line whenever the app prints its '#ready' prompt,
until the run starts ('#env'). It works with or without a reset, so a second job set can
be run on a board that has finished one (the app returns to its prompt after '#done').
--send-start (round-1 USB-Serial/JTAG builds) sends a bare newline instead.
"""
import argparse
import sys
import time

import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("out_file")
    ap.add_argument("--max-seconds", type=float, default=3600)
    ap.add_argument("--no-reset", action="store_true")
    ap.add_argument("--send-start", action="store_true",
                    help="USB-Serial/JTAG console: send newlines until output starts")
    ap.add_argument("--command", help="round-2 builds: command line to send at '#ready'")
    args = ap.parse_args()

    # The USB-Serial/JTAG port may still be enumerating after a flash
    deadline = time.time() + 30
    while True:
        try:
            s = serial.Serial(args.port, 115200, timeout=0.5)
            break
        except serial.SerialException:
            if time.time() > deadline:
                raise
            time.sleep(0.5)
    if not args.no_reset and not args.send_start:
        s.dtr = False
        s.rts = True
        time.sleep(0.2)
        s.rts = False

    end = time.time() + args.max_seconds
    buf = b""
    done = False
    started = not args.send_start and not args.command
    cmd = (args.command + "\n").encode() if args.command else b"\n"
    last_send = 0.0
    with open(args.out_file, "wb") as f:
        if args.command:
            # A board that is already idle at its prompt prints '#ready' only once a second
            s.write(cmd)
            last_send = time.time()
        while time.time() < end:
            if not started and args.send_start and not args.command:
                s.write(cmd)
            data = s.read(4096)
            if not data:
                if not started and args.command and time.time() - last_send > 2:
                    s.write(cmd)
                    last_send = time.time()
                continue
            window = buf + data
            if not started and b"#env" in window:
                started = True
            elif not started and args.command and b"#ready" in window:
                if time.time() - last_send > 0.5:
                    s.write(cmd)
                    last_send = time.time()
            f.write(data)
            f.flush()
            buf = window[-256:]
            if started and b"#done" in buf:
                done = True
                break
    s.close()
    print(f"{'done' if done else 'TIMEOUT'}: {args.out_file}")
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
