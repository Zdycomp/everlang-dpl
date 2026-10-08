#!/usr/bin/env python3
"""
coverage.py — does the syntax reach as far as the semantics?

Consensus among front ends can only ratify what the front ends do. All
four can agree, unanimously and sincerely, on a limitation that the
rest of the language does not have — and a vote would then write that
limitation into the specification.

So one check does not go to a vote. It asks stage 4 what it can hold,
asks stages 1-3 what they can express, and reports the difference. A
capability the runtime demonstrably has and the grammar cannot state
is a gap in the *grammar*, and no number of parsers agreeing changes
that.

This is the boundary check the pipeline was built to make possible.
PIPELINE.md: "nothing could ask 'is this spec expressible in my
grammar' — there was no grammar to ask about." There is now.

The probe imports the Python interpreter directly. It reads it and
never patches it: the C++ phase engine and the Python interpreter stay
on their own sides of the line.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
INTERP = os.path.abspath(os.path.join(HERE, "..", "2-interpreter-python"))


@dataclass
class Gap:
    """A capability stage 4 has and stages 1-3 cannot express."""
    question: str
    capability: str
    runtime_evidence: str
    syntax_evidence: str
    citation: str

    def __str__(self) -> str:
        return (f"GAP {self.question}: {self.capability}\n"
                f"    runtime : {self.runtime_evidence}\n"
                f"    syntax  : {self.syntax_evidence}\n"
                f"    cited   : {self.citation}")


def _load_runtime():
    if INTERP not in sys.path:
        sys.path.insert(0, INTERP)
    import abstract                                    # noqa: E402
    return abstract


def probe_multi_definition(front_end_accepts: Callable[[str], bool]
                           ) -> Optional[Gap]:
    """Can the runtime hold more than one definition at once, and can
    any source text say so?"""
    try:
        abstract = _load_runtime()
    except Exception as exc:                            # pragma: no cover
        return None

    lam = abstract.Lambda()
    lam.define("double", ["n"], "n * 2")
    lam.define("triple", ["n"], "n * 3")
    held = sorted(lam.globals)
    if len(held) < 2:
        return None                                     # no gap to report

    # and both are live, not merely stored
    a = lam.eval("double(4)", {}, 0, "probe")
    b = lam.eval("triple(4)", {}, 0, "probe")
    live = f"double(4)={a.value}, triple(4)={b.value}"

    src = "def double(n) = n * 2\ndef triple(n) = n * 3"
    if front_end_accepts(src):
        return None                                     # syntax reaches it

    return Gap(
        question="multi_definition",
        capability="more than one definition in one namespace",
        runtime_evidence=(f"Lambda.globals holds {held} simultaneously; "
                          f"{live}"),
        syntax_evidence=(f"no front end accepts {src!r} — the published "
                         f"rule is program := fndef | expr, one only"),
        citation=("SEMANTICS.md 7 lists the module system as missing and "
                  "describes the namespace it is missing from as 'one flat "
                  "global namespace' — a namespace the runtime already "
                  "populates and the grammar cannot address."))


def probe_all(front_end_accepts: Callable[[str], bool]) -> List[Gap]:
    gaps = []
    for probe in (probe_multi_definition,):
        g = probe(front_end_accepts)
        if g is not None:
            gaps.append(g)
    return gaps


__all__ = ["Gap", "probe_all", "probe_multi_definition"]
