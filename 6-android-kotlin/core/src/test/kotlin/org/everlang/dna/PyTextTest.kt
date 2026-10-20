package org.everlang.dna

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Direct checks of the CPython str helpers the port relies on, beyond the exhaustive table test. */
class PyTextTest {
    @Test
    fun isSpaceCoversTheKnownDivergencesFromJavaCharacter() {
        // Character.isWhitespace is false for these on JDK 21; CPython's str.isspace() is true.
        for (cp in intArrayOf(0x85, 0xA0, 0x2007, 0x202F)) assertTrue(PyText.isSpace(cp), "U+%04X".format(cp))
        // Character.isSpaceChar is false for the C0 separators; CPython treats them as whitespace.
        for (cp in intArrayOf(0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F)) {
            assertTrue(PyText.isSpace(cp), "U+%04X".format(cp))
        }
        for (cp in intArrayOf(0x180E, 0x200B, 0xFEFF, 0x00, 0x41)) assertFalse(PyText.isSpace(cp), "U+%04X".format(cp))
    }

    @Test
    fun uppercaseExpansionsFollowCPythonFullMapping() {
        assertEquals("SS", PyText.upper("\u00DF"))
        assertEquals("ST", PyText.upper("\uFB05"))
        assertEquals("A\u02BE", PyText.upper("\u1E9A"))
        assertEquals("I", PyText.upper("\u0131"))
        assertEquals("S", PyText.upper("\u017F"))
        assertEquals("\u0399", PyText.upper("\u0345"))
        assertEquals("\u01C4", PyText.upper("\u01C5"))
    }

    @Test
    fun supplementaryUpperFollowsCPython() {
        // CPython: chr(0x10428).upper() == chr(0x10400). U+1F9EC has no case mapping.
        assertEquals("\uD801\uDC00", PyText.upper("\uD801\uDC28"))
        assertEquals("\uD83E\uDDEC", PyText.upper("\uD83E\uDDEC"))
    }

    @Test
    fun validSurrogatePairIsOneCodePointUnlikeCPython() {
        // CPython: chr(0xD800) + chr(0xDC00) is two code points, and the same text as a Kotlin String is
        // U+10000. CPython gives 2 tokens, 4 tokens and affinity 85 for these inputs; the port gives 1, 3, 0.
        val pair = "\uD800\uDC00"
        assertEquals(listOf(0x10000), PyText.codePoints(pair).toList())
        assertEquals(1, DnaSequencer.run(pair).tokens.size)
        assertEquals(3, DnaSequencer.run("A" + pair + "T").tokens.size)
        assertEquals(0, BioPhaseEngine("TAG").calculateHybridizationAffinity("A" + pair))
    }

    @Test
    fun stripRemovesOnlyTheEndsAndKeepsInteriorWhitespace() {
        assertEquals("A B", PyText.strip("\u001CA B\u0085"))
        assertEquals("AAAA", PyText.strip(" AAAA "))
        assertEquals("", PyText.strip(" \t\u2028 "))
    }

    @Test
    fun removeSpaceDropsEveryWhitespaceKindAndNothingElse() {
        assertEquals("ATG", PyText.removeSpace("A\u00A0T\u2028G"))
        assertEquals("ATCG", PyText.removeSpace("A\u0085T\u3000C\u001FG"))
        assertEquals("X\u200BY", PyText.removeSpace("X\u200BY"))
    }

    @Test
    fun codePointsCountsASupplementaryCharacterAsOne() {
        assertEquals(3, PyText.codePoints("A\uD83E\uDDECT").size)
        assertEquals(0x1F9EC, PyText.codePoints("\uD83E\uDDEC")[0])
    }

    @Test
    fun loneSurrogatesAreTheirOwnCodePoints() {
        val cps = PyText.codePoints("\uD800A")
        assertEquals(listOf(0xD800, 0x41), cps.toList())
    }
}
