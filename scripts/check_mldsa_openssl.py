#!/usr/bin/env python3
"""
Independent check of the benchmark's ML-DSA outputs (mldsa-native) against the host's
OpenSSL 3.5 command-line tool: the same seed must give the same public key, and the
deterministic signature (rnd = 32 zero bytes, empty context) of each message must be the
same bytes and must verify.

Usage: check_mldsa_openssl.py <host pq_bench> [N_MESSAGES]
Runs the host binary's mldsa<set>_keygen (run 0 = the signing key's seed) and
mldsa<set>_sign for messages 0 .. N-1 into a temporary directory, then OpenSSL:
  openssl genpkey -algorithm ML-DSA-<set> -pkeyopt hexseed:<run_input(0)>
  openssl pkeyutl -sign -rawin -pkeyopt deterministic:1
  openssl pkeyutl -verify -rawin
Exit status 0 only if every comparison and verification passes.
"""
import os
import subprocess
import sys
import tempfile

PK_LEN = dict((("44", 1312), ("65", 1952), ("87", 2592)))


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    bench = os.path.abspath(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    ver = run(["openssl", "version"]).stdout.decode().strip()
    print(f"OpenSSL: {ver}")
    bad = 0
    with tempfile.TemporaryDirectory() as d:
        for ps in ("44", "65", "87"):
            run([bench, "--board", "host", "--build", "check", "--op", f"mldsa{ps}_keygen",
                 "-n", "1", "--save", d])
            run([bench, "--board", "host", "--build", "check", "--op", f"mldsa{ps}_sign",
                 "-n", str(n), "--save", d, "--save-all"])
            key = os.path.join(d, f"k{ps}.pem")
            pub = os.path.join(d, f"pk{ps}.der")
            run(["openssl", "genpkey", "-algorithm", f"ML-DSA-{ps}", "-pkeyopt",
                 "hexseed:" + "00" * 32, "-out", key])
            run(["openssl", "pkey", "-in", key, "-pubout", "-outform", "DER", "-out", pub])
            ours = open(os.path.join(d, f"mldsa{ps}_keygen_run0.bin"), "rb").read()
            pk_ok = open(pub, "rb").read()[-PK_LEN[ps]:] == ours[:PK_LEN[ps]]
            bad += not pk_ok
            same = verified = 0
            for x in range(n):
                msg = os.path.join(d, f"m{x}.bin")
                with open(msg, "wb") as f:
                    f.write(bytes(28) + x.to_bytes(4, "big"))
                sig = os.path.join(d, f"o{ps}_{x}.bin")
                run(["openssl", "pkeyutl", "-sign", "-inkey", key, "-rawin", "-in", msg,
                     "-pkeyopt", "deterministic:1", "-out", sig])
                our_sig = os.path.join(d, f"mldsa{ps}_sign_run{x}.bin")
                same += open(sig, "rb").read() == open(our_sig, "rb").read()
                r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", pub,
                                    "-keyform", "DER", "-rawin", "-in", msg, "-sigfile",
                                    our_sig], capture_output=True)
                verified += r.returncode == 0
            bad += (same != n) + (verified != n)
            print(f"ML-DSA-{ps}: public key {'matches' if pk_ok else 'DIFFERS'}; "
                  f"{same}/{n} signatures identical to OpenSSL's; "
                  f"{verified}/{n} verified by OpenSSL")
    print("PASS" if not bad else "FAIL")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
