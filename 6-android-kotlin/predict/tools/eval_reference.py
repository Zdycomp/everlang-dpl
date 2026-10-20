#!/usr/bin/env python3
"""Exact reference values for the predictor evaluation (stdlib only).

Run from the 6-android-kotlin root:

    python3 predict/tools/eval_reference.py

Reads predict/tools/markov_order2.tsv, the transition weights of the order-2 source that
PredictorEvalTest samples from, and writes predict/tools/eval_reference.tsv, which the test reads.

Markov stationary law and top-1 values are exact Fractions. Entropies are evaluated from those Fractions
at 60-digit precision, since they involve logarithms:
  * state = (x[t-2], x[t-1]), index 4*x[t-2] + x[t-1], codes A=0 T=1 C=2 G=3;
  * pi is the stationary law of the 16-state pair chain, solved by Gaussian elimination over
    Fractions and checked exactly against pi = pi P;
  * markov.H_rate     = sum_i pi_i H(P_i): entropy rate, bits per base. Orders 2 and up reach it.
  * markov.H_order1   = H(X_t | X_{t-1}) under the stationary law: the best an order-1 model can reach.
  * markov.top1_order1 = sum_a max_c P(X_t = c, X_{t-1} = a): best top-1 accuracy from one symbol.
  * markov.top1_order2 = sum_i pi_i max_c P_i(c): best top-1 accuracy from two symbols.

Tandem repeats: each base of a period-16 template is substituted with probability r, to one of the
other three bases uniformly. Given the infinite past the phase is known, so the entropy rate of the
process is H_b(r) + r*log2(3), and no predictor can get top-1 accuracy above 1 - r. These are process
bounds. An order-k predictor sees only k symbols, so it can sit above them.

Uniform bytes: every 2-bit symbol is uniform, so the rate is 2 bits and top-1 accuracy is 1/4.
"""

import sys
from decimal import Decimal, getcontext
from fractions import Fraction
from pathlib import Path

getcontext().prec = 60

TOOLS = Path(__file__).resolve().parent
MATRIX = TOOLS / "markov_order2.tsv"
OUT = TOOLS / "eval_reference.tsv"
SYMBOLS = "ATCG"  # 2-bit code order: A=0, T=1, C=2, G=3
TANDEM_RATES = ("0", "0.01", "0.05", "0.10")
LN2 = Decimal(2).ln()


def code(ch):
    return SYMBOLS.index(ch)


def read_matrix(path):
    """Returns P[i][c] as Fractions, i = 4*x[t-2] + x[t-1], with rows normalised from the weights."""
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
    header = lines[0].split("\t")
    if header != ["context", "A", "T", "C", "G"]:
        raise SystemExit(f"{path}: unexpected header {header!r}")
    weights = {}
    for ln in lines[1:]:
        fields = ln.split("\t")
        ctx, w = fields[0], [int(x) for x in fields[1:]]
        if len(ctx) != 2 or any(ch not in SYMBOLS for ch in ctx) or len(w) != 4 or min(w) <= 0:
            raise SystemExit(f"{path}: bad row {ln!r}")
        idx = 4 * code(ctx[0]) + code(ctx[1])
        if idx in weights:
            raise SystemExit(f"{path}: duplicate context {ctx}")
        weights[idx] = w
    if sorted(weights) != list(range(16)):
        raise SystemExit(f"{path}: need all 16 two-symbol contexts, got {len(weights)}")
    return [[Fraction(x, sum(weights[i])) for x in weights[i]] for i in range(16)]


