#!/usr/bin/env python3
"""
Independent check of the benchmark's SLH-DSA-SHA2-128s outputs with the OpenSSL CLI
(OpenSSL 3.5 or later, whose SLH-DSA follows FIPS 205).

What the harness does (harness/common/op_slh.c, mirroring
third_party/jade-hbs/main/process/sign_slh_dsa.c):
  - message for run x: x.to_bytes(32, "big");
  - slh_dsa_sign: slh_sign(sig, msg, 32, ctx=NULL, ctx_sz=0, sk, addrnd=NULL, ...), that
    is FIPS 205 pure signing (Algorithm 22, M' = 0x00 || 0x00 || M) with an empty context,
    in the deterministic variant (opt_rand = PK.seed), with Blockstream's fixed 64-byte
    key;
  - slh_dsa_keygen: SK.seed || SK.prf || PK.seed = SHA-512(msg)[0:48], output the 64-byte
    secret key SK.seed || SK.prf || PK.seed || PK.root.

Checks, all with the openssl command-line tool:
  1. Key consistency: keygen from the fixed key's first 48 bytes reproduces its PK.root.
  2. For every message index used by a result row, OpenSSL signs deterministically in pure
     mode and derives the keygen output from the same seed; each result row's out_sha256
     must equal the SHA-256 of OpenSSL's bytes (CSV and ESP32 log rows alike).
  3. Every saved signature file (run 0) verifies in pure mode with an empty context and
     equals OpenSSL's own signature byte for byte. Controls that must fail: internal mode
     (message-encoding 0), the wrong message, and one flipped signature bit.
  4. Every saved keygen file (run 0) equals OpenSSL's keygen output.

Usage: slh_dsa_openssl_verify.py [--results DIR] [--saved DIR ...] [--csv-out FILE]
Exit status 0 only if every check passes.
"""
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ALG = "SLH-DSA-SHA2-128s"
N = 16
# Blockstream's fixed SLH-DSA-SHA2-128s signing key (jade-hbs sign_slh_dsa.c, line 132;
# the same constant is SK_STANDARD_HEX in harness/common/op_slh.c).
SK_HEX = ("0fac4b7b966f29c3ecff665eb4ead66eee253a1a3d501c09d2cc0a7a5afad474"
          "7906277af176f5e3cf644f591fb353c5d12447a500c02be7d4c86bd1e29a84ab")
OPS = ("slh_dsa_sign", "slh_dsa_keygen")


def message(x):
    return x.to_bytes(32, "big")


