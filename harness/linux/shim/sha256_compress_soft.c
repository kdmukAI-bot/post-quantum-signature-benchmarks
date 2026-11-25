/* Plain-C SHA-256 compression: forwards to slhdsa-c's own implementation (renamed at
 * build time), for comparison against the OpenSSL version. */
void sha2_256_compress_soft(void* v);

void sha2_256_compress(void* v) { sha2_256_compress_soft(v); }