def solve(A, b):
    """Gaussian elimination with partial pivoting over Fractions."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = next(r for r in range(col, n) if M[r][col] != 0)
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col and M[r][col] != 0:
                f = M[r][col] / M[col][col]
                M[r] = [x - f * y for x, y in zip(M[r], M[col])]
    return [M[i][n] / M[i][i] for i in range(n)]


def stationary(P):
    n = 16
    T = [[Fraction(0)] * n for _ in range(n)]
    for a in range(4):
        for b in range(4):
            i = 4 * a + b
            for c in range(4):
                T[i][4 * b + c] += P[i][c]
    # pi (T - I) = 0 as a column system, with the last equation replaced by sum(pi) = 1.
    A = [[T[i][j] - (1 if i == j else 0) for i in range(n)] for j in range(n)]
    A[n - 1] = [Fraction(1)] * n
    rhs = [Fraction(0)] * n
    rhs[n - 1] = Fraction(1)
    pi = solve(A, rhs)
    assert sum(pi) == 1, "stationary law must sum to 1"
    for j in range(n):
        assert sum(pi[i] * T[i][j] for i in range(n)) == pi[j], "pi is not stationary"
    assert all(p > 0 for p in pi), "chain must be irreducible here"
    return pi


def dec(fr):
    return Decimal(fr.numerator) / Decimal(fr.denominator)


def log2(x):
    return x.ln() / LN2


def entropy_bits(dist):
    """Shannon entropy in bits of a list of Fractions summing to 1, zero terms skipped."""
    return sum((-dec(p) * log2(dec(p)) for p in dist if p > 0), Decimal(0))


def markov_quantities(P, pi):
    H_rate = sum((dec(pi[i]) * entropy_bits(P[i]) for i in range(16)), Decimal(0))

    # Joint law of (X_{t-1}, X_t): q[a][c] = sum_b pi(b, a) P(c | b, a).
    q = [[Fraction(0)] * 4 for _ in range(4)]
    for b in range(4):
        for a in range(4):
            for c in range(4):
                q[a][c] += pi[4 * b + a] * P[4 * b + a][c]
    m = [sum(q[a]) for a in range(4)]  # marginal of X_{t-1}
    H_order1 = sum((-dec(q[a][c]) * log2(dec(q[a][c] / m[a])) for a in range(4) for c in range(4) if q[a][c] > 0),
                   Decimal(0))
    top1_order1 = sum((max(q[a]) for a in range(4)), Fraction(0))
    top1_order2 = sum((pi[i] * max(P[i]) for i in range(16)), Fraction(0))
    return {
        "H_rate": H_rate,
        "H_order1": H_order1,
        "top1_order1": dec(top1_order1),
        "top1_order2": dec(top1_order2),
        "pi_min": dec(min(pi)),
    }


def binary_entropy(r):
    if r == 0:
        return Decimal(0)
    return -(1 - r) * log2(1 - r) - r * log2(r)


def tandem_floor(rate):
    r = Decimal(rate)
    return binary_entropy(r) + r * log2(Decimal(3))


def fmt(x):
    if x == 0:
        return "0"
    return format(x, ".20g")


def main():
    P = read_matrix(MATRIX)
    pi = stationary(P)
    q = markov_quantities(P, pi)

    rows = [
        ("markov.H_rate", fmt(q["H_rate"]), "bits/base, entropy rate of the order-2 source"),
        ("markov.H_order1", fmt(q["H_order1"]), "bits/base, H(X_t | X_t-1) under the stationary law"),
        ("markov.top1_order1", fmt(q["top1_order1"]), "best top-1 accuracy from one symbol of context"),
        ("markov.top1_order2", fmt(q["top1_order2"]), "best top-1 accuracy from two symbols of context"),
        ("markov.pi_min", fmt(q["pi_min"]), "smallest stationary probability of a pair state"),
        ("uniform.bits", "2", "bits/base, uniform symbols"),
        ("uniform.top1", "0.25", "top-1 accuracy, uniform symbols"),
    ]
    for rate in TANDEM_RATES:
        rows.append((f"tandem.floor.{rate}", fmt(tandem_floor(rate)),
                     f"bits/base, entropy rate of period-16 repeat, substitution rate {rate}"))
        rows.append((f"tandem.top1.{rate}", fmt(Decimal(1) - Decimal(rate)),
                     f"top-1 ceiling, period-16 repeat, substitution rate {rate}"))

    lines = ["key\tvalue\tnote"] + [f"{k}\t{v}\t{n}" for k, v, n in rows]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"wrote {len(rows)} values to {OUT}")
    for k, v, n in rows:
        print(f"{k:<22}{v:<26}{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