def run(args, check=True):
    p = subprocess.run(["openssl"] + args, capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError("openssl %s failed: %s" % (" ".join(args), p.stderr.decode()))
    return p


class OpenSSL:
    def __init__(self, tmp):
        self.tmp = tmp

    def path(self, name):
        return os.path.join(self.tmp, name)

    def keygen(self, seed48, tag):
        """Returns (private key DER path, public key DER path, raw 64-byte private
        key)."""
        priv_der = self.path(tag + "_priv.der")
        pub_der = self.path(tag + "_pub.der")
        run(["genpkey", "-algorithm", ALG, "-pkeyopt", "hexseed:" + seed48.hex(),
             "-outform", "DER", "-out", priv_der])
        run(["pkey", "-inform", "DER", "-in", priv_der, "-pubout", "-outform", "DER",
             "-out", pub_der])
        with open(priv_der, "rb") as f:
            der = f.read()
        with open(pub_der, "rb") as f:
            pub = f.read()
        # PKCS#8 ends with OCTET STRING (0x04, length 64) holding SK.seed || SK.prf ||
        # PK.seed || PK.root; the SubjectPublicKeyInfo ends with the 32-byte PK.seed ||
        # PK.root.
        if der[-66:-64] != b"\x04\x40":
            raise RuntimeError("unexpected PKCS#8 layout")
        raw = der[-64:]
        if pub[-32:] != raw[32:]:
            raise RuntimeError("public key does not match the private key's PK part")
        return priv_der, pub_der, raw

    def sign(self, priv_der, msg, tag):
        m = self.path(tag + ".msg")
        s = self.path(tag + ".sig")
        with open(m, "wb") as f:
            f.write(msg)
        run(["pkeyutl", "-sign", "-rawin", "-keyform", "DER", "-inkey", priv_der,
             "-in", m, "-pkeyopt", "deterministic:1", "-out", s])
        with open(s, "rb") as f:
            return f.read()

    def verify(self, pub_der, msg, sig, tag, internal=False):
        m = self.path(tag + ".msg")
        s = self.path(tag + ".sig")
        with open(m, "wb") as f:
            f.write(msg)
        with open(s, "wb") as f:
            f.write(sig)
        args = ["pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER", "-inkey",
                pub_der, "-in", m, "-sigfile", s]
        if internal:
            args += ["-pkeyopt", "message-encoding:0"]
        p = run(args, check=False)
        return p.returncode == 0 and b"Verified Successfully" in p.stdout


MBOP_COLS = ["tag", "board", "path", "op", "compressions", "wall_s", "cycles",
             "out_sha256", "verified"]


def result_rows(results_dir):
    """Yields (path, row dict) for every slh_dsa_sign or slh_dsa_keygen row in every .csv
    and .log under results_dir. Both formats carry a 'board,...' header; ESP32 logs also
    carry serial noise, which is skipped. The ESP32 microbenchmark's '#mbop' lines
    (harness/esp-idf/main/microbench_esp.c) time whole operations on run 0's input and are
    read as run 0."""
    for dirpath, dirnames, filenames in os.walk(results_dir):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.endswith((".csv", ".log")):
                continue
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                text = f.read().decode("utf-8", errors="replace")
            cols = None
            for ln in text.split("\n"):
                ln = ln.strip("\r")
                if ln.startswith("#mbop,"):
                    parts = ln.split(",")
                    if len(parts) == len(MBOP_COLS) and parts[3] in OPS:
                        r = dict(zip(MBOP_COLS, parts))
                        r["run"] = 0
                        yield path, r
                    continue
                if ln.startswith("board,"):
                    cols = ln.split(",")
                    continue
                if not cols or "out_sha256" not in cols:
                    continue
                parts = ln.split(",")
                if len(parts) != len(cols):
                    continue
                r = dict(zip(cols, parts))
                if r.get("op") not in OPS:
                    continue
                try:
                    r["run"] = int(r["run"])
                except ValueError:
                    continue
                yield path, r


def saved_files(dirs, name):
    for d in dirs:
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames.sort()
            if name in filenames:
                yield os.path.join(dirpath, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(ROOT, "results"))
    ap.add_argument("--saved", nargs="*",
                    default=[os.path.join(ROOT, "results", "raw", "host", "r1", "host-sigs")])
    ap.add_argument("--csv-out", help="write OpenSSL's per-message output hashes here")
    a = ap.parse_args()

    ver = run(["version"]).stdout.decode().strip()
    print("openssl:", ver)
    failures = 0

    rows = list(result_rows(a.results))
    max_run = max(r["run"] for _, r in rows) if rows else 0

    with tempfile.TemporaryDirectory() as tmp:
        ossl = OpenSSL(tmp)
        sk = bytes.fromhex(SK_HEX)
        priv_der, pub_der, raw = ossl.keygen(sk[:3 * N], "fixed")
        ok = raw == sk
        failures += not ok
        print("%s fixed signing key: OpenSSL keygen from its seeds reproduces PK.root"
              % ("ok  " if ok else "FAIL"))

        ref_sig = {}
        ref_key = {}
        sigs = {}
        for x in range(max_run + 1):
            msg = message(x)
            sig = ossl.sign(priv_der, msg, "m%d" % x)
            if len(sig) != 7856 or not ossl.verify(pub_der, msg, sig, "v%d" % x):
                failures += 1
                print("FAIL OpenSSL's own signature for message %d does not verify" % x)
            sigs[x] = sig
            ref_sig[x] = hashlib.sha256(sig).hexdigest()
            seed = hashlib.sha512(msg).digest()[:3 * N]
            _, _, kraw = ossl.keygen(seed, "k%d" % x)
            ref_key[x] = hashlib.sha256(kraw).hexdigest()
        print("OpenSSL deterministic pure-mode signatures and keygen outputs for "
              "messages 0 to %d computed" % max_run)

        if a.csv_out:
            with open(a.csv_out, "w") as f:
                f.write("op,run,out_sha256\n")
                for x in range(max_run + 1):
                    f.write("slh_dsa_sign,%d,%s\n" % (x, ref_sig[x]))
                for x in range(max_run + 1):
                    f.write("slh_dsa_keygen,%d,%s\n" % (x, ref_key[x]))

        # Result rows: group by file for the summary.
        per_file = dict()
        for path, r in rows:
            ref = ref_sig if r["op"] == "slh_dsa_sign" else ref_key
            rel = os.path.relpath(path, ROOT)
            g = per_file.setdefault((rel, r["op"]), [0, 0])
            g[0] += 1
            if ref.get(r["run"]) != r["out_sha256"]:
                g[1] += 1
                failures += 1
                print("FAIL %s %s run %d: out_sha256 differs from OpenSSL"
                      % (rel, r["op"], r["run"]))
        totals = dict()
        for (rel, op), (n, bad) in sorted(per_file.items()):
            area = os.path.dirname(rel)
            t = totals.setdefault((area, op), [0, 0, 0])
            t[0] += 1
            t[1] += n
            t[2] += bad
        print("\nResult rows against OpenSSL (files, rows, mismatches):")
        for (area, op), (nf, n, bad) in sorted(totals.items()):
            print("%s %-28s %-15s files=%3d rows=%5d mismatches=%d"
                  % ("ok  " if not bad else "FAIL", area, op, nf, n, bad))
        nrows = sum(t[1] for t in totals.values())
        for op in OPS:
            n_op = sum(t[1] for (_, o), t in totals.items() if o == op)
            print("%s rows: %d" % (op, n_op))
        nfiles = len(set(rel for rel, _ in per_file))
        print("rows checked: %d in %d files" % (nrows, nfiles))

        # Saved files (run 0).
        print("\nSaved signature files (message 0):")
        n_sig = 0
        msg0 = message(0)
        for path in saved_files(a.saved, "slh_dsa_sign_run0.bin"):
            with open(path, "rb") as f:
                sig = f.read()
            pure = ossl.verify(pub_der, msg0, sig, "s")
            internal = ossl.verify(pub_der, msg0, sig, "s", internal=True)
            wrong_msg = ossl.verify(pub_der, message(1), sig, "s")
            flipped = bytearray(sig)
            flipped[len(sig) // 2] ^= 0x01
            tampered = ossl.verify(pub_der, msg0, bytes(flipped), "s")
            same = sig == sigs[0]
            good = pure and not internal and not wrong_msg and not tampered and same
            n_sig += 1
            failures += not good
            if not good:
                print("FAIL %s: pure=%s internal=%s wrong_msg=%s tampered=%s identical=%s"
                      % (os.path.relpath(path, ROOT), pure, internal, wrong_msg, tampered,
                         same))
        print("%d files: verify in pure mode with an empty context, are identical to "
              "OpenSSL's deterministic signature, and fail in internal mode, with the "
              "wrong message, and with one bit flipped (any exception is listed above)"
              % n_sig)

        print("\nSaved keygen files (seed from message 0):")
        n_key = 0
        for path in saved_files(a.saved, "slh_dsa_keygen_run0.bin"):
            with open(path, "rb") as f:
                b = f.read()
            n_key += 1
            if hashlib.sha256(b).hexdigest() != ref_key[0]:
                failures += 1
                print("FAIL %s differs from OpenSSL's keygen"
                      % os.path.relpath(path, ROOT))
        print("%d files compared with OpenSSL's keygen output" % n_key)

    print("\n%s: %d failure(s)" % ("PASS" if not failures else "FAIL", failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
