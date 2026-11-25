# Benchmark CSV timing resolution, and untimed work in a job's wall time

Two properties of the benchmark harness (`harness/common/main.c` on Linux,
`harness/esp-idf/main/bench_esp.c` on the ESP32 boards) that affect how its numbers can be
reported and how long a run takes.

## Time resolution of the result files

Both harnesses print `wall_s` and `cpu_s` in seconds, with a format that depends on the
measurement round:

| Round | Format | Each run rounded to |
|---|---|---|
| 1, including its optimization runs | `%.4f` | 0.1 ms |
| 2 | `%.4f` | 0.1 ms |
| 3 and 4 | `%.6f` | 1 us |

Round 3 changed only this format (one line in each harness, outside every timed section)
and reran the verification and lattice job sets with otherwise identical builds: the
rebuilt Pi Zero W binaries differ from round 2's only in the two format digits, and the
rebuilt ESP32 images have every function and object at the same address.

The clocks behind the numbers are finer than either format. On the ESP32 boards,
`esp_timer_get_time()` counts whole microseconds, so six decimals carry the clock's full
resolution (these boards report CPU time equal to wall time). On the Pi Zero W,
`clock_gettime()` (CLOCK_MONOTONIC for wall time, CLOCK_PROCESS_CPUTIME_ID for CPU time)
returns nanoseconds, which six decimals round to the microsecond.

### Why 0.1 ms steps are too coarse under a few milliseconds

Rounding to 0.1 ms is a real error for short operations, and averaging does not remove
it: runs of a deterministic operation take almost the same time, so all of them round the
same way. Example: SHRINCS-L stateful verification at level 3 on the ESP32-P4 takes
331 to 339 us per run after the first, with a ten-run mean of 0.337 ms (round 3). Round 2
timed the same ten messages, printed nine runs as 0.0003 and one as 0.0004, and so
reported a mean of 0.310 ms, 8% low. In round 2, a one-core and a two-core build of the
same code also differed by 6.7% (0.75 against 0.80 ms) for this reason alone.

### What the microsecond digits show

On the ESP32 boards, repeated runs of one input agree within a few microseconds: in round
3, FN-DSA-512 verification of a single message varied by 4 to 16 us over its ten runs,
and SHRINCS-L stateful verification, which does the same hashing work for every message,
by 0 to 27 us. Two effects are larger, and both are real rather than noise:

- The first run of a job set often runs with cold caches. SHRINCS-L stateful
  verification at level 1 on the ESP32-P4 takes 1.507 ms in run 0 and 0.972 to 0.974 ms
  in the other nine, which raises the ten-run mean by 5.5%. Means in every round include
  run 0.
- Inputs differ in work. FN-DSA-512 verification of one of the ten messages takes about
  50 us less than the others on the ESP32-P4 and about 100 us less on the Waveshare
  ESP32-S3 Touch LCD 2.

So on these boards a mean over a fixed set of inputs is good to about a microsecond, and
the sixth decimal is worth keeping. On the Pi Zero W, other tasks occasionally take
several milliseconds from a single run (round 2 recorded losses of about 7 ms), so for
short operations there the median or the CPU time is the steadier figure.

### Rule

- Under about 3 ms, use the round-3 files. A round-1 or round-2 mean can be off by up to
  0.05 ms in one direction, because every run of it was rounded the same way.
- From 3 ms up, the rounds agree: on the ESP32 boards, round 3 reproduced round 2's means
  within about 0.5% for every operation of 3 ms or more, apart from FN-DSA-512
  verification at level 1 on the Waveshare ESP32-S3 Touch LCD 2 (3.25 ms), whose 1.2%
  difference is round 2's rounding: round 3's runs, rounded to 0.1 ms, give round 2's
  mean exactly. So round 2's figures for those operations stand.
- To tell print rounding from a real change, round the finer file's runs to the coarser
  file's step before averaging; if that reproduces the coarser mean, the difference is
  the rounding.

## A job set's wall time is much more than its timed rows

Each row times only the operation itself. Work the harness does around it is not timed
but still takes device time:

- `shrincs_selftest` first calls `shrincs_restore()` to derive a consistent key from the
  run's seed, which rebuilds the stateful tree and a whole top hypertree layer. Under
  SHRINCS-B this dominates: on the ESP32-P4 at level 3 a self-test row takes about 3
  minutes of wall time for under 2 s of timed signing (about 4 minutes on the Waveshare
  ESP32-S3 Touch LCD 2, and 5 minutes there on two cores).
- `shrincs_restore()` runs outside the timed section's SHA-unit hold
  (`pqb_mbedtls_core_begin()`), so in the ESP32 builds that use the SHA unit (levels 2
  and 3) every compression acquires and releases the unit on its own, and in two-core
  builds both cores contend for it. The restore therefore takes about the same time at
  every level (about 165 s on one core at level 3 and 213 s at level 1 on the ESP32-P4),
  about three times one hypertree layer of a timed signature at level 3.
- `xmss_selftest` generates its key untimed (about the time of `xmss_keygen`), and
  `shrincs_sign_stateless` verifies its signature and replays the PORS+FP PRF from
  counter 0 to recover the grinding counter after the timed call.

Rule: estimate a job set's run time from measured wall times (the queue logs' start and
done lines), not from the sum of its timed rows. In particular, a job list that runs the
SHRINCS-B self-test n times costs n restores, which can outweigh everything else in the
list.
