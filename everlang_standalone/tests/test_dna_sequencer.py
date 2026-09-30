"""Tests for everlang.biocomputing.sequencer (DNA lexer/parser/sequencer)."""

import unittest

from everlang.biocomputing.sequencer import (
    VALID_BASES,
    DnaSyntaxError,
    DnaLexer,
    DnaParser,
    DnaSequencer,
)


class TestValidBases(unittest.TestCase):
    def test_valid_bases_set(self):
        self.assertEqual(VALID_BASES, frozenset("ATCG"))


class TestDnaLexer(unittest.TestCase):
    def test_cleans_via_uppercase_and_strips_whitespace(self):
        lexer = DnaLexer("at g c")
        lexer.tokenize()
        self.assertEqual(lexer.cleaned_sequence, "ATGC")

    def test_whitespace_does_not_consume_index_slot(self):
        lexer = DnaLexer("A T G")
        tokens = lexer.tokenize()
        self.assertEqual(lexer.cleaned_sequence, "ATG")
        self.assertEqual([t.index for t in tokens], [0, 1, 2])

    def test_invalid_char_keeps_its_index_and_does_not_shift_later_indices(self):
        lexer = DnaLexer("ATXCG")
        tokens = lexer.tokenize()
        self.assertEqual(lexer.cleaned_sequence, "ATXCG")
        self.assertEqual(len(tokens), 5)
        bases = [(t.base, t.index, t.valid) for t in tokens]
        self.assertEqual(
            bases,
            [
                ("A", 0, True),
                ("T", 1, True),
                ("X", 2, False),
                ("C", 3, True),
                ("G", 4, True),
            ],
        )

    def test_invalid_char_mixed_with_whitespace_keeps_index_correct(self):
        # Whitespace is stripped first (no index slot); the bad char still
        # occupies its position in the *cleaned* string.
        lexer = DnaLexer("AT G#C")
        tokens = lexer.tokenize()
        self.assertEqual(lexer.cleaned_sequence, "ATG#C")
        self.assertEqual(
            [(t.base, t.index, t.valid) for t in tokens],
            [
                ("A", 0, True),
                ("T", 1, True),
                ("G", 2, True),
                ("#", 3, False),
                ("C", 4, True),
            ],
        )

    def test_errors_returns_exactly_invalid_tokens(self):
        lexer = DnaLexer("ATXCGZ")
        lexer.tokenize()
        errors = lexer.errors()
        self.assertEqual([t.base for t in errors], ["X", "Z"])
        self.assertTrue(all(not t.valid for t in errors))

    def test_errors_empty_when_all_valid(self):
        lexer = DnaLexer("ATCG")
        lexer.tokenize()
        self.assertEqual(lexer.errors(), [])

    def test_empty_string_cleans_to_empty(self):
        lexer = DnaLexer("")
        tokens = lexer.tokenize()
        self.assertEqual(lexer.cleaned_sequence, "")
        self.assertEqual(tokens, [])

    def test_all_whitespace_cleans_to_empty(self):
        lexer = DnaLexer("   \n\t  ")
        tokens = lexer.tokenize()
        self.assertEqual(lexer.cleaned_sequence, "")
        self.assertEqual(tokens, [])


