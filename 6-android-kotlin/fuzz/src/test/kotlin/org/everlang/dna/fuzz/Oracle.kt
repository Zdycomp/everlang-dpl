package org.everlang.dna.fuzz

import org.everlang.dna.StrandReport
import java.util.SplittableRandom
import kotlin.math.abs

/**
 * One failed check. (seed, index) reproduces it: CaseRandom.forCase(seed, index) rebuilds the same case.
 */
data class Failure(val seed: Long, val index: Long, val kind: String, val detail: String) {
    override fun toString(): String = "seed=$seed case=$index [$kind] $detail"
}

/**
 * Counts of the checks that actually ran, plus the failures. Only the first [maxDetails] failures keep their
 * text. A mutant that fails every case therefore stays bounded in memory, and the per-kind counts stay exact.
 */
class Tally(private val maxDetails: Int) {
    var cases = 0L
    var sequenceChecks = 0L
    val injections: MutableMap<String, Long> = linkedMapOf(
        "insert" to 0L, "substitute" to 0L, "delete" to 0L, "lower" to 0L, "insert4" to 0L,
    )
    var decodeCalls = 0L
    var decodeExpectedValid = 0L
    var decodeExpectedInvalid = 0L
    var emptyDecodeProbes = 0L
    var affinityChecks = 0L
    var failures = 0L
    val failuresByKind: MutableMap<String, Long> = sortedMapOf()
    val details: MutableList<Failure> = ArrayList()

    internal fun record(failure: Failure) {
        failures++
        failuresByKind.merge(failure.kind, 1L) { a, b -> a + b }
        if (details.size < maxDetails) details += failure
    }
}

/**
 * The expected behaviour, computed from the spec and not from core's codec. The only thing shared with core is
 * the whitespace and case predicate, through [PyTextBridge].
 */
internal object PyOracle {
    /** The 2-bit code order: A=00, T=01, C=10, G=11, most significant pair first (quaternary.py). */
    const val BASE_ORDER = "ATCG"

    private val COMPLEMENT: Map<Char, Char> = mapOf('A' to 'T', 'T' to 'A', 'C' to 'G', 'G' to 'C')

    /**
     * Mirrors _oracle_decode: cleaned = "".join(strand.upper().split()). Returns the cleaned bases when decode must
     * accept, and null when it must reject. A strand is valid when the cleaned text is ATCG only and its length is
     * a multiple of 4. The empty string and whitespace-only strands clean to "", which is valid and decodes to b"".
     */
    fun cleanedBases(strand: String): String? {
        val cleaned = PyTextBridge.removeSpace(PyTextBridge.upper(strand))
        if (cleaned.any { it !in BASE_ORDER }) return null
        if (cleaned.length % 4 != 0) return null
        return cleaned
    }

    /** Exact bytes for a valid cleaned strand, computed from the bit mapping. */
    fun expectedBytes(cleaned: String): ByteArray = ByteArray(cleaned.length / 4) { k ->
        var v = 0
        for (j in 0 until 4) v = (v shl 2) or BASE_ORDER.indexOf(cleaned[4 * k + j])
        v.toByte()
    }

    /** Exact strand for bytes, four bases per byte, most significant pair first. */
    fun expectedDna(data: ByteArray): String {
        val out = StringBuilder(data.size * 4)
        for (b in data) {
            val v = b.toInt() and 0xFF
            for (shift in intArrayOf(6, 4, 2, 0)) out.append(BASE_ORDER[(v shr shift) and 3])
        }
        return out.toString()
    }

    /** Watson-Crick partner, A-T and C-G. */
    fun complement(base: Char): Char = COMPLEMENT.getValue(base)
}

/** What a decode call produced: bytes, a rejection (IllegalArgumentException, like Python's ValueError), or a crash. */
internal sealed interface DecodeOutcome {
    class Value(val bytes: ByteArray) : DecodeOutcome
    object Rejected : DecodeOutcome
    class Crashed(val description: String) : DecodeOutcome
}

