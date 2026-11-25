/*
 * mldsa-native configuration for the benchmark (selected with
 * -DMLD_CONFIG_FILE="pqb_mldsa_config.h"). It sets only the options below and then
 * includes the library's own default configuration (third_party/mldsa-native/mldsa/
 * mldsa_native_config.h), so every other option keeps its default.
 *
 *   multi-level build     all three parameter sets in one compilation unit
 *                         (pqb_mldsa_all.c), internal functions static, public API
 *                         namespaced mldsa44_, mldsa65_, mldsa87_
 *   PQB_MLDSA_LOWRAM      MLD_CONFIG_REDUCE_RAM, the library's reduced-RAM option, with
 *                         the namespace mldsalr44_, mldsalr65_, mldsalr87_
 *                         (pqb_mldsa_all_lowram.c)
 *   PQB_MLDSA_COUNT       host attempt-counting builds only: an observe-only signing hook
 *                         (MLD_CONFIG_SIGN_HOOK_FINISH) records the attempt at which each
 *                         signature succeeded. The hook needs
 *                         MLD_CONFIG_NO_RANDOMIZED_API, which removes the randomized API;
 *                         the benchmark uses only the deterministic one. Timed builds
 *                         never set this.
 */
#ifndef MLD_CONFIG_H
#define MLD_CONFIG_MULTILEVEL_BUILD
#define MLD_CONFIG_INTERNAL_API_QUALIFIER static
#if defined(PQB_MLDSA_LOWRAM)
#define MLD_CONFIG_REDUCE_RAM
#define MLD_CONFIG_NAMESPACE_PREFIX mldsalr
#else
#define MLD_CONFIG_NAMESPACE_PREFIX mldsa
#endif

#if defined(PQB_MLDSA_COUNT)
#define MLD_CONFIG_NO_RANDOMIZED_API
#define MLD_CONFIG_SIGN_HOOK_FINISH
#if !defined(__ASSEMBLER__) && !defined(PQB_MLDSA_HOOK_DEFINED)
#define PQB_MLDSA_HOOK_DEFINED
#include <stdint.h>
/* Defined in op_mldsa.c: the 0-based attempt at which the last signature succeeded. */
extern volatile uint32_t pqb_mldsa_last_attempt;
static inline void mld_sign_hook_finish(uint16_t attempt)
{
    pqb_mldsa_last_attempt = attempt;
}
#endif
#endif
#endif /* !MLD_CONFIG_H */

#include "mldsa_native_config.h"
