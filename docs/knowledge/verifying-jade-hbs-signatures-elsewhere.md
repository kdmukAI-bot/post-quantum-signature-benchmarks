# Verifying Jade's hash-based signatures with other implementations

What a verifier outside Blockstream's code must match to accept the signatures made by the
scheme code in Blockstream's Jade fork (github.com/DmitriiKJ/Jade, branch
`hash_based_signatures`, commit `f5c90a5e`), and which of those signatures no standard
verifier can accept. Applies equally to this benchmark's outputs, which run that code
unmodified.

## SLH-DSA-SHA2-128s: FIPS 205 pure mode, not SPHINCS+ round 3

**Rule.** Verify with a FIPS 205 SLH-DSA implementation in pure mode with an empty context
string. In OpenSSL 3.5 and later this is the default mode:

```
openssl pkeyutl -verify -rawin -pubin -inkey pub.pem -in msg.bin -sigfile sig.bin
```

Do not set `message-encoding` to 0 (internal mode), and do not use an implementation of
the SPHINCS+ round 3 specification.

**Why.**

- Jade's `main/slh_dsa/` is slhdsa-c (its headers name "the slhdsa-c project authors" and
  FIPS 205). The signing handler calls `slh_sign(sig, msg, len, NULL, 0, sk, NULL, ...)`,
  which is FIPS 205 Algorithm 22 with an empty context. slhdsa-c's `h_msg` and `prf_msg`
  prepend `0x00 || len(ctx) || ctx` whenever the context size is not its internal-mode
  marker, so the signed string is `M' = 0x00 0x00 || M`. A verifier in internal mode
  (Algorithm 20, `slh_verify_internal`, or OpenSSL's `message-encoding` 0) hashes `M`
  instead of `M'` and rejects every one of these signatures.
- `addrnd` is NULL, so `opt_rand = PK.seed`: FIPS 205's deterministic variant. OpenSSL's
  `-pkeyopt deterministic:1` produces byte-identical signatures from the same key and
  message, which makes byte comparison a valid check alongside verification. (OpenSSL's
  manual describes this option as using "the private key seed"; its output nevertheless
  equals the FIPS 205 deterministic variant, `opt_rand = PK.seed`.)
- FIPS 205 Appendix A lists the changes from SPHINCS+ version 3: PK.seed as an input to
  PRF, two new address types (WOTS_PRF and FORS_PRF), SHA-512 in place of SHA-256 for
  category 3 and 5 SHA2 sets, R and PK.seed as inputs to MGF1 in H_msg for the SHA2 sets,
  and a different method of extracting FORS indices from the digest, which the appendix
  says is not compatible with the round 3 reference implementation. Appendix A.1 adds the
  pure and prehash domain separation (Algorithms 22 to 25). The H_msg change, the FORS
  index extraction, and the pure-mode prefix each change what a verifier computes, so a
  round 3 verifier rejects FIPS 205 signatures even for the same parameter set; the PRF
  changes alter which keys and signatures a given seed produces.

**Encodings.** Jade's keys and signatures carry no ASN.1 or length framing:

- Secret key, 64 bytes: `SK.seed || SK.prf || PK.seed || PK.root` (FIPS 205 Figure 15).
- Public key, 32 bytes: `PK.seed || PK.root` (Figure 16), the second half of the secret
  key.
- Signature, 7,856 bytes: `R || SIG_FORS || SIG_HT`, which OpenSSL takes as is.

To build OpenSSL key files from raw seeds (OpenSSL documents the `seed` parameter as being
for testing):

```
openssl genpkey -algorithm SLH-DSA-SHA2-128s \
    -pkeyopt hexseed:<hex of SK.seed || SK.prf || PK.seed> -out priv.pem
openssl pkey -in priv.pem -pubout -out pub.pem
```

## "SPHINCS+ 2^40" is FIPS 205 with nonstandard parameters

Blockstream's table and Jade's handler call this set SPHINCS+, but it runs the same
slhdsa-c code in the same pure, deterministic mode. The handler copies the
SLH-DSA-SHA2-128s parameter structure and overrides h = 45, d = 5, h' = 9, a = 13, k = 10,
lg_w = 4, giving 5,776-byte signatures. The digest length m stays at 128s's 30; FIPS 205's
formula would give 24 for these values, and since only the first 24 bytes of the MGF1
output are read, the difference has no effect.

**Rule.** No standard verifier accepts these signatures: OpenSSL loads only the 12 FIPS
205 parameter sets, and a round 3 implementation has the differences above. Use a FIPS 205
verifier that takes its parameters as data (this benchmark's
`scripts/fips205_sha2_check.py`, cross-checked against OpenSSL on SLH-DSA-SHA2-128s).

## XMSS 2^10 is not RFC 8391 XMSS

Jade's `main/xmss/` is the xmss-reference code with two changes that affect signatures:

- A new OID, `0x000000ff`: SHA-256 truncated to n = 16 bytes, a 4-byte hash padding
  prefix, tree height 10, w = 16. RFC 8391 and NIST SP 800-208 define no such set, and
  xmss-reference's `xmss_parse_oid` rejects it.
- WOTS+ replaced by WOTS+C: no checksum chains (len2 = 0, so 32 chains), and the signer
  grinds a 4-byte counter until the base-w digits of a counter hash (new padding value 5)
  sum to len1(w - 1)/2 = 240. The counter is stored at the start of the one-time
  signature. A signature is 696 bytes: a 4-byte index, the 16-byte R, the 4-byte counter,
  32 chain values of 16 bytes, and 10 authentication-path nodes of 16 bytes.

**Rule.** Unmodified xmss-reference, or any RFC 8391 or SP 800-208 verifier, cannot check
these signatures; only Jade's own XMSS code can. The benchmark's `xmss_selftest` operation
signs with a consistently generated key and verifies with that code, which is the only
check available without writing a new implementation.

Jade's fixed XMSS test key (`sign_xmss.c`) stores a root that its seeds do not produce, so
signatures made with it cannot verify against the stored key.

## SHRINCS: what a second implementation can and cannot check

- BlockstreamResearch/shrincs-cpp uses the same parameters and address types as Jade's
  port, restores the same key from a 3n-byte seed, and accepts Jade's stateful signatures.
  Jade's port follows its file layout and function names, and both come from the same
  group, so agreement is a cross-check between two implementations, not an independent
  reading of the specification.
- Both implementations verify against the variant's fixed target sum (the constant SWN:
  2,040 for SHRINCS-B, 140 for SHRINCS-L). The signer's `swn` argument is not carried in
  the signature, so a SHRINCS-L signature ground to any other sum (Blockstream's table has
  swn=96 rows) cannot verify under either implementation.
- Jade's signing handler (`sign_shrincs.c`) has one fixed 96-byte test key for both
  variant builds (seed, prf, sf, sl, pk.seed, pk.root). Under SHRINCS-L parameters, sf,
  sl, and root all follow from its seeds, and signatures made with it verify. Under
  SHRINCS-B none of the three match, so those signatures fail verification even though
  they are correct. They can still be checked up to the final root comparison: the
  signature's first 16 bytes must equal the stored sl, and the stateful root rebuilt from
  the signature (whose message hash binds the stored pk.root, as signing did) must equal
  the sf that the key's seeds produce.
- Grinding on two cores returns the first valid counter either core finds, and
  shrincs-cpp's signer grinds on several threads, so SHRINCS signatures from different
  core or thread counts can differ in bytes for the same key and message. Compare them by
  verification, not by bytes.
