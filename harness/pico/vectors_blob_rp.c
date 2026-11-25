/*
 * Embeds the verification vector blob (harness/common/vectors.c reads it) with the
 * assembler's .incbin, as harness/common/vectors_blob.c does, but in a .flashdata
 * section: the SDK's linker scripts keep .flashdata in flash for every binary type, so a
 * copy_to_ram build does not copy the 320 to 345 KB blob into SRAM. The operations copy
 * what they use into RAM before their timed sections (pqb_vec_copy()).
 */
__asm__(".section .flashdata.pqb_vectors,\"a\"\n"
        ".balign 4\n"
        ".global pqb_vectors_start\n"
        ".global pqb_vectors_end\n"
        "pqb_vectors_start:\n"
        ".incbin \"" PQB_VECTORS_FILE "\"\n"
        "pqb_vectors_end:\n"
        ".byte 0\n"
        ".previous\n");
