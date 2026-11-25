/*
 * Embeds the verification vector blob (see vectors.c) with the assembler's .incbin, from
 * a C file so that every platform's C flags apply unchanged. PQB_VECTORS_FILE is the
 * blob's path as a string literal, passed by the build (harness/linux/Makefile,
 * harness/esp-idf CMakeLists.txt). Built only when the blob exists.
 */
__asm__(".section .rodata.pqb_vectors,\"a\"\n"
        ".balign 4\n"
        ".global pqb_vectors_start\n"
        ".global pqb_vectors_end\n"
        "pqb_vectors_start:\n"
        ".incbin \"" PQB_VECTORS_FILE "\"\n"
        "pqb_vectors_end:\n"
        ".byte 0\n"
        ".previous\n");
