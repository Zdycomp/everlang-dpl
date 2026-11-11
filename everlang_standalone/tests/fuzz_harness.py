"""Seeded fuzz harness for the binary sequencer and EArchive.heal().

Run from everlang_standalone/:

    python3 tests/fuzz_harness.py --cases 100000 --seed 1
    python3 tests/fuzz_harness.py --cases 1000000 --chunks 10 --seed 1

Every case is reproducible from (seed, case index). Failures are collected
with their seed and index and printed; the process exits non-zero if any
invariant is violated. Oracles are exact where the spec is exact (codec
round-trip, decode acceptance) and invariant-based where it is not (heal
repairs: we check bounds, monotonic charges and refusal semantics, not the
specific repair text).
"""

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from everlang.biocomputing.binary_sequencer import BinarySequencer  # noqa: E402
from everlang.core.archive import EArchive  # noqa: E402
from everlang.core.vocabulary import E_CERTAIN, LANGUAGES  # noqa: E402

ATCG = frozenset("ATCG")
HOSTILE_CHARS = list("XN-*#.0 \t\n\r\x00\x7féßİ ﻿\U0001F9EC") + ["acgt"[0], "g", "t"]
COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}

# Healthy and defective source snippets per language. Defects are the
# bracket / quote families the engines are documented to handle (SEMANTICS 9).
SNIPPETS = {
    "python": ["def f(x):\n    return (x + 1\n", "print('hi\n", "x = [1, 2\n", "y = {'a': 1\n"],
    "javascript": ["function f(x) {\n  return x + 1;\n", "let s = 'abc\n", "const a = [1, 2;\n"],
    "go": ["func f() {\n\treturn\n", "s := \"abc\n", "a := []int{1, 2\n"],
    "rust": ["fn f() {\n    let x = 1;\n", "let s = \"abc;\n", "let v = vec![1, 2;\n"],
    "java": ["class A { void f() {\n", "String s = \"abc;\n", "int[] a = {1, 2;\n"],
    "kotlin": ["fun f() {\n    val x = 1\n", "val s = \"abc\n", "val a = listOf(1, 2\n"],
    "ever": ["let x = (1 + 2\n", "let s = \"abc\n"],
}


class Failure:
    def __init__(self, seed, index, kind, detail):
        self.seed, self.index, self.kind, self.detail = seed, index, kind, detail

    def __str__(self):
        return f"seed={self.seed} case={self.index} [{self.kind}] {self.detail}"


def _rng(seed, index):
    return random.Random((seed * 1_000_003) ^ index)


def _random_bytes(rng):
    mode = rng.random()
    if mode < 0.1:
        n = rng.choice([0, 1, 2, 3, 4, 5, 7, 8, 9])
    else:
        n = rng.randint(0, 48)
    if mode < 0.2:
        return bytes([rng.choice([0x00, 0xFF, 0x1B, 0x80])]) * n
    return bytes(rng.getrandbits(8) for _ in range(n))


def _oracle_decode(strand):
    """Exact spec for decode(): whitespace is ignored, case is folded."""
    cleaned = "".join(strand.upper().split())
    if any(ch not in ATCG for ch in cleaned):
        return None
    if len(cleaned) % 4 != 0:
        return None
    return cleaned


