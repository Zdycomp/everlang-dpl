package org.everlang.dna

/**
 * CPython 3.13 str semantics for the operations the port uses: str.isspace(), str.upper(),
 * str.split() (whitespace removal) and str.strip(). Python indexes text by code point, so every
 * operation here walks code points, not UTF-16 code units.
 *
 * The lookups come from the generated [PyUnicodeTables] (core/tools/gen_bmp_tables.py), not from
 * java.lang.Character or String.toUpperCase. Platform Unicode data disagrees with CPython in two
 * ways, both checked against core/src/test/resources/bmp_python.tsv on JDK 21:
 *  - Character.isWhitespace is false for U+0085, U+00A0, U+2007 and U+202F, where str.isspace()
 *    is true. Character.isSpaceChar is also false for U+0009-U+000D, U+001C-U+001F and U+0085.
 *  - String.toUpperCase(Locale.ROOT) agreed with CPython on every BMP code point on JDK 21. It is
 *    still not used, because Android ICU data varies by device and the tables fix the behavior.
 *
 * Supplementary code points (U+10000 and up) are uppercased from a table generated the same way,
 * and [upper] matches CPython on every one of them. The port never classifies a supplementary code
 * point as a base or whitespace, and no mapping changes a length: the generator verified that no
 * supplementary code point is whitespace, none uppercases to A, T, C or G, and each uppercases to a
 * single code point.
 *
 * Known divergence: surrogates. A Java String cannot tell two lone surrogates from one valid pair.
 * Python's chr(0xD800) + chr(0xDC00) is two code points, but as a Kotlin String it is the same text
 * as U+10000. [codePoints] reads a valid pair as one code point, so the lengths and indices of the
 * port follow that reading. CPython gives 2 tokens for the pair, 4 tokens for "A" + pair + "T", and
 * affinity 85 for ("TAG", "A" + pair). The port gives 1, 3 and 0. The public contract takes a String,
 * so no input can carry the difference. Splitting a valid pair into code units would break U+10000
 * and every other supplementary character, which CPython reads as one code point.
 */
internal object PyText {
    private const val SUPPLEMENTARY = 0x10000

    /** str.isspace() for one code point. */
    fun isSpace(cp: Int): Boolean {
        if (cp < 0x80) return cp == 0x20 || cp in 0x09..0x0D || cp in 0x1C..0x1F
        if (cp >= SUPPLEMENTARY) return false
        return PyUnicodeTables.SPACE.binarySearch(cp) >= 0
    }

    /** Appends str.upper() of one code point (may be several chars, for example U+00DF -> "SS"). */
    fun appendUpper(cp: Int, out: StringBuilder) {
        when {
            cp < 0x80 -> out.append((if (cp in 0x61..0x7A) cp - 0x20 else cp).toChar())
            cp >= SUPPLEMENTARY -> {
                val index = PyUnicodeTables.SUPPLEMENTARY_UPPER_KEYS.binarySearch(cp)
                out.appendCodePoint(if (index >= 0) PyUnicodeTables.SUPPLEMENTARY_UPPER_VALUES[index] else cp)
            }
            else -> {
                val index = PyUnicodeTables.UPPER_KEYS.binarySearch(cp)
                if (index >= 0) out.append(PyUnicodeTables.UPPER_VALUES[index]) else out.append(cp.toChar())
            }
        }
    }

    /** str.upper(). */
    fun upper(text: String): String {
        val out = StringBuilder(text.length)
        var i = 0
        while (i < text.length) {
            val cp = text.codePointAt(i)
            appendUpper(cp, out)
            i += width(cp)
        }
        return out.toString()
    }

    /** "".join(text.split()): every str.isspace() code point is removed. */
    fun removeSpace(text: String): String {
        val out = StringBuilder(text.length)
        var i = 0
        while (i < text.length) {
            val cp = text.codePointAt(i)
            if (!isSpace(cp)) out.appendCodePoint(cp)
            i += width(cp)
        }
        return out.toString()
    }

    /** str.strip(): leading and trailing str.isspace() code points are removed, interior ones are kept. */
    fun strip(text: String): String {
        val cps = codePoints(text)
        var start = 0
        var end = cps.size
        while (start < end && isSpace(cps[start])) start++
        while (end > start && isSpace(cps[end - 1])) end--
        val out = StringBuilder(text.length)
        for (k in start until end) out.appendCodePoint(cps[k])
        return out.toString()
    }

    /** The code points of [text], in order. A lone surrogate is its own code point. */
    fun codePoints(text: String): IntArray {
        var count = 0
        var i = 0
        while (i < text.length) {
            i += width(text.codePointAt(i))
            count++
        }
        val out = IntArray(count)
        i = 0
        var k = 0
        while (i < text.length) {
            val cp = text.codePointAt(i)
            out[k++] = cp
            i += width(cp)
        }
        return out
    }

    private fun width(cp: Int): Int = if (cp >= SUPPLEMENTARY) 2 else 1
}
