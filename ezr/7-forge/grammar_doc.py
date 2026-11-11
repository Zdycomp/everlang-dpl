#!/usr/bin/env python3
"""
grammar_doc.py — render the grammar the parsers actually run.

SEMANTICS.md 7 lists "Formal grammar (EBNF)" as missing, with the
consequence "parsing is regex-based". Writing one by hand would close
the entry and open a worse problem: a document that agrees with the
code today and quietly stops agreeing later.

So the EBNF is *emitted* from the chart parser's rule table — the same
list the parser walks. It cannot drift, because there is nothing for it
to drift from.

The token table is emitted the same way: by scanning every operator and
keyword through the ratified lexers and reporting the kind they agree
on. What kind a bare '<' carries was the language's first open
question; the answer belongs in the document as a fact that was
measured, not as one that was typed.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

from lexers import LEXERS, keywords
from parsers import GRAMMAR, _sync_grammar
from spec import SPEC

HERE = os.path.dirname(os.path.abspath(__file__))
EBNF_PATH = os.path.join(HERE, "GRAMMAR.ebnf")

#: Rule-name to EBNF-name, for the ones worth spelling out in full.
PRETTY = {
    "S": None,                      # the wrapper, not part of the language
    "program": "program",
    "deflist": "definitions",
    "fndef": "definition",
    "params": "parameters",
    "expr": "expression",
    "ifexpr": "conditional",
    "letexpr": "binding",
    "compare": "comparison",
    "additive": "additive",
    "multiply": "multiplicative",
    "unary": "unary",
    "atom": "atom",
    "arglist": "arguments",
}

TERMINAL = {
    "%NUM": "number", "%STR": "string", "%NAME": "name",
    "%CMP": "compare-op", "%LPAR": '"("', "%RPAR": '")"',
    "%COMMA": '","', "%EQ": '"="',
    "%LBRACK": '"["', "%RBRACK": '"]"',
}


def _sym(s: str) -> str:
    if s in TERMINAL:
        return TERMINAL[s]
    if s.startswith("'"):
        return '"' + s[1:-1] + '"'
    return PRETTY.get(s, s)


def rules_by_lhs() -> Dict[str, List[Tuple[str, ...]]]:
    _sync_grammar()
    out: Dict[str, List[Tuple[str, ...]]] = {}
    for lhs, rhs, _act in GRAMMAR:
        if PRETTY.get(lhs, lhs) is None:
            continue
        out.setdefault(lhs, []).append(rhs)
    return out


def token_table() -> List[Tuple[str, str]]:
    """Ask the scanners what kind each piece of punctuation carries.

    Reported only where all four agree — a kind three of them assign is
    not a fact about the language.
    """
    probes = ["<", ">", "<=", ">=", "==", "!=", "+", "-", "*", "/",
              "=", "(", ")", ",", "[", "]"]
    rows: List[Tuple[str, str]] = []
    for text in probes:
        kinds = set()
        for fn in LEXERS.values():
            out = fn(f"a {text} b" if text not in "()," else text)
            hit = [t for t in out.toks if t.text == text]
            kinds.add(hit[0].kind if hit else "?")
        rows.append((text, kinds.pop() if len(kinds) == 1 else "DISPUTED"))
    return rows


def render() -> str:
    by = rules_by_lhs()
    order = ["program", "deflist", "fndef", "params", "expr", "ifexpr",
             "letexpr", "compare", "additive", "multiply", "unary", "atom",
             "arglist"]

    L: List[str] = []
    L.append("(* " + "=" * 68)
    L.append("   EZR — CORE GRAMMAR")
    L.append("")
    L.append("   Emitted from the chart parser's rule table by")
    L.append("   grammar_doc.py. Do not edit: edit the rules and")
    L.append("   re-emit, or the document and the parser part company.")
    L.append("")
    L.append("   Closes the first entry of SEMANTICS.md section 7,")
    L.append('   "Formal grammar (EBNF) | parsing is regex-based".')
    L.append("")
    L.append("   Codric Enterprise")
    L.append("   " + "=" * 68 + " *)")
    L.append("")
    L.append("(* ---- syntax ---------------------------------------- *)")
    L.append("")

    width = max(len(PRETTY.get(k, k) or k) for k in order if k in by)
    for lhs in order:
        if lhs not in by:
            continue
        name = PRETTY.get(lhs, lhs)
        alts = [" , ".join(_sym(s) for s in rhs) for rhs in by[lhs]]
        pad = " " * (width - len(name))
        L.append(f"{name}{pad} = {alts[0]}")
        for a in alts[1:]:
            L.append(f"{' ' * width}   | {a}")
        L.append(f"{' ' * width}   ;")
        L.append("")

    L.append("(* ---- lexis ----------------------------------------- *)")
    L.append("")
    kws = sorted(keywords())
    L.append(f"keyword        = {' | '.join(chr(34) + k + chr(34) for k in kws)} ;")
    L.append('name           = ( letter | "_" ) , { letter | digit | "_" }')
    L.append("                 (* and not a keyword *) ;")
    L.append('number         = digit , { digit } , [ "." , digit , { digit } ] ;')
    L.append('string         = \'"\' , { character - \'"\' - newline } , \'"\' ;')
    L.append("boolean        = \"true\" | \"false\" ;")
    L.append('comment        = "#" , { character - newline } ;')
    L.append("")

    L.append("(* ---- token kinds ----------------------------------- *)")
    L.append("(*  Measured, not asserted: every kind below is one all   *)")
    L.append("(*  four scanners assign. Which kind carries a bare '<'   *)")
    L.append("(*  was the language's first open question.               *)")
    L.append("")
    groups: Dict[str, List[str]] = {}
    for text, kind in token_table():
        groups.setdefault(kind, []).append(text)
    for kind in sorted(groups):
        members = "  ".join(groups[kind])
        L.append(f"   {kind:<7} {members}")
    L.append("   NUM     a number")
    L.append("   STR     a string")
    L.append("   NAME    a name that is not a keyword")
    L.append("   KW      " + "  ".join(kws))
    L.append("   EOF     end of input")
    L.append("")

    L.append("(* ---- settled questions ----------------------------- *)")
    L.append("")
    for q in sorted(SPEC.settled_questions, key=lambda q: q.key):
        L.append(f"   {q.key} = {q.answer!r}")
        L.append(f"       {q.asks}")
        L.append(f"       generation {q.generation}; {q.rationale[:200]}")
        L.append("")

    return "\n".join(L) + "\n"


def write() -> str:
    text = render()
    with open(EBNF_PATH, "w") as fh:
        fh.write(text)
    return EBNF_PATH


if __name__ == "__main__":
    print(write())
