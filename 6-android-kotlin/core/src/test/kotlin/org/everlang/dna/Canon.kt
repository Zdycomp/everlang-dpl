package org.everlang.dna

/**
 * Test-only encodings. They match core/tools/gen_golden.py byte for byte: UTF-16BE hex for String
 * arguments, lowercase hex for bytes, and the canonical text forms documented in that script.
 */
internal object Canon {
    private const val HEX = "0123456789abcdef"

    /** Rebuilds the exact UTF-16 code units of a String argument, without re-decoding surrogates. */
    fun decodeUtf16Hex(hex: String): String {
        require(hex.length % 4 == 0) { "UTF-16BE hex length must be a multiple of 4: $hex" }
        return String(CharArray(hex.length / 4) { i -> hex.substring(4 * i, 4 * i + 4).toInt(16).toChar() })
    }

    fun hexToBytes(hex: String): ByteArray {
        require(hex.length % 2 == 0) { "hex length must be even: $hex" }
        return ByteArray(hex.length / 2) { i -> hex.substring(2 * i, 2 * i + 2).toInt(16).toByte() }
    }

    fun bytesToHex(bytes: ByteArray): String = buildString(bytes.size * 2) {
        for (b in bytes) {
            val v = b.toInt() and 0xFF
            append(HEX[v shr 4])
            append(HEX[v and 15])
        }
    }

    fun asciiHex(text: String): String = bytesToHex(text.toByteArray(Charsets.US_ASCII))

    /** The Python float bit pattern: big-endian IEEE-754, 16 lowercase hex digits. */
    fun gcField(gc: Double?): String =
        if (gc == null) "-" else java.lang.Long.toHexString(gc.toRawBits()).padStart(16, '0')

    private fun cpHex(c: Char): String = Integer.toHexString(c.code)

    fun tokenField(t: BaseToken): String = "t${cpHex(t.base)}:${t.index}:${if (t.valid) 1 else 0}"

    fun pairField(p: BasePair): String {
        val comp = p.complement?.let { cpHex(it) } ?: "-"
        return "p${p.index}:${cpHex(p.base)}:$comp:${if (p.valid) 1 else 0}"
    }

    fun codonField(c: Codon): String = "c${c.startIndex}:" + c.pairs.joinToString("|") { pairField(it) }

    fun sequence(res: SequenceResult): String =
        "T[${res.tokens.joinToString(",") { tokenField(it) }}];" +
            "P[${res.pairs.joinToString(",") { pairField(it) }}];" +
            "C[${res.codons.joinToString(",") { codonField(it) }}];" +
            "R[${res.trailingPartial.joinToString(",") { pairField(it) }}];" +
            "LE[${res.lexerErrors.joinToString(",") { tokenField(it) }}];" +
            "PE[${res.parserErrors.joinToString(",") { tokenField(it) }}];" +
            "GC=${gcField(res.gcContent)};V=${if (res.valid) 1 else 0}"

    fun strand(res: StrandReport): String =
        "DNA=${res.dna};N=${res.byteCount};" +
            "C[${res.codons.joinToString(",") { codonField(it) }}];" +
            "R[${res.trailingPartial.joinToString(",") { pairField(it) }}];" +
            "GC=${gcField(res.gcContent)};RT=${if (res.roundTrip) 1 else 0}"

    /** Reads a classpath resource as US-ASCII lines, keeping every line. */
    fun resourceLines(name: String): List<String> {
        val stream = checkNotNull(Canon::class.java.getResourceAsStream(name)) { "missing test resource $name" }
        return stream.bufferedReader(Charsets.US_ASCII).use { it.readLines() }
    }
}
