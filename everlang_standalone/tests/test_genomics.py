"""
Tests for genomics module: k-mer indexing, query engine, reference loading.
"""
import os
import tempfile
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

    def test_fastq_loading(self):
        """Test loading sequences from FASTQ format."""
        import tempfile

        # Create a temporary FASTQ file
        fastq_data = """@read1 description
ATCGATCGATCG
+read1
IIIIIIIIIIII
@read2 description
GCTAGCTAGCTA
+read2
IIIIIIIIIIII
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fastq', delete=False) as f:
            f.write(fastq_data)
            fastq_path = f.name

        try:
            loader = ReferenceGenomeLoader()
            loader.load_fastq(fastq_path)

            stats = loader.stats()
            self.assertEqual(len(stats['chromosomes_loaded']), 2)
            self.assertIn('read1', stats['chromosomes_loaded'])
            self.assertIn('read2', stats['chromosomes_loaded'])
        finally:
            import os
            os.unlink(fastq_path)

    def test_fastq_with_max_bp(self):
        """Test FASTQ loading with base pair limit."""
        import tempfile

        # Create a temporary FASTQ file
        fastq_data = """@read1
ATCGATCGATCGATCGATCG
+read1
IIIIIIIIIIIIIIIIIIII
@read2
GCTAGCTAGCTAGCTAGCTA
+read2
IIIIIIIIIIIIIIIIIIII
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fastq', delete=False) as f:
            f.write(fastq_data)
            fastq_path = f.name

        try:
            loader = ReferenceGenomeLoader()
            loader.load_fastq(fastq_path, max_bp=25)  # Load only ~25 bp

            stats = loader.stats()
            total_bp = stats['total_genome_length']
            self.assertLessEqual(total_bp, 25 + 20)  # Allow for one full read beyond limit
        finally:
            import os
            os.unlink(fastq_path)

    def test_fastq_invalid_format(self):
        """Test FASTQ loading with invalid format."""
        import tempfile

        # Create an invalid FASTQ file (invalid + line without +)
        invalid_data = "@read1\nATCGATCG\ninvalid\nIIIIIIII\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fastq', delete=False) as f:
            f.write(invalid_data)
            fastq_path = f.name

        try:
            loader = ReferenceGenomeLoader()
            with self.assertRaises(ValueError):
                loader.load_fastq(fastq_path)
        finally:
            import os
            os.unlink(fastq_path)


if __name__ == "__main__":
    unittest.main()


class TestRecordCoordinates(unittest.TestCase):
    """Each loaded record gets its own range in one global coordinate space."""

    def _fasta(self, records):
        handle = tempfile.NamedTemporaryFile("w", suffix=".fa", delete=False)
        self.addCleanup(os.unlink, handle.name)
        for name, seq in records:
            handle.write(f">{name}\n{seq}\n")
        handle.close()
        return handle.name

    def test_identical_records_do_not_share_positions(self):
        seq = "ATCGGCTAGCTAGGCTAACGT"
        loader = ReferenceGenomeLoader()
        loader.load_fasta(self._fasta([("chrA", seq), ("chrB", seq)]))
        kmer = seq[:11]
        positions = sorted(loader.get_index().query(kmer))
        self.assertEqual(positions, [0, len(seq)])
        self.assertEqual(loader.resolve(positions[0]), ("chrA", 0))
        self.assertEqual(loader.resolve(positions[1]), ("chrB", 0))
        self.assertEqual(loader.record_offset("chrB"), len(seq))

    def test_resolve_rejects_positions_outside_records(self):
        loader = ReferenceGenomeLoader()
        loader.load_fasta(self._fasta([("chrA", "ATCGATCGATCGAT")]))
        with self.assertRaises(ValueError):
            loader.resolve(14)
        with self.assertRaises(ValueError):
            loader.resolve(-1)

    def test_query_hits_from_different_chromosomes_stay_separate(self):
        seq = "GATTACAGATTACAGATTACACCGT"
        loader = ReferenceGenomeLoader()
        loader.load_fasta(self._fasta([("chrA", seq), ("chrB", seq)]))
        matches = SequenceQueryEngine(loader.get_index()).query(seq, top_k=10, min_coverage=0.5)
        resolved = {loader.resolve(m.reference_position) for m in matches}
        self.assertIn(("chrA", 0), resolved)
        self.assertIn(("chrB", 0), resolved)

    def test_subset_honours_max_bp_per_chr(self):
        loader = GRCh38Loader()
        loader.load_grch38_subset(chromosomes=["chr1", "chr2"], max_bp_per_chr=5_000)
        self.assertEqual(loader.chromosomes, {"chr1": 5_000, "chr2": 5_000})
        self.assertEqual(loader.resolve(5_000), ("chr2", 0))

    def test_coverage_of_query_shorter_than_k_is_zero(self):
        index = KmerIndex()
        index.add_sequence("ATCGATCGATCGATCG")
        self.assertEqual(index.get_coverage("ATCG"), 0.0)
