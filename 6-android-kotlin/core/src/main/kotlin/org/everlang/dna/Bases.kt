package org.everlang.dna

/**
 * The four bases and their two mappings: the 2-bit code used by [Quaternary] (A=00, T=01, C=10,
 * G=11) and the Watson-Crick partner used by the parser and the affinity engine (A-T, C-G).
 */
internal object Bases {
    const val NONE = -1

    /** 2-bit code of an upper-case base code point, or [NONE]. */
    fun code(cp: Int): Int = when (cp) {
        'A'.code -> 0
        'T'.code -> 1
        'C'.code -> 2
        'G'.code -> 3
        else -> NONE
    }

    /** Watson-Crick partner of an upper-case base code point, or [NONE]. */
    fun complement(cp: Int): Int = when (cp) {
        'A'.code -> 'T'.code
        'T'.code -> 'A'.code
        'C'.code -> 'G'.code
        'G'.code -> 'C'.code
        else -> NONE
    }
}
