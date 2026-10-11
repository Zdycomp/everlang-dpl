#!/usr/bin/env python3
"""
laws.py — properties that must hold for every input, not just the ones
somebody thought to write down.

A golden case says what one program does. A law says what *all*
programs do, which is the only kind of statement that can survive a
fuzzer. SEMANTICS.md's G1 — evaluation is total, no exceptions — is a
law in exactly this sense, and the front end either has the same
property or the guarantee is false for the pipeline as a whole.

Each law returns a list of violations. Empty means it held.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from contract import unparse


@dataclass
class Violation:
    law: str
    pair: str
    src: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.law}] {self.pair}: {self.detail}  on {self.src!r}"


@dataclass
class Run:
    """One pair's answer for one source.

    `verdict` is what agreement is judged on: the tree when the text is
    accepted, otherwise the stage and the binding defect. The *position*
    of a refusal is deliberately excluded. A chart parser reports the
    furthest column its grammar reached and a recursive-descent parser
    reports the token it choked on; both are honest, they are not the
    same number, and neither is a claim about the language. Position is
    still checked — law_position requires it to land inside the text —
    it just does not decide whether two front ends agree.
    """
    pair: str
    lex_canon: str
    parse_canon: str
    ast: Any = None
    lex_ok: bool = False
    parse_ok: bool = False
    fail_pos: Optional[int] = None
    fail_defect: Optional[str] = None
    crash: Optional[str] = None
    toks: Tuple = ()
    verdict: str = ""


# ═════════════════════════════════════════════
# The laws
# ═════════════════════════════════════════════

def law_total(src: str, runs: Dict[str, Run]) -> List[Violation]:
    """G1, at the front end. A scanner or parser that raises makes
    totality a property of whoever remembered to catch it."""
    return [Violation("total", r.pair, src, f"raised {r.crash}")
            for r in runs.values() if r.crash]


def law_agreement(src: str, runs: Dict[str, Run]) -> List[Violation]:
    """Every pair reaches the same answer.

    This is the load-bearing law. Independent derivations agreeing is
    what SEMANTICS.md 2.2 counts as evidence; the same derivation in
    four hats is not.
    """
    live = {k: r for k, r in runs.items() if not r.crash}
    if len(live) < 2:
        return []
    groups: Dict[str, List[str]] = {}
    for k, r in live.items():
        groups.setdefault(r.verdict, []).append(k)
    if len(groups) == 1:
        return []
    winner = max(groups.values(), key=len)
    out = []
    for verdict, members in groups.items():
        if members is winner:
            continue
        for m in members:
            out.append(Violation(
                "agreement", m, src,
                f"said {verdict[:70]!r}, {len(winner)} others said "
                f"{live[winner[0]].verdict[:70]!r}"))
    return out


def law_roundtrip(src: str, runs: Dict[str, Run],
                  reparse) -> List[Violation]:
    """Print an accepted tree and read it back: same tree.

    Without this a parser can be self-consistently wrong — agreeing
    with itself on a tree that no longer denotes the program it came
    from. It is also the property a transpiler will need first, since
    an emitter is a printer with a different target.
    """
    out = []
    for r in runs.values():
        if r.crash or not r.parse_ok or r.ast is None:
            continue
        try:
            text = unparse(r.ast)
        except Exception as exc:                      # pragma: no cover
            out.append(Violation("roundtrip", r.pair, src,
                                 f"could not print: {exc!r}"))
            continue
        again = reparse(r.pair, text)
        if again is None:
            out.append(Violation("roundtrip", r.pair, src,
                                 f"printed {text!r}, which it then refused"))
        elif again != r.verdict:
            out.append(Violation("roundtrip", r.pair, src,
                                 f"printed {text!r} -> {again[:60]!r}, "
                                 f"was {r.verdict[:60]!r}"))
    return out


def law_determinism(src: str, runs: Dict[str, Run],
                    rerun) -> List[Violation]:
    """The same text twice gives the same answer. A parser carrying
    state between calls would pass every other law and still be
    unusable."""
    out = []
    for r in runs.values():
        if r.crash:
            continue
        second = rerun(r.pair, src)
        if second != r.verdict:
            out.append(Violation("determinism", r.pair, src,
                                 f"second run differed: {second[:60]!r}"))
    return out


def law_unambiguous(src: str, runs: Dict[str, Run]) -> List[Violation]:
    """No program has two trees.

    Only the chart parser can report this; the other three resolve
    ambiguity silently by construction, which is precisely why one
    grammar-driven witness is worth carrying.
    """
    return [Violation("unambiguous", r.pair, src,
                      "grammar admits more than one tree")
            for r in runs.values()
            if not r.crash and r.fail_defect == "overbound"]


def law_position(src: str, runs: Dict[str, Run]) -> List[Violation]:
    """A refusal points inside the text it refused."""
    out = []
    n = len(src)
    for r in runs.values():
        if r.crash or r.fail_pos is None:
            continue
        if not (0 <= r.fail_pos <= n):
            out.append(Violation("position", r.pair, src,
                                 f"refused at {r.fail_pos}, text is {n} long"))
    return out


def law_token_stream(src: str, runs: Dict[str, Run]) -> List[Violation]:
    """A successful scan ends in exactly one EOF, and every token sits
    at a position strictly after the one before it."""
    out = []
    seen: Dict[str, bool] = {}
    for r in runs.values():
        if r.crash or not r.lex_ok or not r.toks:
            continue
        lexer = r.pair.split(" x ")[0]
        if lexer in seen:
            continue
        seen[lexer] = True
        kinds = [t.kind for t in r.toks]
        if kinds.count("EOF") != 1 or kinds[-1] != "EOF":
            out.append(Violation("token-stream", r.pair, src,
                                 f"EOF appears {kinds.count('EOF')} times, "
                                 f"last kind is {kinds[-1]}"))
        last = -1
        for t in r.toks:
            if t.pos < last:
                out.append(Violation("token-stream", r.pair, src,
                                     f"token {t.kind} at {t.pos} goes "
                                     f"backwards from {last}"))
                break
            if t.pos > len(src):
                out.append(Violation("token-stream", r.pair, src,
                                     f"token {t.kind} at {t.pos}, text is "
                                     f"{len(src)} long"))
                break
            last = t.pos
    return out


#: Laws that need only the runs. The two that need to re-invoke a pair
#: are called directly by the forge, which owns the pairs.
SIMPLE_LAWS = [law_total, law_agreement, law_unambiguous,
               law_position, law_token_stream]

LAW_NAMES = ["total", "agreement", "roundtrip", "determinism",
             "unambiguous", "position", "token-stream"]

__all__ = ["Violation", "Run", "SIMPLE_LAWS", "LAW_NAMES",
           "law_total", "law_agreement", "law_roundtrip",
           "law_determinism", "law_unambiguous", "law_position",
           "law_token_stream"]
