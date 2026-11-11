package org.everlang.dna.predict

import kotlin.math.abs
import kotlin.math.max
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Cross-check against predict/src/test/resources/predict_reference.tsv, which
 * predict/tools/ref_predict.py writes from an independent implementation. Each row is one
 * (input, order, alpha). Tolerances per row:
 *
 *   bases, top-1 accuracy   exact equality
 *   bits per base           1e-9 absolute
 *   total bits              1e-9 relative (log2 may differ from Python's by one ulp)
 *   final probabilities     1e-12 absolute
 *
 * Every mismatch is listed in the failure message. Nothing is skipped.
 */
class ReferenceParityTest {
    private val rows: List<List<String>> by lazy {
        val text = ReferenceParityTest::class.java.getResourceAsStream(RESOURCE)
            ?.use { it.readBytes().toString(Charsets.UTF_8) }
            ?: error("$RESOURCE is missing from the test resources")
        val lines = text.lines().filter { it.isNotEmpty() }
        assertEquals(HEADER.joinToString("\t"), lines.first(), "header line")
        lines.drop(1).map { line ->
            line.split('\t').also { assertEquals(HEADER.size, it.size, "field count in: $line") }
        }
    }

    @Test
    fun referenceCoversEveryKindAndOrder() {
        assertEquals(EXPECTED_ROWS, rows.size, "row count")
        assertEquals(setOf("symbols", "bytes"), rows.map { it[1] }.toSet())
        assertEquals(setOf("1", "3", "8"), rows.map { it[2] }.toSet())
    }

    @Test
    fun everyRowMatchesTheReference() {
        val mismatches = mutableListOf<String>()
        for ((i, f) in rows.withIndex()) check(f, "row ${i + 1} [${f[0]} ${f[1]} order=${f[2]} alpha=${f[3]}]", mismatches)
        assertTrue(mismatches.isEmpty(), "${mismatches.size} of ${rows.size} rows differ:\n" + mismatches.joinToString("\n"))
    }

    private fun check(f: List<String>, where: String, out: MutableList<String>) {
        val kind = f[1]
        val order = f[2].toInt()
        val alpha = f[3].toDouble()
        val symbols: ByteArray
        val report: PredictionReport
        when (kind) {
            "symbols" -> {
                symbols = symbolsOfLetters(f[4])
                report = evaluateSymbols(symbols, order, alpha)
            }
            "bytes" -> {
                val data = hexToBytes(f[4])
                symbols = symbolsOfBytes(data)
                report = evaluateBytes(data, order, alpha)
            }
            else -> {
                out += "$where: unknown kind $kind"
                return
            }
        }

        val model = OrderKModel(order, alpha)
        for (s in symbols) model.update(s.toInt())
        val p = model.probabilities()

        val refBases = f[5].toLong()
        val refTotalBits = f[7].toDouble()
        val refBitsPerBase = f[8].toDouble()
        val refTop1 = f[9].toDouble()
        val refProbs = DoubleArray(4) { f[10 + it].toDouble() }

        if (report.bases != refBases) out += "$where: bases ${report.bases} != $refBases"
        if (report.top1Accuracy != refTop1) out += "$where: top1 ${report.top1Accuracy} != $refTop1"
        if (abs(report.bitsPerBase - refBitsPerBase) > 1e-9) {
            out += "$where: bitsPerBase ${report.bitsPerBase} != $refBitsPerBase (diff ${report.bitsPerBase - refBitsPerBase})"
        }
        if (abs(report.totalBits - refTotalBits) > 1e-9 * max(1.0, abs(refTotalBits))) {
            out += "$where: totalBits ${report.totalBits} != $refTotalBits"
        }
        for (s in 0..3) {
            if (abs(p[s] - refProbs[s]) > 1e-12) out += "$where: p[$s] ${p[s]} != ${refProbs[s]}"
        }
    }

    private fun symbolsOfLetters(text: String): ByteArray = ByteArray(text.length) { i ->
        val code = "ATCG".indexOf(text[i])
        require(code >= 0) { "not a base: '${text[i]}' at $i" }
        code.toByte()
    }

    private fun hexToBytes(hex: String): ByteArray {
        require(hex.length % 2 == 0) { "odd hex length" }
        return ByteArray(hex.length / 2) { i -> hex.substring(2 * i, 2 * i + 2).toInt(16).toByte() }
    }

    /** Most significant bit pair first, with explicit shifts. Written here, not taken from the code under test. */
    private fun symbolsOfBytes(data: ByteArray): ByteArray {
        val out = ByteArray(4 * data.size)
        var k = 0
        for (b in data) {
            val v = b.toInt() and 0xFF
            out[k++] = ((v shr 6) and 3).toByte()
            out[k++] = ((v shr 4) and 3).toByte()
            out[k++] = ((v shr 2) and 3).toByte()
            out[k++] = (v and 3).toByte()
        }
        return out
    }

    private companion object {
        const val RESOURCE = "/predict_reference.tsv"
        const val EXPECTED_ROWS = 22
        val HEADER = listOf(
            "name", "kind", "order", "alpha", "input", "bases", "hits",
            "total_bits", "bits_per_base", "top1_accuracy", "p_A", "p_T", "p_C", "p_G",
        )
    }
}
