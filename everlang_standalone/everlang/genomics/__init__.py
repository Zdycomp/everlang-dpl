"""
Genomics module: Real-time sequence matching against reference genomes.

Provides k-mer indexing, distributed query processing, and confidence-scored
matching across billions of base pairs.
"""

from .kmer_index import KmerIndex
from .query_engine import SequenceQueryEngine
from .reference_loader import ReferenceGenomeLoader

__all__ = ["KmerIndex", "SequenceQueryEngine", "ReferenceGenomeLoader"]
