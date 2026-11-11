package org.everlang.dna.predict

/**
 * Adaptive order-k context model over the four bases, with additive (Lidstone) smoothing. It is a
 * statistical estimator: it reports what it measures on the input it is given, and makes no claim
 * beyond that.
 *
 * Symbols are the 2-bit codes used by core's [org.everlang.dna.Quaternary]: A=0, T=1, C=2, G=3.
 * The context is the last [order] symbols packed two bits each, with the most recent symbol in the
 * low bits. Before the first symbol the context is all zero, the padding rule: the history is
 * treated as A repeated [order] times.
 *
 * For the next symbol s in context c:
 *
 *     p(s | c) = (n[c][s] + alpha) / (sum over t of n[c][t] + 4 * alpha)
 *
 * [update] increments n[c][s] and moves the context forward. Counts only grow until [reset].
 *
 * Higher order is not free on incompressible input: each context is seen fewer times, so the
 * learning cost per symbol rises. OrderKModelTest checks that order 8 costs more than order 3 on
 * seeded random bytes.
 *
 * Memory: the count table has 4^order contexts times 4 symbols, one 32-bit Int each, so it takes
 * 16 * 4^order bytes:
 *
 *     order   table        order   table
 *       1       64 B         6      64 KiB
 *       2      256 B         7     256 KiB
 *       3        1 KiB       8       1 MiB
 *       4        4 KiB       9       4 MiB
 *       5       16 KiB      10      16 MiB
 *
 * Orders outside 1..[MAX_ORDER] are rejected before any table is allocated. Order 11 would need
 * 64 MiB, so it is refused.
 *
 * Counts are Int. [update] throws ArithmeticException if one cell would pass Int.MAX_VALUE. An
 * instance is not safe for concurrent use.
 */
class OrderKModel(val order: Int, val alpha: Double = DEFAULT_ALPHA) {
    init {
        require(order in 1..MAX_ORDER) { "order must be in 1..$MAX_ORDER, got $order" }
        require(alpha > 0.0 && alpha.isFinite()) { "alpha must be a positive finite number, got $alpha" }
    }

    private val mask: Int = (1 shl (2 * order)) - 1
    private val counts: IntArray = IntArray(4 shl (2 * order))
    private var context: Int = 0

    /** Predictive distribution for the next symbol, indexed by 2-bit code. Sums to 1. */
    fun probabilities(): DoubleArray = DoubleArray(4).also { fill(it) }

    /** Records [symbol] (0..3) in the current context and advances the context. */
    fun update(symbol: Int) {
        require(symbol in 0..3) { "symbol must be in 0..3, got $symbol" }
        val cell = context * 4 + symbol
        counts[cell] = Math.addExact(counts[cell], 1)
        context = ((context shl 2) or symbol) and mask
    }

    /** Clears all counts and the context, so the model behaves as a freshly constructed one. */
    fun reset() {
        counts.fill(0)
        context = 0
    }

    /** Writes [probabilities] into [out] without allocating. */
    internal fun fill(out: DoubleArray) {
        val base = context * 4
        val total = counts[base].toLong() + counts[base + 1] + counts[base + 2] + counts[base + 3]
        val denom = total.toDouble() + 4.0 * alpha
        for (s in 0..3) out[s] = (counts[base + s] + alpha) / denom
    }

    /**
     * The most frequent symbol in the current context, lowest index on ties. This is the top-1
     * prediction. For a fixed context p is strictly increasing in the count, so the argmax of
     * the probabilities is the same symbol.
     */
    internal fun mostFrequent(): Int {
        val base = context * 4
        var best = 0
        for (s in 1..3) if (counts[base + s] > counts[base + best]) best = s
        return best
    }

    companion object {
        /** Largest supported order. Its table is 16 MiB. */
        const val MAX_ORDER = 10

        /** Default smoothing constant. */
        const val DEFAULT_ALPHA = 0.5
    }
}
