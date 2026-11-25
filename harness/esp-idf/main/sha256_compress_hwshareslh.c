/*
 * PQB_SLH_COMPRESS=hwshareslh: the shared-unit backend (sha256_compress_hwshare.c) with the
 * sharing rule enabled only for SLH-DSA operations; SHRINCS and XMSS run as hwshadow.
 */
#define PQB_SHARE_SLH_ONLY 1
#include "sha256_compress_hwshare.c"
