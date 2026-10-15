package org.everlang.dna

/**
 * One lexical token. [base] is the uppercased code point, and [index] is its position in the
 * cleaned sequence (whitespace takes no slot). [valid] is true only for A, T, C and G.
 *
 * Limitation: a code point above U+FFFF cannot be stored in a Char, so [base] is U+FFFD for it.
 * [index] and [valid] still match the reference exactly. The golden test writes the reference's
 * base through the same projection.
 */
data class BaseToken(val base: Char, val index: Int, val valid: Boolean)

/** A Watson-Crick pairing. [complement] is null when the token was invalid. */
data class BasePair(val index: Int, val base: Char, val complement: Char?, val valid: Boolean)

/** Three consecutive pairs grouped into a triplet. */
data class Codon(val pairs: List<BasePair>, val startIndex: Int)

/** Raised when the cleaned input is empty. Mirrors sequencer.DnaSyntaxError. */
class DnaSyntaxError(message: String) : Exception(message)

data class SequenceResult(
    val tokens: List<BaseToken>,
    val pairs: List<BasePair>,
    val codons: List<Codon>,
    val trailingPartial: List<BasePair>,
    val lexerErrors: List<BaseToken>,
    val parserErrors: List<BaseToken>,
    val gcContent: Double?,
    val valid: Boolean,
)

/** Mirrors sequencer.DnaLexer: cleans with upper-then-remove-whitespace, then tokenizes by code point. */
internal class DnaLexer(rawSequence: String) {
    val cleanedSequence: String = PyText.removeSpace(PyText.upper(rawSequence))
    private var tokens: List<BaseToken> = emptyList()

    fun tokenize(): List<BaseToken> {
        val cps = PyText.codePoints(cleanedSequence)
        val out = ArrayList<BaseToken>(cps.size)
        for (i in cps.indices) {
            val cp = cps[i]
            out += BaseToken(base = projectChar(cp), index = i, valid = Bases.code(cp) != Bases.NONE)
        }
        tokens = out
        return out
    }

    fun errors(): List<BaseToken> = tokens.filter { !it.valid }

    private fun projectChar(cp: Int): Char = if (cp <= 0xFFFF) cp.toChar() else '�'
}

/** Mirrors sequencer.DnaParser: pairs every token, groups triplets, keeps the trailing remainder. */
internal class DnaParser(private val tokens: List<BaseToken>) {
    private var pairs: List<BasePair> = emptyList()
    private var parseErrors: List<BaseToken> = emptyList()
    private var codons: List<Codon> = emptyList()
    private var trailing: List<BasePair> = emptyList()

    /** Throws [DnaSyntaxError] when the token stream is empty. */
    fun parse(): List<BasePair> {
        if (tokens.isEmpty()) throw DnaSyntaxError("cannot parse an empty DNA sequence")
        val out = ArrayList<BasePair>(tokens.size)
        val errors = ArrayList<BaseToken>()
        for (tok in tokens) {
            if (tok.valid) {
                out += BasePair(tok.index, tok.base, Bases.complement(tok.base.code).toChar(), true)
            } else {
                out += BasePair(tok.index, tok.base, null, false)
                errors += tok
            }
        }
        pairs = out
        parseErrors = errors
        groupCodons(out)
        return out
    }

    fun codons(): List<Codon> = codons

    val trailingPartial: List<BasePair> get() = trailing

    fun parseErrors(): List<BaseToken> = parseErrors

    private fun groupCodons(all: List<BasePair>) {
        val grouped = ArrayList<Codon>()
        var i = 0
        while (i + 3 <= all.size) {
            grouped += Codon(listOf(all[i], all[i + 1], all[i + 2]), all[i].index)
            i += 3
        }
        codons = grouped
        trailing = all.subList(i, all.size).toList()
    }
}

/** Mirrors sequencer.DnaSequencer.run. */
object DnaSequencer {
    /**
     * Lexes and parses [raw]. Throws [DnaSyntaxError] when the cleaned input is empty (all
     * whitespace counts as empty). Invalid characters do not throw: they become tokens with
     * valid=false, and [SequenceResult.valid] is false.
     *
     * gcContent is the share of G and C among the valid bases, or null when there are no valid
     * bases.
     */
    fun run(raw: String): SequenceResult {
        val lexer = DnaLexer(raw)
        val tokens = lexer.tokenize()
        val lexerErrors = lexer.errors()

        val parser = DnaParser(tokens)
        val pairs = parser.parse()
        val parserErrors = parser.parseErrors()

        var validCount = 0
        var gcCount = 0
        for (pair in pairs) {
            if (pair.valid) {
                validCount++
                if (pair.base == 'G' || pair.base == 'C') gcCount++
            }
        }
        val gc = if (validCount > 0) gcCount.toDouble() / validCount else null

        return SequenceResult(
            tokens = tokens,
            pairs = pairs,
            codons = parser.codons(),
            trailingPartial = parser.trailingPartial,
            lexerErrors = lexerErrors,
            parserErrors = parserErrors,
            gcContent = gc,
            valid = lexerErrors.isEmpty() && parserErrors.isEmpty(),
        )
    }
}
