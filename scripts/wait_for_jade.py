#!/usr/bin/env python3
"""
Wait until a Jade answers get_version_info, then exit 0 (exit 1 on timeout).

Jade only reads serial requests while its dashboard (home screen) is idle, so requests sent
while a setup screen is open sit in a queue. Before each attempt this drains any stray
replies left over from earlier queued requests.
"""
import argparse
import os
import sys
import time

import serial

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "jade-hbs"))
from jadepy.jade import JadeAPI  # noqa: E402


def drain(port, seconds):
    with serial.Serial(port, 115200, timeout=0.5) as p:
        junk = b""
        end = time.time() + seconds
        while time.time() < end:
            junk += p.read(4096)
    return len(junk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--max-wait", type=int, default=600, help="seconds")
    args = ap.parse_args()

    deadline = time.time() + args.max_wait
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            n = drain(args.port, 2)
        except serial.SerialException as e:
            # The USB device disappears briefly while the board resets
            print(f"attempt {attempt}: port unavailable ({e.errno})", flush=True)
            time.sleep(2)
            continue
        jade = JadeAPI.create_serial(device=args.port, timeout=3)
        try:
            jade.connect()
            info = jade.get_version_info()
            print(f"attempt {attempt}: answered (drained {n} stale bytes): "
                  f"version={info.get('JADE_VERSION')} board={info.get('BOARD_TYPE')} "
                  f"state={info.get('JADE_STATE')}", flush=True)
            return 0
        except Exception as e:
            print(f"attempt {attempt}: no answer ({type(e).__name__}), drained {n} bytes",
                  flush=True)
        finally:
            try:
                jade.disconnect()
            except Exception:
                pass
        time.sleep(2)
    print("gave up waiting", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
