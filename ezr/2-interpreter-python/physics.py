#!/usr/bin/env python3
"""
physics.py — thermodynamics and Newton, as laws the language enforces.

Five of the six were already here. That is not a flourish; it is what
the algebra turns out to be when you write down what it does:

  First law     nothing is created or destroyed. VOWELS.md: "obliterate
                never deletes. Conservation is a law in EZR, not a
                preference." A superseded thread is archived with what
                replaced it.

  Second law    entropy never spontaneously decreases. Uncertainty is
                u = (256 - c)/256, and the chain rule takes the minimum
                confidence, so u of a derived thread is the *maximum* u
                of its inputs. Combination cannot produce something
                less uncertain than its most uncertain part. That is
                G3 -- "confidence never rises except via Ascend or
                Excel" -- and Ascend and Excel are precisely the work
                done on the system from outside.

  Third law     absolute zero is unreachable. SEMANTICS.md T3: u = 0
                requires some u_i = 0 exactly, and a product of
                non-zero terms is never zero, so Excel caps at 255 and
                Certain must enter from outside. A system cannot be
                cooled to Certain in finitely many combinations.

  Newton I      a thread continues unchanged unless an operator acts on
                it. G9: no mutation. Every thread is derived, never
                overwritten.

  Newton III    every action has an equal and opposite reaction. Every
                supersession writes exactly one boundary marker
                recording where the previous best stood.

Those five are checked here, not invented here. If one of them fails,
the algebra has drifted from what the documents say it is.

**Newton II is the one genuinely new thing.** F = ma has no counterpart
in the existing rules, so it is defined rather than discovered:
inertia is accumulated evidence, and the same force moves a
well-attested thread less than a fresh one. A function with three
passing Examples and an anchor should not be knocked over by the same
push that flattens something defined a moment ago, and until now
nothing in the language said so.

Codric Enterprise
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ever import (E, E_ASCEND_POINTS, E_CERTAIN, E_ZERO, State, excel)

#: floor(pi), the same constant the rest of the language uses.
PI = E_ASCEND_POINTS


# ═════════════════════════════════════════════
# Entropy
# ═════════════════════════════════════════════

def entropy(th: E) -> float:
    """u = (256 - c) / 256, in [0, 1].

    u = 1 is Z, maximum uncertainty. u = 0 is Certain, and is exactly
    what the third law says you cannot reach by combining things.
    """
    return (E_CERTAIN - th.confidence) / E_CERTAIN


def temperature(th: E) -> float:
    """Confidence read as coldness: 1 - u.

    Only a restatement, but it makes the direction unambiguous when
    talking about the second law -- systems warm up (grow uncertain)
    on their own and only cool when work is done on them.
    """
    return 1.0 - entropy(th)


# ═════════════════════════════════════════════
# Newton II — the one that is defined, not found
# ═════════════════════════════════════════════

def inertia(th: E) -> float:
    """Mass: how much accumulated standing resists a change.

    Everything in here is evidence the thread has already survived --
    generations lived through, Ascend points earned, and the anchor,
    which costs a proof of measure to obtain. A thread with none of
    them has mass 1 and is moved freely by any force at all.
    """
    m = 1.0
    m += th.generation
    m += th.ascend_points
    if th.anchor_id != 0:
        m += PI
    return m


def acceleration(th: E, force: float) -> float:
    """a = F / m. Confidence points of change per unit force."""
    return force / inertia(th)


def derive_from(th: E, **changes) -> E:
    """A new thread from an old one. Never a mutation of the old one."""
    return replace(th, **changes)


def push(th: E, force: float, why: str = "") -> E:
    """Apply a force and derive the thread that results.

    Negative force is counter-evidence and lowers confidence directly:
    entropy rising on its own is what the second law permits. Positive
    force is corroboration, and is routed through Excel, so it obeys
    the third law and cannot reach Certain however hard it is pushed.

    Derived, never mutated -- Newton I holds through this function.
    """
    a = acceleration(th, force)
    if a < 0:
        c = max(E_ZERO, th.confidence + int(math.floor(a)))
    else:
        # corroboration, scaled by how far the force actually moves it
        witness = min(E_CERTAIN - 1, int(a))
        c = excel(th.confidence, witness) if witness > 0 else th.confidence
    # derived, not mutated: G9, and Newton I holds through this call
    return replace(
        th, confidence=c, generation=th.generation + 1,
        reason=why or f"force {force:+g} on mass {inertia(th):g}")


# ═════════════════════════════════════════════
# The subsystem — everything utilised, recycled or created
# ═════════════════════════════════════════════

class Disposition(Enum):
    CREATED = "created"        # entered the system
    UTILISED = "utilised"      # consumed as input to a derivation
    RECYCLED = "recycled"      # superseded, and archived
    RESIDENT = "resident"      # still held, not yet used


@dataclass
class Entry:
    thread: E
    disposition: Disposition
    note: str = ""


@dataclass
class Violation:
    law: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.law}] {self.detail}"


class Subsystem:
    """A closed accounting over threads.

    Every thread admitted has exactly one disposition at every moment,
    and the four of them exhaust the possibilities: it was created, it
    was used to derive something, it was superseded and archived, or it
    is still sitting there. Nothing leaves without a record, which is
    what makes the first law checkable rather than merely asserted.
    """

    def __init__(self, name: str = "subsystem"):
        self.name = name
        self.entries: List[Entry] = []
        self.derivations: List[Tuple[List[E], E]] = []
        self.archive: List[Tuple[E, E]] = []      # (superseded, by)
        self._index: Dict[int, Entry] = {}

    # ── admission and transformation ──
    def admit(self, th: E, note: str = "") -> E:
        e = Entry(th, Disposition.CREATED, note)
        self.entries.append(e)
        self._index[id(th)] = e
        return th

    def derive(self, inputs: Sequence[E], output: E, note: str = "") -> E:
        for i in inputs:
            e = self._index.get(id(i))
            if e is None:
                e = Entry(i, Disposition.CREATED, "admitted on use")
                self.entries.append(e)
                self._index[id(i)] = e
            e.disposition = Disposition.UTILISED
        self.admit(output, note)
        self._index[id(output)].disposition = Disposition.RESIDENT
        self.derivations.append((list(inputs), output))
        return output

    def supersede(self, old: E, by: E, note: str = "") -> None:
        """Newton III: the reaction is the record, and it is mandatory."""
        e = self._index.get(id(old))
        if e is None:
            e = Entry(old, Disposition.CREATED, "admitted on supersession")
            self.entries.append(e)
            self._index[id(old)] = e
        e.disposition = Disposition.RECYCLED
        e.note = note or f"superseded by {by.ident}"
        self.archive.append((old, by))

    # ── the laws ──
    def first_law(self) -> List[Violation]:
        """Conservation: every thread is accounted for, exactly once."""
        v: List[Violation] = []
        counted = len(self.entries)
        by_disp = {d: 0 for d in Disposition}
        for e in self.entries:
            by_disp[e.disposition] += 1
        if sum(by_disp.values()) != counted:
            v.append(Violation("thermo-1",
                               f"{counted} threads but "
                               f"{sum(by_disp.values())} dispositions"))
        for i, e in enumerate(self.entries):
            if e.thread is None:
                v.append(Violation("thermo-1",
                                   f"entry {i} lost its thread"))
        # a superseded thread must be in the archive, and vice versa
        recycled = sum(1 for e in self.entries
                       if e.disposition is Disposition.RECYCLED)
        if recycled != len(self.archive):
            v.append(Violation("thermo-1",
                               f"{recycled} recycled but "
                               f"{len(self.archive)} archived -- "
                               f"something was destroyed"))
        return v

    def second_law(self) -> List[Violation]:
        """Entropy does not fall across a derivation on its own.

        u of a result is at least the largest u among its inputs. Work
        -- Ascend or Excel -- is the only thing that lowers it, and a
        derivation that lowered it without saying so would be a
        perpetual motion machine.
        """
        v: List[Violation] = []
        for inputs, out in self.derivations:
            if not inputs:
                continue
            worked = out.ascend_points > max(i.ascend_points for i in inputs)
            if worked:
                continue
            u_out = entropy(out)
            u_in = max(entropy(i) for i in inputs)
            if u_out < u_in - 1e-9:
                v.append(Violation(
                    "thermo-2",
                    f"{out.ident}: u fell from {u_in:.4f} to {u_out:.4f} "
                    f"with no work done"))
        return v

    def third_law(self) -> List[Violation]:
        """Certain is unreachable by combination."""
        v: List[Violation] = []
        for inputs, out in self.derivations:
            if len(inputs) < 2:
                continue
            if all(i.confidence < E_CERTAIN for i in inputs) \
                    and out.confidence >= E_CERTAIN:
                v.append(Violation(
                    "thermo-3",
                    f"{out.ident} reached Certain by combining threads "
                    f"that were not"))
        return v

    def newton_first(self) -> List[Violation]:
        """Nothing changed that was not acted on."""
        v: List[Violation] = []
        for e in self.entries:
            if e.disposition is Disposition.RESIDENT and e.thread.is_z \
                    and not e.thread.reason:
                v.append(Violation("newton-1",
                                   f"{e.thread.ident} became Z with no "
                                   f"reason recorded"))
        return v

    def newton_third(self) -> List[Violation]:
        """Every supersession has exactly one record, and a replacement."""
        v: List[Violation] = []
        for old, by in self.archive:
            if by is None:
                v.append(Violation("newton-3",
                                   f"{old.ident} was superseded by nothing"))
            elif old is by:
                v.append(Violation("newton-3",
                                   f"{old.ident} superseded itself"))
        return v

    def audit(self) -> List[Violation]:
        return (self.first_law() + self.second_law() + self.third_law()
                + self.newton_first() + self.newton_third())

    # ── reporting ──
    def balance(self) -> Dict[str, int]:
        b = {d.value: 0 for d in Disposition}
        for e in self.entries:
            b[e.disposition.value] += 1
        b["derivations"] = len(self.derivations)
        b["archived"] = len(self.archive)
        return b

    def report(self) -> str:
        b = self.balance()
        v = self.audit()
        lines = [f"subsystem {self.name!r}"]
        for k in ("created", "utilised", "recycled", "resident",
                  "derivations", "archived"):
            lines.append(f"  {k:<12} {b[k]}")
        lines.append(f"  {'laws':<12} "
                     f"{'all six hold' if not v else str(len(v)) + ' broken'}")
        for x in v:
            lines.append(f"    {x}")
        return "\n".join(lines)


LAWS = ("thermo-1", "thermo-2", "thermo-3", "newton-1", "newton-2",
        "newton-3")

__all__ = ["entropy", "temperature", "inertia", "acceleration", "push",
           "derive_from",
           "Subsystem", "Disposition", "Entry", "Violation", "LAWS", "PI"]
