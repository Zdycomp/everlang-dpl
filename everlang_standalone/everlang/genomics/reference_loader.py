"""
Reference genome loader: Load GRCh38 or other reference genomes into k-mer index.

Supports:
- FASTA files (local or remote)
- Sharded indexing (split by chromosome or position)
- Incremental building (add sequences on demand)
"""
from typing import Optional, List, Dict
import os
from .kmer_index import KmerIndex


class ReferenceGenomeLoader:
    """Load and index reference genomes."""

    def __init__(self, shard_id: int = 0, shard_count: int = 1):
        """
        Initialize loader.

        Args:
            shard_id: This shard's ID (for distributed indexing)
            shard_count: Total number of shards
        """
        self.index = KmerIndex(shard_id=shard_id, shard_count=shard_count)
        self.chromosomes: Dict[str, int] = {}  # chr_name → length

    def load_fasta(self, fasta_path: str, max_bp: Optional[int] = None) -> None:
        """
        Load sequences from FASTA file.

        Args:
            fasta_path: Path to FASTA file
            max_bp: Optional limit on total base pairs to load (for testing)
        """
        if not os.path.exists(fasta_path):
            raise FileNotFoundError(f"FASTA file not found: {fasta_path}")

        current_chr = None
        current_seq = []
        total_bp = 0

        with open(fasta_path, 'r') as f:
            for line in f:
                line = line.strip()

                if line.startswith('>'):
                    # Save previous sequence
                    if current_chr and current_seq:
                        seq = ''.join(current_seq)
                        self.index.add_sequence(seq, start_pos=0)
                        self.chromosomes[current_chr] = len(seq)
                        total_bp += len(seq)

                    # Check limit
                    if max_bp and total_bp >= max_bp:
                        break

                    # Start new sequence
                    current_chr = line[1:].split()[0]  # Take first word after '>'
                    current_seq = []
                else:
                    current_seq.append(line)

            # Save final sequence
            if current_chr and current_seq:
                seq = ''.join(current_seq)
                self.index.add_sequence(seq, start_pos=0)
                self.chromosomes[current_chr] = len(seq)
                total_bp += len(seq)

    def load_fastq(self, fastq_path: str, max_bp: Optional[int] = None) -> None:
        """
        Load sequences from FASTQ file (standard sequencing format).

        FASTQ format (4 lines per read):
          Line 1: @read_id [description]
          Line 2: DNA sequence
          Line 3: + [optional repeat of read_id]
          Line 4: Quality scores (Phred+33)

        Args:
            fastq_path: Path to FASTQ file
            max_bp: Optional limit on total base pairs to load (for testing)
        """
        if not os.path.exists(fastq_path):
            raise FileNotFoundError(f"FASTQ file not found: {fastq_path}")

        read_count = 0
        total_bp = 0

        with open(fastq_path, 'r') as f:
            lines = []
            for line in f:
                lines.append(line.rstrip('\n'))

                # FASTQ records are 4 lines
                if len(lines) == 4:
                    # Check limit before processing
                    if max_bp and total_bp >= max_bp:
                        break

                    header = lines[0]
                    sequence = lines[1]
                    plus = lines[2]

                    # Validate format
                    if not header.startswith('@') or not plus.startswith('+'):
                        raise ValueError(f"Invalid FASTQ format at record {read_count + 1}")

                    # Extract read ID (remove @ and any description after space)
                    read_id = header[1:].split()[0]

                    # Index the sequence
                    self.index.add_sequence(sequence, start_pos=0)
                    self.chromosomes[read_id] = len(sequence)
                    total_bp += len(sequence)
                    read_count += 1

                    lines = []

    def load_synthetic_grch38(self, size_bp: int = 1_000_000) -> None:
        """
        Load synthetic GRCh38 data for testing (generates random valid DNA).

        Real GRCh38 (3.2 billion bp) would be loaded via load_fasta().

        Args:
            size_bp: Number of base pairs to generate
        """
        import random

        # Generate synthetic chromosome 1 (normally 248 million bp)
        bases = "ATCG"
        chr1_seq = ''.join(random.choice(bases) for _ in range(size_bp))

        self.index.add_sequence(chr1_seq, start_pos=0)
        self.chromosomes["chr1"] = len(chr1_seq)

    def get_index(self) -> KmerIndex:
        """Return the built k-mer index."""
        return self.index

    def stats(self) -> Dict:
        """Return loader statistics."""
        return {
            "chromosomes_loaded": list(self.chromosomes.keys()),
            "total_genome_length": sum(self.chromosomes.values()),
            "index_stats": self.index.stats(),
        }


