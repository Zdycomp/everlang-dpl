package org.everlang.dna.fuzz

import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Checks the oracle's own inputs and rules against values written out by hand. The fuzz results are only as strong
 * as these, because a wrong oracle would pass a wrong codec.
 */
class OracleSelfCheckTest {
    @Test
    fun pyTextBridgeHasCPythonWhitespaceAndCaseSemantics() {
        // Character.isWhitespace is false for these, but str.isspace() is true, so they must be removed.
        assertEquals("", PyTextBridge.removeSpace("\u0085    "))
        // Not whitespace in CPython, so they must survive removal.
        assertEquals("​﻿", PyTextBridge.removeSpace("​﻿"))
        assertTrue(PyTextBridge.isSpace(0x1C))
        assertFalse(PyTextBridge.isSpace(0x180E))
        // Full case mapping: sharp s expands.
        assertEquals("SS", PyTextBridge.upper("ß"))
    }

    @Test
    fun hostileCharsAreExactlyThePythonHarnessList() {
        val expected = listOf(
            "X", "N", "-", "*", "#", ".", "0", " ", "\t", "\n", "\r", "\u0000", "\u007F",
            "é", "ß", "İ", " ", "﻿", "🧬",
            "a", "g", "t",
        )
        assertEquals(expected, CaseGen.HOSTILE_CHARS)
        assertEquals(22, CaseGen.HOSTILE_CHARS.size)
    }

    @Test
    fun oracleAcceptsAndRejectsLikeThePythonDecodeOracle() {
        fun accepted(strand: String): Boolean = PyOracle.cleanedBases(strand) != null

        assertTrue(accepted(""))
        assertTrue(accepted(" \t\n\r"))
        assertTrue(accepted("atcg"))
        assertTrue(accepted("AT CG"))
        assertTrue(accepted("A TCG"))
        assertTrue(accepted("A TCG"), "NBSP is str.isspace() in CPython")

        assertFalse(accepted("ATC"), "length not a multiple of 4")
        assertFalse(accepted("ATCGN"))
        assertFalse(accepted("A​TCG"), "zero-width space is not whitespace")
        assertFalse(accepted("A\u0000TCG"))
        assertFalse(accepted("ßATC"), "sharp s uppercases to SS, which is not ATCG")
        assertFalse(accepted("ATCG🧬"))
        assertNull(PyOracle.cleanedBases("ATCGX"))
    }

    @Test
    fun expectedBytesFollowTheBitMapping() {
        assertContentEquals(byteArrayOf(0x1B), PyOracle.expectedBytes("ATCG"))
        assertContentEquals(byteArrayOf(0x55), PyOracle.expectedBytes("TTTT"))
        assertContentEquals(byteArrayOf(0xFF.toByte()), PyOracle.expectedBytes("GGGG"))
        assertContentEquals(byteArrayOf(0, 0), PyOracle.expectedBytes("AAAAAAAA"))
        assertEquals("ATCG", PyOracle.expectedDna(byteArrayOf(0x1B)))
        assertEquals("GGGG", PyOracle.expectedDna(byteArrayOf(0xFF.toByte())))
    }

    @Test
    fun coreCodecAgreesWithTheHandWrittenMapping() {
        val codec = CoreStrandCodec()
        assertEquals("ATCG", codec.sequence(byteArrayOf(0x1B)).dna)
        assertContentEquals(byteArrayOf(0x1B), codec.decode("atcg"))
        assertContentEquals(byteArrayOf(0x1B), codec.decode("AT CG"))
        assertContentEquals(ByteArray(0), codec.decode(""))
        assertContentEquals(ByteArray(0), codec.decode("   "))
    }

    @Test
    fun caseSeedingIsDeterministicAndDistinctPerIndex() {
        val first = CaseRandom.forCase(1L, 5L).nextLong()
        assertEquals(first, CaseRandom.forCase(1L, 5L).nextLong())
        assertNotEquals(first, CaseRandom.forCase(1L, 6L).nextLong())
        assertNotEquals(first, CaseRandom.forCase(2L, 5L).nextLong())
    }
}
