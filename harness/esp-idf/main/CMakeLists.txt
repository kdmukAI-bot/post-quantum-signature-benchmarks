# ESP-IDF build of the shared benchmark (harness/common) over Blockstream's Jade scheme
# sources. The scheme sources are copied from third_party/jade-hbs at configure time
# (unmodified apart from renaming slhdsa-c's sha2_256_compress so a replacement can stand in
# for it).
#
# Cache variables (pass with idf.py -D...):
#   PQB_SHRINCS=B|L             SHRINCS variant (default B)
#   PQB_SLH_COMPRESS=soft|hw    SLH-DSA SHA-256 compression: plain C or the SHA peripheral
#   PQB_JADE_SHA_SEMANTICS=1    leave Jade's unstarted mbedTLS contexts as they are (to
#                               reproduce the Jade firmware's SHRINCS output exactly)
#   PQB_RUNS=N                  runs per timed operation (default 10)
#   PQB_DUAL_CORE=1             enable Blockstream's dual-core paths in slh_dsa.c and
#                               wots_c.c (their "Comment to make it multithread" defines)
#   PQB_SHA_API=mbedtls|direct  how SHRINCS and XMSS hash: ESP-IDF's mbedTLS (default), or a
#                               direct SHA-256 API over slhdsa-c's code and the selected
#                               compression function (no mbedTLS locking per call)
#
# Optimization options (added later; all default off, and the builds above are unchanged):
#   PQB_SLH_COMPRESS=hwreg     the SHA peripheral through its registers, mode set once per
#                              hold, compression function in IRAM
#                              (sha256_compress_hwreg.c)
#   PQB_SLH_COMPRESS=hwshadow  as hwreg, writing only the message-register words that
#                              changed since the previous block (sha256_compress_hwshadow.c)
#   PQB_SLH_COMPRESS=hwmin     as hwshadow, and no state-register writes for blocks that
#                              start from the initial value or continue the previous block
#                              (sha256_compress_hwmin.c)
#   PQB_SLH_COMPRESS=hwshare   as hwshadow, and the second core uses the SHA peripheral
#                              while the first core is not hashing
#                              (sha256_compress_hwshare.c; dual-core builds)
#   PQB_SLH_COMPRESS=hwshareslh  as hwshare for SLH-DSA operations, as hwshadow for SHRINCS
#                              and XMSS (sha256_compress_hwshareslh.c)
#   PQB_SLH_COMPRESS=mb        run-time selectable, counting backend for the microbenchmark
#   PQB_DIRECT_FAST=1          with PQB_SHA_API=direct: the context API with fewer copies
#                              (sha256_ctx_fast.c instead of sha256_ctx_direct.c)
#   PQB_MICROBENCH=1           run the SHA-256 compression microbenchmark instead of the
#                              benchmark jobs (needs PQB_SLH_COMPRESS=mb and
#                              PQB_SHA_API=direct)
#   PQB_IRAM=1                 place the scheme code and the SHA-256 code in IRAM
#                              (linker fragment pqb_iram.lf; no source changes)
#   PQB_COPTS="-O3;..."        extra compile options for this component, after the defaults
#   PQB_SCREEN=1               signing operations only, without the self-tests (screening)
#   PQB_TAG=text               appended to the variant string, to label optimized builds
#
# Round 2 (all builds): the lattice schemes (mldsa-native and c-fn-dsa from third_party/,
# unmodified; see harness/common/op_mldsa.c and op_fndsa.c) and the verification vectors
# harness/linux/vectors/vectors-<PQB_SHRINCS>.bin (made by the host harness, pq_bench
# --write-vectors) are compiled in, and the job set is chosen at run time over the console
# (bench_esp.c). Lattice code stays in flash in every build (PQB_IRAM places only
# the hash-based scheme code, as before).
# sdkconfig overlays (cache sizes and similar) are selected with the standard
# SDKCONFIG_DEFAULTS variable, for example
# -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.opt-cache".

set(PQB_ROOT ${CMAKE_CURRENT_LIST_DIR}/../../..)
set(JADE_MAIN ${PQB_ROOT}/third_party/jade-hbs/main)
set(MLDSA_DIR ${PQB_ROOT}/third_party/mldsa-native/mldsa)
set(FNDSA_DIR ${PQB_ROOT}/third_party/c-fn-dsa)
set(GEN ${CMAKE_BINARY_DIR}/pqgen)

if(NOT DEFINED PQB_SHRINCS)
    set(PQB_SHRINCS B)
endif()
if(NOT DEFINED PQB_SLH_COMPRESS)
    set(PQB_SLH_COMPRESS soft)
