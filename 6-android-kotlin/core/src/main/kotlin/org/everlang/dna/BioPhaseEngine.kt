package org.everlang.dna

/**
 * Hybridization affinity of a strand against a gate, on the 0..256 scale. Mirrors
 * everlang_standalone/everlang/biocomputing/dna_engine.py, which is the parity spec.
 *
 * The gate is stored as str.upper().strip(). The input is also str.upper().strip(), so only
 * leading and trailing whitespace is removed and interior whitespace counts as a position that
 * never matches. Lengths are counted in code points, so a valid surrogate pair counts once. CPython
 * counts the two halves of such a pair separately; see [PyText] for that divergence.
 */
class BioPhaseEngine(targetGate: String) {
    /** The normalised gate, for example "  atcg \n" becomes "ATCG". */
    val gateSequence: String = PyText.strip(PyText.upper(targetGate))

    private val gateCodePoints: IntArray = PyText.codePoints(gateSequence)

    /**
     * Returns 0 when the lengths differ or the gate is empty. Otherwise returns
     * `((matches.toDouble() / length) * 256).toInt()`, which truncates like Python's int().
     */
    fun calculateHybridizationAffinity(input: String): Int {
        val inputCodePoints = PyText.codePoints(PyText.strip(PyText.upper(input)))
        if (inputCodePoints.size != gateCodePoints.size || gateCodePoints.isEmpty()) return 0

        var matches = 0
        for (i in inputCodePoints.indices) {
            val partner = Bases.complement(inputCodePoints[i])
            if (partner != Bases.NONE && partner == gateCodePoints[i]) matches++
        }
        return ((matches.toDouble() / gateCodePoints.size) * 256).toInt()
    }
}
