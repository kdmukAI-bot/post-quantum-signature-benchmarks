#!/usr/bin/env python3
"""
Pure-Python FIPS 205 (SLH-DSA) key generation and verification for SHA2 parameter sets at
security category 1 (n = 16), written from the standard's algorithms rather than from
Blockstream's code, and parameterized so it also covers Blockstream's nonstandard
"SPHINCS+ 2^40" set (FIPS 205 algorithms with h=45, d=5, h'=9, a=13, k=10, lg_w=4), which
OpenSSL cannot load.

Algorithm numbers below are FIPS 205's (August 2024). Only what verification and key
generation need is implemented; there is no signing.

Checks:
  1. Cross-check against OpenSSL on SLH-DSA-SHA2-128s: this code's keygen reproduces the
     fixed key's PK.root (OpenSSL does too, see slh_dsa_openssl_verify.py), and the saved
     128s signatures verify here as well, with the same failing controls.
  2. SPHINCS+ 2^40: the fixed key's PK.root follows from its seeds; every saved
     sphincs40_sign_run0.bin verifies in pure mode with an empty context and fails in
     internal mode, with the wrong message, and with one bit flipped.
  3. SPHINCS+ 2^40 keygen rows: out_sha256 of every sphincs40_keygen row in results/
     equals the SHA-256 of this code's keygen output for that run's seed
     (SHA-512(msg)[0:48]).

Usage: fips205_sha2_check.py [--results DIR] [--saved DIR ...] [--keygen-runs N]
"""
import argparse
import hashlib
import hmac
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Address types (FIPS 205 section 4.2).
WOTS_HASH, WOTS_PK, TREE, FORS_TREE, FORS_ROOTS, WOTS_PRF, FORS_PRF = range(7)


class Params:
    def __init__(self, name, n, h, d, hp, a, k, lg_w, m):
        assert h == d * hp
        self.name, self.n, self.h, self.d, self.hp = name, n, h, d, hp
        self.a, self.k, self.lg_w, self.m = a, k, lg_w, m
        self.w = 1 << lg_w
        self.len1 = (8 * n + lg_w - 1) // lg_w
        # len2 = floor(log2(len1 * (w - 1)) / lg_w) + 1 (FIPS 205 equation 5.3)
        self.len2 = (self.len1 * (self.w - 1)).bit_length() - 1
        self.len2 = self.len2 // lg_w + 1
        self.len = self.len1 + self.len2
        self.sig_bytes = (1 + k * (1 + a) + h + d * self.len) * n


# FIPS 205 table 2.
SLH_DSA_SHA2_128S = Params("SLH-DSA-SHA2-128s", 16, 63, 7, 9, 12, 14, 4, 30)
# Blockstream's set: third_party/jade-hbs/main/process/sign_slh_dsa.c copies the 128s
# parameters and overrides h, d, hp, a, k, and lg_w; m stays 30. FIPS 205 would give m =
# 24 for these values; H_msg's MGF1 output is a prefix-stable stream and only its first 24
# bytes are read, so the extra 6 bytes change nothing.
SPHINCS_2_40 = Params("SPHINCS+ 2^40 (Blockstream)", 16, 45, 5, 9, 13, 10, 4, 30)


def to_int(b):
    return int.from_bytes(b, "big")


def to_byte(x, n):
    return x.to_bytes(n, "big")


def base_2b(x, b, out_len):
    """Algorithm 4."""
    i = bits = total = 0
    out = []
    for _ in range(out_len):
        while bits < b:
            total = (total << 8) + x[i]
            i += 1
            bits += 8
        bits -= b
        out.append((total >> bits) & ((1 << b) - 1))
    return out


class Adrs:
    """The 32-byte address of FIPS 205 section 4.2 and its 22-byte compressed form."""

    def __init__(self, b=None):
        self.b = bytearray(32) if b is None else bytearray(b)

    def copy(self):
        return Adrs(self.b)

    def set_layer(self, x):
        self.b[0:4] = to_byte(x, 4)

    def set_tree(self, x):
        self.b[4:16] = to_byte(x, 12)

    def set_type_and_clear(self, y):
        self.b[16:20] = to_byte(y, 4)
        self.b[20:32] = bytes(12)

    def set_key_pair(self, i):
        self.b[20:24] = to_byte(i, 4)

    def get_key_pair(self):
        return to_int(self.b[20:24])

    def set_chain(self, i):
        self.b[24:28] = to_byte(i, 4)

    set_tree_height = set_chain

    def set_hash(self, i):
        self.b[28:32] = to_byte(i, 4)

    set_tree_index = set_hash

    def get_tree_index(self):
        return to_int(self.b[28:32])

    def compressed(self):
        # ADRS^c = ADRS[3] || ADRS[8:16] || ADRS[19] || ADRS[20:32] (section 11.2)
        b = self.b
        return bytes(b[3:4] + b[8:16] + b[19:20] + b[20:32])


