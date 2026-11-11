#!/usr/bin/env python3
"""Independent Python reference for the order-k predictor in the predict module (stdlib only).

Run from the 6-android-kotlin project root:

    python3 predict/tools/ref_predict.py

Writes predict/src/test/resources/predict_reference.tsv, which
predict/src/test/kotlin/org/everlang/dna/predict/ReferenceParityTest.kt reads.

The model is re-derived here from its definition, not ported from the Kotlin code:
  * contexts are tuples of the last `order` symbols, starting from an explicit
    all-A history (the padding rule);
  * p(s | c) = (n[c][s] + alpha) / (sum_t n[c][t] + 4 * alpha);
  * top-1 is the symbol with the largest count in the context, lowest index on ties;
  * byte inputs are split most significant bits first into 2-bit symbols with explicit
    shifts, A=0 T=1 C=2 G=3.

This file shares no code with the Kotlin module, with core, or with everlang_standalone.
Inputs come from fixed seeds, and each input is written literally to the TSV, so the Kotlin
side never has to reproduce a Python RNG.
"""

import math
import random
import sys
from pathlib import Path

PREDICT = Path(__file__).resolve().parent.parent
OUT = PREDICT / "src" / "test" / "resources" / "predict_reference.tsv"

BASES = "ATCG"  # 2-bit code order: A=0, T=1, C=2, G=3
ORDERS = (1, 3, 8)
DEFAULT_ALPHA = 0.5
HEADER = (
    "name", "kind", "order", "alpha", "input", "bases", "hits",
    "total_bits", "bits_per_base", "top1_accuracy", "p_A", "p_T", "p_C", "p_G",
)

# Sticky, asymmetric transition weights for the Markov source: row = previous symbol.
MARKOV_ROWS = (
    (6, 2, 1, 1),
    (1, 6, 2, 1),
    (1, 1, 6, 2),
    (2, 1, 1, 6),
)


def symbols_from_bytes(data):
    """Each byte becomes four 2-bit symbols, most significant pair first."""
    out = []
    for b in data:
        out.append((b >> 6) & 3)
        out.append((b >> 4) & 3)
        out.append((b >> 2) & 3)
        out.append(b & 3)
    return out


def probs_of(cell, alpha):
    denom = sum(cell) + 4 * alpha
    return [(n + alpha) / denom for n in cell]


def run_model(symbols, order, alpha):
    """Predict-then-update over `symbols`. Returns the measured quantities."""
    cells = {}
    history = (0,) * order  # padded: A repeated `order` times
    total_bits = 0.0
    hits = 0
    for s in symbols:
        cell = cells.setdefault(history, [0, 0, 0, 0])
        p = probs_of(cell, alpha)
        best = 0
        for t in (1, 2, 3):
            if cell[t] > cell[best]:
                best = t
        if best == s:
            hits += 1
        total_bits += -math.log2(p[s])
        cell[s] += 1
        history = history[1:] + (s,)
    final = probs_of(cells.get(history, [0, 0, 0, 0]), alpha)
    bases = len(symbols)
    return {
        "bases": bases,
        "hits": hits,
        "total_bits": total_bits,
        "bits_per_base": total_bits / bases,
        "top1_accuracy": hits / bases,
        "final_probs": final,
    }


def build_cases():
    """(name, kind, payload) where payload is a symbol list or a bytes object."""
    iid_rng = random.Random(101)
    iid_biased = iid_rng.choices(range(4), weights=[4, 1, 1, 4], k=3000)

    markov_rng = random.Random(202)
    markov = []
    prev = 0
    for _ in range(2000):
        prev = markov_rng.choices(range(4), weights=MARKOV_ROWS[prev])[0]
        markov.append(prev)

    short_rng = random.Random(303)
    short5 = short_rng.choices(range(4), weights=[1, 1, 1, 1], k=5)

    periodic = [BASES.index(c) for c in "ATCG" * 250]
    periodic_mut = list(periodic)
    periodic_mut[500] = (periodic_mut[500] + 1) % 4  # one base changed: C -> G

    bytes_rng = random.Random(404)
    bytes_uniform = bytes(bytes_rng.getrandbits(8) for _ in range(96))

    biased_byte_weights = [1] * 256
    biased_byte_weights[0x1B] = 60  # 00 01 10 11 (A T C G)
    biased_byte_weights[0xE4] = 30  # 11 10 01 00
    bytes_biased_rng = random.Random(505)
    bytes_biased = bytes(bytes_biased_rng.choices(range(256), weights=biased_byte_weights, k=96))

    return [
        ("iid_biased", "symbols", iid_biased),
        ("markov", "symbols", markov),
        ("short5", "symbols", short5),
        ("periodic", "symbols", periodic),
        ("periodic_mut", "symbols", periodic_mut),
        ("bytes_uniform", "bytes", bytes_uniform),
        ("bytes_biased", "bytes", bytes_biased),
    ]


def matrix():
    """Every (case, order, alpha) combination written to the TSV."""
    cases = build_cases()
    jobs = []
    for order in ORDERS:
        for name, kind, payload in cases:
            jobs.append((name, kind, payload, order, DEFAULT_ALPHA))
    # One non-default alpha, so the smoothing constant is cross-checked as well.
    iid = next(c for c in cases if c[0] == "iid_biased")
    jobs.append((iid[0], iid[1], iid[2], 3, 0.1))
    return jobs


def encode_input(kind, payload):
    if kind == "symbols":
        return "".join(BASES[s] for s in payload)
    return payload.hex()


def main():
    rows = []
    for name, kind, payload, order, alpha in matrix():
        symbols = payload if kind == "symbols" else symbols_from_bytes(payload)
        r = run_model(symbols, order, alpha)
        assert abs(sum(r["final_probs"]) - 1.0) < 1e-12, "reference probabilities must sum to 1"
        rows.append((name, kind, order, alpha, encode_input(kind, payload), r))

    lines = ["\t".join(HEADER)]
    for name, kind, order, alpha, text, r in rows:
        p = r["final_probs"]
        lines.append("\t".join([
            name,
            kind,
            str(order),
            repr(alpha),
            text,
            str(r["bases"]),
            str(r["hits"]),
            repr(r["total_bits"]),
            repr(r["bits_per_base"]),
            repr(r["top1_accuracy"]),
            repr(p[0]),
            repr(p[1]),
            repr(p[2]),
            repr(p[3]),
        ]))

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"wrote {len(rows)} rows to {OUT}")
    print(f"{'name':<14}{'kind':<9}{'order':>5}{'alpha':>6}{'bases':>7}{'bits/base':>12}{'top1':>10}")
    for name, kind, order, alpha, _text, r in rows:
        print(f"{name:<14}{kind:<9}{order:>5}{alpha:>6}{r['bases']:>7}"
              f"{r['bits_per_base']:>12.6f}{r['top1_accuracy']:>10.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
