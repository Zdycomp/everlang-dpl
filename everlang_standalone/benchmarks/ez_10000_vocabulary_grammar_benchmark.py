"""
10,000-word volume benchmark across the DPL ("Dynamic Phase Language")
four-stage pipeline, the DNA lexer/parser/sequencer, and the six-language
SuperTranspiler generator.

This does not invent new grammar or vocabulary for Everlang/DPL -- there is
no SEMANTICS.md and no textual Everlang parser. It generates 10,000
synthetic "words" (random identifiers/values/DNA sequences) and quantifies
how the EXISTING lexer (DnaLexer), parser (DnaParser), sequencer
(DnaSequencer), generator (SuperTranspiler), and the 4-stage EZPipeline
(EXAMINE -> EVALUATE -> EXECUTE -> ARCHIVE, the actual "quad-phase" in
Dynamic Phase Language) behave at volume -- the same pattern as the
existing ez_300_code_healing_benchmark.py and ez_cpu_stress_test.py, just
sized up by roughly 33x (300 -> 10,000) and widened to cover the sequencer
and transpiler modules those two benchmarks predate.
"""
import os
import random
import string
import sys
import time
from collections import Counter

# Ensure the package root (parent of the benchmarks/ dir) is importable,
# regardless of the current working directory the script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from everlang.core.particle import EParticle
from everlang.pipeline import EZPipeline
from everlang.biocomputing.sequencer import DnaSequencer, DnaSyntaxError
from everlang.transpiler import SuperTranspiler

WORD_COUNT = 10_000
DNA_BASES = "ATCG"
INVALID_CHARS = "XYZ#@!"
TYPE_SPECS = ["String", "Int", "float", "BigDecimal", "bool", "ByteArray"]
PIPELINE_LANGUAGES = [
    "Python", "JavaScript", "TypeScript", "Rust", "Clang_C",
    "C++", "Go", "Java", "Kotlin", "Swift",
]
PIPELINE_SAMPLE_SNIPPETS = [
    "def calculate_total(items): return sum(items)",
    "val x: String? = null",  # syntax drift -> EMULATED_REPAIR
    "void* ptr = NULL; *ptr = 0xDEADBEEF;",  # memory hazard -> QUARANTINED_Z
]


def _random_word(rng: random.Random, length: int) -> str:
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(length))


def _random_dna(rng: random.Random, length: int, invalid_rate: float) -> str:
    chars = []
    for _ in range(length):
        if rng.random() < invalid_rate:
            chars.append(rng.choice(INVALID_CHARS))
        else:
            chars.append(rng.choice(DNA_BASES))
    return "".join(chars)


def run_sequencer_volume(rng: random.Random, word_count: int) -> dict:
    sequencer = DnaSequencer()
    stats = Counter()
    total_codons = 0
    total_trailing = 0
    gc_contents = []
    start = time.perf_counter()

    for i in range(word_count):
        length = rng.randint(4, 64)
        # 1 in 5 words gets some invalid characters injected, exercising the
        # lexer's error-token path; 1 in 1000 is empty, exercising DnaSyntaxError.
        if i % 1000 == 0:
            seq = ""
        else:
            invalid_rate = 0.15 if i % 5 == 0 else 0.0
            seq = _random_dna(rng, length, invalid_rate)

        try:
            result = sequencer.run(seq)
        except DnaSyntaxError:
            stats["syntax_error"] += 1
            continue

        stats["valid" if result["valid"] else "invalid"] += 1
        total_codons += len(result["codons"])
        total_trailing += len(result["trailing_partial"])
        if result["gc_content"] is not None:
            gc_contents.append(result["gc_content"])

    elapsed = time.perf_counter() - start
    return {
        "elapsed_sec": elapsed,
        "words_per_sec": word_count / elapsed if elapsed > 0 else float("inf"),
        "valid": stats["valid"],
        "invalid": stats["invalid"],
        "syntax_errors": stats["syntax_error"],
        "total_codons": total_codons,
        "total_trailing_partial": total_trailing,
        "avg_gc_content": sum(gc_contents) / len(gc_contents) if gc_contents else None,
    }


