#!/usr/bin/env python3
"""
selfheal.py — a demonstration that the loop actually closes.

Claims about self-correction are cheap. This puts a real defect back
into the matrix and shows the forge finding and fixing it with nobody
helping.

The defect is not invented for the occasion. It is the bug that was
genuinely in the trie scanner: `"$"` was used as the end-of-token
marker in the trie, and `$` is a character a source text may contain,
so a `$` in the input walked into the marker and the next character
indexed a tuple. The fuzzer found it at generation 7 on `false =$= 35`.

Run it:

    python3 selfheal.py            # inject, detect, repair, verify
    python3 selfheal.py --keep     # leave the repair in the ledger

By default it restores the ledger afterwards, so a demonstration does
not leave a permanent shield behind on a scanner that is not actually
broken.

Codric Enterprise
"""

from __future__ import annotations

import argparse
import re
import sys

from contract import Fail, LexOut, Tok
from lexers import PUNCT, SPACE, keywords

# ── the historical defect, reproduced exactly ────────────────────────

_BROKEN_OPERATORS = {
    "<=": "CMP", ">=": "CMP", "==": "CMP", "!=": "CMP",
    "<": "CMP", ">": "CMP",
    "+": "OP", "-": "OP", "*": "OP", "/": "OP",
    "=": "EQ", "(": "LPAR", ")": "RPAR", ",": "COMMA",
}


def _broken_trie(table):
    root = {}
    for text, kind in table.items():
        node = root
        for c in text:
            node = node.setdefault(c, {})
        node["$"] = (text, kind)      # <-- the bug: a source character
    return root


_TRIE = _broken_trie(_BROKEN_OPERATORS)


def lex_trie_broken(src: str) -> LexOut:
    """The trie scanner as it was before the sentinel was fixed."""
    kw = keywords()
    out = LexOut()
    i, line, n = 0, 1, len(src)
    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1; i += 1; continue
        if ch in SPACE:
            i += 1; continue
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        start = i
        if ch == '"':
            j = src.find('"', i + 1)
            nl = src.find("\n", i + 1)
            if j < 0 or (0 <= nl < j):
                out.fail = Fail("lex", "unbounded", start, line)
                return out
            out.toks.append(Tok("STR", src[i:j + 1], start, line))
            i = j + 1
            continue
        if ch.isdigit():
            m = re.compile(r"\d+\.\d+|\d+").match(src, i)
            out.toks.append(Tok("NUM", m.group(), start, line))
            i = m.end()
            continue
        if ch.isalpha() or ch == "_":
            m = re.compile(r"[A-Za-z_]\w*").match(src, i)
            text = m.group()
            out.toks.append(
                Tok("KW" if text in kw else "NAME", text, start, line))
            i = m.end()
            continue
        node, j, best = _TRIE, i, None
        while j < n and src[j] in node:
            node = node[src[j]]
            j += 1
            if "$" in node:
                best = (node["$"], j)
        if best is None:
            out.fail = Fail("lex", "misbound", start, line)
            return out
        (text, kind), end = best
        out.toks.append(Tok(kind, text, start, line))
        i = end
    out.toks.append(Tok("EOF", "", i, line))
    return out


# ── the demonstration ────────────────────────────────────────────────

TRIGGER = "1 =$= 2"
WITNESS_SET = [TRIGGER, "(true + true) - (if 7 < 86 then false =$= 35 else 16)"]


def main(keep: bool) -> int:
    import forge
    from corpus import GOLDEN, PROBES

    before = list(forge.REPAIRS.entries)

    f = forge.Forge(budget=0, verbose=False)
    f.lexers["L4-trie"] = lex_trie_broken          # inject
    f.pairs = forge.build_pairs(f.lexers, f.parsers)

    print("=" * 70)
    print("SELF-REPAIR — injecting the historical trie sentinel defect")
    print("=" * 70)

    table = f.verdict_table(TRIGGER)
    down = sorted(k for k, v in table.items() if v is None)
    alive = {k: v for k, v in table.items() if v is not None}
    print(f"\ninput            {TRIGGER!r}")
    print(f"front ends down  {len(down)} of {len(table)}")
    print(f"  {', '.join(down)}")
    agreed = sorted({v for v in alive.values()})
    print(f"survivors agree  {agreed} ({len(alive)} of them)")

    print("\n--- running self-repair, headless ---")
    regression = [c.src for c in GOLDEN] + [c.src for c in PROBES]
    report = f.self_repair(WITNESS_SET, regression=regression, generation=999)

    print("\n--- after ---")
    table = f.verdict_table(TRIGGER)
    down = [k for k, v in table.items() if v is None]
    verdicts = sorted({v for v in table.values() if v is not None})
    print(f"front ends down  {len(down)}")
    print(f"all verdicts     {verdicts}")

    intact = all(
        len({v for v in f.verdict_table(s).values() if v is not None}) == 1
        for s in ["1 + 1", "def f(n) = n", "1 - 2 - 3", "a $ b"])
    print(f"regression       {'intact' if intact else 'DISTURBED'}")

    ok = (not down and len(verdicts) == 1 and intact
          and report["adopted"] and not report["rejected"])

    if not keep:
        forge.REPAIRS.entries = before
        forge.REPAIRS.save()
        print("\nledger restored (pass --keep to leave the repair in place)")

    print("\n" + "=" * 70)
    print("RESULT:", "loop closed — detected, repaired and verified unaided"
          if ok else "loop did NOT close")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    sys.exit(main(ap.parse_args().keep))
