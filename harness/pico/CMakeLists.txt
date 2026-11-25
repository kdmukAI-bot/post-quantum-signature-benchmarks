# Pico SDK build of the shared benchmark (harness/common) for the Waveshare RP2350 Touch
# LCD 2 (RP2350A, Arm Cortex-M33 cores only; the Hazard3 RISC-V cores are not used). Built
# in the pinned Docker image of harness/pico/docker/Dockerfile by
# scripts/r4_rp2350_build.sh.
#
# Blockstream's Jade scheme sources are copied from third_party/jade-hbs at configure
# time, unmodified apart from the two edits both other harnesses make: slhdsa-c's
# sha2_256_compress() is renamed so a replacement can stand in for it, and in two-core
# builds the "#define CONFIG_FREERTOS_UNICORE 1" line of slh_dsa.c and wots_c.c is removed
# (Jade's "Comment to make it multithread" switch). The lattice libraries are compiled
# from third_party/, unmodified.
#
# The application runs under FreeRTOS SMP (raspberrypi/FreeRTOS-Kernel, RP2350_ARM_NTZ
# port), as Jade and the ESP32 harness run under ESP-IDF's FreeRTOS, so Jade's two-core
# code paths (xTaskCreatePinnedToCore, task notifications, vTaskDelay, vTaskDelete) run
# with their own semantics; shim/freertos/task.h maps the ESP-IDF names onto the kernel.
#
# Cache variables (pass with cmake -D...):
#   PQB_SHRINCS=B|L          SHRINCS variant (default B)
#   PQB_SLH_COMPRESS=...     SHA-256 compression behind slhdsa-c and the direct context
#                            API
#                              soft      slhdsa-c's portable C (level 1)
#                              sdk       the SHA-256 accelerator through the SDK's
#                                        hardware_sha256 driver functions (level 2)
#                              reg       the accelerator through its registers (level 3
#                                        candidate)
#                              asm       OpenSSL's ARMv4/Thumb-2 assembly (screen only)
#                              mb        run-time selectable, for the microbenchmark
#   PQB_DUAL_CORE=0|1        Blockstream's two-core paths (default 0)
#   PQB_RUNS=N               default runs per op (default 10)
#   PQB_OPT=O2|O3            optimization level for every source (default O2)
#   PQB_LTO=1                link-time optimization
#   PQB_PLACEMENT=flash|ram|hot
#                            flash: the SDK's default binary type, code runs in place
#                                   from flash through the XIP cache (default)
#                            ram:   copy_to_ram binary, all code and read-only data copied
#                                   to SRAM at boot (the vector blob stays in flash)
#                            hot:   default binary with the hash-based scheme code and the
#                                   SHA-256 code placed in SRAM by a linker script
#                                   (ld_hot/; no source changes)
#   PQB_FALLBACK=asm         with sdk or reg: OpenSSL's Thumb-2 assembly instead of
#                            slhdsa-c's portable C for compressions the accelerator does
#                            not serve (core 1 in two-core builds; states it has not seen)
#   PQB_CTX_FAST=1           direct context API with fewer copies (the ESP32 level-3
#                            sha256_ctx_fast.c) instead of
#                            harness/linux/shim/sha256_ctx_direct.c
#   PQB_MICROBENCH=1         run the SHA-256 microbenchmark instead of the job sets
#                            (needs PQB_SLH_COMPRESS=mb)
#   PQB_FNDSA_CM4=1          c-fn-dsa with its own ARM Cortex-M4 assembly and inline
#                            assembly (FNDSA_ASM_CORTEXM4=1 and the five *_cm4.s files;
#                            labeled lattice variation). The Cortex-M33 with its DSP
#                            extension executes the ARMv7E-M instructions it uses;
#                            c-fn-dsa's failsafe check looks for __ARM_ARCH_7EM__, which
#                            this option defines for c-fn-dsa's sources only (GCC defines
#                            __ARM_ARCH_8M_MAIN__ for the M33).
#   PQB_HEAP_KB=N            FreeRTOS heap size in KiB (default 400; smaller for ram)
#   PQB_TAG=text             appended to the variant string
cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED PICO_BOARD)
    set(PICO_BOARD pico2)