class TestDnaParser(unittest.TestCase):
    def test_watson_crick_pairing_all_bases(self):
        lexer = DnaLexer("ATCG")
        tokens = lexer.tokenize()
        parser = DnaParser(tokens)
        pairs = parser.parse()
        complements = {p.base: p.complement for p in pairs}
        self.assertEqual(complements, {"A": "T", "T": "A", "C": "G", "G": "C"})
        self.assertTrue(all(p.valid for p in pairs))

    def test_parse_raises_on_empty_token_list(self):
        parser = DnaParser([])
        with self.assertRaises(DnaSyntaxError):
            parser.parse()

    def test_invalid_token_produces_invalid_unpaired_basepair_and_parse_continues(self):
        lexer = DnaLexer("ATXCG")
        tokens = lexer.tokenize()
        parser = DnaParser(tokens)
        pairs = parser.parse()
        # parser did not abort: all 5 tokens produced a pair
        self.assertEqual(len(pairs), 5)
        bad = pairs[2]
        self.assertEqual(bad.base, "X")
        self.assertEqual(bad.index, 2)
        self.assertFalse(bad.valid)
        self.assertIsNone(bad.complement)

    def test_parse_errors_collects_invalid_tokens(self):
        lexer = DnaLexer("ATXCGZ")
        tokens = lexer.tokenize()
        parser = DnaParser(tokens)
        parser.parse()
        errs = parser.parse_errors()
        self.assertEqual([t.base for t in errs], ["X", "Z"])

    def test_codon_grouping_exact_multiple_of_three(self):
        lexer = DnaLexer("ATCGAT")  # 6 valid bases -> 2 codons
        tokens = lexer.tokenize()
        parser = DnaParser(tokens)
        parser.parse()
        codons = parser.codons()
        self.assertEqual(len(codons), 2)
        self.assertEqual(parser.trailing_partial, ())
        self.assertEqual(codons[0].start_index, 0)
        self.assertEqual(codons[1].start_index, 3)
        self.assertEqual([p.base for p in codons[0].pairs], ["A", "T", "C"])
        self.assertEqual([p.base for p in codons[1].pairs], ["G", "A", "T"])

    def test_codon_grouping_leaves_one_trailing_pair(self):
        lexer = DnaLexer("ATCGA")  # 5 bases -> 1 codon + 2 trailing
        tokens = lexer.tokenize()
        parser = DnaParser(tokens)
        parser.parse()
        self.assertEqual(len(parser.codons()), 1)
        self.assertEqual(len(parser.trailing_partial), 2)
        self.assertEqual([p.base for p in parser.trailing_partial], ["G", "A"])

    def test_codon_grouping_leaves_two_trailing_pairs(self):
        lexer = DnaLexer("ATCGATC")  # 7 bases -> 2 codons + 1 trailing
        tokens = lexer.tokenize()
        parser = DnaParser(tokens)
        parser.parse()
        self.assertEqual(len(parser.codons()), 2)
        self.assertEqual(len(parser.trailing_partial), 1)
        self.assertEqual(parser.trailing_partial[0].base, "C")

    def test_codons_include_invalid_pairs_in_original_order(self):
        # 6 tokens total (5 valid + 1 invalid) -> grouped into 2 codons of 3,
        # regardless of validity, in original positional order.
        lexer = DnaLexer("ATXCGA")
        tokens = lexer.tokenize()
        parser = DnaParser(tokens)
        parser.parse()
        codons = parser.codons()
        self.assertEqual(len(codons), 2)
        self.assertEqual(parser.trailing_partial, ())
        self.assertEqual(
            [p.base for p in codons[0].pairs], ["A", "T", "X"]
        )
        self.assertFalse(codons[0].pairs[2].valid)
        self.assertEqual(
            [p.base for p in codons[1].pairs], ["C", "G", "A"]
        )


class TestDnaSequencer(unittest.TestCase):
    def test_run_raises_on_empty_string(self):
        with self.assertRaises(DnaSyntaxError):
            DnaSequencer().run("")

    def test_run_raises_on_all_whitespace_string(self):
        with self.assertRaises(DnaSyntaxError):
            DnaSequencer().run("   \t \n ")

    def test_run_valid_true_when_no_errors(self):
        result = DnaSequencer().run("ATCGAT")
        self.assertTrue(result["valid"])
        self.assertEqual(result["lexer_errors"], [])
        self.assertEqual(result["parser_errors"], [])

    def test_run_valid_false_when_invalid_chars_present(self):
        result = DnaSequencer().run("ATXCG")
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["lexer_errors"]), 1)
        self.assertEqual(len(result["parser_errors"]), 1)

    def test_gc_content_known_value(self):
        # A T C G -> 2 of 4 valid bases are G/C -> 0.5
        result = DnaSequencer().run("ATCG")
        self.assertAlmostEqual(result["gc_content"], 0.5)

    def test_gc_content_excludes_invalid_bases(self):
        # Valid bases: A, T, C, G (4 total), of which C and G are GC -> 0.5
        # The invalid 'X' must not count toward the denominator.
        result = DnaSequencer().run("ATXCG")
        self.assertAlmostEqual(result["gc_content"], 0.5)

    def test_gc_content_none_when_zero_valid_bases_but_pairs_nonempty(self):
        result = DnaSequencer().run("XYZ")
        self.assertEqual(len(result["pairs"]), 3)
        self.assertIsNone(result["gc_content"])

    def test_round_trip_all_valid_multiple_of_three(self):
        result = DnaSequencer().run("ATCGATCGA")  # 9 bases -> 3 codons
        self.assertEqual(len(result["codons"]), 3)
        self.assertEqual(result["trailing_partial"], ())
        covered = sum(len(c.pairs) for c in result["codons"])
        self.assertEqual(covered, 9)
        self.assertEqual(len(result["pairs"]), 9)
        self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
