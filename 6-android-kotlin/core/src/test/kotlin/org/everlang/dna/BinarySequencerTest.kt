package org.everlang.dna

import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Mirrors everlang_standalone/tests/test_binary_sequencer.py. */
class BinarySequencerTest {
    private val seq = BinarySequencer()

    private fun bytes(vararg v: Int) = ByteArray(v.size) { v[it].toByte() }

    // Encoding

    @Test
    fun knownByteVector() {
        // 0x1B = 00 01 10 11 -> A T C G (2 bits per base, MSB first)
        assertEquals("ATCG", seq.sequence(bytes(0x1B)).dna)
    }

    @Test
    fun allZeroAndAllOneBytes() {
        assertEquals("AAAA", seq.sequence(bytes(0x00)).dna)
        assertEquals("GGGG", seq.sequence(bytes(0xFF)).dna)
    }

    @Test
    fun oneByteIsFourBases() {
        val report = seq.sequence(ByteArray(10) { it.toByte() })
        assertEquals(40, report.dna.length)
        assertEquals(10, report.byteCount)
    }

    @Test
    fun emptyInputYieldsEmptyStrand() {
        val report = seq.sequence(ByteArray(0))
        assertEquals("", report.dna)
        assertTrue(report.codons.isEmpty())
        assertNull(report.gcContent)
        assertTrue(report.roundTrip)
    }

    @Test
    fun gcContentForAllOnesIsOne() {
        assertEquals(1.0, seq.sequence(bytes(0xFF)).gcContent)
    }

    @Test
    fun codonsGroupSixteenBasesFromFourBytes() {
        val report = seq.sequence(bytes(1, 2, 3, 4))
        assertEquals(5, report.codons.size)
        assertEquals(1, report.trailingPartial.size)
    }

    // Round trip and strict decode

    @Test
    fun roundTripEveryByteValue() {
        val data = ByteArray(256) { it.toByte() }
        val report = seq.sequence(data)
        assertTrue(report.roundTrip)
        assertContentEquals(data, seq.decode(report.dna))
    }

    @Test
    fun decodeRejectsNonAtcg() {
        assertFailsWith<IllegalArgumentException> { seq.decode("ATXG") }
    }

    @Test
    fun decodeEmptyOrWhitespaceStrandIsEmptyBytes() {
        assertContentEquals(ByteArray(0), seq.decode(""))
        assertContentEquals(ByteArray(0), seq.decode("  \n"))
    }

    @Test
    fun decodeAcceptsLowercaseAndWhitespace() {
        assertContentEquals(bytes(0x1B), seq.decode("at cg\n"))
    }

    @Test
    fun decodeRejectsPartialByte() {
        assertFailsWith<IllegalArgumentException> { seq.decode("ATC") }
    }

    @Test
    fun decodeAcceptsUnicodeWhitespaceThatPythonSplitsOn() {
        assertContentEquals(bytes(0x1B), seq.decode("AT\u00A0CG"))
        assertContentEquals(bytes(0x1B), seq.decode("AT\u2028CG\u001c"))
    }

    @Test
    fun decodeRejectsFoldedCharactersThatAreNotBases() {
        assertFailsWith<IllegalArgumentException> { seq.decode("\u00DF") }
        assertFailsWith<IllegalArgumentException> { seq.decode("\uFB05AAA") }
    }

    // Affinity

    @Test
    fun complementaryGateIsFullAffinity() {
        // Complement of ATCG (Watson-Crick, base by base) is TAGC
        assertEquals(256, seq.affinity("ATCG", "TAGC"))
    }

    @Test
    fun mismatchedGateLowersAffinity() {
        assertEquals(64, seq.affinity("ATCG", "AAAA"))
    }

    @Test
    fun affinityDelegatesToTheEngine() {
        assertEquals(BioPhaseEngine("AAAA").calculateHybridizationAffinity("TTAA"), seq.affinity("TTAA", "AAAA"))
    }
}
