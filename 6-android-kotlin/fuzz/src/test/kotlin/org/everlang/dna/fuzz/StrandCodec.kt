package org.everlang.dna.fuzz

import org.everlang.dna.BinarySequencer
import org.everlang.dna.StrandReport

/**
 * The codec surface the oracle checks. [CoreStrandCodec] delegates to the real implementation. The mutants in
 * Mutants.kt wrap an implementation and sabotage one method, to prove that the oracle notices.
 */
interface StrandCodec {
    fun sequence(data: ByteArray): StrandReport

    /** Strict decode. Throws IllegalArgumentException to reject. */
    fun decode(dna: String): ByteArray

    fun affinity(dna: String, gate: String): Int
}

/** The real codec, from org.everlang.dna.BinarySequencer. */
class CoreStrandCodec : StrandCodec {
    private val sequencer = BinarySequencer()

    override fun sequence(data: ByteArray): StrandReport = sequencer.sequence(data)

    override fun decode(dna: String): ByteArray = sequencer.decode(dna)

    override fun affinity(dna: String, gate: String): Int = sequencer.affinity(dna, gate)
}
