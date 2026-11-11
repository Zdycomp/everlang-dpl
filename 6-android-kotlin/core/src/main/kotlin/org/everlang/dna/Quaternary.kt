package org.everlang.dna

/**
 * Bytes <-> DNA with the 2-bit mapping A=00, T=01, C=10, G=11, most significant bits first, so
 * every byte is four bases. Mirrors everlang_standalone/everlang/biocomputing/quaternary.py.
 */
object Quaternary {
    private val BASE_FOR_CODE = charArrayOf('A', 'T', 'C', 'G')

    /** Encodes each byte as four bases, most significant pair first. */
    fun bytesToDna(data: ByteArray): String {
        val out = StringBuilder(data.size * 4)
        for (b in data) {
            val v = b.toInt() and 0xFF
            out.append(BASE_FOR_CODE[(v shr 6) and 3])
            out.append(BASE_FOR_CODE[(v shr 4) and 3])
            out.append(BASE_FOR_CODE[(v shr 2) and 3])
            out.append(BASE_FOR_CODE[v and 3])
        }
        return out.toString()
    }

    /**
     * Lax decode, mirroring QuaternaryTranslationLayer.DNA_to_bytes. The text is uppercased with the
     * full case mapping. Every code point that is not A, T, C or G is dropped, and a trailing
     * partial byte is dropped.
     *
     * The Python step `.replace(" ", "")` is not repeated: it removes only ASCII spaces, which the
     * alphabet filter drops anyway, so the output is the same.
     */
    fun dnaToBytes(dna: String): ByteArray {
        val upper = PyText.upper(dna)
        val codes = IntArray(upper.length)
        var n = 0
        for (cp in PyText.codePoints(upper)) {
            val code = Bases.code(cp)
            if (code != Bases.NONE) codes[n++] = code
        }
        return ByteArray(n / 4) { k ->
            ((codes[4 * k] shl 6) or (codes[4 * k + 1] shl 4) or (codes[4 * k + 2] shl 2) or codes[4 * k + 3]).toByte()
        }
    }
}
