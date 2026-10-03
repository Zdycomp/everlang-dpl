"""
Genomics module: an in-memory 11-mer index and a seed-and-score query engine for matching short sequences against a reference (pure Python; tested on synthetic data only).

Provides k-mer indexing, distributed query processing, and confidence-scored
matching across billions of base pairs.
"""

from .kmer_index import KmerIndex
from .query_engine import SequenceQueryEngine
from .reference_loader import ReferenceGenomeLoader

__all__ = ["KmerIndex", "SequenceQueryEngine", "ReferenceGenomeLoader"]
