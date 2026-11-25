# Using the ESP32 SHA unit for hash-based signatures

Hash-based signature schemes spend nearly all of their time in SHA-256, over millions of short
inputs. The ESP32-S3 and ESP32-P4 each have a SHA-256 hardware unit, but the usual route to
it (mbedTLS) gives up most of the benefit for this workload, and SLH-DSA's hot path cannot use
mbedTLS at all. This note records how the benchmark reaches the hardware directly and the
constraints that come with it.

## SLH-DSA needs a raw compression function

slhdsa-c computes most hashes by calling `sha2_256_compress(void *v)` on a caller-held buffer:
eight big-endian state words followed by one 64-byte message block. It reuses precomputed
midstates this way. mbedTLS has no API for compressing a caller-supplied midstate, so Jade's
SLH-DSA code runs SHA-256 in portable C even though the chip has a SHA unit.

ESP-IDF's low-level API in `sha/sha_core.h` does support it, on chips with
`SOC_SHA_SUPPORT_RESUME` (both the ESP32-S3 and the ESP32-P4):

```c
esp_sha_set_mode(SHA2_256);
esp_sha_write_digest_state(SHA2_256, state);   /* load the midstate */
esp_sha_block(SHA2_256, block, false);         /* false: not the first block */
esp_sha_read_digest_state(SHA2_256, state);
```

`esp_sha_acquire_hardware()` and `esp_sha_release_hardware()` take and release the unit. Hold
it across a whole signing or key generation operation rather than taking it per compression.

Implementation: `harness/esp-idf/main/sha256_compress_hw.c`.

## One SHA unit per chip

There is one SHA unit, shared by both cores. When both cores used it concurrently without
coordination, the signatures came out wrong; nothing crashed or reported an error. The rule the
benchmark follows:

- The core that holds the unit (core 0, the benchmark task) uses it.
- Any other core computes the compression in plain C.
- When no core holds it, a call takes the unit, compresses one block, and releases it.

This hybrid is what "hardware plus second core" means in the results. The second core still
helps, because Blockstream's dual-core code splits work between cores, and core 1 contributes
plain-C throughput alongside the hardware on core 0.

## The mbedTLS route costs about as much as it saves

SHRINCS and XMSS hash through `mbedtls_sha256_*`. With hardware SHA enabled, ESP-IDF's port
takes and releases the unit inside every `mbedtls_sha256_update()` call
(`components/mbedtls/port/sha/core/esp_sha256.c`). For these
schemes that fixed cost dominates. On the ESP32-P4 (single runs during screening), SHRINCS-B
signing took:

| Path | Time |
|---|---|
| mbedTLS, hardware SHA | 6.43 s |
| Direct API, plain-C compression | 7.07 s |
| Direct API, hardware compression | 2.79 s |

The direct API (`PQB_SHA_API=direct`) replaces the mbedTLS SHA-256 context with slhdsa-c's
incremental SHA-256 over the selected compression function
(`harness/esp-idf/main/shim_direct/`, `harness/esp-idf/main/sha256_ctx_direct.c`).

## Measured effect (10 runs each)

| SLH-DSA-128s signing | ESP32-S3, 240 MHz | ESP32-P4, 400 MHz |
|---|---|---|
| Plain C, one core | 38.37 s | 24.59 s |
| Hardware, one core | 10.10 s | 8.21 s |
| Hardware plus second core | 9.20 s | 6.50 s |

On the ESP32-S3, both cores run about 20% slower per hash when both are busy. In SHRINCS-L
grinding, the core holding the unit went from 9.60 to 11.48 µs per attempt and the plain-C
core from 22.20 to 26.88 µs. The ESP32-P4 shows no such slowdown. The cause has not been
investigated.
