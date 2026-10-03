"""
Sequence query engine: Match sequences against reference genome with confidence scoring.

Uses k-mer matching to find candidate positions, then scores matches based on:
- K-mer coverage (fraction of query k-mers that match)
- Match density (matches per reference region)
- EParticle confidence (0-256 scale based on match quality)
"""
from typing import List, Dict, Tuple
from dataclasses import dataclass
from .kmer_index import KmerIndex


@dataclass
class SequenceMatch:
    """Result of a single sequence match."""
    query_sequence: str
    reference_position: int
    kmer_matches: int
    coverage: float
    confidence: int
    match_strength: str  # "exact", "high", "medium", "low"


class SequenceQueryEngine:
    """Real-time sequence matching engine with confidence scoring."""

    def __init__(self, kmer_index: KmerIndex):
        """
        Initialize query engine with a pre-built k-mer index.

        Args:
            kmer_index: KmerIndex containing reference genome
        """
        self.index = kmer_index
        self.query_count = 0
        self.match_count = 0

    def query(self, sequence: str, top_k: int = 10, min_coverage: float = 0.7) -> List[SequenceMatch]:
        """
        Query sequence against reference genome.

        Args:
            sequence: Query DNA sequence
            top_k: Return top K matches (sorted by confidence)
            min_coverage: Minimum k-mer coverage threshold (0.0-1.0)

        Returns:
            List of SequenceMatch results, sorted by confidence (descending)
        """
        self.query_count += 1
        seq = sequence.upper()

        # Get all k-mer matches
        kmer_matches = self.index.query_all_kmers(seq)

        if not kmer_matches:
            return []

        # Group matches by reference position
        position_hits: Dict[int, int] = {}

        for kmer, positions in kmer_matches.items():
            for pos in positions:
                # Key insight: if k-mer matches at position, the query likely
                # starts at (pos - offset_in_query)
                for offset in range(len(seq) - self.index.kmer_size + 1):
                    if seq[offset : offset + self.index.kmer_size] == kmer:
                        ref_start = pos - offset
                        if ref_start >= 0:
                            position_hits[ref_start] = position_hits.get(ref_start, 0) + 1

        if not position_hits:
            return []

        # Score each position
        matches = []
        coverage = self.index.get_coverage(seq)

        for ref_pos, hit_count in position_hits.items():
            if coverage < min_coverage:
                continue

            confidence = self._compute_confidence(
                coverage=coverage,
                hit_count=hit_count,
                kmer_count=len(kmer_matches),
            )

            strength = self._classify_match(coverage)

            match = SequenceMatch(
                query_sequence=seq,
                reference_position=ref_pos,
                kmer_matches=hit_count,
                coverage=coverage,
                confidence=confidence,
                match_strength=strength,
            )
            matches.append(match)
            self.match_count += 1

        # Sort by confidence (descending)
        matches.sort(key=lambda m: m.confidence, reverse=True)

        return matches[:top_k]

    def _compute_confidence(self, coverage: float, hit_count: int, kmer_count: int) -> int:
        """
        Compute confidence score (0-256) from match quality metrics.

        Formula:
          confidence = min(256, 128 + (coverage * 100) + min(50, hit_count * 2))

        This matches EParticle's confidence scale and the self-healing repair formula
        used elsewhere in Everlang.
        """
        base = int(128 + (coverage * 100))  # 128-228 from coverage
        bonus = min(50, hit_count * 2)      # 0-50 from hit density
        confidence = min(256, base + bonus)
        return max(0, confidence)

    def _classify_match(self, coverage: float) -> str:
        """Classify match strength by coverage."""
        if coverage >= 0.95:
            return "exact"
        elif coverage >= 0.85:
            return "high"
        elif coverage >= 0.70:
            return "medium"
        else:
            return "low"

    def batch_query(
        self,
        sequences: List[str],
        top_k: int = 10,
        min_coverage: float = 0.7,
    ) -> List[Tuple[str, List[SequenceMatch]]]:
        """
        Query multiple sequences in batch.

        Args:
            sequences: List of query sequences
            top_k: Top K results per sequence
            min_coverage: Minimum coverage threshold

        Returns:
            List of (sequence, matches) tuples
        """
        results = []
        for seq in sequences:
            matches = self.query(seq, top_k, min_coverage)
            results.append((seq, matches))
        return results

    def stats(self) -> Dict:
        """Return query statistics."""
        return {
            "total_queries": self.query_count,
            "total_matches_found": self.match_count,
            "avg_matches_per_query": (
                self.match_count / self.query_count if self.query_count > 0 else 0
            ),
            "index_stats": self.index.stats(),
        }