def run_transpiler_volume(rng: random.Random, word_count: int) -> dict:
    transpiler = SuperTranspiler()
    per_language_chars = Counter()
    start = time.perf_counter()

    for i in range(word_count):
        name = _random_word(rng, rng.randint(3, 12))
        val = _random_word(rng, rng.randint(1, 20))
        type_spec = rng.choice(TYPE_SPECS)
        conf = rng.randint(0, 256)
        rendered = transpiler.transpile(name, val, type_spec, conf)
        for lang, code in rendered.items():
            per_language_chars[lang] += len(code)

    elapsed = time.perf_counter() - start
    total_renderings = word_count * len(transpiler.templates)
    return {
        "elapsed_sec": elapsed,
        "words_per_sec": word_count / elapsed if elapsed > 0 else float("inf"),
        "total_renderings": total_renderings,
        "renderings_per_sec": total_renderings / elapsed if elapsed > 0 else float("inf"),
        "per_language_chars": dict(per_language_chars),
    }


def run_pipeline_sample(rng: random.Random, sample_size: int) -> dict:
    """The full 4-stage DPL pipeline (EXAMINE -> EVALUATE -> EXECUTE -> ARCHIVE)
    is the most expensive of the four components exercised here, so it's run
    over a representative sample rather than the full 10,000 -- same
    trade-off ez_300_code_healing_benchmark.py already makes at smaller scale."""
    pipeline = EZPipeline()
    rule_particle = EParticle("VolumeBenchmarkRule", 230)
    stats = Counter()
    start = time.perf_counter()

    for i in range(sample_size):
        lang = PIPELINE_LANGUAGES[i % len(PIPELINE_LANGUAGES)]
        code = PIPELINE_SAMPLE_SNIPPETS[i % len(PIPELINE_SAMPLE_SNIPPETS)]
        result = pipeline.run(f"VOL_{i:05d}", code, lang, rule_particle)
        stats[result["examine_status"]] += 1

    elapsed = time.perf_counter() - start
    return {
        "elapsed_sec": elapsed,
        "sample_size": sample_size,
        "by_examine_status": dict(stats),
        "archive_boundary_markers": len(pipeline.archive.boundary_markers),
    }


def run_10000_word_benchmark():
    rng = random.Random(0)  # deterministic across runs

    print("=" * 80)
    print("  10,000-WORD VOLUME BENCHMARK: LEXER / PARSER / SEQUENCER / GENERATOR")
    print("  (Dynamic Phase Language: EXAMINE -> EVALUATE -> EXECUTE -> ARCHIVE)")
    print("=" * 80)

    seq_stats = run_sequencer_volume(rng, WORD_COUNT)
    print(f"\n[1. DnaLexer + DnaParser + DnaSequencer: {WORD_COUNT:,} words]")
    print(f"  Throughput            : {seq_stats['words_per_sec']:,.1f} words/sec "
          f"({seq_stats['elapsed_sec']:.3f}s total)")
    print(f"  Valid (no lexer/parser errors) : {seq_stats['valid']:,}")
    print(f"  Invalid (contained bad bases)  : {seq_stats['invalid']:,}")
    print(f"  Syntax errors (empty sequence) : {seq_stats['syntax_errors']:,}")
    print(f"  Total codons grouped           : {seq_stats['total_codons']:,}")
    print(f"  Total trailing partial pairs   : {seq_stats['total_trailing_partial']:,}")
    if seq_stats["avg_gc_content"] is not None:
        print(f"  Average GC content             : {seq_stats['avg_gc_content']:.3f}")

    trans_stats = run_transpiler_volume(rng, WORD_COUNT)
    print(f"\n[2. SuperTranspiler generator: {WORD_COUNT:,} words x 6 languages]")
    print(f"  Throughput             : {trans_stats['words_per_sec']:,.1f} words/sec")
    print(f"  Total renderings       : {trans_stats['total_renderings']:,} "
          f"({trans_stats['renderings_per_sec']:,.1f}/sec)")
    print("  Characters generated per language:")
    for lang, chars in sorted(trans_stats["per_language_chars"].items()):
        print(f"    {lang:<8}: {chars:,}")

    pipe_stats = run_pipeline_sample(rng, sample_size=300)
    print(f"\n[3. Full EZPipeline (EXAMINE->EVALUATE->EXECUTE->ARCHIVE), "
          f"{pipe_stats['sample_size']} representative snippets]")
    print(f"  Elapsed                : {pipe_stats['elapsed_sec']:.3f}s")
    print(f"  By EXAMINE status      : {pipe_stats['by_examine_status']}")
    print(f"  Archive boundary markers logged : {pipe_stats['archive_boundary_markers']:,}")

    print("\n" + "=" * 80)
    print(f" TOTAL WORDS PROCESSED ACROSS SEQUENCER + GENERATOR: {WORD_COUNT * 2:,}")
    print(" RUNTIME RESILIENCE: 100.0% (0 unhandled exceptions)")
    print("=" * 80)


if __name__ == "__main__":
    run_10000_word_benchmark()
