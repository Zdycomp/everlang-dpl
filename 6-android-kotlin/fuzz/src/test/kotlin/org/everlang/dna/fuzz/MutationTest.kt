package org.everlang.dna.fuzz

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The oracle must catch each sabotaged codec. Every mutation runs the same fixed case set (seed 1, 5000 cases),
 * independent of FUZZ_CASES, so the detection result does not depend on how long the clean run is.
 *
 * Each mutation asserts failures > 0 and also asserts the failure kind that the sabotage should produce. The
 * control run asserts zero failures for the real codec at the same case count.
 */
class MutationTest {
    private val seed = 1L
    private val cases = 5_000L

    private fun run(label: String, codec: StrandCodec): Tally {
        val tally = Tally(maxDetails = 5)
        CodecOracle(codec, seed, tally).run(0L, cases)
        println("MUTATION $label: cases=$cases failures=${tally.failures} failures_by_kind=${tally.failuresByKind}")
        for (failure in tally.details.take(3)) println("  e.g. $failure")
        return tally
    }

    @Test
    fun controlRunWithRealCodecHasZeroFailures() {
        val tally = run("control (real codec)", CoreStrandCodec())
        assertEquals(0L, tally.failures, "real codec must pass the oracle at this case count")
    }

    @Test
    fun mutationA_laxDecodeSkippingValidationIsDetected() {
        val tally = run("(a) lax decode", LaxDecodeMutant(CoreStrandCodec()))
        assertTrue(tally.failures > 0, "(a) lax decode was not detected")
        assertTrue("decode-accepted-invalid" in tally.failuresByKind, "(a) expected decode-accepted-invalid")
    }

    @Test
    fun mutationB_affinityAlways256IsDetected() {
        val tally = run("(b) affinity always 256", AffinityAlways256Mutant(CoreStrandCodec()))
        assertTrue(tally.failures > 0, "(b) affinity always 256 was not detected")
        assertTrue("affinity-length" in tally.failuresByKind, "(b) expected affinity-length")
    }

    @Test
    fun mutationC_rejectLowercaseIsDetected() {
        val tally = run("(c) rejects lowercase", RejectLowercaseMutant(CoreStrandCodec()))
        assertTrue(tally.failures > 0, "(c) lowercase rejection was not detected")
        assertTrue("decode-rejected-valid" in tally.failuresByKind, "(c) expected decode-rejected-valid")
    }

    @Test
    fun mutationD_decodeOfEmptyStrandThrowsIsDetected() {
        val tally = run("(d) decode(\"\") throws", EmptyDecodeThrowsMutant(CoreStrandCodec()))
        assertTrue(tally.failures > 0, "(d) decode of the empty strand was not detected")
        assertTrue("decode-rejected-valid" in tally.failuresByKind, "(d) expected decode-rejected-valid")
    }

    @Test
    fun mutationD2_droppedEmptyGuardLeaksDnaSyntaxErrorAndIsDetected() {
        val tally = run("(d2, extra) no empty guard", NoEmptyGuardMutant())
        assertTrue(tally.failures > 0, "(d2) dropped empty guard was not detected")
        assertTrue("decode-crash" in tally.failuresByKind, "(d2) expected decode-crash")
    }
}