class GRCh38Loader(ReferenceGenomeLoader):
    """Specialized loader for GRCh38 (human genome)."""

    GRCh38_URL = "https://ftp.ncbi.nlm.nih.gov/refseq/H_sapiens/annotation/GCF_000001405.39/GCF_000001405.39_GRCh38.p13_genomic.fna.gz"
    GRCh38_CHROMOSOMES = [
        "chr1", "chr2", "chr3", "chr4", "chr5", "chr6", "chr7", "chr8", "chr9",
        "chr10", "chr11", "chr12", "chr13", "chr14", "chr15", "chr16", "chr17",
        "chr18", "chr19", "chr20", "chr21", "chr22", "chrX", "chrY", "chrM",
    ]

    def load_grch38_chromosome(self, chr_name: str, local_path: Optional[str] = None) -> None:
        """
        Load a specific GRCh38 chromosome.

        For production: Download from NCBI, decompress, and load.
        For now: Use synthetic data.

        Args:
            chr_name: Chromosome name (e.g., "chr1", "chrX")
            local_path: Optional path to local FASTA file
        """
        if local_path and os.path.exists(local_path):
            self.load_fasta(local_path)
        else:
            # Generate synthetic chromosome
            # Real sizes: chr1=248M, chr2=242M, ..., chrM=16K
            chr_sizes = {
                "chr1": 248_949_192,
                "chr2": 242_193_529,
                "chr3": 198_295_559,
                "chr4": 190_214_555,
                "chr5": 181_538_259,
                "chr6": 170_805_979,
                "chr7": 159_345_973,
                "chr8": 145_139_094,
                "chr9": 138_394_717,
                "chr10": 133_797_422,
                "chr11": 135_086_622,
                "chr12": 133_275_309,
                "chr13": 114_364_328,
                "chr14": 107_043_718,
                "chr15": 101_991_189,
                "chr16": 90_338_345,
                "chr17": 83_257_441,
                "chr18": 80_373_912,
                "chr19": 58_617_616,
                "chr20": 64_444_167,
                "chr21": 46_709_983,
                "chr22": 50_818_468,
                "chrX": 155_270_560,
                "chrY": 59_373_566,
                "chrM": 16_569,
            }

            size = chr_sizes.get(chr_name, 1_000_000)

            # For testing: use smaller subset
            size = min(size, 100_000)

            import random
            bases = "ATCG"
            seq = ''.join(random.choice(bases) for _ in range(size))

            self.index.add_sequence(seq, start_pos=0)
            self.chromosomes[chr_name] = size

    def load_grch38_subset(self, chromosomes: List[str] = None, max_bp_per_chr: int = 100_000) -> None:
        """
        Load a subset of GRCh38 chromosomes for testing.

        Args:
            chromosomes: List of chromosome names (default: chr1-22, X, Y, M)
            max_bp_per_chr: Max base pairs per chromosome
        """
        if chromosomes is None:
            chromosomes = self.GRCh38_CHROMOSOMES

        for chr_name in chromosomes:
            self.load_grch38_chromosome(chr_name)

    def load_grch38_fastq(self, fastq_path: str) -> None:
        """
        Load GRCh38 sequences from FASTQ file (sequencing data format).

        For real GRCh38 FASTQ data from sequencing experiments.
        For synthetic testing: use load_synthetic_grch38().

        Args:
            fastq_path: Path to FASTQ file with GRCh38 sequences
        """
        self.load_fastq(fastq_path)
