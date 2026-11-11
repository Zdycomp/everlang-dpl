package org.everlang.dna.predict

import kotlin.math.log2

/**
 * Measured result of a predict-then-update pass over a symbol stream.
 *
 * @property bases number of symbols scored.
 * @property totalBits sum over symbols of -log2 p(actual symbol | context), before that symbol
 *   is learned.
 * @property bitsPerBase totalBits / bases, or 0.0 when there are no symbols.
 * @property top1Accuracy fraction of symbols equal to the most frequent symbol in their context
 *   (lowest index on ties), or 0.0 when there are no symbols.
 * @property baselineBitsPerBase the cost of a uniform guess over four bases, log2(4) = 2. It is a
 *   fixed reference value, not a measurement. Compare [bitsPerBase] against it.
 */
data class PredictionReport(
    val bases: Long,
    val totalBits: Double,
    val bitsPerBase: Double,
    val top1Accuracy: Double,
    val baselineBitsPerBase: Double,
)

/** Uniform guess over four bases: log2(4) bits per base. */
const val BASELINE_BITS_PER_BASE: Double = 2.0

/**
 * Predict-then-update over [symbols], each a 2-bit code 0..3 (A=0, T=1, C=2, G=3). Every symbol is
 * scored by the model as it stands, then learned. Throws IllegalArgumentException for a value
 * outside 0..3, and for an [order] or [alpha] that [OrderKModel] rejects.
 */
fun evaluateSymbols(symbols: ByteArray, order: Int, alpha: Double = OrderKModel.DEFAULT_ALPHA): PredictionReport {
    val model = OrderKModel(order, alpha)
    val pass = Pass()
    for (b in symbols) pass.observe(model, b.toInt())
    return pass.report()
}

/**
 * The binary, strand, predict pipeline: each byte becomes four symbols, most significant pair
 * first, which is the strand [org.everlang.dna.Quaternary.bytesToDna] produces. The result equals
 * [evaluateSymbols] on those codes. The report counts 4 * data.size bases.
 */
fun evaluateBytes(data: ByteArray, order: Int, alpha: Double = OrderKModel.DEFAULT_ALPHA): PredictionReport {
    val model = OrderKModel(order, alpha)
    val pass = Pass()
    for (b in data) {
        val v = b.toInt() and 0xFF
        pass.observe(model, (v shr 6) and 3)
        pass.observe(model, (v shr 4) and 3)
        pass.observe(model, (v shr 2) and 3)
        pass.observe(model, v and 3)
    }
    return pass.report()
}

private class Pass {
    private var bases = 0L
    private var hits = 0L
    private var totalBits = 0.0
    private val p = DoubleArray(4)

    fun observe(model: OrderKModel, symbol: Int) {
        require(symbol in 0..3) { "symbol must be in 0..3, got $symbol" }
        model.fill(p)
        totalBits += -log2(p[symbol])
        if (model.mostFrequent() == symbol) hits++
        model.update(symbol)
        bases++
    }

    fun report(): PredictionReport = PredictionReport(
        bases = bases,
        totalBits = totalBits,
        bitsPerBase = if (bases == 0L) 0.0 else totalBits / bases,
        top1Accuracy = if (bases == 0L) 0.0 else hits.toDouble() / bases,
        baselineBitsPerBase = BASELINE_BITS_PER_BASE,
    )
}
