# ESP-IDF hardware SHA: an unstarted mbedtls_sha256 context hashes with SHA-1

## Rule

On ESP-IDF builds with `CONFIG_MBEDTLS_HARDWARE_SHA` (the default on the ESP32-S3 and
ESP32-P4), always call `mbedtls_sha256_starts(&ctx, 0)` after `mbedtls_sha256_init(&ctx)`
and before the first `mbedtls_sha256_update()`. Code that skips `starts()` still compiles
and runs, but it does not compute SHA-256.

## What happens without starts()

`mbedtls_sha256_init()` zeroes the context. In ESP-IDF's hardware SHA port the context
carries a mode field whose values come from the `SHA_TYPE` enum, where `SHA1 = 0`,
followed by `SHA2_224` and `SHA2_256`. A zeroed context therefore drives the SHA
peripheral in SHA-1 mode. `mbedtls_sha256_finish()` then writes the 20-byte SHA-1 digest
followed by 12 zero bytes into the 32-byte output.

The result is deterministic and repeatable, so nothing fails at run time. Self-consistent
code (sign and verify on the same build) also works, because both sides make the same
substitution. The outputs differ from any implementation that computes SHA-256, such as
upstream libraries that call `SHA256_Init()` before hashing.

## Where this matters

Code ported from a library whose SHA-256 API needs no separate start call (for example
OpenSSL's `SHA256_Init`, which initializes and starts in one call) is prone to this. A
mechanical port to `mbedtls_sha256_init()` alone produces SHA-1 on ESP hardware.

Blockstream's Jade port of SHRINCS (DmitriiKJ/Jade, branch `hash_based_signatures`, commit
`f5c90a5e`) calls `mbedtls_sha256_init()` without `starts()`, where upstream shrincs-c
calls `SHA256_Init()`. The Jade firmware's SHRINCS-B signature for message 0 begins
`d7531457`. A desktop build that emulates the unstarted-context behavior reproduces it
byte for byte, while a build with upstream semantics produces a signature whose SHA-256
begins `1797f13d`.

## How to detect it

Build the same code on a desktop with an mbedTLS shim that treats an unstarted context as
SHA-1 with zero padding, and compare outputs with the device. In this repository that is
`make EMU=esp` in `harness/linux/` (compile flag `SHIM_EMULATE_ESP_UNSTARTED_SHA1`,
implemented in `harness/linux/shim/mbedtls_shim.c`). On the ESP side, `harness/esp-idf`
starts every context as SHA-256 by default (`harness/esp-idf/main/shim/mbedtls/sha256.h`)
and reproduces Jade's behavior only with `-DPQB_JADE_SHA_SEMANTICS=1`.
