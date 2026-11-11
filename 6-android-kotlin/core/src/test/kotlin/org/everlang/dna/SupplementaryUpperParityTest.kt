package org.everlang.dna

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Checks PyText.upper on the supplementary code points against
 * core/src/test/resources/supplementary_upper_python.tsv. The table lists every supplementary code point whose
 * str.upper() is not the identity, as generated from CPython by core/tools/gen_bmp_tables.py. The generator checks
 * each code point of U+10000..U+10FFFF against CPython. This test checks every listed mapping through the port,
 * and that the port leaves every unlisted code point unchanged.
 */
class SupplementaryUpperParityTest {
    private fun rows(): List<Pair<Int, Int>> {
        val lines = Canon.resourceLines("/supplementary_upper_python.tsv")
        assertEquals("codepoint\tupper_codepoint", lines.first(), "unexpected table header")
        return lines.drop(1).map { line ->
            val f = line.split('\t')
            assertEquals(2, f.size, "bad row: $line")
            f[0].toInt(16) to f[1].toInt(16)
        }
    }

    private fun text(cp: Int): String = String(Character.toChars(cp))

    @Test
    fun everyListedMappingMatchesCPython() {
        val rows = rows()
        assertEquals(260, rows.size, "CPython 3.13 changes 260 supplementary code points under upper()")
        val mismatches = rows.filter { (cp, up) -> PyText.upper(text(cp)) != text(up) }
        assertTrue(
            mismatches.isEmpty(),
            "${mismatches.size} supplementary upper mismatches:\n" +
                mismatches.take(50).joinToString("\n") { (cp, up) ->
                    "U+%05X expected U+%05X, port gives U+%05X".format(cp, up, PyText.codePoints(PyText.upper(text(cp)))[0])
                },
        )
    }

    @Test
    fun unlistedSupplementaryCodePointsAreUnchanged() {
        val listed = rows().map { it.first }.toHashSet()
        val changed = ArrayList<Int>()
        for (cp in 0x10000..0x10FFFF) {
            if (cp in listed) continue
            if (PyText.upper(text(cp)) != text(cp)) changed += cp
        }
        assertTrue(
            changed.isEmpty(),
            "port changes ${changed.size} unlisted supplementary code points, first: " +
                changed.take(20).joinToString(" ") { "U+%05X".format(it) },
        )
    }
}
