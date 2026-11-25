/*
 * PQB_SLH_COMPRESS=asm (screening only): slhdsa-c's sha2_256_compress() is OpenSSL
 * 3.4.1's ARMv4 integer SHA-256 block function in its Thumb-2 form, the single-block
 * big-endian copy that the Pi Zero W level-3 build uses
 * (harness/linux/shim/openssl-armv4/sha256-armv4-be.S, assembled by
 * sha256_armv4_thumb.S).
 */
void sha2_256_compress_asm(void* v);

void sha2_256_compress(void* v) { sha2_256_compress_asm(v); }
