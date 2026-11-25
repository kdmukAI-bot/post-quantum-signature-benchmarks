# Benchmarking Blockstream's Jade hash-based signature code

Notes for anyone timing or reusing the scheme code in Blockstream's Jade fork
(github.com/DmitriiKJ/Jade, branch `hash_based_signatures`, commit `f5c90a5e`), which produced
the Jade Plus column of Blockstream's hardware wallet comparison.

## Build settings in Jade's ESP32-S3 configs

All of Jade's ESP32-S3 configs (Jade Plus v2 and v2c, development and production, and the
Waveshare ESP32-S3 Touch LCD 2 config) set:

- `CONFIG_COMPILER_OPTIMIZATION_SIZE` (-Os)
- `CONFIG_SPIRAM_FETCH_INSTRUCTIONS` and `CONFIG_SPIRAM_RODATA` (code and constants in PSRAM)
- 240 MHz CPU clock

Stack checking differs: `sdkconfig_dev_jade_v2.defaults` uses `STACK_CHECK_MODE_ALL`, while
`sdkconfig_jade_v2_prod.defaults` and the Waveshare config use `STACK_CHECK_MODE_STRONG`. The
build Blockstream used for its article is not stated in the material examined. Of these
settings, `-Os` and the stack protector lengthen signing; code placement in PSRAM does not
(see "Where the gap comes from").

## Scheme code choices

- **Single core.** `slh_dsa.c` and `wots_c.c` begin with `#define CONFIG_FREERTOS_UNICORE 1`
  ("Comment to make it multithread"), which compiles out the dual-core paths that exist below.
- **Mixed hash backends.** SLH-DSA hashes with slhdsa-c's portable C SHA-256 (no hardware; see
  `esp32-sha-unit-raw-compression.md`). SHRINCS and XMSS hash through mbedTLS, which uses the
  hardware SHA unit on ESP builds.
- **SHA-1 in SHRINCS.** The SHRINCS port leaves mbedTLS contexts unstarted, which hashes with
  SHA-1 on ESP hardware (`esp-idf-mbedtls-unstarted-sha256-context.md`).
- **Cold signing.** Leaf caches are disabled (`if (0 && ...)`), so every signature computes
  its trees from scratch.

## Traps when reusing the handlers

- The SHRINCS and XMSS signing handlers use hard-coded test keys. The SHRINCS key is one key
  for both variant builds and is consistent only under SHRINCS-L parameters: SHRINCS-L
  signatures made with it verify, while under SHRINCS-B its stored sf, sl, and root do not
  follow from its seeds. The XMSS key stores a root that its seeds do not produce. Timing is
  unaffected, but SHRINCS-B and XMSS signatures made with these keys can never verify.
  Correctness checks for those need keys generated consistently (the benchmark's
  `*_selftest` operations). Details: `verifying-jade-hbs-signatures-elsewhere.md`.
- `wots_c.c` calls the progress callback without a NULL check. Pass a no-op callback.
- The SLH-DSA key generation handler also writes the leaf cache to NVS flash, which the
  host-side timing includes.

## Timing method

`test_shrincs.py` times each request on the host with `time.time()` and prints a running mean
over messages 0 to 99. The timed interval includes the USB RPC round trip and any display work
done during the request; the SLH-DSA signing handler, for one, drives a progress bar through
`update_progress_bar()`. This benchmark times only the scheme call, on the device
(`esp_timer_get_time()`), with a no-op progress callback.

## Where the gap comes from

SLH-DSA-128s signing isolates the effect of each difference best, because Jade and the
benchmark's plain-C build run the same hashing code and produce identical signatures:

| Step | Time | Factor |
|---|---|---|
| Jade Plus, Blockstream's published figure | 52.85 s | |
| Jade firmware (Waveshare config) on a Waveshare ESP32-S3 Touch LCD 2 | 48.99 s | 1.08x |
| Benchmark, plain C, -O2, on-device timing, same board | 38.37 s | 1.28x |
| SHA hardware unit | 10.10 s | 3.80x |
| Second core (hybrid) | 9.20 s | 1.10x |

The first two steps were separated with diagnostic builds of Jade's firmware that change one
setting at a time, timed on the device around the scheme call.

**The 1.28x step** is almost entirely Jade's `-Os`. Each factor below is a ratio of signing
times:

| Difference | Factor |
|---|---|
| Host timing over USB (request, reply, and dispatch) | 0.999 |
| `-Os` to `-O2` | 0.799 |
| Stack protector strong to none, and no progress bar | 0.991 |
| Other tasks on the signing core (a touchscreen polling task and `esp_timer`, 0.9% of core 0) | 0.991 |
| ESP-IDF 5.4 to 5.5.5 (toolchain included) | 1.000 |

Their product, 38.38 s, leaves less than 0.1% unexplained. Code and constants in PSRAM cost
nothing here: moving them to flash made signing 0.1% to 0.2% slower, as the hot code fits in
the 16 KB instruction cache. Singly, the stack protector in strong mode costs 0.5% and the
progress bar 0.1% at `-Os`; the progress bar also adds tens of milliseconds of run-to-run
spread.

**The 1.08x step** matches the stack protector setting of Jade's Jade Plus development config
(`sdkconfig_dev_jade_v2.defaults`, `STACK_CHECK_MODE_ALL`), where the Waveshare and
production configs use strong mode. On the Waveshare board, "all" against "strong" lengthens
signing by 8.9% (SLH-DSA), 9.4% (SPHINCS+ 2^40), 23% (SHRINCS-B), and 22% (XMSS); the
published figures exceed the Waveshare figures by 7.9%, 14%, 34%, and 21%. A development build
therefore accounts for the SLH-DSA and XMSS steps to within about 1% and leaves 4% (SPHINCS+
2^40) and 9% (SHRINCS-B) unexplained. The article does not state which build produced its
figures. The other candidates measured small: the progress bar (0.1%), host timing
(0.1% to 0.3%), and code placement in PSRAM (0.2%). The Jade Plus's PSRAM part is not stated
in the public sources examined, but Jade's configs run it in the same octal mode at 80 MHz as
on the Waveshare board.

For SHRINCS and XMSS, the benchmark's plain-C build is faster than Jade's hardware-SHA path on
the same board (SHRINCS-B signing 11.09 s against 16.20 s), consistent with the mbedTLS
per-call overhead. That path also makes more function calls per hash, which fits the larger
cost of the "all" stack protector there.

## Native (Linux) harness note

OpenSSL 3's one-shot `SHA256()` goes through the EVP layer and looks up the algorithm on every
call. For these schemes that overhead dominates: XMSS signing on a Pi Zero W took 29.9 s with
one-shot calls and about 5.4 s with `SHA256_Init`, `SHA256_Update`, and `SHA256_Final`. The
benchmark's mbedTLS shim (`harness/linux/shim/mbedtls_shim.c`) uses the low-level calls.
