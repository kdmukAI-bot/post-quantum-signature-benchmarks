#!/usr/bin/env python3
"""
Host-side driver for Blockstream's hash-based signature benchmark firmware (the
DmitriiKJ/Jade hash_based_signatures branch, cloned in ../jade-hbs).

Timing matches Blockstream's own test_shrincs.py: wall-clock time on the host around each
RPC call. Each figure therefore includes USB transfer and the on-screen progress bar, the
same as the published Jade Plus numbers.

Requires a DEBUG firmware build: the script loads a throwaway test wallet into RAM with
debug_set_mnemonic, so no PIN or PIN server is needed. Never use a real seed here.

Example:
    .venv/bin/python scripts/run_jade_bench.py --port /dev/ttyACM1 --board ws_s3_lcd2 \
        --op slh_dsa_sign -n 10
"""
import argparse
import csv
import datetime
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "jade-hbs"))
from jadepy.jade import JadeAPI  # noqa: E402

TEST_MNEMONIC = " ".join(["abandon"] * 11 + ["about"])
SIGN_PATH = [44, 0, 0]

# op name -> (rpc method, function building params from run index x and swn)
OPS = {
    "slh_dsa_keygen": ("slh_dsa_key_gen",
                       lambda x, swn: {"bytes": x.to_bytes(32, "big"), "is_standard": True}),
    "slh_dsa_sign": ("sign_slh_dsa",
                     lambda x, swn: {"path": SIGN_PATH, "message": x.to_bytes(32, "big"),
                                     "is_standard": True}),
    "sphincs40_keygen": ("slh_dsa_key_gen",
                         lambda x, swn: {"bytes": x.to_bytes(32, "big"),
                                         "is_standard": False}),
    "sphincs40_sign": ("sign_slh_dsa",
                       lambda x, swn: {"path": SIGN_PATH, "message": x.to_bytes(32, "big"),
                                       "is_standard": False}),
    "shrincs_keygen": ("shrincs_key_gen",
                       lambda x, swn: {"bytes": x.to_bytes(32, "big")}),
    "shrincs_sign": ("sign_shrincs",
                     lambda x, swn: {"path": SIGN_PATH, "message": x.to_bytes(32, "big"),
                                     "swn": swn}),
    "xmss_keygen": ("xmss_key_gen",
                    lambda x, swn: {"bytes": x.to_bytes(32, "big")}),
    "xmss_sign": ("sign_xmss",
                  lambda x, swn: {"path": SIGN_PATH, "message": x.to_bytes(32, "big")}),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True, help="serial device, e.g. /dev/ttyACM1")
    ap.add_argument("--board", required=True, help="label written to the CSV")
    ap.add_argument("--op", required=True, choices=sorted(OPS))
    ap.add_argument("-n", "--runs", type=int, default=10)
    ap.add_argument("--swn", type=int, default=2040,
                    help="WOTS+C target sum for shrincs_sign (2040 for SHRINCS-B builds; "
                         "96 or 140 for SHRINCS-L builds)")
    ap.add_argument("--build", default="", help="free-text build label for the CSV")
    ap.add_argument("--csv", default=os.path.join(HERE, "..", "results", "jade_runs.csv"))
    args = ap.parse_args()

    method, make_params = OPS[args.op]
    os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
    new_file = not os.path.exists(args.csv)

    jade = JadeAPI.create_serial(device=args.port)
    jade.connect()
    try:
        info = jade.get_version_info()
        state = info.get("JADE_STATE")
        print(f"Connected: {info.get('JADE_VERSION')} board={info.get('BOARD_TYPE')} "
              f"state={state}")
        # Loading the test wallet can raise a confirmation on the device screen, so only do
        # it when no wallet is in RAM yet; otherwise unattended runs would stall.
        if state not in ("READY", "TEMP"):
            if not jade.set_mnemonic(TEST_MNEMONIC, temporary_wallet=True):
                sys.exit("debug_set_mnemonic failed (is this a DEBUG build?)")
        if not jade.auth_user("mainnet"):
            sys.exit("auth_user failed")

        times = []
        with open(args.csv, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["utc", "board", "build", "op", "swn", "run", "seconds",
                            "reply_bytes"])
            for x in range(args.runs):
                t0 = time.perf_counter()
                reply = jade._jadeRpc(method, make_params(x, args.swn), long_timeout=True)
                dt = time.perf_counter() - t0
                times.append(dt)
                swn = args.swn if args.op == "shrincs_sign" else ""
                w.writerow([datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            args.board, args.build, args.op, swn, x, f"{dt:.4f}",
                            len(reply)])
                f.flush()
                print(f"{args.op} run {x + 1}/{args.runs}: {dt:8.3f} s  "
                      f"reply={len(reply)} B  mean so far={statistics.mean(times):8.3f} s")

        print(f"\n{args.op}: n={len(times)} mean={statistics.mean(times):.3f} s "
              f"median={statistics.median(times):.3f} s min={min(times):.3f} s "
              f"max={max(times):.3f} s")
    finally:
        jade.disconnect()


if __name__ == "__main__":
    main()