def check_codec(seed, index, rng, seq):
    fails = []
    data = _random_bytes(rng)
    res = seq.sequence(data)
    dna = res["dna"]
    if len(dna) != 4 * len(data):
        fails.append(("codec-length", f"{len(dna)} bases for {len(data)} bytes"))
    if not set(dna) <= ATCG:
        fails.append(("codec-alphabet", repr(dna)))
    if not res["round_trip"]:
        fails.append(("codec-roundtrip", data.hex()))
    if len(res["codons"]) != len(dna) // 3 or len(res["trailing_partial"]) != len(dna) % 3:
        fails.append(("codon-grouping", f"{len(dna)} bases"))
    gc = res["gc_content"]
    if (gc is None) != (not dna) or (gc is not None and not 0.0 <= gc <= 1.0):
        fails.append(("gc-range", repr(gc)))
    if dna and gc is not None:
        expect_gc = sum(ch in "GC" for ch in dna) / len(dna)
        if abs(gc - expect_gc) > 1e-12:
            fails.append(("gc-value", f"{gc} != {expect_gc}"))

    # Error injection: substitute, delete, insert, or case-flip, then check the decode oracle.
    if dna:
        op = rng.choice(["insert", "substitute", "delete", "lower", "insert4"])
        pos = rng.randrange(len(dna))
        if op == "insert":
            strand = dna[:pos] + rng.choice(HOSTILE_CHARS + list(ATCG)) + dna[pos:]
        elif op == "insert4":
            # Four bases keep the length a multiple of 4: validity is decided by the alphabet alone.
            strand = dna[:pos] + "".join(rng.choice("ATCG") for _ in range(4)) + dna[pos:]
        elif op == "substitute":
            strand = dna[:pos] + rng.choice(HOSTILE_CHARS + list("ATCG")) + dna[pos + 1:]
        elif op == "delete":
            strand = dna[:pos] + dna[pos + 1:]
        else:
            strand = dna[:pos] + dna[pos].lower() + dna[pos + 1:]
        expected = _oracle_decode(strand)
        try:
            got = seq.decode(strand)
        except ValueError:
            got = None
            raised = True
        else:
            raised = False
        if expected is None:
            if not raised:
                fails.append(("decode-accepted-invalid", repr(strand)))
        else:
            if raised:
                fails.append(("decode-rejected-valid", repr(strand)))
            else:
                exp_bytes = bytes(
                    int("".join(f"{'ATCG'.index(b):02b}" for b in expected[i:i + 4]), 2)
                    for i in range(0, len(expected), 4)
                )
                if got != exp_bytes:
                    fails.append(("decode-value", repr(strand)))

    # Affinity: complement gate is exactly 256, length mismatch is exactly 0.
    if dna:
        comp = "".join(COMPLEMENT[b] for b in dna)
        if seq.affinity(dna, comp) != 256:
            fails.append(("affinity-complement", dna))
        if seq.affinity(dna, comp + "A") != 0:
            fails.append(("affinity-length", dna))
        rand_gate = "".join(rng.choice("ATCG") for _ in dna)
        score = seq.affinity(dna, rand_gate)
        matches = sum(1 for a, g in zip(dna, rand_gate) if COMPLEMENT[a] == g)
        expect_score = int(matches / len(dna) * 256)  # dna_engine.py:29
        if score != expect_score:
            fails.append(("affinity-value", f"{score} != {expect_score}"))
    return fails


CLEAN_SNIPPETS = {
    "python": "x = 1\n",
    "javascript": "let x = 1;\n",
    "go": "package main\n",
    "rust": "let x = 1;\n",
    "java": "int x = 1;\n",
    "kotlin": "val x = 1\n",
    "ever": "let x = 1\n",
}