/**
 * Runs seeded cases against one codec. Check names, check order and the exact oracles follow
 * everlang_standalone/tests/fuzz_harness.py::check_codec.
 *
 * Additions beyond the Python harness:
 *  - codec-mapping: sequence() must give the exact A=00 T=01 C=10 G=11 strand. The Python harness checks length,
 *    alphabet, the round-trip flag and codon grouping, but never the mapping itself.
 *  - decode-rejected-valid and decode-value on the empty-strand probes: every case decodes "" and one
 *    whitespace-only strand, and both must return an empty array. The Python harness never decodes an empty strand,
 *    because each strand it builds has at least three bases, so it never reaches the empty-input guard.
 *  - decode-crash, codec-crash, affinity-crash: a throwable other than IllegalArgumentException is recorded as a
 *    failure and the run continues. Python would stop the process at the first such exception.
 *
 * Not ported: the heal checks (check_heal). See FuzzTest for the reason.
 */
internal class CodecOracle(private val codec: StrandCodec, private val seed: Long, val tally: Tally) {

    /** Runs the cases with index in [from, from + count). */
    fun run(from: Long, count: Long) {
        for (index in from until from + count) runCase(index)
    }

    private fun runCase(index: Long) {
        val rng = CaseRandom.forCase(seed, index)
        tally.cases++
        val data = CaseGen.randomBytes(rng)
        val dna = checkSequence(index, data)
        if (dna != null && dna.isNotEmpty()) {
            checkInjectedDecode(index, rng, dna)
            checkAffinity(index, rng, dna)
        }
        probeEmptyDecode(index, rng)
    }

    /** Mirrors the codec checks at the top of check_codec, plus the exact-mapping addition. */
    private fun checkSequence(index: Long, data: ByteArray): String? {
        val report: StrandReport = try {
            codec.sequence(data)
        } catch (e: Throwable) {
            fail(index, "codec-crash", "sequence(${data.size} bytes): ${describe(e)}")
            return null
        }
        tally.sequenceChecks++
        val dna = report.dna
        if (dna.length != 4 * data.size) fail(index, "codec-length", "${dna.length} bases for ${data.size} bytes")
        if (!dna.all { it in PyOracle.BASE_ORDER }) fail(index, "codec-alphabet", reprText(dna))

        val expected = PyOracle.expectedDna(data)
        if (dna != expected) {
            fail(
                index,
                "codec-mapping",
                "first 32 bases: got ${reprText(dna.take(32))}, expected ${reprText(expected.take(32))}",
            )
        }
        if (!report.roundTrip) fail(index, "codec-roundtrip", hexBytes(data))
        if (report.codons.size != dna.length / 3 || report.trailingPartial.size != dna.length % 3) {
            fail(index, "codon-grouping", "${dna.length} bases")
        }

        val gc = report.gcContent
        if ((gc == null) != dna.isEmpty() || (gc != null && !(gc >= 0.0 && gc <= 1.0))) {
            fail(index, "gc-range", gc.toString())
        }
        if (gc != null && dna.isNotEmpty()) {
            val expectGc = dna.count { it == 'G' || it == 'C' }.toDouble() / dna.length
            if (abs(gc - expectGc) > 1e-12) fail(index, "gc-value", "$gc != $expectGc")
        }
        return dna
    }

    /** Mirrors the error-injection block: one of five operations, then the decode oracle. */
    private fun checkInjectedDecode(index: Long, rng: SplittableRandom, dna: String) {
        val op = CaseGen.INJECTION_OPS[rng.nextInt(CaseGen.INJECTION_OPS.size)]
        val pos = rng.nextInt(dna.length)
        val strand = when (op) {
            "insert" -> dna.substring(0, pos) + CaseGen.pick(rng, CaseGen.INJECTION_POOL) + dna.substring(pos)
            "insert4" -> dna.substring(0, pos) + CaseGen.randomBases(rng, 4) + dna.substring(pos)
            "substitute" -> dna.substring(0, pos) + CaseGen.pick(rng, CaseGen.INJECTION_POOL) + dna.substring(pos + 1)
            "delete" -> dna.substring(0, pos) + dna.substring(pos + 1)
            else -> dna.substring(0, pos) + dna[pos].lowercaseChar() + dna.substring(pos + 1)
        }
        tally.injections.merge(op, 1L) { a, b -> a + b }
        checkDecode(index, strand, PyOracle.cleanedBases(strand))
    }