endif()
set(PICO_PLATFORM rp2350-arm-s)
# The board carries 16 MiB of flash (picotool info); pico2's header says 4 MiB.
set(PICO_FLASH_SIZE_BYTES 16777216)

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
include($ENV{FREERTOS_KERNEL_PATH}/portable/ThirdParty/GCC/RP2350_ARM_NTZ/FreeRTOS_Kernel_import.cmake)

project(pqb_rp C CXX ASM)
set(CMAKE_C_STANDARD 11)

if(NOT DEFINED PQB_OPT)
    set(PQB_OPT O2)
endif()
# The SDK's default build type is Release (-O3 -DNDEBUG); the levels set -O2 or -O3 and
# keep the Release default's NDEBUG.
set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
set(CMAKE_C_FLAGS_RELEASE "-${PQB_OPT} -DNDEBUG" CACHE STRING "" FORCE)
set(CMAKE_CXX_FLAGS_RELEASE "-${PQB_OPT} -DNDEBUG" CACHE STRING "" FORCE)
set(CMAKE_ASM_FLAGS_RELEASE "-DNDEBUG" CACHE STRING "" FORCE)

pico_sdk_init()

set(PQB_ROOT ${CMAKE_CURRENT_LIST_DIR}/../..)
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
if(NOT DEFINED PQB_DUAL_CORE)
    set(PQB_DUAL_CORE 0)
endif()
if(NOT DEFINED PQB_PLACEMENT)
    set(PQB_PLACEMENT flash)
endif()
if(NOT DEFINED PQB_HEAP_KB)
    if(PQB_PLACEMENT STREQUAL "ram")
        set(PQB_HEAP_KB 200)
    else()
        set(PQB_HEAP_KB 400)
    endif()
endif()

# --- Jade scheme sources, copied as the other harnesses copy them
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
    message(FATAL_ERROR "missing ${PQB_VECTORS_FILE}")
endif()
set(MLDSA_SRCS ${PQB_ROOT}/harness/common/lattice/pqb_mldsa_all.c
    ${PQB_ROOT}/harness/common/lattice/pqb_mldsa_all_lowram.c)
set(FNDSA_SRCS codec.c mq.c sha3.c sysrng.c util.c kgen.c kgen_fxp.c kgen_gauss.c kgen_mp31.c
    kgen_ntru.c kgen_poly.c kgen_zint31.c sign.c sign_core.c sign_fpoly.c sign_fpr.c
    sign_sampler.c vrfy.c)
list(TRANSFORM FNDSA_SRCS PREPEND ${FNDSA_DIR}/)
set(FNDSA_DEFS "FNDSA_AVX2=0;FNDSA_SSE2=0;FNDSA_NEON=0;FNDSA_RV64D=0")
if(PQB_FNDSA_CM4)
    set(FNDSA_ASM_SRCS codec_cm4.s mq_cm4.s sha3_cm4.s sign_fpr_cm4.s sign_sampler_cm4.s)
    list(TRANSFORM FNDSA_ASM_SRCS PREPEND ${FNDSA_DIR}/)
    list(APPEND FNDSA_DEFS "FNDSA_ASM_CORTEXM4=1" "__ARM_ARCH_7EM__=1")
else()
    set(FNDSA_ASM_SRCS "")
endif()

set(BENCH_SRCS
    ${PQB_ROOT}/harness/common/common.c ${PQB_ROOT}/harness/common/op_slh.c
    ${PQB_ROOT}/harness/common/op_shrincs.c ${PQB_ROOT}/harness/common/op_xmss.c
    ${PQB_ROOT}/harness/common/op_mldsa.c ${PQB_ROOT}/harness/common/op_fndsa.c
    ${PQB_ROOT}/harness/common/vectors.c)
if(PQB_CTX_FAST)
    set(CTX_SRC ${PQB_ROOT}/harness/esp-idf/main/sha256_ctx_fast.c)
else()
    set(CTX_SRC ${PQB_ROOT}/harness/linux/shim/sha256_ctx_direct.c)
endif()
if(PQB_SLH_COMPRESS STREQUAL "soft")
    set(COMPRESS_SRCS ${PQB_ROOT}/harness/linux/shim/sha256_compress_soft.c)
