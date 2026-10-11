#!/usr/bin/env python3
"""
repair.py — the forge fixing its own front ends, without being told.

Up to here the loop was half-closed. The forge could find a defect,
classify it, and carry a counterexample forever, but a person still
wrote every fix. This closes it: detect, localise, synthesise a repair,
verify it against everything already known, and adopt it only if it
strictly improves matters.

## What decides the repair

Not a guess. When one front end raises on an input, the others are
still standing there with an answer, so the repair asks them. If at
least pi = 3 of them agree on a verdict, that agreement is the target
the repair has to hit — the same consensus rule VOWELS.md already uses
for its oracle and the forge already uses for arbitration, pointed at
the implementation instead of the specification.

Where they do not agree, it **withholds**. A repair invented against no
agreed target would be the forge teaching itself a fact nobody
verified, which is the one thing this project exists to prevent.

## What a repair is allowed to be

Stated, because an unbounded repair space is how a self-modifying
system talks itself into anything:

  R1  totality shield   a component that raises is made to refuse
                        instead, with the defect class the others
                        agree on. Restores G1.
  R2  regenerate        the generated parser is re-emitted from the
                        current grammar.

That is the whole grammar of repairs. R1 does not claim to fix the
logic that raised — it restores the stated guarantee and pins the
input that exposed it, permanently, in the corpus. The root cause stays
visible and stays findable; what stops is the language violating its
own G1 while nobody is looking.

## What adoption requires

A candidate is adopted only when it fixes the defect **and changes
nothing else**: every input already known must produce the identical
verdict afterwards. That is what keeps a shield from quietly becoming
a way to make failures disappear — it cannot alter a passing case,
because a candidate that alters one is rejected.

Nothing is deleted. A superseded behaviour is recorded with what
replaced it and why, because conservation is a law here (VOWELS.md,
`obliterate`) and not a preference.

Codric Enterprise
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from contract import Fail, LexOut, ParseOut

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER_PATH = os.path.join(HERE, "repairs.json")

PI = 3                    # SEMANTICS.md 1.1 — floor(pi)
TWO_THIRDS = 2.0 / 3.0


# ═════════════════════════════════════════════
# Findings
# ═════════════════════════════════════════════

@dataclass
class Defect:
    """One component, one input, one thing that should not happen."""
    component: str
    stage: str                    # "lex" | "parse"
    src: str
    kind: str                     # "raises"
    detail: str
    target: Optional[str] = None  # verdict the others agree on
    witnesses: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"{self.component} {self.kind} on {self.src[:40]!r} "
                f"-> {self.detail}")


@dataclass
class Candidate:
    """A proposed repair, and what it would cost."""
    rule: str                     # "R1" | "R2"
    component: str
    stage: str
    defect_class: str
    rationale: str
    install: Callable[[], None]


@dataclass
class Outcome:
    candidate: Candidate
    fixed: bool
    collateral: List[str] = field(default_factory=list)

    @property
    def adopted(self) -> bool:
        return self.fixed and not self.collateral


# ═════════════════════════════════════════════
# R1 — the totality shield
# ═════════════════════════════════════════════

def shield(fn: Callable, stage: str, defect_class: str) -> Callable:
    """Wrap a component so an escaping exception becomes a refusal.

    Normal behaviour is untouched: only the exception path is
    intercepted, so a component that never raises is indistinguishable
    from its unshielded self. That is what makes the verification below
    meaningful rather than circular.
    """
    def shielded(arg):
        try:
            return fn(arg)
        except Exception:
            f = Fail(stage, defect_class, 0, 1)
            return LexOut(fail=f) if stage == "lex" else ParseOut(fail=f)

    shielded.__name__ = getattr(fn, "__name__", "component") + "_shielded"
    shielded.__doc__ = (f"Shielded by repair.py: an escaping exception "
                        f"becomes Fail({stage}/{defect_class}). "
                        f"Original: {getattr(fn, '__doc__', None)}")
    shielded._unshielded = fn          # conservation: the original survives
    shielded._shield = (stage, defect_class)
    return shielded


def is_shielded(fn: Callable) -> bool:
    return hasattr(fn, "_shield")


# ═════════════════════════════════════════════
# The ledger — nothing is deleted
# ═════════════════════════════════════════════

class RepairLedger:
    def __init__(self, path: str = LEDGER_PATH):
        self.path = path
        self.entries: List[dict] = []
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                self.entries = json.load(fh).get("repairs", [])
        except (OSError, ValueError):
            self.entries = []

    def save(self) -> None:
        with open(self.path, "w") as fh:
            json.dump({
                "note": "Repairs the forge made to its own front ends. "
                        "Each entry records what raised, what the other "
                        "witnesses agreed the answer should be, and the "
                        "input that exposed it. Nothing here is deleted; "
                        "a superseded repair is marked, not removed.",
                "repairs": self.entries,
            }, fh, indent=2)
            fh.write("\n")

    def record(self, defect: Defect, cand: Candidate,
               generation: int) -> None:
        self.entries.append({
            "generation": generation,
            "rule": cand.rule,
            "component": cand.component,
            "stage": cand.stage,
            "defect_class": cand.defect_class,
            "raised": defect.detail,
            "exposed_by": defect.src,
            "agreed_by": defect.witnesses,
            "target_verdict": defect.target,
            "rationale": cand.rationale,
            "superseded": False,
        })
        self.save()

    @property
    def active(self) -> List[dict]:
        return [e for e in self.entries if not e.get("superseded")]

    def apply(self, registry: Dict[str, Callable], stage: str
              ) -> Dict[str, Callable]:
        """Re-install every recorded shield for this stage.

        Repairs live on disk, not in memory, so a fix found in one run
        is still in force in the next one -- the same reason
        `ratified.json` exists.
        """
        out = dict(registry)
        for e in self.active:
            if e["stage"] != stage:
                continue
            name = e["component"]
            fn = out.get(name)
            if fn is None or is_shielded(fn):
                continue
            out[name] = shield(fn, stage, e["defect_class"])
        return out


# ═════════════════════════════════════════════
# The loop
# ═════════════════════════════════════════════

class SelfRepair:
    """detect -> localise -> synthesise -> verify -> adopt -> record.

    `probe(component_name, stage, src)` must return a verdict string, or
    raise nothing and return None if the component blew up. The forge
    injects it, which keeps this module free of any dependency on the
    forge itself and therefore testable on its own.
    """

    def __init__(self, lexers: Dict[str, Callable],
                 parsers: Dict[str, Callable],
                 verdicts: Callable[[str], Dict[str, Optional[str]]],
                 ledger: Optional[RepairLedger] = None,
                 verbose: bool = True):
        self.lexers = lexers
        self.parsers = parsers
        self.verdicts = verdicts       # src -> {pair_name: verdict|None}
        self.ledger = ledger or RepairLedger()
        self.verbose = verbose

    # ── detect + localise ──
    def scan(self, inputs: Sequence[str]) -> List[Defect]:
        """Find components that raise, and blame the right one.

        A lexer that blows up takes every pair it appears in with it; a
        parser does the same down its own column. So the component at
        fault is the one whose whole row or column is down while some
        other row and column are still standing.
        """
        found: Dict[Tuple[str, str], Defect] = {}

        for src in inputs:
            table = self.verdicts(src)
            crashed = {k for k, v in table.items() if v is None}
            if not crashed:
                continue

            alive = {k: v for k, v in table.items() if v is not None}
            for name in self.lexers:
                row = {k for k in table if k.split(" x ")[0] == name}
                if row and row <= crashed and not (crashed - row):
                    found.setdefault((name, "lex"), self._defect(
                        name, "lex", src, alive))
            for name in self.parsers:
                col = {k for k in table if k.split(" x ")[1] == name}
                if col and col <= crashed and not (crashed - col):
                    found.setdefault((name, "parse"), self._defect(
                        name, "parse", src, alive))
        return list(found.values())

    def _defect(self, name: str, stage: str, src: str,
                alive: Dict[str, str]) -> Defect:
        d = Defect(component=name, stage=stage, src=src,
                   kind="raises", detail="exception escaped the component")
        target, who = self._consensus(alive)
        d.target, d.witnesses = target, who
        return d

    @staticmethod
    def _consensus(alive: Dict[str, str]) -> Tuple[Optional[str], List[str]]:
        """The verdict the survivors agree on, on VOWELS.md's terms."""
        if not alive:
            return None, []
        groups: Dict[str, List[str]] = {}
        for who, verdict in alive.items():
            groups.setdefault(verdict, []).append(who)
        best_v, best = max(groups.items(), key=lambda kv: len(kv[1]))
        if len(best) >= PI and len(best) >= TWO_THIRDS * len(alive):
            return best_v, sorted(best)
        return None, []

    # ── synthesise ──
    def synthesize(self, d: Defect) -> List[Candidate]:
        if d.target is None:
            return []                       # withhold: no agreed target
        defect_class = self._class_of(d.target)
        if defect_class is None:
            return []

        registry = self.lexers if d.stage == "lex" else self.parsers

        def install(name=d.component, stage=d.stage, dc=defect_class,
                    reg=registry):
            reg[name] = shield(reg[name], stage, dc)

        return [Candidate(
            rule="R1", component=d.component, stage=d.stage,
            defect_class=defect_class,
            rationale=(f"{len(d.witnesses)} of the surviving front ends "
                       f"agree the answer is {d.target!r}; the shield "
                       f"makes {d.component} refuse with that defect "
                       f"class instead of raising, restoring G1"),
            install=install)]

    @staticmethod
    def _class_of(verdict: str) -> Optional[str]:
        """Pull the defect class out of a verdict like FAIL[lex/misbound]."""
        if not verdict.startswith("FAIL["):
            # The others accepted it. A shield cannot synthesise a tree,
            # so this is out of the stated repair grammar and is reported
            # rather than guessed at.
            return None
        try:
            return verdict[verdict.index("/") + 1:verdict.index("]")]
        except ValueError:
            return None

    # ── verify ──
    def verify(self, cand: Candidate, d: Defect,
               regression: Sequence[str]) -> Outcome:
        """Adopt only if it fixes this and disturbs nothing else."""
        before = {src: self.verdicts(src) for src in regression}
        cand.install()
        after = {src: self.verdicts(src) for src in regression}

        fixed = all(v is not None for v in self.verdicts(d.src).values())
        collateral = []
        for src in regression:
            for pair, was in before[src].items():
                now = after[src].get(pair)
                if was is not None and now != was:
                    collateral.append(f"{pair} on {src[:30]!r}: "
                                      f"{was[:28]!r} -> "
                                      f"{(now or 'crash')[:28]!r}")
        return Outcome(candidate=cand, fixed=fixed, collateral=collateral)

    # ── the whole thing ──
    def run(self, inputs: Sequence[str], regression: Sequence[str],
            generation: int = 0) -> Dict[str, Any]:
        report: Dict[str, Any] = {"defects": [], "adopted": [],
                                  "withheld": [], "rejected": []}
        for d in self.scan(inputs):
            report["defects"].append(str(d))
            if self.verbose:
                print(f"  defect    {d}")

            cands = self.synthesize(d)
            if not cands:
                why = ("no agreed target among the survivors"
                       if d.target is None else
                       "the others accept it; a shield cannot build a tree")
                report["withheld"].append(f"{d.component}: {why}")
                if self.verbose:
                    print(f"  WITHHELD  {d.component} — {why}")
                continue

            for cand in cands:
                out = self.verify(cand, d, regression)
                if out.adopted:
                    self.ledger.record(d, cand, generation)
                    report["adopted"].append(
                        f"{cand.rule} {cand.component} -> "
                        f"refuses with {cand.defect_class}")
                    if self.verbose:
                        print(f"  ADOPTED   {cand.rule} {cand.component} "
                              f"-> refuses with {cand.defect_class}")
                    break
                why = (f"changed {len(out.collateral)} other verdicts"
                       if out.collateral else "did not fix it")
                report["rejected"].append(f"{cand.component}: {why}")
                if self.verbose:
                    print(f"  REJECTED  {cand.component} — "
                          f"{len(out.collateral)} collateral changes")
        return report


__all__ = ["Defect", "Candidate", "Outcome", "SelfRepair", "RepairLedger",
           "shield", "is_shielded", "PI"]
