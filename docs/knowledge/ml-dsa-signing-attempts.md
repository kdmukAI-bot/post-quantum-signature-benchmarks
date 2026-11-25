# ML-DSA signing time is a per-message expected value

## Why a mean over a few messages misleads

ML-DSA signing (FIPS 204, Algorithm 7) repeats a rejection-sampling loop until a candidate
signature passes its norm and hint checks. The number of attempts is geometric and, for
deterministic signing (rnd = 32 zero bytes, which FIPS 204 permits; hedged signing with
fresh randomness is the default), a fixed function of the key and the message. Signing
time is close to linear in it.

With the benchmark's key (seed `run_input(0)`) and messages `run_input(x)`, the attempts
for messages 0 to 9 average 3.40 (ML-DSA-44), 9.00 (ML-DSA-65), and 2.80 (ML-DSA-87),
against long-run means of about 4.36, 5.14, and 3.91. A ten-message mean of ML-DSA-65
signing time would overstate the expected time by roughly 75%.

Expected attempts: mldsa-native's test suite (`test/src/test_sign_hook.c`, commit
834a90d5) uses 4.361, 5.138, and 3.906, measured over 3 x 10^8 signatures with fresh keys,
and says they match the FIPS 204 errata; the 4.25, 5.10, and 3.85 printed in FIPS 204
Table 1 count only the first-stage rejections. Over 20,000 messages with the benchmark's
own key the means were 4.332, 5.090, and 3.883 (counted by the harness's host build).

## Method

1. Count attempts per message on the host. mldsa-native has an observe-only signing hook
   (`MLD_CONFIG_SIGN_HOOK_FINISH`, which needs `MLD_CONFIG_NO_RANDOMIZED_API`); the host
   counting build (`harness/linux/Makefile COUNT=1`) enables it and writes `attempts=A` to
   the grind column. Its outputs are byte-identical to the default build's, and
   deterministic signing gives the same bytes on every board, so the counts hold
   everywhere. Timed builds keep the library's default configuration.
2. Fit each board's times: time = fixed + per_attempt x attempts
   (`scripts/grind_fit_r2.py --attempts ...`).
3. Report fixed + per_attempt x E with E from step 1's reference values, and state which E
   was used.

The fit is approximate in one known way: an attempt rejected at the first check (the z
norm) costs less than one that reaches the hint computation, so per_attempt is an average
over rejection stages. The residual of the fit shows how much this matters per board.

## Reduced-RAM builds

mldsa-native's `MLD_CONFIG_REDUCE_RAM` recomputes data on the fly instead of keeping it,
and gives byte-identical outputs. It moves work into the loop, so the per-attempt cost
rises more than the fixed cost; fit the reduced-RAM rows separately.