class Sha2Cat1:
    """The section 11.2.1 functions for security category 1 (SHA-256 throughout)."""

    def __init__(self, prm, pk_seed):
        self.prm = prm
        self.n = prm.n
        self.pk_seed = pk_seed
        # SHA-256(PK.seed || toByte(0, 64 - n) || ...): the first block is fixed per key.
        self.base = hashlib.sha256(pk_seed + bytes(64 - self.n))

    def _h(self, adrs, data):
        s = self.base.copy()
        s.update(adrs.compressed())
        s.update(data)
        return s.digest()[: self.n]

    F = H = T = _h

    def prf(self, sk_seed, adrs):
        return self._h(adrs, sk_seed)

    def h_msg(self, r, pk_root, m):
        inner = hashlib.sha256(r + self.pk_seed + pk_root + m).digest()
        seed = r + self.pk_seed + inner
        out = b""
        c = 0
        while len(out) < self.prm.m:
            out += hashlib.sha256(seed + to_byte(c, 4)).digest()
            c += 1
        return out[: self.prm.m]

    def prf_msg(self, sk_prf, opt_rand, m):
        return hmac.new(sk_prf, opt_rand + m, hashlib.sha256).digest()[: self.n]


def chain(fn, x, i, s, adrs):
    """Algorithm 5."""
    for j in range(i, i + s):
        adrs.set_hash(j)
        x = fn.F(adrs, x)
    return x


def wots_pkgen(fn, sk_seed, adrs):
    """Algorithm 6."""
    prm = fn.prm
    sk_adrs = adrs.copy()
    sk_adrs.set_type_and_clear(WOTS_PRF)
    sk_adrs.set_key_pair(adrs.get_key_pair())
    tmp = []
    for i in range(prm.len):
        sk_adrs.set_chain(i)
        sk = fn.prf(sk_seed, sk_adrs)
        adrs.set_chain(i)
        tmp.append(chain(fn, sk, 0, prm.w - 1, adrs))
    pk_adrs = adrs.copy()
    pk_adrs.set_type_and_clear(WOTS_PK)
    pk_adrs.set_key_pair(adrs.get_key_pair())
    return fn.T(pk_adrs, b"".join(tmp))


def wots_digits(prm, m):
    msg = base_2b(m, prm.lg_w, prm.len1)
    csum = sum(prm.w - 1 - v for v in msg)
    csum <<= (8 - ((prm.len2 * prm.lg_w) % 8)) % 8
    nbytes = (prm.len2 * prm.lg_w + 7) // 8
    return msg + base_2b(to_byte(csum, nbytes), prm.lg_w, prm.len2)


def wots_pk_from_sig(fn, sig, m, adrs):
    """Algorithm 8."""
    prm = fn.prm
    n = prm.n
    msg = wots_digits(prm, m)
    tmp = []
    for i in range(prm.len):
        adrs.set_chain(i)
        tmp.append(chain(fn, sig[i * n:(i + 1) * n], msg[i], prm.w - 1 - msg[i], adrs))
    pk_adrs = adrs.copy()
    pk_adrs.set_type_and_clear(WOTS_PK)
    pk_adrs.set_key_pair(adrs.get_key_pair())
    return fn.T(pk_adrs, b"".join(tmp))


def xmss_node(fn, sk_seed, i, z, adrs):
    """Algorithm 9."""
    if z == 0:
        adrs.set_type_and_clear(WOTS_HASH)
        adrs.set_key_pair(i)
        return wots_pkgen(fn, sk_seed, adrs)
    lnode = xmss_node(fn, sk_seed, 2 * i, z - 1, adrs)
    rnode = xmss_node(fn, sk_seed, 2 * i + 1, z - 1, adrs)
    adrs.set_type_and_clear(TREE)
    adrs.set_tree_height(z)
    adrs.set_tree_index(i)
    return fn.H(adrs, lnode + rnode)


