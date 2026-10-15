package org.everlang.dna.fuzz

import org.everlang.dna.DnaSequencer
import org.everlang.dna.Quaternary

/*
 * Sabotaged codecs. Each one changes a single behaviour of the real codec, and MutationTest asserts that the oracle
 * reports at least one failure for each. A mutant that the oracle misses would mean the oracle is too weak.
 */

/** (a) decode with validation skipped: Quaternary's lax decode drops bad characters and partial bytes. */
class LaxDecodeMutant(core: StrandCodec) : StrandCodec by core {
    override fun decode(dna: String): ByteArray = Quaternary.dnaToBytes(dna)
}

/** (b) affinity always reports a perfect complement match, even for a length mismatch. */
class AffinityAlways256Mutant(core: StrandCodec) : StrandCodec by core {
    override fun affinity(dna: String, gate: String): Int = 256
}

/** (c) decode rejects lowercase input, although the spec folds case. */
class RejectLowercaseMutant(private val core: StrandCodec) : StrandCodec by core {
    override fun decode(dna: String): ByteArray {
        require(dna.none { it in 'a'..'z' }) { "lowercase rejected" }
        return core.decode(dna)
    }
}

/** (d) decode("") throws instead of returning an empty array. */
class EmptyDecodeThrowsMutant(private val core: StrandCodec) : StrandCodec by core {
    override fun decode(dna: String): ByteArray {
        require(dna.isNotEmpty()) { "decode refuses the empty strand" }
        return core.decode(dna)
    }
}

/**
 * (d2, extra) the empty-input guard is dropped, so decode goes straight to DnaSequencer.run. That throws
 * DnaSyntaxError for "" and for whitespace-only input, which is not an IllegalArgumentException.
 */
class NoEmptyGuardMutant : StrandCodec by CoreStrandCodec() {
    override fun decode(dna: String): ByteArray {
        val result = DnaSequencer.run(dna)
        if (result.lexerErrors.isNotEmpty()) throw IllegalArgumentException("strand contains non-ATCG characters")
        if (result.pairs.size % 4 != 0) throw IllegalArgumentException("strand length is not a multiple of 4")
        return Quaternary.dnaToBytes(dna)
    }
}