else()
    set(COMPRESS_SRCS ${CMAKE_CURRENT_LIST_DIR}/sha256_compress_${PQB_SLH_COMPRESS}.c)
endif()
if(PQB_SLH_COMPRESS STREQUAL "asm" OR PQB_SLH_COMPRESS STREQUAL "mb"
   OR PQB_FALLBACK STREQUAL "asm")
    list(APPEND COMPRESS_SRCS ${CMAKE_CURRENT_LIST_DIR}/sha256_armv4_thumb.S)
endif()
set(RP_SRCS bench_rp.c pqb_rp_alloc.c pqb_rp_fault.c sha512_slhdsa.c vectors_blob_rp.c)
if(PQB_MICROBENCH)
    if(NOT PQB_SLH_COMPRESS STREQUAL "mb")
        message(FATAL_ERROR "PQB_MICROBENCH needs PQB_SLH_COMPRESS=mb")
    endif()
    list(APPEND RP_SRCS microbench_rp.c)
endif()

add_executable(pqb_rp ${RP_SRCS} ${COMPRESS_SRCS} ${CTX_SRC} ${BENCH_SRCS} ${SCHEME_SRCS}
    ${MLDSA_SRCS} ${FNDSA_SRCS} ${FNDSA_ASM_SRCS})

target_include_directories(pqb_rp PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}            # FreeRTOSConfig.h, pqb_rp_alloc.h
    ${CMAKE_CURRENT_LIST_DIR}/shim       # freertos/, esp_timer.h, esp_attr.h, random.h, ...
    ${PQB_ROOT}/harness/linux/shim_direct        # mbedtls/sha256.h: the direct SHA-256 API
    ${GEN} ${PQB_ROOT}/harness/common ${FNDSA_DIR})

set_source_files_properties(vectors_blob_rp.c PROPERTIES
    COMPILE_DEFINITIONS "PQB_VECTORS_FILE=\"${PQB_VECTORS_FILE}\""
    OBJECT_DEPENDS ${PQB_VECTORS_FILE})
set_source_files_properties(${PQB_ROOT}/harness/common/vectors.c PROPERTIES
    COMPILE_DEFINITIONS PQB_HAVE_VECTORS=1
    OBJECT_DEPENDS ${PQB_VECTORS_FILE})
# common.c takes its clock from esp_timer_get_time() under ESP_PLATFORM; shim/esp_timer.h
# supplies that function from the SDK's time_us_64() (the 1 MHz system timer).
set_source_files_properties(${PQB_ROOT}/harness/common/common.c PROPERTIES
    COMPILE_DEFINITIONS ESP_PLATFORM=1)
set_source_files_properties(${MLDSA_SRCS} PROPERTIES
    COMPILE_DEFINITIONS "MLD_CONFIG_FILE=\"pqb_mldsa_config.h\""
    INCLUDE_DIRECTORIES "${PQB_ROOT}/harness/common/lattice;${MLDSA_DIR}"
    OBJECT_DEPENDS "${PQB_ROOT}/harness/common/lattice/pqb_mldsa_config.h;${PQB_ROOT}/harness/common/lattice/pqb_mldsa_all.c")
set_source_files_properties(${FNDSA_SRCS} PROPERTIES
    COMPILE_DEFINITIONS "${FNDSA_DEFS}"
    COMPILE_OPTIONS "-w")
if(PQB_FNDSA_CM4)
    # The .s files start with ".cpu cortex-m4", which leaves the assembler without an FPU;
    # they use the FPU's registers as scratch storage (vmov), so name the M33's
    # single-precision FPU for them.
    set_source_files_properties(${FNDSA_ASM_SRCS} PROPERTIES
        COMPILE_OPTIONS "-Wa,-mfpu=fpv5-sp-d16")
endif()
# The harness's allocations go to the FreeRTOS heap, where they are counted with the task
# stacks (pqb_rp_alloc.h); only harness code allocates.
set_source_files_properties(${BENCH_SRCS} bench_rp.c microbench_rp.c PROPERTIES
    COMPILE_OPTIONS "-include;${CMAKE_CURRENT_LIST_DIR}/pqb_rp_alloc.h")

if(PQB_DUAL_CORE)
    set(PQB_CORES dual-core)
