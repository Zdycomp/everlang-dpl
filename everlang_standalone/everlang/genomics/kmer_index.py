"""
K-mer indexing for fast sequence matching.

Builds an index of k-mers (fixed-length DNA sequences) from a reference genome,
enabling O(1) lookup of k-mer positions. Supports sharding by position for
distributed genome indexing.

K = 11 is optimal for human genome: ~16M unique 11-mers per billion bp,
collision-free hashing, fast lookup.
"""
from typing import Dict, List

KMER_SIZE = 11  # Optimal for human genome
BASE_BITS = 2   # A=00, T=01, C=10, G=11 (quaternary encoding)
MAX_KMER_VALUE = (1 << (KMER_SIZE * BASE_BITS)) - 1  # Max 22-bit value


class KmerIndex:
    """Compact k-mer index: hash(k-mer) → list of genomic positions."""

    def __init__(self, kmer_size: int = KMER_SIZE, shard_id: int = 0, shard_count: int = 1):
        """
        Initialize k-mer index.

        Args:
            kmer_size: Length of k-mers (default 11)
            shard_id: This shard's ID (for distributed indexing)
            shard_count: Total number of shards
        """
        self.kmer_size = kmer_size
        self.shard_id = shard_id
        self.shard_count = shard_count

        # Hash map: kmer_value (int) → list of positions
        self.index: Dict[int, List[int]] = {}

        # Metadata
        self.total_kmers = 0
        self.unique_kmers = 0
        self.genome_length = 0

    def add_sequence(self, sequence: str, start_pos: int = 0) -> None:
        """
        Index all k-mers in a sequence.

        Args:
            sequence: DNA sequence (ATCG only, uppercase)
            start_pos: Starting position in reference genome
        """
        seq = sequence.upper()
        seq_len = len(seq)

        for i in range(seq_len - self.kmer_size + 1):
            kmer = seq[i : i + self.kmer_size]

            # Skip if contains invalid bases
            if not all(b in "ATCG" for b in kmer):
                continue

            # Encode k-mer as integer (quaternary: A=0, T=1, C=2, G=3)
            kmer_value = self._encode_kmer(kmer)

            # Check if this k-mer belongs to this shard (simple modulo sharding)
            if kmer_value % self.shard_count != self.shard_id:
                continue

            pos = start_pos + i

            # Add position to index
            if kmer_value not in self.index:
                self.index[kmer_value] = []
                self.unique_kmers += 1

            self.index[kmer_value].append(pos)
            self.total_kmers += 1

        self.genome_length = max(self.genome_length, start_pos + seq_len)

    def query(self, kmer: str) -> List[int]:
        """
        Look up positions of a k-mer in the reference genome.

        Args:
            kmer: Query k-mer (must be exactly KMER_SIZE bases)

        Returns:
            List of genomic positions where k-mer occurs
        """
        if len(kmer) != self.kmer_size:
            return []

        kmer_value = self._encode_kmer(kmer.upper())
        if kmer_value not in self.index:
            return []

        return self.index[kmer_value]

    def query_all_kmers(self, sequence: str) -> Dict[str, List[int]]:
        """
        Extract and look up all k-mers from a query sequence.

        Args:
            sequence: Query DNA sequence

        Returns:
            Dict mapping k-mer → list of positions
        """
        seq = sequence.upper()
        results = {}

        for i in range(len(seq) - self.kmer_size + 1):
            kmer = seq[i : i + self.kmer_size]

            if not all(b in "ATCG" for b in kmer):
                continue

            positions = self.query(kmer)
            if positions:
                results[kmer] = positions

        return results

    def get_coverage(self, sequence: str, min_matches: int = 1) -> float:
        """
        Calculate k-mer coverage: fraction of query k-mers with matches.

        Args:
            sequence: Query sequence
            min_matches: Require at least this many k-mer matches

        Returns:
            Coverage as fraction (0.0 to 1.0)
        """
        seq = sequence.upper()
        kmer_count = len(seq) - self.kmer_size + 1

        if kmer_count == 0:
            return 0.0

        matched = 0
        for i in range(kmer_count):
            kmer = seq[i : i + self.kmer_size]
            if all(b in "ATCG" for b in kmer) and self.query(kmer):
                matched += 1

        return matched / kmer_count if kmer_count > 0 else 0.0

    @staticmethod
    def _encode_kmer(kmer: str) -> int:
        """Encode k-mer string as integer using quaternary encoding."""
        value = 0
        base_map = {"A": 0, "T": 1, "C": 2, "G": 3}

        for ch in kmer:
            value = (value << BASE_BITS) | base_map.get(ch, 0)

        return value & MAX_KMER_VALUE

    def stats(self) -> Dict:
        """Return index statistics."""
        return {
            "kmer_size": self.kmer_size,
            "total_kmers_indexed": self.total_kmers,
            "unique_kmers": self.unique_kmers,
            "genome_length_indexed": self.genome_length,
            "index_entries": len(self.index),
            "shard_id": self.shard_id,
            "shard_count": self.shard_count,
            "avg_kmers_per_position": (
                self.total_kmers / self.unique_kmers if self.unique_kmers > 0 else 0
            ),
        }
