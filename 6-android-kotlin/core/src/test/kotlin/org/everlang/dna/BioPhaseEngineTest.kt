package org.everlang.dna

import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Mirrors the BioPhaseEngine affinity cases of everlang_standalone/tests/test_biocomputing.py.
 * process_displacement, EParticle and VibeDnaCompiler are not ported and have no tests here.
 */
class BioPhaseEngineTest {
    private fun complement(seq: String): String = seq.map { c -> mapOf('A' to 'T', 'T' to 'A', 'C' to 'G', 'G' to 'C')[c]!! }.joinToString("")

    @Test
    fun affinityZeroOnEmptyGate() {
        assertEquals(0, BioPhaseEngine("").calculateHybridizationAffinity(""))
        assertEquals(0, BioPhaseEngine("   ").calculateHybridizationAffinity("ATCG"))
    }

    @Test
    fun affinityZeroOnLengthMismatch() {
        val engine = BioPhaseEngine("ATCGATCG")
        assertEquals(0, engine.calculateHybridizationAffinity("TAGCTAG"))
        assertEquals(0, engine.calculateHybridizationAffinity("TAGCTAGCT"))
    }

    @Test
    fun perfectComplementIs256() {
        val gate = "ATCGGCTAATCGGCTA"
        assertEquals(256, BioPhaseEngine(gate).calculateHybridizationAffinity(complement(gate)))
    }

    @Test
    fun identicalStrandIsZero() {
        assertEquals(0, BioPhaseEngine("ATCG").calculateHybridizationAffinity("ATCG"))
    }

    @Test
    fun partialAffinityValues() {
        val engine = BioPhaseEngine("A".repeat(16))
        assertEquals(192, engine.calculateHybridizationAffinity("T".repeat(12) + "A".repeat(4)))
        assertEquals(176, engine.calculateHybridizationAffinity("T".repeat(11) + "A".repeat(5)))
    }

    @Test
    fun eightBaseGatePartialValue() {
        assertEquals(192, BioPhaseEngine("A".repeat(8)).calculateHybridizationAffinity("T".repeat(6) + "AA"))
    }

    @Test
    fun gateAndInputAreUppercasedAndStrippedAtTheEnds() {
        val engine = BioPhaseEngine("  atcg \n")
        assertEquals("ATCG", engine.gateSequence)
        assertEquals(256, engine.calculateHybridizationAffinity(" tagc\t"))
    }

    @Test
    fun interiorWhitespaceIsNotStrippedAndNeverMatches() {
        // "TT TT" keeps its interior space, so it has 5 positions; the space never matches.
        assertEquals(204, BioPhaseEngine("AAAAA").calculateHybridizationAffinity("TT TT"))
    }

    @Test
    fun gateStripsOnlyTheEnds() {
        assertEquals("AAAA", BioPhaseEngine(" AAAA ").gateSequence)
        assertEquals(256, BioPhaseEngine(" AAAA ").calculateHybridizationAffinity(" TTTT"))
    }

    @Test
    fun lengthIsCountedInCodePointsNotUtf16Units() {
        // Input "T" + U+1F9EC is 2 code points (3 UTF-16 units), matching a 2-base gate.
        assertEquals(128, BioPhaseEngine("AA").calculateHybridizationAffinity("T\uD83E\uDDEC"))
    }
}
