#!/usr/bin/env python3
"""
spec.py — the ratified decision table.

An open question is a point where the language was never actually
specified and independent implementations therefore answered
differently. The forge finds those by disagreement, arbitrates them by
the consensus rule the language already uses, and records the ruling
here.

Two states, and the difference matters:

  UNRATIFIED   no ruling. Every implementation answers natively — from
               whatever its own technique suggests. Divergence here is
               information, not a bug.

  RATIFIED     a ruling exists. Every implementation conforms.

Conforming to a written ruling does not make witnesses dependent.
Independence in SEMANTICS.md 2.2 is independence of *derivation*, and
the derivations stay separate — a trie, a table, a hand scanner. What
converges is the naming, which was never anybody's evidence.

The table is data on disk (`ratified.json`) rather than source, so a
generation can ratify a question without anybody editing a module. That
is what lets the loop actually close.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE_PATH = os.path.join(HERE, "ratified.json")

UNRATIFIED = None


@dataclass
class Question:
    """An open point in the language, and the ruling if one exists."""
    key: str
    asks: str
    answer: Any = UNRATIFIED
    generation: int = 0
    witnesses: List[str] = field(default_factory=list)
    rationale: str = ""

    @property
    def settled(self) -> bool:
        return self.answer is not UNRATIFIED


#: Every question the forge knows how to express a ruling for. A
#: divergence on anything outside this list is escalated rather than
#: guessed at — see forge.py.
QUESTIONS: Dict[str, str] = {
    "cmp_kind":
        "Which token kind carries a bare '<' or '>'?",
    "unterminated_string_defect":
        "Which binding defect classifies a string with no closing quote?",
    "reserved_words":
        "Which words may an EZR program not use as a name?",
    "multi_definition":
        "May one source text carry more than one definition?",
    "chained_comparison":
        "Does 'a < b < c' parse?",
    "trailing_comma":
        "May an argument or parameter list end with a comma?",
    "trailing_expression":
        "May a run of definitions be followed by an expression?",
}


class Spec:
    def __init__(self, path: str = TABLE_PATH):
        self.path = path
        self.questions: Dict[str, Question] = {
            k: Question(k, asks) for k, asks in QUESTIONS.items()
        }
        self.load()

    # ── persistence ──
    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path) as fh:
            raw = json.load(fh)
        for k, rec in raw.get("questions", {}).items():
            q = self.questions.get(k) or Question(k, rec.get("asks", ""))
            q.answer = rec.get("answer", UNRATIFIED)
            q.generation = rec.get("generation", 0)
            q.witnesses = rec.get("witnesses", [])
            q.rationale = rec.get("rationale", "")
            self.questions[k] = q

    def save(self) -> None:
        payload = {
            "note": "Written by the forge. Each entry is a question the "
                    "language had left open and the generation that "
                    "settled it.",
            "questions": {
                k: {"asks": q.asks, "answer": q.answer,
                    "generation": q.generation, "witnesses": q.witnesses,
                    "rationale": q.rationale}
                for k, q in sorted(self.questions.items())
            },
        }
        with open(self.path, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False)
            fh.write("\n")

    # ── reading ──
    def get(self, key: str, native: Any) -> Any:
        """The ruling if there is one, otherwise the caller's own
        native answer. This is the whole mechanism."""
        q = self.questions.get(key)
        if q is None or not q.settled:
            return native
        return q.answer

    def ratify(self, key: str, answer: Any, generation: int,
               witnesses: List[str], rationale: str) -> None:
        q = self.questions.setdefault(key, Question(key, QUESTIONS.get(key, "")))
        q.answer = answer
        q.generation = generation
        q.witnesses = sorted(witnesses)
        q.rationale = rationale

    @property
    def open_questions(self) -> List[Question]:
        return [q for q in self.questions.values() if not q.settled]

    @property
    def settled_questions(self) -> List[Question]:
        return [q for q in self.questions.values() if q.settled]

    def reset(self) -> None:
        for q in self.questions.values():
            q.answer = UNRATIFIED
            q.generation = 0
            q.witnesses = []
            q.rationale = ""


#: One shared table per process. Implementations read it; the forge
#: writes it.
SPEC = Spec()


def reload_spec() -> Spec:
    SPEC.__init__(SPEC.path)
    return SPEC


__all__ = ["SPEC", "Spec", "Question", "QUESTIONS", "UNRATIFIED",
           "reload_spec", "TABLE_PATH"]
