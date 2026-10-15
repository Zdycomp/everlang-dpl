package org.everlang.dna

/**
 * Result of encoding bytes as a strand. Mirrors the dict returned by
 * everlang_standalone/everlang/biocomputing/binary_sequencer.py.
 */
data class StrandReport(
    val dna: String,
    val byteCount: Int,
    val codons: List<Codon>,
    val trailingPartial: List<BasePair>,
    val gcContent: Double?,
    val roundTrip: Boolean,
)

/** Encodes bytes as a DNA strand and decodes strands back, strictly. Mirrors binary_sequencer.py. */
class BinarySequencer {
    fun sequence(data: ByteArray): StrandReport {
        if (data.isEmpty()) {
            return StrandReport(
                dna = "",
                byteCount = 0,
                codons = emptyList(),
                trailingPartial = emptyList(),
                gcContent = null,
                roundTrip = true,
            )
        }
        val dna = Quaternary.bytesToDna(data)
        val result = DnaSequencer.run(dna)
        return StrandReport(
            dna = dna,
            byteCount = data.size,
            codons = result.codons,
            trailingPartial = result.trailingPartial,
            gcContent = result.gcContent,
            roundTrip = decode(dna).contentEquals(data),
        )
    }

    /**
     * Strict decode. Whitespace (str.isspace code points) is ignored and case is folded. An empty
     * or whitespace-only strand gives an empty array.
     *
     * @throws IllegalArgumentException when the strand has a character other than A, T, C, G (after
     *   case folding), or when its base count is not a multiple of 4. The Python reference raises
     *   ValueError here. Python builds the bad-character text with repr(), which escapes control and
     *   surrogate characters and picks the quote style. This port uses plain single quotes, so the
     *   text can differ for those characters. The exception type and the accept/reject decision are
     *   the parity contract, and the golden test checks only those.
     */
    fun decode(dna: String): ByteArray {
        if (PyText.removeSpace(dna).isEmpty()) return ByteArray(0)
        val result = DnaSequencer.run(dna)
        if (result.lexerErrors.isNotEmpty()) {
            val bad = result.lexerErrors.joinToString("") { it.base.toString() }
            throw IllegalArgumentException("strand contains non-ATCG characters: '$bad'")
        }
        if (result.pairs.size % BASES_PER_BYTE != 0) {
            throw IllegalArgumentException(
                "strand length ${result.pairs.size} is not a multiple of $BASES_PER_BYTE",
            )
        }
        return Quaternary.dnaToBytes(dna)
    }

    /** Hybridization affinity of [dna] against [gate], 0..256. See [BioPhaseEngine]. */
    fun affinity(dna: String, gate: String): Int = BioPhaseEngine(gate).calculateHybridizationAffinity(dna)

    private companion object {
        const val BASES_PER_BYTE = 4
    }
}
