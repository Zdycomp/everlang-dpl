package org.everlang.dna

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Mirrors everlang_standalone/tests/test_dna_sequencer.py. */
class DnaSequencerTest {
    private fun tuples(tokens: List<BaseToken>) = tokens.map { Triple(it.base, it.index, it.valid) }

    private fun pairTuples(pairs: List<BasePair>) = pairs.map { Triple(it.base, it.index, it.valid) }

    // Lexer

    @Test
    fun lexerCleansViaUppercaseAndStripsWhitespace() {
        val lexer = DnaLexer("at g c")
        lexer.tokenize()
        assertEquals("ATGC", lexer.cleanedSequence)
    }

    @Test
    fun lexerWhitespaceDoesNotConsumeAnIndexSlot() {
        val lexer = DnaLexer("A T G")
        val tokens = lexer.tokenize()
        assertEquals("ATG", lexer.cleanedSequence)
        assertEquals(listOf(0, 1, 2), tokens.map { it.index })
    }

    @Test
    fun lexerInvalidCharKeepsItsIndexAndDoesNotShiftLaterIndices() {
        val lexer = DnaLexer("ATXCG")
        val tokens = lexer.tokenize()
        assertEquals("ATXCG", lexer.cleanedSequence)
        assertEquals(
            listOf(Triple('A', 0, true), Triple('T', 1, true), Triple('X', 2, false), Triple('C', 3, true), Triple('G', 4, true)),
            tuples(tokens),
        )
    }

    @Test
    fun lexerInvalidCharMixedWithWhitespaceKeepsIndexCorrect() {
        val lexer = DnaLexer("AT G#C")
        val tokens = lexer.tokenize()
        assertEquals("ATG#C", lexer.cleanedSequence)
        assertEquals(
            listOf(Triple('A', 0, true), Triple('T', 1, true), Triple('G', 2, true), Triple('#', 3, false), Triple('C', 4, true)),
            tuples(tokens),
        )
    }

    @Test
    fun lexerErrorsReturnsExactlyTheInvalidTokens() {
        val lexer = DnaLexer("ATXCGZ")
        lexer.tokenize()
        val errors = lexer.errors()
        assertEquals(listOf('X', 'Z'), errors.map { it.base })
        assertTrue(errors.all { !it.valid })
    }

    @Test
    fun lexerErrorsEmptyWhenAllValid() {
        val lexer = DnaLexer("ATCG")
        lexer.tokenize()
        assertTrue(lexer.errors().isEmpty())
    }

    @Test
    fun lexerEmptyStringCleansToEmpty() {
        val lexer = DnaLexer("")
        assertTrue(lexer.tokenize().isEmpty())
        assertEquals("", lexer.cleanedSequence)
    }

    @Test
    fun lexerAllWhitespaceCleansToEmpty() {
        val lexer = DnaLexer("   \n\t  ")
        assertTrue(lexer.tokenize().isEmpty())
        assertEquals("", lexer.cleanedSequence)
    }

    @Test
    fun lexerRemovesEveryWhitespaceKindIncludingUnicodeSpaces() {
        val lexer = DnaLexer("A\u00A0T\u2028C\u0085G\u001cA")
        lexer.tokenize()
        assertEquals("ATCGA", lexer.cleanedSequence)
    }

    @Test
    fun lexerSharpSExpandsToTwoInvalidTokens() {
        val lexer = DnaLexer("a\u00DFA")
        val tokens = lexer.tokenize()
        assertEquals(listOf(Triple('A', 0, true), Triple('S', 1, false), Triple('S', 2, false), Triple('A', 3, true)), tuples(tokens))
    }

    @Test
    fun lexerSupplementaryCodePointIsOneTokenWithProjectedBase() {
        val lexer = DnaLexer("A\uD83E\uDDECT")
        val tokens = lexer.tokenize()
        assertEquals(3, tokens.size)
        assertEquals(listOf(0, 1, 2), tokens.map { it.index })
        assertEquals(Triple('\uFFFD', 1, false), tuples(tokens)[1])
    }

    // Parser

    @Test
    fun parserWatsonCrickPairingForAllBases() {
        val pairs = DnaParser(DnaLexer("ATCG").tokenize()).parse()
        val complements = pairs.associate { it.base to it.complement }
        assertEquals(mapOf('A' to 'T', 'T' to 'A', 'C' to 'G', 'G' to 'C'), complements)
        assertTrue(pairs.all { it.valid })
    }

    @Test
    fun parserRaisesOnEmptyTokenList() {
        assertFailsWith<DnaSyntaxError> { DnaParser(emptyList()).parse() }
    }

    @Test
    fun parserInvalidTokenProducesInvalidUnpairedBasePairAndParsingContinues() {
        val pairs = DnaParser(DnaLexer("ATXCG").tokenize()).parse()
        assertEquals(5, pairs.size)
        val bad = pairs[2]
        assertEquals('X', bad.base)
        assertEquals(2, bad.index)
        assertFalse(bad.valid)
        assertNull(bad.complement)
    }

