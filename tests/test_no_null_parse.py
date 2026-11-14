"""No-Null Standard, Python front door: no lexer, parser or runtime entry
point returns None. A source that fails yields an Unparsed node plus an error
Z, never a null tree. Seeded fuzz, so every run is the same run.

Exit 0 pass, 1 fail.
"""

import os
import random
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "2-interpreter-python"))

from syntax import lex, parse, Unparsed, compile_ever  # noqa: E402
from forgive import parse_forgiving  # noqa: E402

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def sources(rng, n):
    seeds = ["", "   ", "1 +", "a $ b", "(((", "let x = ", ";;;", '"open',
             "heal (1 / zero) using (\"p\") fallback (3)", "def f(n) = ", "if z then",
             "[1, 2", "9@", "xs[", "example f(0) = 1", "anchor", "é中", "\x00"]
    alphabet = "()[]{}+-*/<>=!,;.\"' \n\tabz019$@z"
    out = list(seeds)
    for _ in range(n):
        out.append("".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40))))
    out.append("(" * 2000 + "1" + ")" * 2000)  # past the stack: must be refused, not raised
    return out


def main() -> int:
    rng = random.Random(20261113)
    count = 0
    for src in sources(rng, 400):
        count += 1
        toks, lerr = lex(src)
        check(toks is not None, f"lex returned no token list for {src!r}")
        node, err = parse(src)
        check(node is not None, f"parse returned None node for {src!r}")
        if err is not None:
            check(isinstance(node, Unparsed), f"failed parse without Unparsed node for {src!r}")
            check(bool(getattr(err, "reason", "")), f"error has no reason for {src!r}")
        fnode, ferr, corr = parse_forgiving(src)
        check(fnode is not None, f"parse_forgiving returned None for {src!r}")
        check(corr is not None, f"parse_forgiving returned no correction list for {src!r}")
        if ferr is not None:
            check(isinstance(fnode, Unparsed), f"forgiving failure without Unparsed for {src!r}")
        result = compile_ever(src)
        check(result is not None, f"compile_ever returned None for {src!r}")
        if result.error is not None:
            check(result.error.reason != "", f"compile_ever error without reason for {src!r}")
    # Consumers that count parses must skip failed sources, not count them as shapes.
    from syntax import distinct_shapes
    n_shapes, _ = distinct_shapes(["n + 1", "let x = ((", '"bad'])
    check(n_shapes == 1, f"distinct_shapes counted a failed parse: {n_shapes} shapes, expected 1")
    if FAILS:
        for f in FAILS[:20]:
            print("FAIL", f)
        print(f"no-null parse: {len(FAILS)} failure(s) over {count} sources")
        return 1
    print(f"no-null parse: {count} sources, no None from lex, parse, forgiving parse or compile_ever")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
