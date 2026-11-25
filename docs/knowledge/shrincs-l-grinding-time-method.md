# Reporting SHRINCS-L signing time at swn=140

## Why a plain average misleads

WOTS+C signing tries counters 0, 1, 2, and so on until the hash of (message digest, counter)
written as base-W digits sums to the target swn. For SHRINCS-L, W=4 and L=64, so the sum of 64
base-4 digits has mean 96. At swn=96 a valid counter turns up after 22.5 attempts on average.
At swn=140 the target is far in the tail: the exact expected count is

    E = 4^64 / (number of 64-digit base-4 strings whose digits sum to 140) = 6,218,398

The attempt count per message is geometric, so signing time varies widely by message. On the
ESP32-S3 with hardware SHA it ranged from 3.2 s to 48 s across messages 0 to 9. Those ten
messages needed 1.92 million attempts on average, about 0.31 of E, so their mean time
understates the expected time about threefold. Even 100 messages leave a standard error of
roughly 10%.

## Method

1. Time is linear in attempts within a build: time = fixed + attempts x per-attempt. Across all
   single-core builds the fit residual was at most 0.01 s on the ESP32 targets (20 points each)
   and 0.26 s on the Pi Zero W (200 points).
2. The counter is in the signature: bytes 48 to 51, big-endian, of the stateful signature (an
   N=16-byte prefix, then R_LEN=32 bytes of randomness, then the counter). Single-core grinding
   starts at 0, so attempts = counter + 1.
3. Outputs are deterministic and identical across platforms, so the host build supplies the
   counters for every message (`pq_bench --save-all`), and each device's times are fitted
   against them.
4. Report expected time = fixed + per-attempt x E, alongside the per-attempt time.

Script: `scripts/grind_fit.py`.

## Dual-core builds

Blockstream's dual-core grinding (wots_c.c with the single-core define removed) gives even
counters to core 0 and odd counters to core 1, and returns whichever valid counter is found
first. Consequences:

- Output bytes can differ from the single-core build when a higher counter on one core is
  found before a lower one on the other. This happened for several swn=96 messages and, with
  SHRINCS-B, for one signing message and the self-test. Correctness for this path rests on the
  dual-core self-test, which signs and verifies with a consistent key.
- For a message whose lowest valid counter c is even, time = fixed + (c/2 + 1) x t0; for odd c,
  time = fixed + (c + 1)/2 x t1, where t0 and t1 are the per-attempt times of the two cores.
  These fit closely (each core's per-attempt time varies by less than 0.4% across messages).
- The expected time is fixed + E / (1/t0 + 1/t1). The static even/odd split does not reduce
  expected throughput; it only changes which messages are slow. With the hybrid SHA setup
  (core 0 on the SHA unit, core 1 in plain C), a message whose valid counter is odd can take
  longer than on a single core.

## Results

| Build | Fixed | Per attempt | Expected time, swn=140 |
|---|---|---|---|
| Pi Zero W, OpenSSL | 0.160 s | 4.18 µs | 26.1 s |
| ESP32-P4, plain C | 0.643 s | 13.80 µs | 86.5 s |
| ESP32-P4, hardware | 0.260 s | 6.50 µs | 40.7 s |
| ESP32-P4, hardware plus second core | 0.193 s | 6.42 / 13.89 µs | 27.5 s |
| ESP32-S3, plain C | 1.016 s | 22.20 µs | 139.1 s |
| ESP32-S3, hardware | 0.363 s | 9.60 µs | 60.1 s |
| ESP32-S3, hardware plus second core | 0.313 s | 11.48 / 26.88 µs | 50.3 s |

The Pi Zero W's 100-message mean (26.1 s, 6.216 million attempts on average) agrees with its
expected value.

## Comparing with published numbers

Blockstream's test script prints a running mean over messages 0 to 99; the number of messages
behind their swn=140 figures is not stated in the article text examined. Jade's SHRINCS port
also hashes partly with SHA-1 (see `esp-idf-mbedtls-unstarted-sha256-context.md`), so the
counter a given message needs on Jade differs from upstream. Only expected values are
comparable across implementations.
