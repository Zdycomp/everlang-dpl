"""The JSON shape every app result uses.

    {
      "value":      <the value, never null>   # unknown: {"unknown": true}
      "state":      "known" | "unknown",
      "score":      0..256,
      "percent":    0..100,                    # score / 256, rounded half up
      "label":      "very sure" | "pretty sure" | "not sure" | "can't tell",
      "reasons":    [{"code": ..., "reason": ...}, ...],   # never empty
      "chain":      [...],                     # unknown only: steps it passed
      "evidence":   [{"phrase": ..., "source": ...}, ...], # words that drove it
      "provenance": [{"step", "source", "at", "confidence"}, ...]
    }

Nothing in this shape is null, None or empty-by-default. An unknown value
says so in ``value``, and always carries at least one reason.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, List, Optional, Tuple, Union

from . import C, CERTAIN, NOT_RECORDED, Unknown
from .reasons import check_note_code

VERY_SURE_FROM = 224    # score at or above which a value reads "very sure"
PRETTY_SURE_FROM = 160  # score at or above which a value reads "pretty sure"
CANT_TELL = "can't tell"

LABELS = (
    (VERY_SURE_FROM, "very sure"),
    (PRETTY_SURE_FROM, "pretty sure"),
    (1, "not sure"),
)


def label_for(score: int, *, unknown: bool = False) -> str:
    """Map a 0–256 score to plain words. An unknown value is always "can't tell"."""
    if unknown or score <= 0:
        return CANT_TELL
    for floor, words in LABELS:
        if score >= floor:
            return words
    return CANT_TELL  # unreachable for 0..256; kept so the function is total


def percent_for(score: int) -> int:
    """score / 256 as a whole percent, rounded half up. 256 is 100, 120 is 47."""
    if score <= 0:
        return 0
    return min(100, (score * 100 + CERTAIN // 2) // CERTAIN)


def _json_value(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("a non-finite number cannot be serialised as a value")
        return value
    if isinstance(value, str):
        return value
    raise TypeError(f"{type(value).__name__} is not a value this shape carries; "
                    "reduce it to a number, string or boolean first")


def provenance(x: Union[C, Unknown]) -> List[dict]:
    """Every step that produced ``x``, origin first, each with its own confidence.

    Walks the derivation graph once per node (shared inputs are reported once),
    so a long sum does not repeat its terms.
    """
    steps: List[dict] = []
    seen = set()

    def walk(node: Any) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, Unknown):
            steps.append({"step": "unknown", "source": node.code,
                          "at": NOT_RECORDED, "confidence": 0})
            return
        for inp in node._inputs:
            walk(inp)
        steps.append({"step": node._op, "source": node.source,
                      "at": node.at, "confidence": node.confidence})

    walk(x)
    return steps


def auto_notes(x: C) -> List[Tuple[str, str]]:
    """The reason notes implied by how a known value was produced.

    A literal is CERTAIN_LITERAL. A value read from outside is INTAKE_SOURCE,
    and names its source. A corroborated value is CORROBORATED. Anything else
    computed is DERIVED. Callers that know more pass their own notes.
    """
    if not isinstance(x, C):
        raise TypeError("auto_notes takes a C value")
    if x._op == "input":
        if x.source == "literal in code":
            return [("CERTAIN_LITERAL", "written directly in the program or the call")]
        return [("INTAKE_SOURCE", f"read from {x.source}")]
    if x._op == "corroborate":
        return [("CORROBORATED", "two independent sources agree on this value")]
    return [("DERIVED", f"computed by {x._op}; its confidence is the least of its inputs")]


def to_result(x: Union[C, Unknown], *,
              notes: Iterable[Tuple[str, str]] = (),
              evidence: Iterable[dict] = (),
              with_provenance: bool = True) -> dict:
    """Wrap a C or Unknown in the app's JSON shape.

    ``notes`` is a list of ``(note_code, text)`` pairs that say why a known
    value is trusted the way it is. A known value with no note raises: a
    score nobody can explain is not sent to the phone.
    """
    if isinstance(x, Unknown):
        out = {
            "value": {"unknown": True},
            "state": "unknown",
            "score": 0,
            "percent": 0,
            "label": CANT_TELL,
            "reasons": [{"code": x.code, "reason": x.reason}],
            "chain": list(x.chain),
            "evidence": [],
        }
    elif isinstance(x, C):
        reasons = []
        for code, text in notes:
            check_note_code(code)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("each reason needs its text")
            reasons.append({"code": code, "reason": text})
        if not reasons:
            raise ValueError("a known value needs at least one reason note")
        ev = []
        for e in evidence:
            if not isinstance(e.get("phrase"), str) or not e["phrase"]:
                raise ValueError("evidence needs a non-empty phrase")
            if not isinstance(e.get("source"), str) or not e["source"]:
                raise ValueError("evidence needs a non-empty source")
            ev.append({"phrase": e["phrase"], "source": e["source"]})
        out = {
            "value": _json_value(x.value),
            "state": "known",
            "score": x.confidence,
            "percent": percent_for(x.confidence),
            "label": label_for(x.confidence),
            "reasons": reasons,
            "chain": [],
            "evidence": ev,
        }
    else:
        raise TypeError(f"to_result takes C or Unknown, not {type(x).__name__}")

    if with_provenance:
        out["provenance"] = provenance(x)
    return out
