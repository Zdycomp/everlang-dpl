#!/usr/bin/env python3
"""
K-mer sequence matching demo on a SYNTHETIC reference.

The reference is random A/C/G/T generated here with a fixed seed. It is not real
human sequence, and nothing is downloaded: the file keeps its original name only
so existing links and docs still resolve.

Measures, for the pure-Python KmerIndex + SequenceQueryEngine:
- index build time and memory per unique 11-mer
- query throughput
- whether the top hit lands on the true locus, for exact and mutated queries

Usage:
  python3 benchmarks/grch38_realtime_demo.py
"""
import os
import random
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from everlang.genomics.query_engine import SequenceQueryEngine
from everlang.genomics.reference_loader import ReferenceGenomeLoader

SEED = 7
RECORDS = {"synthA": 100_000, "synthB": 100_000, "synthC": 100_000, "synthD": 100_000}
QUERIES_PER_CASE = 300
QUERY_LENGTH = 60
MIN_COVERAGE = 0.5


def make_reference(rng):
    return {name: "".join(rng.choice("ACGT") for _ in range(size)) for name, size in RECORDS.items()}


def make_queries(rng, reference, count, mismatches):
    """(sequence, (record, offset)) pairs sampled from the reference, with `mismatches` substitutions."""
    queries = []
    names = list(reference)
    for _ in range(count):
        name = rng.choice(names)
        start = rng.randrange(0, len(reference[name]) - QUERY_LENGTH)
        seq = list(reference[name][start:start + QUERY_LENGTH])
        for i in rng.sample(range(QUERY_LENGTH), mismatches):
            seq[i] = rng.choice([b for b in "ACGT" if b != seq[i]])
        queries.append(("".join(seq), (name, start)))
    return queries


def main():
    rng = random.Random(SEED)
    reference = make_reference(rng)
    total_bp = sum(len(s) for s in reference.values())

    print("=" * 78)
    print("  K-MER SEQUENCE MATCHING DEMO (SYNTHETIC RANDOM REFERENCE)")
    print("=" * 78)

    with tempfile.NamedTemporaryFile("w", suffix=".fa", delete=False) as handle:
        for name, seq in reference.items():
            handle.write(f">{name}\n{seq}\n")
        fasta = handle.name
    try:
        loader = ReferenceGenomeLoader()
        tracemalloc.start()
        start = time.perf_counter()
        loader.load_fasta(fasta)
        build_seconds = time.perf_counter() - start
        peak_bytes = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    finally:
        os.unlink(fasta)

    index = loader.get_index()
    unique = loader.stats()["index_stats"]["unique_kmers"]
    print(f"\nReference: {len(reference)} random records, {total_bp:,} bp (seed {SEED})")
    print(f"Index build: {build_seconds:.1f} s ({total_bp / build_seconds / 1000:,.0f} kbp/s), "
          f"{unique:,} unique 11-mers, peak {peak_bytes / 1e6:.0f} MB "
          f"(~{peak_bytes / unique:.0f} bytes per unique 11-mer)")

    engine = SequenceQueryEngine(index)
    print(f"\nQueries: {QUERY_LENGTH} bp sampled from the reference, min_coverage={MIN_COVERAGE}")
    print(f"\n{'mismatches':>10} {'queries/s':>10} {'any hit':>9} {'top hit at true locus':>22}")
    for mismatches in (0, 1, 2, 4):
        queries = make_queries(rng, reference, QUERIES_PER_CASE, mismatches)
        start = time.perf_counter()
        results = [engine.query(seq, top_k=1, min_coverage=MIN_COVERAGE) for seq, _ in queries]
        elapsed = time.perf_counter() - start
        hit = sum(1 for r in results if r)
        correct = 0
        for (_, (name, offset)), r in zip(queries, results):
            if r and loader.resolve(r[0].reference_position) == (name, offset):
                correct += 1
        print(f"{mismatches:>10} {len(queries) / elapsed:>10,.0f} {hit / len(queries):>8.0%} "
              f"{correct / len(queries):>21.0%}")

    print("\nWhat this does and does not show:")
    print("- Correctness on random sequence only. Real genomes are repetitive, which makes seed hits")
    print("  far less specific; none of that is exercised here.")
    print("- Memory and build time grow with reference size. At the rate measured above a")
    print(f"  3.2 Gbp genome would need roughly {3.2e9 / total_bp * peak_bytes / 1e9:,.0f} GB and a very long build in this")
    print("  pure-Python index, so it is not a full-genome tool. BWA, minimap2 and similar aligners")
    print("  index a human genome in a few GB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