endif()
if(NOT DEFINED PQB_RUNS)
    set(PQB_RUNS 10)
endif()
if(NOT DEFINED PQB_SHA_API)
    set(PQB_SHA_API mbedtls)
endif()
set(PQB_EXTRA_SRCS "")
set(PQB_SHIM_DIRS shim)
if(PQB_SHA_API STREQUAL "direct")
    set(PQB_EXTRA_SRCS sha256_ctx_direct.c)
    set(PQB_SHIM_DIRS shim_direct shim)
    if(PQB_DIRECT_FAST)
        set(PQB_EXTRA_SRCS sha256_ctx_fast.c)
    endif()
endif()
if(PQB_MICROBENCH)
    if(NOT PQB_SLH_COMPRESS STREQUAL "mb" OR NOT PQB_SHA_API STREQUAL "direct")
        message(FATAL_ERROR
                "PQB_MICROBENCH needs PQB_SLH_COMPRESS=mb and PQB_SHA_API=direct")
    endif()
    list(APPEND PQB_EXTRA_SRCS microbench_esp.c)
endif()
set(PQB_LDFRAGMENTS "")
if(PQB_IRAM)
    set(PQB_LDFRAGMENTS pqb_iram.lf)
endif()

if(NOT CMAKE_BUILD_EARLY_EXPANSION)
    file(REMOVE_RECURSE ${GEN})
    file(COPY ${JADE_MAIN}/shrincs ${JADE_MAIN}/slh_dsa ${JADE_MAIN}/xmss DESTINATION ${GEN})
    file(READ ${GEN}/slh_dsa/sha2_256.c SHA_SRC)
    string(REPLACE "void sha2_256_compress(void *v)\n" "void sha2_256_compress_soft(void *v)\n"
           SHA_SRC_RENAMED "${SHA_SRC}")
    if(SHA_SRC_RENAMED STREQUAL SHA_SRC)
        message(FATAL_ERROR "could not rename sha2_256_compress in slh_dsa/sha2_256.c")
    endif()
    file(WRITE ${GEN}/slh_dsa/sha2_256.c "${SHA_SRC_RENAMED}")
    if(PQB_DUAL_CORE)
        foreach(f slh_dsa/slh_dsa.c shrincs/wots_c.c)
            file(READ ${GEN}/${f} SRC)
            string(REPLACE "#define CONFIG_FREERTOS_UNICORE 1\n"
                   "/* dual-core build: single-core define removed */\n" SRC_DUAL "${SRC}")
            if(SRC_DUAL STREQUAL SRC)
                message(FATAL_ERROR "could not remove the single-core define in ${f}")
            endif()
            file(WRITE ${GEN}/${f} "${SRC_DUAL}")
        endforeach()
    endif()
    file(WRITE ${GEN}/jade_tasks.h
         "#pragma once\n#define JADE_CORE_PRIMARY 0\n#define JADE_CORE_SECONDARY 1\n"
         "#define JADE_TASK_PRIO_TEMPORARY 5\n")
endif()

set(SCHEME_SRCS
    shrincs/address.c shrincs/hash.c shrincs/pors_fp.c shrincs/shrincs.c shrincs/uxmss.c
    shrincs/wots_c.c shrincs/xmss.c
    slh_dsa/sha2_256.c slh_dsa/sha2_512.c slh_dsa/sha3_api.c slh_dsa/sha3_f1600.c
    slh_dsa/slh_dsa.c slh_dsa/slh_prehash.c slh_dsa/slh_sha2.c slh_dsa/slh_shake.c
    xmss/fips202.c xmss/hash_address.c xmss/hash.c xmss/params.c xmss/randombytes.c
    xmss/utils.c xmss/wots.c xmss/xmss_commons.c xmss/xmss_core.c xmss/xmss.c)
list(TRANSFORM SCHEME_SRCS PREPEND ${GEN}/)

set(PQB_VECTORS_FILE ${PQB_ROOT}/harness/linux/vectors/vectors-${PQB_SHRINCS}.bin)
if(NOT EXISTS ${PQB_VECTORS_FILE})
    message(FATAL_ERROR "missing ${PQB_VECTORS_FILE}: run the host harness with --write-vectors")
endif()
set(MLDSA_SRCS ${PQB_ROOT}/harness/common/lattice/pqb_mldsa_all.c
    ${PQB_ROOT}/harness/common/lattice/pqb_mldsa_all_lowram.c)