else()
    set(PQB_CORES single-core)
endif()
set(PQB_VARIANT_STR
    "shrincs-${PQB_SHRINCS} compress-${PQB_SLH_COMPRESS} sha-api-direct ${PQB_CORES}")
if(DEFINED PQB_TAG AND NOT PQB_TAG STREQUAL "")
    string(APPEND PQB_VARIANT_STR " ${PQB_TAG}")
endif()

target_compile_definitions(pqb_rp PRIVATE
    SHRINCS_${PQB_SHRINCS} PQB_RUNS=${PQB_RUNS} PQB_SHA_API_DIRECT=1
    PQB_VARIANT="${PQB_VARIANT_STR}" PQB_OPT_STR="${PQB_OPT}"
    PQB_PLACEMENT_STR="${PQB_PLACEMENT}" PQB_HEAP_KB=${PQB_HEAP_KB}
    PICO_FLASH_SIZE_BYTES=16777216
    PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=0)
if(PQB_DUAL_CORE)
    target_compile_definitions(pqb_rp PRIVATE PQB_DUAL_CORE=1)
endif()
if(PQB_FALLBACK STREQUAL "asm")
    target_compile_definitions(pqb_rp PRIVATE PQB_RPH_SOFT_FN=sha2_256_compress_asm)
endif()
if(PQB_MICROBENCH)
    target_compile_definitions(pqb_rp PRIVATE PQB_MICROBENCH=1)
endif()
if(PQB_LTO)
    # Link-time optimization over the benchmark's own sources (scheme, lattice, harness,
    # SHA-256 code). The SDK's and FreeRTOS's sources stay out: with them included, an
    # LTRANS unit failed to assemble ("offset out of range").
    target_compile_definitions(pqb_rp PRIVATE PQB_LTO=1)
    set_property(SOURCE bench_rp.c pqb_rp_alloc.c sha512_slhdsa.c ${COMPRESS_SRCS} ${CTX_SRC}
        ${BENCH_SRCS} ${SCHEME_SRCS} ${MLDSA_SRCS} ${FNDSA_SRCS}
        APPEND PROPERTY COMPILE_OPTIONS -flto)
    target_link_options(pqb_rp PRIVATE -flto -${PQB_OPT})
endif()
# wots_c.c includes freertos/task.h first; the ESP32 harness forces FreeRTOS.h in first
# too
set_source_files_properties(${SCHEME_SRCS} PROPERTIES
    COMPILE_OPTIONS "-include;${CMAKE_CURRENT_LIST_DIR}/shim/freertos/FreeRTOS.h")
target_compile_options(pqb_rp PRIVATE
    $<$<COMPILE_LANGUAGE:C>:-Wno-unused-function -Wno-unused-variable
    -Wno-unused-but-set-variable -Wno-maybe-uninitialized -Wno-format>)

target_link_libraries(pqb_rp PRIVATE pico_stdlib pico_multicore pico_rand hardware_sha256
    hardware_dma hardware_clocks hardware_watchdog FreeRTOS-Kernel FreeRTOS-Kernel-Heap4)

pico_enable_stdio_usb(pqb_rp 1)
pico_enable_stdio_uart(pqb_rp 0)

if(PQB_PLACEMENT STREQUAL "ram")
    pico_set_binary_type(pqb_rp copy_to_ram)
elseif(PQB_PLACEMENT STREQUAL "hot")
    # ld_hot/ overrides two pieces of the SDK's default linker script: the objects it
    # names are left out of the flash .text and .rodata output sections, so the SDK's own
    # rule moves them into .data, which the boot code copies to SRAM (as ESP-IDF's linker
    # fragments place code in IRAM; harness/esp-idf/main/pqb_iram.lf lists the same
    # objects)
    pico_add_linker_script_override_path(pqb_rp ${CMAKE_CURRENT_LIST_DIR}/ld_hot
        FILES default_text_excludes.incl default_rodata_excludes.incl)
elseif(NOT PQB_PLACEMENT STREQUAL "flash")
    message(FATAL_ERROR "unknown PQB_PLACEMENT ${PQB_PLACEMENT}")
endif()

pico_set_program_name(pqb_rp "pqb_rp")
pico_add_extra_outputs(pqb_rp)