    /** Decode oracle. [cleaned] is the expected cleaned strand, or null when decode must reject. */
    private fun checkDecode(index: Long, strand: String, cleaned: String?) {
        tally.decodeCalls++
        if (cleaned == null) tally.decodeExpectedInvalid++ else tally.decodeExpectedValid++
        when (val outcome = decodeOutcome(strand)) {
            is DecodeOutcome.Crashed ->
                fail(index, "decode-crash", "decode(${reprText(strand)}): ${outcome.description}")
            DecodeOutcome.Rejected ->
                if (cleaned != null) fail(index, "decode-rejected-valid", reprText(strand))
            is DecodeOutcome.Value ->
                if (cleaned == null) {
                    fail(index, "decode-accepted-invalid", reprText(strand))
                } else {
                    val expected = PyOracle.expectedBytes(cleaned)
                    if (!outcome.bytes.contentEquals(expected)) {
                        fail(
                            index,
                            "decode-value",
                            "${reprText(strand)} got ${hexBytes(outcome.bytes)} expected ${hexBytes(expected)}",
                        )
                    }
                }
        }
    }

    private fun decodeOutcome(strand: String): DecodeOutcome = try {
        DecodeOutcome.Value(codec.decode(strand))
    } catch (e: IllegalArgumentException) {
        DecodeOutcome.Rejected
    } catch (e: Throwable) {
        DecodeOutcome.Crashed(describe(e))
    }

    /** Mirrors the affinity block: complement gate is 256, length mismatch is 0, random gate matches the formula. */
    private fun checkAffinity(index: Long, rng: SplittableRandom, dna: String) {
        tally.affinityChecks++
        val complement = String(CharArray(dna.length) { PyOracle.complement(dna[it]) })
        val randomGate = CaseGen.randomBases(rng, dna.length)
        try {
            if (codec.affinity(dna, complement) != 256) fail(index, "affinity-complement", reprText(dna))
            if (codec.affinity(dna, complement + "A") != 0) fail(index, "affinity-length", reprText(dna))
            val score = codec.affinity(dna, randomGate)
            var matches = 0
            for (i in dna.indices) if (PyOracle.complement(dna[i]) == randomGate[i]) matches++
            // dna_engine.py:29 computes int((matches / len) * 256): divide first, then scale, then truncate.
            val expect = ((matches.toDouble() / dna.length) * 256).toInt()
            if (score != expect) fail(index, "affinity-value", "$score != $expect")
        } catch (e: Throwable) {
            fail(index, "affinity-crash", describe(e))
        }
    }

    /** Addition: decode("") and a whitespace-only strand must both return an empty array. */
    private fun probeEmptyDecode(index: Long, rng: SplittableRandom) {
        checkDecode(index, "", PyOracle.cleanedBases(""))
        tally.emptyDecodeProbes++
        val whitespace = CaseGen.whitespaceOnly(rng)
        checkDecode(index, whitespace, PyOracle.cleanedBases(whitespace))
        tally.emptyDecodeProbes++
    }

    private fun fail(index: Long, kind: String, detail: String) {
        tally.record(Failure(seed, index, kind, detail))
    }
}

internal fun describe(e: Throwable): String = "${e.javaClass.name}: ${e.message}"

internal fun hexBytes(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 0xFF) }

/** Quotes text the way Python's repr would for printable ASCII, and escapes everything else as \uXXXX. */
internal fun reprText(text: String): String = buildString {
    append('\'')
    for (ch in text) {
        when {
            ch == '\'' || ch == '\\' -> append('\\').append(ch)
            ch.code in 0x20..0x7E -> append(ch)
            else -> append("\\u%04X".format(ch.code))
        }
    }
    append('\'')
}