set(FNDSA_SRCS codec.c mq.c sha3.c sysrng.c util.c kgen.c kgen_fxp.c kgen_gauss.c kgen_mp31.c
    kgen_ntru.c kgen_poly.c kgen_zint31.c sign.c sign_core.c sign_fpoly.c sign_fpr.c
    sign_sampler.c vrfy.c)
list(TRANSFORM FNDSA_SRCS PREPEND ${FNDSA_DIR}/)

idf_component_register(
    SRCS bench_esp.c sha256_compress_${PQB_SLH_COMPRESS}.c ${PQB_EXTRA_SRCS}
         ${PQB_ROOT}/harness/common/common.c ${PQB_ROOT}/harness/common/op_slh.c
         ${PQB_ROOT}/harness/common/op_shrincs.c ${PQB_ROOT}/harness/common/op_xmss.c
         ${PQB_ROOT}/harness/common/op_mldsa.c ${PQB_ROOT}/harness/common/op_fndsa.c
         ${PQB_ROOT}/harness/common/vectors.c ${PQB_ROOT}/harness/common/vectors_blob.c
         ${SCHEME_SRCS} ${MLDSA_SRCS} ${FNDSA_SRCS}
    PRIV_INCLUDE_DIRS ${PQB_SHIM_DIRS} ${GEN} ${PQB_ROOT}/harness/common ${FNDSA_DIR}
    PRIV_REQUIRES mbedtls esp_timer esp_hw_support esp_driver_usb_serial_jtag esp_driver_uart
    LDFRAGMENTS ${PQB_LDFRAGMENTS})

set_source_files_properties(${PQB_ROOT}/harness/common/vectors_blob.c PROPERTIES
    COMPILE_DEFINITIONS "PQB_VECTORS_FILE=\"${PQB_VECTORS_FILE}\""
    OBJECT_DEPENDS ${PQB_VECTORS_FILE})
set_source_files_properties(${PQB_ROOT}/harness/common/vectors.c PROPERTIES
    COMPILE_DEFINITIONS PQB_HAVE_VECTORS=1
    OBJECT_DEPENDS ${PQB_VECTORS_FILE})
set_source_files_properties(${MLDSA_SRCS} PROPERTIES
    COMPILE_DEFINITIONS "MLD_CONFIG_FILE=\"pqb_mldsa_config.h\""
    INCLUDE_DIRECTORIES "${PQB_ROOT}/harness/common/lattice;${MLDSA_DIR}"
    OBJECT_DEPENDS "${PQB_ROOT}/harness/common/lattice/pqb_mldsa_config.h;${PQB_ROOT}/harness/common/lattice/pqb_mldsa_all.c")
set_source_files_properties(${FNDSA_SRCS} PROPERTIES
    COMPILE_DEFINITIONS "FNDSA_AVX2=0;FNDSA_SSE2=0;FNDSA_NEON=0;FNDSA_RV64D=0"
    COMPILE_OPTIONS "-w")

if(PQB_DUAL_CORE)
    set(PQB_CORES dual-core)
else()
    set(PQB_CORES single-core)
endif()
set(PQB_VARIANT_STR
    "shrincs-${PQB_SHRINCS} compress-${PQB_SLH_COMPRESS} sha-api-${PQB_SHA_API} ${PQB_CORES}")
if(DEFINED PQB_TAG AND NOT PQB_TAG STREQUAL "")
    string(APPEND PQB_VARIANT_STR " ${PQB_TAG}")
endif()
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    SHRINCS_${PQB_SHRINCS} PQB_RUNS=${PQB_RUNS}
    PQB_VARIANT="${PQB_VARIANT_STR}")
if(PQB_MICROBENCH)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PQB_MICROBENCH=1)
endif()
if(PQB_SCREEN)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PQB_SCREEN=1)
endif()
if(PQB_SHA_API STREQUAL "direct")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PQB_SHA_API_DIRECT=1)
endif()
# wots_c.c includes freertos/task.h first; Jade's single-file build had FreeRTOS.h earlier
target_compile_options(${COMPONENT_LIB} PRIVATE "SHELL:-include freertos/FreeRTOS.h")
if(PQB_JADE_SHA_SEMANTICS)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PQB_JADE_SHA_SEMANTICS=1)
endif()
target_compile_options(${COMPONENT_LIB} PRIVATE
    -Wno-unused-function -Wno-unused-variable -Wno-unused-but-set-variable
    -Wno-maybe-uninitialized -Wno-format)
if(DEFINED PQB_COPTS AND NOT PQB_COPTS STREQUAL "")
    target_compile_options(${COMPONENT_LIB} PRIVATE ${PQB_COPTS})
endif()
