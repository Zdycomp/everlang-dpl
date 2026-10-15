"""Tests for everlang.biocomputing.binary_sequencer (binary-backed DNA sequencer)."""

import unittest

from everlang.biocomputing.binary_sequencer import BinarySequencer


class TestBinarySequencerEncoding(unittest.TestCase):
    def setUp(self):
        self.seq = BinarySequencer()

    def test_known_byte_vector(self):
        # 0x1B = 00 01 10 11 -> A T C G (2 bits per base, MSB first)
        result = self.seq.sequence(bytes([0x1B]))
        self.assertEqual(result["dna"], "ATCG")

    def test_all_zero_and_all_one_bytes(self):
        self.assertEqual(self.seq.sequence(bytes([0x00]))["dna"], "AAAA")
        self.assertEqual(self.seq.sequence(bytes([0xFF]))["dna"], "GGGG")

    def test_one_byte_is_four_bases(self):
        result = self.seq.sequence(bytes(range(10)))
        self.assertEqual(len(result["dna"]), 10 * 4)
        self.assertEqual(result["byte_count"], 10)

    def test_empty_input_yields_empty_strand(self):
        result = self.seq.sequence(b"")
        self.assertEqual(result["dna"], "")
        self.assertEqual(result["codons"], [])
        self.assertIsNone(result["gc_content"])
        self.assertTrue(result["round_trip"])

    def test_gc_content_for_all_ones_is_one(self):
        self.assertEqual(self.seq.sequence(bytes([0xFF]))["gc_content"], 1.0)

    def test_codons_group_sixteen_bases_from_four_bytes(self):
        result = self.seq.sequence(bytes([1, 2, 3, 4]))
        self.assertEqual(len(result["codons"]), 5)
        self.assertEqual(len(result["trailing_partial"]), 1)


class TestBinarySequencerRoundTrip(unittest.TestCase):
    def setUp(self):
        self.seq = BinarySequencer()

    def test_round_trip_every_byte_value(self):
        data = bytes(range(256))
        result = self.seq.sequence(data)
        self.assertTrue(result["round_trip"])
        self.assertEqual(self.seq.decode(result["dna"]), data)

    def test_decode_rejects_non_atcg(self):
        with self.assertRaises(ValueError):
            self.seq.decode("ATXG")

    def test_decode_empty_strand_is_empty_bytes(self):
        self.assertEqual(self.seq.decode(""), b"")
        self.assertEqual(self.seq.decode("  \n"), b"")

    def test_decode_accepts_lowercase_and_whitespace(self):
        self.assertEqual(self.seq.decode("at cg\n"), bytes([0x1B]))

    def test_decode_rejects_partial_byte(self):
        with self.assertRaises(ValueError):
            self.seq.decode("ATC")


class TestBinarySequencerAffinity(unittest.TestCase):
    def setUp(self):
        self.seq = BinarySequencer()

    def test_complementary_gate_is_full_affinity(self):
        # Complement of ATCG (Watson-Crick, base by base) is TAGC
        self.assertEqual(self.seq.affinity("ATCG", "TAGC"), 256)

    def test_mismatched_gate_lowers_affinity(self):
        self.assertLess(self.seq.affinity("ATCG", "AAAA"), 256)


if __name__ == "__main__":
    unittest.main()