def check_heal(seed, index, rng, archive):
    fails = []
    lang = rng.choice(LANGUAGES)
    defective = rng.random() < 0.8
    src = rng.choice(SNIPPETS[lang]) if defective else CLEAN_SNIPPETS[lang]
    if defective and rng.random() < 0.3:
        pos = rng.randrange(len(src) + 1)
        src = src[:pos] + rng.choice(HOSTILE_CHARS) + src[pos:]
    # Initial confidence is deliberately generated out of range: archive.py clamps it to 0..256.
    conf0 = rng.randint(-50, E_CERTAIN + 50)
    conf_in = max(0, min(E_CERTAIN, conf0))
    try:
        h = archive.heal(src, lang, f"fuzz-{seed}-{index}", confidence=conf0)
    except (KeyError, ValueError) as exc:
        # heal() deliberately raises on vocabulary or pair violations: that is a bug.
        return [("heal-raised", f"{lang}: {type(exc).__name__}: {exc}")]
    except Exception as exc:  # noqa: BLE001 - anything else is a crash
        return [("heal-crash", f"{lang}: {type(exc).__name__}: {exc}")]
    if not 0 <= h.confidence <= E_CERTAIN:
        fails.append(("heal-confidence-range", str(h.confidence)))
    if h.refused and h.confidence != 0:
        fails.append(("heal-refused-not-zero", f"{lang} conf={h.confidence}"))
    if h.refused and h.code is not None:
        fails.append(("heal-refused-has-code", lang))
    prev = conf_in
    for rec in h.repairs:
        if not (0 <= rec["conf_after"] <= rec["conf_before"] <= E_CERTAIN):
            fails.append(("heal-charge", f"{rec['name']} {rec['conf_before']}->{rec['conf_after']}"))
        if rec["conf_before"] != prev:
            fails.append(("heal-charge-order", rec["name"]))
        cost = rec["cost"]
        if cost not in (8, 32):
            fails.append(("heal-cost-value", f"{rec['name']} cost={cost}"))
        if rec["conf_before"] - rec["conf_after"] != min(cost, rec["conf_before"]):
            fails.append(("heal-cost-applied", rec["name"]))
        prev = rec["conf_after"]
    if not h.refused and not h.repairs and h.confidence != conf_in:
        fails.append(("heal-conf-untethered", f"{lang} {h.confidence} != {conf_in} with no repairs"))
    if not h.refused and h.repairs and h.confidence != prev:
        fails.append(("heal-conf-untethered", f"{lang} {h.confidence} != last charge {prev}"))
    if not defective and (h.repairs or h.refused):
        fails.append(("heal-clean-input-touched", f"{lang}: repairs={len(h.repairs)} refused={h.refused}"))
    return fails


def run_chunk(seed, start, count, check_heal_too=True):
    seq = BinarySequencer()
    archive = EArchive()
    failures = []
    stats = {"codec": 0, "heal": 0}
    for index in range(start, start + count):
        rng = _rng(seed, index)
        for kind, detail in check_codec(seed, index, rng, seq):
            failures.append(Failure(seed, index, kind, detail))
        stats["codec"] += 1
        if check_heal_too and index % 4 == 0:
            for kind, detail in check_heal(seed, index, rng, archive):
                failures.append(Failure(seed, index, kind, detail))
            stats["heal"] += 1
    return failures, stats


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--chunks", type=int, default=1, help="split the run into N seeded chunks")
    ap.add_argument("--max-report", type=int, default=20)
    args = ap.parse_args(argv)

    # Heal checks pass vacuously if the ezr engines are missing (heal.py refuses everything).
    # Refuse to run in that state, and require a known defect to reach the engines.
    from everlang.core import heal as heal_engine
    if not heal_engine._load():
        print("FATAL: ezr repair engines did not load; heal invariants would be vacuous")
        return 2
    probe = EArchive().heal("def f(x):\n    return (x + 1\n", "python", "probe")
    if not (probe.refused or probe.repairs):
        print("FATAL: known-defective probe was neither repaired nor refused")
        return 2

    per = args.cases // args.chunks
    total_failures, total = [], {"codec": 0, "heal": 0}
    started = time.time()
    for c in range(args.chunks):
        seed = args.seed + c
        t0 = time.time()
        failures, stats = run_chunk(seed, 0, per)
        total_failures.extend(failures)
        for k in total:
            total[k] += stats[k]
        print(f"chunk {c + 1}/{args.chunks} seed={seed} cases={per} "
              f"failures={len(failures)} ({time.time() - t0:.1f}s)", flush=True)

    elapsed = time.time() - started
    print(f"TOTAL codec_cases={total['codec']} heal_cases={total['heal']} "
          f"failures={len(total_failures)} elapsed={elapsed:.1f}s")
    for f in total_failures[: args.max_report]:
        print("  FAIL", f)
    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(main())
