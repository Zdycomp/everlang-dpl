package org.everlang.dna.fuzz

import java.util.SplittableRandom

/**
 * Per-case randomness. Case (seed, index) always draws the same numbers, so a reported failure is reproduced by
 * rerunning that seed and index.
 *
 * The stream is not Python's Mersenne Twister. Kotlin seeds therefore do not map to the Python harness's cases.
 * Only the oracles and the pools are ported.
 */
internal object CaseRandom {
    fun forCase(seed: Long, index: Long): SplittableRandom = SplittableRandom(mix64((seed * 1_000_003L) xor index))

    /** SplitMix64 finalizer, so that neighbouring (seed, index) pairs get unrelated streams. */
    private fun mix64(input: Long): Long {
        var z = input + 0x9E3779B97F4A7C15uL.toLong()
        z = (z xor (z ushr 30)) * 0xBF58476D1CE4E5B9uL.toLong()
        z = (z xor (z ushr 27)) * 0x94D049BB133111EBuL.toLong()
        return z xor (z ushr 31)
    }
}

/** Input generators and the fixed pools from everlang_standalone/tests/fuzz_harness.py. */
internal object CaseGen {
    /**
     * Python's HOSTILE_CHARS, in the same order: list("XN-*#.0 \t\n\r\x00\x7féßİ  ﻿\U0001F9EC")
     * + ["a", "g", "t"]. U+1F9EC is one code point but a surrogate pair in Kotlin, so each entry is a String.
     */
    val HOSTILE_CHARS: List<String> = listOf(
        "X", "N", "-", "*", "#", ".", "0", " ", "\t", "\n", "\r", "\u0000", "\u007F",
        "é", "ß", "İ", " ", "﻿", "🧬",
        "a", "g", "t",
    )

    /**
     * The four bases in a fixed order. The Python harness uses list(frozenset), whose order depends on the hash
     * seed, so its ATCG choices are not reproducible across processes. Here the order is fixed.
     */
    val BASES: List<String> = listOf("A", "T", "C", "G")

    /** Injection operations, in the same order as the Python harness. */
    val INJECTION_OPS: List<String> = listOf("insert", "substitute", "delete", "lower", "insert4")

    /** Python: HOSTILE_CHARS + list(ATCG). Used by insert and substitute. */
    val INJECTION_POOL: List<String> = HOSTILE_CHARS + BASES

    /** Whitespace-only probes for decode. Each is a str.isspace() code point. */
    val WHITESPACE_PROBES: List<String> = listOf(" ", "\t", "\n", "\r", " ")

    private val EMPTY_SIZES = intArrayOf(0, 1, 2, 3, 4, 5, 7, 8, 9)
    private val REPEAT_BYTES = intArrayOf(0x00, 0xFF, 0x1B, 0x80)

    /** Mirrors _random_bytes: 10% empty-ish sizes, 10% one repeated byte, the rest random 0..48 bytes. */
    fun randomBytes(rng: SplittableRandom): ByteArray {
        val mode = rng.nextDouble()
        val n = if (mode < 0.1) EMPTY_SIZES[rng.nextInt(EMPTY_SIZES.size)] else rng.nextInt(0, 49)
        if (mode < 0.2) {
            val repeated = REPEAT_BYTES[rng.nextInt(REPEAT_BYTES.size)].toByte()
            return ByteArray(n) { repeated }
        }
        return ByteArray(n) { rng.nextInt(256).toByte() }
    }

    fun pick(rng: SplittableRandom, pool: List<String>): String = pool[rng.nextInt(pool.size)]

    /** n random bases from ATCG, each drawn independently. */
    fun randomBases(rng: SplittableRandom, n: Int): String = buildString {
        repeat(n) { append(BASES[rng.nextInt(BASES.size)]) }
    }

    /** One to four whitespace code points, as a strand that decodes to empty. */
    fun whitespaceOnly(rng: SplittableRandom): String = buildString {
        repeat(1 + rng.nextInt(4)) { append(WHITESPACE_PROBES[rng.nextInt(WHITESPACE_PROBES.size)]) }
    }
}
