"""
Tests for genomics module: k-mer indexing, query engine, reference loading.
"""
import unittest
from everlang.genomics import KmerIndex, SequenceQueryEngine, ReferenceGenomeLoader
from everlang.genomics.reference_loader import GRCh38Loader


class TestKmerIndex(unittest.TestCase):
    """Test k-mer indexing and lookup."""

    def setUp(self):
        self.index = KmerIndex(kmer_size=11)

    def test_kmer_encoding_decoding(self):
        """Test k-mer quaternary encoding."""
        kmer = "ATCGATCGATC"
        encoded = KmerIndex._encode_kmer(kmer)
        self.assertIsInstance(encoded, int)
        self.assertGreaterEqual(encoded, 0)

    def test_add_and_query_sequence(self):
        """Test adding sequence and querying k-mers."""
        seq = "ATCGATCGATCGATCGATCG"
        self.index.add_sequence(seq)

        # Query a 11-mer from the sequence
        kmer = seq[0:11]
        positions = self.index.query(kmer)
        self.assertIn(0, positions)

    def test_query_nonexistent_kmer(self):
        """Test querying k-mer not in index."""
        seq = "ATCGATCGATCGATCGATCG"
        self.index.add_sequence(seq)

        # This k-mer shouldn't be in the sequence
        nonexistent = "AAAAAAAAAAAAA"[:11]
        positions = self.index.query(nonexistent)
        self.assertEqual(positions, [])

    def test_coverage_calculation(self):
        """Test k-mer coverage calculation."""
        ref_seq = "ATCGATCGATCGATCGATCGATCGATCG"
        self.index.add_sequence(ref_seq)

        # Query with identical sequence
        coverage = self.index.get_coverage(ref_seq)
        self.assertEqual(coverage, 1.0)  # 100% coverage

        # Query with partial match
        partial = "ATCGATCGATC" + "NNNNNNNNNNNNNNNNNN"
        coverage = self.index.get_coverage(partial)
        self.assertGreater(coverage, 0)
        self.assertLess(coverage, 1.0)

    def test_index_statistics(self):
        """Test index metadata and statistics."""
        seq = "ATCGATCGATCGATCGATCGATCGATCG"
        self.index.add_sequence(seq)

        stats = self.index.stats()
        self.assertGreater(stats["total_kmers_indexed"], 0)
        self.assertGreater(stats["unique_kmers"], 0)
        self.assertEqual(stats["genome_length_indexed"], len(seq))


class TestSequenceQueryEngine(unittest.TestCase):
    """Test sequence matching and confidence scoring."""

    def setUp(self):
        self.index = KmerIndex(kmer_size=11)
        self.engine = SequenceQueryEngine(self.index)

        # Add reference sequence
        self.ref_seq = "ATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG"
        self.index.add_sequence(self.ref_seq)

    def test_exact_match_query(self):
        """Test querying sequence identical to reference."""
        matches = self.engine.query(self.ref_seq, top_k=1)
        self.assertGreater(len(matches), 0)
        best_match = matches[0]
        self.assertEqual(best_match.coverage, 1.0)
        self.assertEqual(best_match.match_strength, "exact")
        self.assertGreaterEqual(best_match.confidence, 200)

    def test_partial_match_query(self):
        """Test querying partial match."""
        partial = self.ref_seq[:15]
        matches = self.engine.query(partial, top_k=1)
        self.assertGreater(len(matches), 0)
        match = matches[0]
        self.assertGreaterEqual(match.coverage, 0.7)

    def test_no_match_query(self):
        """Test querying sequence with no matches."""
        nonexistent = "A" * 100
        matches = self.engine.query(nonexistent)
        self.assertEqual(len(matches), 0)

    def test_confidence_scoring(self):
        """Test confidence score computation."""
        # Perfect match should have high confidence
        matches = self.engine.query(self.ref_seq, top_k=1)
        if matches:
            self.assertGreaterEqual(matches[0].confidence, 200)
            self.assertLessEqual(matches[0].confidence, 256)

    def test_batch_query(self):
        """Test batch querying."""
        queries = [
            self.ref_seq[:20],
            self.ref_seq[5:25],
            "AAAAAAAAAAAAAAAAAAA",
        ]

        results = self.engine.batch_query(queries)
        self.assertEqual(len(results), 3)

        # First two should have matches, third should not
        self.assertGreater(len(results[0][1]), 0)
        self.assertGreater(len(results[1][1]), 0)
        self.assertEqual(len(results[2][1]), 0)

    def test_query_statistics(self):
        """Test query engine statistics."""
        self.engine.query(self.ref_seq)
        stats = self.engine.stats()

        self.assertEqual(stats["total_queries"], 1)
        self.assertGreater(stats["total_matches_found"], 0)


class TestReferenceGenomeLoader(unittest.TestCase):
    """Test reference genome loading."""

    def test_synthetic_grch38_load(self):
        """Test loading synthetic GRCh38 data."""
        loader = ReferenceGenomeLoader()
        loader.load_synthetic_grch38(size_bp=50_000)

        stats = loader.stats()
        self.assertEqual(len(stats["chromosomes_loaded"]), 1)
        self.assertEqual(stats["total_genome_length"], 50_000)

    def test_grch38_chromosome_load(self):
        """Test loading specific GRCh38 chromosome."""
        loader = GRCh38Loader()
        loader.load_grch38_chromosome("chr1")

        stats = loader.stats()
        self.assertIn("chr1", stats["chromosomes_loaded"])

    def test_grch38_subset_load(self):
        """Test loading subset of GRCh38."""
        loader = GRCh38Loader()
        loader.load_grch38_subset(chromosomes=["chr1", "chr2"], max_bp_per_chr=10_000)

        stats = loader.stats()
        self.assertEqual(len(stats["chromosomes_loaded"]), 2)
        self.assertIn("chr1", stats["chromosomes_loaded"])
        self.assertIn("chr2", stats["chromosomes_loaded"])

    def test_index_retrieval(self):
        """Test getting index from loader."""
        loader = ReferenceGenomeLoader()
        loader.load_synthetic_grch38(size_bp=10_000)

        index = loader.get_index()
        self.assertIsInstance(index, KmerIndex)
        self.assertGreater(index.total_kmers, 0)


if __name__ == "__main__":
    unittest.main()
