package org.everlang.dna.predict

import org.everlang.dna.Quaternary
import java.util.Random
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class OrderKModelTest {
    private fun symbolsOf(text: String): ByteArray = ByteArray(text.length) { "ATCG".indexOf(text[it]).toByte() }

    @Test
    fun freshModelIsUniform() {
        for (order in listOf(1, 3, 10)) {
            val p = OrderKModel(order).probabilities()
            assertEquals(4, p.size)
            for (x in p) assertEquals(0.25, x, "order $order")
        }
    }

    @Test
    fun probabilitiesSumToOneAfterRandomUpdates() {
        for (order in listOf(1, 3, 5, 8, 10)) {
            val model = OrderKModel(order)
            val rnd = Random(order.toLong())
            repeat(5000) {
                model.update(rnd.nextInt(4))
                val p = model.probabilities()
                assertEquals(1.0, p.sum(), 1e-12, "order $order")
                for (x in p) assertTrue(x > 0.0 && x < 1.0, "order $order, p=$x")
            }
        }
    }

    @Test
    fun orderZeroAndElevenAreRejected() {
        assertFailsWith<IllegalArgumentException> { OrderKModel(0) }
        assertFailsWith<IllegalArgumentException> { OrderKModel(11) }
        assertFailsWith<IllegalArgumentException> { OrderKModel(-1) }
        assertFailsWith<IllegalArgumentException> { evaluateSymbols(ByteArray(4), 0) }
        assertFailsWith<IllegalArgumentException> { evaluateBytes(ByteArray(4), 11) }
        OrderKModel(1)
        OrderKModel(10)
    }

    @Test
    fun alphaMustBePositiveAndFinite() {
        for (a in listOf(0.0, -0.5, Double.NaN, Double.POSITIVE_INFINITY)) {
            assertFailsWith<IllegalArgumentException>("alpha=$a") { OrderKModel(3, a) }
        }
    }

    @Test
    fun symbolsOutsideZeroToThreeAreRejected() {
        val model = OrderKModel(2)
        for (s in listOf(-1, 4, 255)) assertFailsWith<IllegalArgumentException>("update($s)") { model.update(s) }
        assertFailsWith<IllegalArgumentException> { evaluateSymbols(byteArrayOf(0, 4), 2) }
        assertFailsWith<IllegalArgumentException> { evaluateSymbols(byteArrayOf(-1), 2) }
    }

    @Test
    fun resetRestoresUniformProbabilities() {
        val model = OrderKModel(3)
        val rnd = Random(9)
        repeat(1000) { model.update(rnd.nextInt(4)) }
        model.reset()
        for (x in model.probabilities()) assertEquals(0.25, x)
    }

    @Test
    fun resetClearsContextAsWellAsCounts() {
        val rnd = Random(11)
        val model = OrderKModel(2)
        repeat(37) { model.update(rnd.nextInt(4)) }
        model.reset()
        val fresh = OrderKModel(2)
        repeat(500) {
            assertContentEquals(fresh.probabilities(), model.probabilities())
            val s = rnd.nextInt(4)
            model.update(s)
            fresh.update(s)
        }
        assertContentEquals(fresh.probabilities(), model.probabilities())
    }

    @Test
    fun singleSymbolFromFreshModelCostsTwoBits() {
        val r = evaluateSymbols(byteArrayOf(2), 1)
        assertEquals(1L, r.bases)
        assertEquals(2.0, r.totalBits, 1e-12)
        assertEquals(2.0, r.bitsPerBase, 1e-12)
    }

    @Test
    fun top1TieGoesToLowestIndex() {
        // A fresh model is uniform, so the first prediction is a four-way tie and A (index 0) wins.
        assertEquals(1.0, evaluateSymbols(byteArrayOf(0), 1).top1Accuracy)
        assertEquals(0.0, evaluateSymbols(byteArrayOf(1), 1).top1Accuracy)
        assertEquals(0.0, evaluateSymbols(byteArrayOf(2), 1).top1Accuracy)
        assertEquals(0.0, evaluateSymbols(byteArrayOf(3), 1).top1Accuracy)
    }

    @Test
    fun emptyInputReportsZerosAndBaseline() {
        val expected = PredictionReport(0L, 0.0, 0.0, 0.0, 2.0)
        assertEquals(expected, evaluateSymbols(ByteArray(0), 3))
        assertEquals(expected, evaluateBytes(ByteArray(0), 3))
    }

    @Test
    fun periodicSequenceIsLearned() {
        val r = evaluateSymbols(symbolsOf("ATCG".repeat(10000)), order = 3)
        assertEquals(40000L, r.bases)
        assertTrue(r.bitsPerBase < 0.05, "bitsPerBase=${r.bitsPerBase}")
        assertTrue(r.top1Accuracy > 0.99, "top1=${r.top1Accuracy}")
    }

    @Test
    fun seededRandomBytesStayNearTwoBitsPerBase() {
        val data = ByteArray(256 * 1024)
        Random(RANDOM_SEED).nextBytes(data)
        val r = evaluateBytes(data, order = 3)
        assertEquals(4L * data.size, r.bases)
        assertTrue(r.bitsPerBase in 1.95..2.05, "bitsPerBase=${r.bitsPerBase}")
    }

    @Test
    fun higherOrderCostsMoreOnTheSameRandomBytes() {
        val data = ByteArray(256 * 1024)
        Random(RANDOM_SEED).nextBytes(data)
        val low = evaluateBytes(data, 3).bitsPerBase
        val high = evaluateBytes(data, 8).bitsPerBase
        assertTrue(high > low, "order 8 ($high) should cost more than order 3 ($low) on random input")
    }

    @Test
    fun evaluateBytesEqualsEvaluateSymbolsOnTheStrand() {
        val data = ByteArray(700)
        Random(77).nextBytes(data)
        val strand = Quaternary.bytesToDna(data)
        val codes = symbolsOf(strand)
        for (order in listOf(1, 3, 8)) {
            assertEquals(evaluateSymbols(codes, order), evaluateBytes(data, order), "order $order")
        }
        assertEquals(4L * data.size, evaluateBytes(data, 3).bases)
    }

    private companion object {
        const val RANDOM_SEED = 20260615L
    }
}