def xmss_pk_from_sig(fn, idx, sig_xmss, m, adrs):
    """Algorithm 11."""
    prm = fn.prm
    n = prm.n
    adrs.set_type_and_clear(WOTS_HASH)
    adrs.set_key_pair(idx)
    node = wots_pk_from_sig(fn, sig_xmss[: prm.len * n], m, adrs)
    auth = sig_xmss[prm.len * n:]
    adrs.set_type_and_clear(TREE)
    adrs.set_tree_index(idx)
    for k in range(prm.hp):
        adrs.set_tree_height(k + 1)
        a_k = auth[k * n:(k + 1) * n]
        if (idx >> k) % 2 == 0:
            adrs.set_tree_index(adrs.get_tree_index() // 2)
            node = fn.H(adrs, node + a_k)
        else:
            adrs.set_tree_index((adrs.get_tree_index() - 1) // 2)
            node = fn.H(adrs, a_k + node)
    return node


def ht_verify(fn, m, sig_ht, idx_tree, idx_leaf, pk_root):
    """Algorithm 13."""
    prm = fn.prm
    step = (prm.hp + prm.len) * prm.n
    adrs = Adrs()
    adrs.set_tree(idx_tree)
    node = xmss_pk_from_sig(fn, idx_leaf, sig_ht[:step], m, adrs)
    for j in range(1, prm.d):
        idx_leaf = idx_tree % (1 << prm.hp)
        idx_tree >>= prm.hp
        adrs.set_layer(j)
        adrs.set_tree(idx_tree)
        node = xmss_pk_from_sig(fn, idx_leaf, sig_ht[j * step:(j + 1) * step], node, adrs)
    return node == pk_root


def fors_pk_from_sig(fn, sig_fors, md, adrs):
    """Algorithm 17."""
    prm = fn.prm
    n, a, k = prm.n, prm.a, prm.k
    indices = base_2b(md, a, k)
    roots = []
    for i in range(k):
        off = i * (a + 1) * n
        sk = sig_fors[off:off + n]
        adrs.set_tree_height(0)
        adrs.set_tree_index((i << a) + indices[i])
        node = fn.F(adrs, sk)
        auth = sig_fors[off + n:off + (a + 1) * n]
        for j in range(a):
            adrs.set_tree_height(j + 1)
            a_j = auth[j * n:(j + 1) * n]
            if (indices[i] >> j) % 2 == 0:
                adrs.set_tree_index(adrs.get_tree_index() // 2)
                node = fn.H(adrs, node + a_j)
            else:
                adrs.set_tree_index((adrs.get_tree_index() - 1) // 2)
                node = fn.H(adrs, a_j + node)
        roots.append(node)
    pk_adrs = adrs.copy()
    pk_adrs.set_type_and_clear(FORS_ROOTS)
    pk_adrs.set_key_pair(adrs.get_key_pair())
    return fn.T(pk_adrs, b"".join(roots))


def keygen_internal(prm, sk_seed, sk_prf, pk_seed):
    """Algorithm 18. Returns the 4n-byte secret key SK.seed || SK.prf || PK.seed ||
    PK.root."""
    fn = Sha2Cat1(prm, pk_seed)
    adrs = Adrs()
    adrs.set_layer(prm.d - 1)
    pk_root = xmss_node(fn, sk_seed, 0, prm.hp, adrs)
    return sk_seed + sk_prf + pk_seed + pk_root


def verify_internal(prm, m, sig, pk):
    """Algorithm 20."""
    n = prm.n
    if len(sig) != prm.sig_bytes:
        return False
    pk_seed, pk_root = pk[:n], pk[n:2 * n]
    fn = Sha2Cat1(prm, pk_seed)
    adrs = Adrs()
    r = sig[:n]
    sig_fors = sig[n:(1 + prm.k * (1 + prm.a)) * n]
    sig_ht = sig[(1 + prm.k * (1 + prm.a)) * n:]
    digest = fn.h_msg(r, pk_root, m)
    md_len = (prm.k * prm.a + 7) // 8
    tree_len = (prm.h - prm.hp + 7) // 8
    leaf_len = (prm.hp + 7) // 8
    md = digest[:md_len]
    idx_tree = to_int(digest[md_len:md_len + tree_len]) % (1 << (prm.h - prm.hp))
    idx_leaf = to_int(digest[md_len + tree_len:md_len + tree_len + leaf_len])
    idx_leaf %= 1 << prm.hp
    adrs.set_tree(idx_tree)
    adrs.set_type_and_clear(FORS_TREE)
    adrs.set_key_pair(idx_leaf)
    pk_fors = fors_pk_from_sig(fn, sig_fors, md, adrs)
    return ht_verify(fn, pk_fors, sig_ht, idx_tree, idx_leaf, pk_root)


def verify_pure(prm, m, sig, pk, ctx=b""):
    """Algorithm 24: M' = toByte(0, 1) || toByte(|ctx|, 1) || ctx || M."""
    if len(ctx) > 255:
        return False
    return verify_internal(prm, bytes([0, len(ctx)]) + ctx + m, sig, pk)


def message(x):
    return x.to_bytes(32, "big")


def saved_files(dirs, name):
    for d in dirs:
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames.sort()
            if name in filenames:
                yield os.path.join(dirpath, name)


def keygen_rows(results_dir, op):
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
                if ln.startswith("board,"):
                    cols = ln.split(",")
                    continue
                if not cols or "out_sha256" not in cols:
                    continue
                parts = ln.split(",")
                if len(parts) != len(cols):
                    continue
                r = dict(zip(cols, parts))
                if r.get("op") == op:
                    try:
                        r["run"] = int(r["run"])
                    except ValueError:
                        continue
                    yield path, r


# Blockstream's fixed keys (third_party/jade-hbs/main/process/sign_slh_dsa.c lines 132 and
# 145).
SK_128S = bytes.fromhex(
    "0fac4b7b966f29c3ecff665eb4ead66eee253a1a3d501c09d2cc0a7a5afad474"
    "7906277af176f5e3cf644f591fb353c5d12447a500c02be7d4c86bd1e29a84ab")
SK_2_40 = bytes.fromhex(
    "e39c0e870f7e0270c5e8bc4ecb8447f59acf02c625e6da1e2018140412e2c8d6"
    "9fc70fec2531104d439e8409a144308e99a230a89e6ccc8fd40855d7f519029d")


def check_saved(prm, sk, dirs, name):
    """Returns (files, failures) for the saved signatures of message 0."""
    n = prm.n
    pk = sk[2 * n:]
    files = fails = 0
    for path in saved_files(dirs, name):
        with open(path, "rb") as f:
            sig = f.read()
        flipped = bytearray(sig)
        flipped[len(sig) // 2] ^= 0x01
        pure = verify_pure(prm, message(0), sig, pk)
        internal = verify_internal(prm, message(0), sig, pk)
        wrong = verify_pure(prm, message(1), sig, pk)
        tampered = verify_pure(prm, message(0), bytes(flipped), pk)
        files += 1
        if not (pure and not internal and not wrong and not tampered):
            fails += 1
            print("FAIL %s: pure=%s internal=%s wrong_msg=%s tampered=%s"
                  % (os.path.relpath(path, ROOT), pure, internal, wrong, tampered))
    return files, fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(ROOT, "results"))
    ap.add_argument("--saved", nargs="*",
                    default=[os.path.join(ROOT, "results", "raw", "host", "r1", "host-sigs")])
    ap.add_argument("--keygen-runs", type=int, default=100,
                    help="check sphincs40_keygen rows for runs below this index")
    a = ap.parse_args()
    failures = 0

    for prm, sk, name in ((SLH_DSA_SHA2_128S, SK_128S, "slh_dsa_sign_run0.bin"),
                          (SPHINCS_2_40, SK_2_40, "sphincs40_sign_run0.bin")):
        n = prm.n
        ok = keygen_internal(prm, sk[:n], sk[n:2 * n], sk[2 * n:3 * n]) == sk
        failures += not ok
        print("%s %s fixed key: PK.root follows from its seeds (len=%d, sig=%d bytes)"
              % ("ok  " if ok else "FAIL", prm.name, prm.len, prm.sig_bytes))
        files, fails = check_saved(prm, sk, a.saved, name)
        failures += fails
        print("%s %s: %d saved signatures of message 0 verify in pure mode with an empty "
              "context; internal mode, the wrong message, and one flipped bit fail"
              % ("ok  " if not fails and files else "FAIL", prm.name, files))
        if not files:
            failures += 1

    # sphincs40_keygen rows: SK.seed || SK.prf || PK.seed = SHA-512(msg)[0:48].
    want = dict()
    for x in range(a.keygen_runs):
        s = hashlib.sha512(message(x)).digest()[:48]
        out = keygen_internal(SPHINCS_2_40, s[:16], s[16:32], s[32:48])
        want[x] = hashlib.sha256(out).hexdigest()
    rows = mism = skipped = 0
    files = set()
    for path, r in keygen_rows(a.results, "sphincs40_keygen"):
        if r["run"] not in want:
            skipped += 1
            continue
        rows += 1
        files.add(path)
        if r["out_sha256"] != want[r["run"]]:
            mism += 1
            print("FAIL %s run %d" % (os.path.relpath(path, ROOT), r["run"]))
    failures += mism
    print("%s sphincs40_keygen: %d rows in %d files match this code's keygen "
          "(%d mismatches, %d rows beyond run %d not checked)"
          % ("ok  " if not mism else "FAIL", rows - mism, len(files), mism, skipped,
             a.keygen_runs - 1))
    nkey = kbad = 0
    for path in saved_files(a.saved, "sphincs40_keygen_run0.bin"):
        nkey += 1
        with open(path, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != want[0]:
                kbad += 1
                print("FAIL %s" % os.path.relpath(path, ROOT))
    failures += kbad
    print("%s sphincs40_keygen_run0.bin: %d saved files match this code's keygen"
          % ("ok  " if not kbad else "FAIL", nkey - kbad))

    print("%s: %d failure(s)" % ("PASS" if not failures else "FAIL", failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
