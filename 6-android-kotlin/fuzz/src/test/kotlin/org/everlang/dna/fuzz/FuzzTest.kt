package org.everlang.dna.fuzz

import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * The clean run. The real codec must produce zero failures across FUZZ_CASES seeded cases.
 *
 * Environment, with defaults in parentheses:
 *  - FUZZ_CASES (20000): number of cases, indices 0 until FUZZ_CASES.
 *  - FUZZ_SEED (1): seed. Each failure prints as "seed=S case=I [kind] detail", and "FUZZ_SEED=S" with case I
 *    reproduces it.
 *  - FUZZ_MAX_REPORT (20): how many failure lines to print. The per-kind counts are always exact.
 *
 * Not ported from fuzz_harness.py: the heal checks (check_heal, EArchive.heal, repair_candidates, propose_rules).
 * They test ezr's Python repair engines (forgive.py and the edapt fixers). Those engines do not exist in Kotlin,
 * so there is nothing to port. This module makes no heal claim.
 */
class FuzzTest {
    @Test
    fun cleanCodecHasZeroFailuresOverSeededCases() {
        val cases = envLong("FUZZ_CASES", 20_000L)
        val seed = envLong("FUZZ_SEED", 1L)
        val maxReport = envLong("FUZZ_MAX_REPORT", 20L).toInt()
        require(cases >= 1L) { "FUZZ_CASES must be at least 1, got $cases" }

        val tally = Tally(maxReport)
        val started = System.nanoTime()
        CodecOracle(CoreStrandCodec(), seed, tally).run(0L, cases)
        val elapsedMs = (System.nanoTime() - started) / 1_000_000L

        println(summaryLine(seed, cases, elapsedMs, tally))
        for (failure in tally.details) println("FAIL $failure")

        assertTrue(
            tally.failures == 0L,
            "${tally.failures} failure(s) in $cases cases (seed=$seed): " +
                tally.details.take(5).joinToString("; ") { it.toString() },
        )
    }
}

/** Reads a numeric environment variable. Unset or blank means the default. A set but invalid value fails loudly. */
internal fun envLong(name: String, default: Long): Long {
    val raw = System.getenv(name)
    if (raw.isNullOrBlank()) return default
    return raw.trim().toLongOrNull() ?: throw IllegalArgumentException("$name must be an integer, got '$raw'")
}

/** One summary line, with every count the run actually performed. */
internal fun summaryLine(seed: Long, requested: Long, elapsedMs: Long, tally: Tally): String = buildString {
    append("FUZZ_SUMMARY seed=$seed cases_requested=$requested cases_run=${tally.cases} elapsed_ms=$elapsedMs")
    append(" sequence_checks=${tally.sequenceChecks}")
    append(" injections=${tally.injections}")
    append(" decode_calls=${tally.decodeCalls}")
    append(" decode_expected_valid=${tally.decodeExpectedValid}")
    append(" decode_expected_invalid=${tally.decodeExpectedInvalid}")
    append(" empty_decode_probes=${tally.emptyDecodeProbes}")
    append(" affinity_checks=${tally.affinityChecks}")
    append(" failures=${tally.failures}")
    append(" failures_by_kind=${tally.failuresByKind}")
}
