package org.everlang.dna

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Exhaustive BMP check against core/src/test/resources/bmp_python.tsv. The table is generated from
 * CPython by core/tools/gen_bmp_tables.py: one row per code point U+0000..U+FFFF, with
 * str.isspace() and str.upper(). Every row is checked. Any mismatch fails the test and the
 * failure lists the code points that differ.
 */
class BmpParityTest {
    private class Row(val cp: Int, val isSpace: Boolean, val upper: String)

    private fun rows(): List<Row> {
        val lines = Canon.resourceLines("/bmp_python.tsv")
        assertEquals("codepoint\tisspace\tupper_utf16be_hex", lines.first(), "unexpected table header")
        val rows = lines.drop(1).map { line ->
            val f = line.split('\t')
            assertEquals(3, f.size, "bad row: $line")
            val space = when (f[1]) {
                "1" -> true
                "0" -> false
                else -> error("isspace column must be 0 or 1: $line")
            }
            Row(f[0].toInt(16), space, Canon.decodeUtf16Hex(f[2]))
        }
        assertEquals(0x10000, rows.size, "table must hold every BMP code point")
        rows.forEachIndexed { i, r -> assertEquals(i, r.cp, "rows must be U+0000..U+FFFF in order") }
        return rows
    }

    private fun hexOf(s: String): String = s.map { "%04X".format(it.code) }.joinToString(" ")

    @Test
    fun whitespacePredicateMatchesCPythonOnEveryBmpCodePoint() {
        val mismatches = ArrayList<String>()
        for (r in rows()) {
            val ch = r.cp.toChar().toString()
            val predicate = PyText.isSpace(r.cp)
            val viaStrip = PyText.strip(ch).isEmpty()
            val viaSplit = PyText.removeSpace("x$ch").length == 1
            if (predicate != r.isSpace || viaStrip != r.isSpace || viaSplit != r.isSpace) {
                mismatches += "U+%04X python=%s isSpace=%s strip=%s removeSpace=%s".format(
                    r.cp, r.isSpace, predicate, viaStrip, viaSplit,
                )
            }
        }
        assertTrue(
            mismatches.isEmpty(),
            "${mismatches.size} whitespace mismatches against bmp_python.tsv:\n" + mismatches.take(50).joinToString("\n"),
        )
    }

    @Test
    fun uppercaseMatchesCPythonOnEveryBmpCodePoint() {
        val mismatches = ArrayList<String>()
        for (r in rows()) {
            val ch = r.cp.toChar().toString()
            val alone = PyText.upper(ch)
            val inContext = PyText.upper("a" + ch + "z")
            if (alone != r.upper || inContext != "A" + r.upper + "Z") {
                mismatches += "U+%04X python=[%s] kotlin=[%s] inContext=[%s]".format(
                    r.cp, hexOf(r.upper), hexOf(alone), hexOf(inContext),
                )
            }
        }
        assertTrue(
            mismatches.isEmpty(),
            "${mismatches.size} uppercase mismatches against bmp_python.tsv:\n" + mismatches.take(50).joinToString("\n"),
        )
    }

    @Test
    fun tableSpotChecksAgreeWithKnownCPythonBehavior() {
        val table = rows()
        assertEquals("SS", table[0xDF].upper)
        assertEquals("ST", table[0xFB05].upper)
        assertEquals(29, table.count { it.isSpace })
        assertTrue(table[0x85].isSpace && table[0xA0].isSpace && table[0x2007].isSpace && table[0x202F].isSpace)
        assertTrue(!table[0x180E].isSpace && !table[0x200B].isSpace && !table[0xFEFF].isSpace)
    }
}
