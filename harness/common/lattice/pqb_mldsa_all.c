/*
 * mldsa-native, all three parameter sets in one compilation unit, as in the library's
 * examples/monolithic_build_multilevel/mldsa_native_all.c. The library sources are
 * included unmodified from third_party/mldsa-native/mldsa/; configuration is in
 * pqb_mldsa_config.h. Compiled twice: as is, and with PQB_MLDSA_LOWRAM defined
 * (pqb_mldsa_all_lowram.c).
 */
#define MLD_CONFIG_MULTILEVEL_WITH_SHARED
#define MLD_CONFIG_MONOBUILD_KEEP_SHARED_HEADERS
#define MLD_CONFIG_PARAMETER_SET 44
#include "mldsa_native.c"
#undef MLD_CONFIG_PARAMETER_SET
#undef MLD_CONFIG_MULTILEVEL_WITH_SHARED

#define MLD_CONFIG_MULTILEVEL_NO_SHARED
#define MLD_CONFIG_PARAMETER_SET 65
#include "mldsa_native.c"
#undef MLD_CONFIG_PARAMETER_SET
#undef MLD_CONFIG_MONOBUILD_KEEP_SHARED_HEADERS

#define MLD_CONFIG_PARAMETER_SET 87
#include "mldsa_native.c"
#undef MLD_CONFIG_PARAMETER_SET
