"""Financial continuity: decisions that can be audited and replayed.

A profile says how a value may be used for an action. Two profiles ship:

* ``DEFAULT``    — a value below the threshold is DISPLAY_ONLY: shown, not used.
* ``FINANCIAL``  — strict. An Unknown, or a value below the threshold, is HALT:
                   no trade, no settlement. The full explanation is still
                   returned, so a person can see why.

Every decision is a pure function of its recorded inputs and its ``at`` stamp.
Nothing reads the clock, so the same inputs give the same confidence and the
same outcome every time. ``AuditLog`` writes each decision as one line of
JSON, chained by SHA-256 to the line before it. The file is append-only:
lines are never rewritten, and ``verify`` finds any edit, deletion or
reordering. ``replay`` recomputes every recorded decision from its inputs and
reports any line that no longer matches what was recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

from . import C, CERTAIN, FLOOR, Unknown, corroborate, cmean, csum, mse
from .result import auto_notes, to_result

ALLOW        = "ALLOW"          # usable for the action
HALT         = "HALT"           # strict: the action stops, explanation returned
DISPLAY_ONLY = "DISPLAY_ONLY"   # shown to a person, not used for an action

GENESIS = "0" * 64              # the chain's first prev_hash


@dataclass(frozen=True)
class Profile:
    name: str
    strict: bool
    threshold: int = FLOOR      # confidence an action needs

    def __post_init__(self):
        if not 0 <= self.threshold <= CERTAIN:
            raise ValueError("threshold must be from 0 to 256")


DEFAULT   = Profile("default", strict=False, threshold=FLOOR)
FINANCIAL = Profile("financial-continuity", strict=True, threshold=224)  # "very sure"

PROFILES: Dict[str, Profile] = {p.name: p for p in (DEFAULT, FINANCIAL)}


# ═══════════════════════════════════════════════
# Records: the JSON form of a value, for the audit log
# ═══════════════════════════════════════════════

def record_of(x: Union[C, Unknown]) -> dict:
    """A value as plain JSON, enough to rebuild it exactly."""
    if isinstance(x, Unknown):
        return {"state": "unknown", "code": x.code, "reason": x.reason}
    if isinstance(x, C):
        return {"state": "known", "value": x.value, "confidence": x.confidence,
                "source": x.source, "at": x.at}
    raise TypeError("record_of takes a C or an Unknown")


def from_record(r: Mapping[str, Any]) -> Union[C, Unknown]:
    if r.get("state") == "unknown":
        return Unknown(r["code"], r["reason"])
    if r.get("state") == "known":
        return C(r["value"], r["confidence"], source=r["source"], at=r["at"])
    raise ValueError("a record must say whether it is known or unknown")


def _records(key: str, inputs: Mapping[str, Any]) -> List[Union[C, Unknown]]:
    return [from_record(r) for r in inputs[key]]


# Each computation takes its JSON inputs and returns a C or an Unknown.
COMPUTATIONS: Dict[str, Callable[[Mapping[str, Any]], Union[C, Unknown]]] = {
    "value":       lambda i: from_record(i["value"]),
    "csum":        lambda i: csum(_records("items", i)),
    "cmean":       lambda i: cmean(_records("items", i)),
    "mse":         lambda i: mse(_records("predicted", i), _records("actual", i)),
    "corroborate": lambda i: corroborate(from_record(i["a"]), from_record(i["b"])),
}


# ═══════════════════════════════════════════════
# Decisions
# ═══════════════════════════════════════════════

@dataclass(frozen=True)
class Decision:
    profile: str
    strict: bool
    action: str
    at: str
    computation: str
    inputs: Dict[str, Any]
    confidence: int
    threshold: int
    outcome: str
    reason: str
    result: Dict[str, Any]

    def to_record(self) -> dict:
        return {
            "profile": self.profile,
            "strict": self.strict,
            "action": self.action,
            "at": self.at,
            "computation": self.computation,
            "inputs": self.inputs,
            "confidence": self.confidence,
            "threshold": self.threshold,
            "outcome": self.outcome,
            "reason": self.reason,
            "result": self.result,
        }


def decide(profile: Profile, action: str, *, at: str, computation: str,
           inputs: Mapping[str, Any]) -> Decision:
    """Compute a value from its recorded inputs and decide what it may do.

    ``at`` is the caller's timestamp for this decision. It is recorded, never
    read from the clock. ``inputs`` must be JSON-safe, so the decision can be
    replayed from the log.
    """
    if not isinstance(action, str) or not action.strip():
        raise ValueError("a decision needs a named action")
    if not isinstance(at, str) or not at.strip():
        raise ValueError("a decision needs an 'at' stamp from the caller")
    if computation not in COMPUTATIONS:
        raise ValueError(f"unknown computation {computation!r}; "
                         f"known: {sorted(COMPUTATIONS)}")
    value = COMPUTATIONS[computation](inputs)

    if isinstance(value, Unknown):
        confidence = 0
        outcome = HALT if profile.strict else DISPLAY_ONLY
        reason = f"{value.code}: {value.reason}"
        result = to_result(value)
    else:
        confidence = value.confidence
        result = to_result(value, notes=auto_notes(value))
        if confidence < profile.threshold:
            outcome = HALT if profile.strict else DISPLAY_ONLY
            reason = (f"confidence {confidence} is below the {profile.threshold} "
                      f"that {action} needs")
        else:
            outcome = ALLOW
            reason = f"confidence {confidence} meets the {profile.threshold} that {action} needs"

    return Decision(profile=profile.name, strict=profile.strict, action=action,
                    at=at, computation=computation, inputs=dict(inputs),
                    confidence=confidence, threshold=profile.threshold,
                    outcome=outcome, reason=reason, result=result)


# ═══════════════════════════════════════════════
# The audit log: append-only, hash-chained JSON lines
# ═══════════════════════════════════════════════

class AuditError(Exception):
    """The log is broken, or a write was refused to keep it intact."""


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _hash_of(entry: Mapping[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()


def _read_lines(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return text.split("\n")[:-1] if text else []


class AuditLog:
    """Append-only decision log. One JSON object per line."""

    def __init__(self, path: str):
        self.path = path

    def append(self, decision: Decision) -> dict:
        report = self.verify()
        if not report["ok"]:
            raise AuditError(f"the log is broken at line {report['problems'][0][0]}; "
                             "refusing to append to it")
        entries = [json.loads(line) for line in _read_lines(self.path)]
        prev = entries[-1]["hash"] if entries else GENESIS
        entry = dict(decision.to_record())
        entry["seq"] = len(entries) + 1
        entry["prev_hash"] = prev
        entry["hash"] = _hash_of(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(_canon(entry) + "\n")
        return entry

    def entries(self) -> List[dict]:
        return [json.loads(line) for line in _read_lines(self.path)]

    def verify(self) -> dict:
        """Check every line: its sequence number, the hash of the line before it,
        and its own hash. Returns {"ok", "records", "problems": [(line, why)]}."""
        problems = []
        prev = GENESIS
        lines = _read_lines(self.path)
        for i, line in enumerate(lines, start=1):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                problems.append((i, "not valid JSON"))
                break
            if entry.get("seq") != i:
                problems.append((i, f"sequence number is {entry.get('seq')}, expected {i}"))
            if entry.get("prev_hash") != prev:
                problems.append((i, "prev_hash does not match the line before it"))
            if entry.get("hash") != _hash_of(entry):
                problems.append((i, "hash does not match the line's contents"))
            prev = entry.get("hash", "")
        return {"ok": not problems, "records": len(lines), "problems": problems}


def replay(path: str, profiles: Optional[Mapping[str, Profile]] = None) -> dict:
    """Recompute every recorded decision from its inputs and compare.

    A line matches only if its confidence, threshold, outcome, reason and full
    result are exactly what the decision produces now. Returns
    {"records", "mismatches": [(seq, field)]}. An empty mismatch list means the
    recorded decisions are exactly reproducible.
    """
    table = dict(PROFILES if profiles is None else profiles)
    mismatches: List[tuple] = []
    entries = [json.loads(line) for line in _read_lines(path)]
    for e in entries:
        profile = table.get(e["profile"])
        if profile is None:
            mismatches.append((e["seq"], "profile is not known to this replay"))
            continue
        d = decide(profile, e["action"], at=e["at"],
                   computation=e["computation"], inputs=e["inputs"])
        now = d.to_record()
        for field in ("confidence", "threshold", "outcome", "reason", "result", "strict"):
            if now[field] != e[field]:
                mismatches.append((e["seq"], field))
    return {"records": len(entries), "mismatches": mismatches}


__all__ = [
    "Profile", "DEFAULT", "FINANCIAL", "PROFILES",
    "ALLOW", "HALT", "DISPLAY_ONLY", "GENESIS",
    "record_of", "from_record", "COMPUTATIONS",
    "Decision", "decide", "AuditLog", "AuditError", "replay",
]
