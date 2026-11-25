PQB_PLACEMENT=hot: replacements for two files of the Pico SDK 2.3.1 linker script
(src/rp2_common/pico_standard_link/script_include/), added with
pico_add_linker_script_override_path(). The SDK's versions exclude only libgcc and libm
from the flash .text and .rodata sections; these also exclude the hash-based scheme
objects, the SHA-256 code, and newlib's memcpy, memset, and memmove, which the SDK's
section_default_data.incl then places in .data (copied to SRAM at boot). The object list
matches harness/esp-idf/main/pqb_iram.lf. Comment syntax is not used inside the .incl files
because the SDK INCLUDEs them in the middle of an output-section description.