    @Test
    fun parserCollectsInvalidTokensAsParseErrors() {
        val parser = DnaParser(DnaLexer("ATXCGZ").tokenize())
        parser.parse()
        assertEquals(listOf('X', 'Z'), parser.parseErrors().map { it.base })
    }

    @Test
    fun parserCodonGroupingForAnExactMultipleOfThree() {
        val parser = DnaParser(DnaLexer("ATCGAT").tokenize())
        parser.parse()
        val codons = parser.codons()
        assertEquals(2, codons.size)
        assertTrue(parser.trailingPartial.isEmpty())
        assertEquals(listOf(0, 3), codons.map { it.startIndex })
        assertEquals(listOf('A', 'T', 'C'), codons[0].pairs.map { it.base })
        assertEquals(listOf('G', 'A', 'T'), codons[1].pairs.map { it.base })
    }

    @Test
    fun parserCodonGroupingLeavesOneTrailingPairWhenFiveBases() {
        val parser = DnaParser(DnaLexer("ATCGA").tokenize())
        parser.parse()
        assertEquals(1, parser.codons().size)
        assertEquals(listOf('G', 'A'), parser.trailingPartial.map { it.base })
    }

    @Test
    fun parserCodonGroupingLeavesOneTrailingPairWhenSevenBases() {
        val parser = DnaParser(DnaLexer("ATCGATC").tokenize())
        parser.parse()
        assertEquals(2, parser.codons().size)
        assertEquals(listOf('C'), parser.trailingPartial.map { it.base })
    }

    @Test
    fun parserCodonsIncludeInvalidPairsInOriginalOrder() {
        val parser = DnaParser(DnaLexer("ATXCGA").tokenize())
        parser.parse()
        val codons = parser.codons()
        assertEquals(2, codons.size)
        assertTrue(parser.trailingPartial.isEmpty())
        assertEquals(listOf('A', 'T', 'X'), codons[0].pairs.map { it.base })
        assertFalse(codons[0].pairs[2].valid)
        assertEquals(listOf('C', 'G', 'A'), codons[1].pairs.map { it.base })
    }

    // Sequencer

    @Test
    fun runRaisesOnEmptyString() {
        assertFailsWith<DnaSyntaxError> { DnaSequencer.run("") }
    }

    @Test
    fun runRaisesOnAllWhitespaceString() {
        assertFailsWith<DnaSyntaxError> { DnaSequencer.run("   \t \n ") }
    }

    @Test
    fun runRaisesWhenOnlyUnicodeWhitespaceIsPresent() {
        assertFailsWith<DnaSyntaxError> { DnaSequencer.run("\u00A0\u2028\u001c") }
    }

    @Test
    fun runValidIsTrueWhenThereAreNoErrors() {
        val result = DnaSequencer.run("ATCGAT")
        assertTrue(result.valid)
        assertTrue(result.lexerErrors.isEmpty())
        assertTrue(result.parserErrors.isEmpty())
    }

    @Test
    fun runValidIsFalseWhenInvalidCharsArePresent() {
        val result = DnaSequencer.run("ATXCG")
        assertFalse(result.valid)
        assertEquals(1, result.lexerErrors.size)
        assertEquals(1, result.parserErrors.size)
    }

    @Test
    fun gcContentKnownValue() {
        assertEquals(0.5, DnaSequencer.run("ATCG").gcContent)
    }

    @Test
    fun gcContentExcludesInvalidBases() {
        assertEquals(0.5, DnaSequencer.run("ATXCG").gcContent)
    }

    @Test
    fun gcContentIsNullWhenNoValidBasesButPairsExist() {
        val result = DnaSequencer.run("XYZ")
        assertEquals(3, result.pairs.size)
        assertNull(result.gcContent)
    }

    @Test
    fun roundTripAllValidMultipleOfThree() {
        val result = DnaSequencer.run("ATCGATCGA")
        assertEquals(3, result.codons.size)
        assertTrue(result.trailingPartial.isEmpty())
        assertEquals(9, result.codons.sumOf { it.pairs.size })
        assertEquals(9, result.pairs.size)
        assertTrue(result.valid)
    }

    @Test
    fun ligatureFiUppercasesToStWhichContributesOneValidBase() {
        val result = DnaSequencer.run("\uFB05AAA")
        assertEquals(
            listOf(Triple('S', 0, false), Triple('T', 1, true), Triple('A', 2, true), Triple('A', 3, true), Triple('A', 4, true)),
            tuples(result.tokens),
        )
        assertEquals(0.0, result.gcContent)
        assertFalse(result.valid)
    }

    @Test
    fun pairsCarryTheSameIndicesAsTokens() {
        val result = DnaSequencer.run("aT G#")
        assertEquals(result.tokens.map { it.index }, result.pairs.map { it.index })
        assertEquals(listOf(Triple('A', 0, true), Triple('T', 1, true), Triple('G', 2, true), Triple('#', 3, false)), pairTuples(result.pairs))
    }
}
