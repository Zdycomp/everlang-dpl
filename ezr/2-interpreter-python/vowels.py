#!/usr/bin/env python3
"""
vowels.py — Ever / Tapestry, the vowel operator families

    A   operates on trust        Any Assimilate Anchor Ascend
                                 Apply2All Auto-Didact
    E   the thread itself        the noun everything else acts on
    I   INTRODUCTION             brings code into being      — synthesis
    O   OWNERSHIP                takes control of what is    — selection
    U   UNDERSTANDING            deconstructs and attacks    — criticism

I, O and U close a loop, and the loop is what makes the system
self-generating rather than merely self-checking:

    understand  ->  undermine  ->  implement  ->  integrate
         ^                                            |
         |                                            v
    own  <-  obliterate  <-  optimize  <-  ultracode

Criticism finds the gap. Introduction fills it. Ownership decides what
survives. Nothing is deleted at any point: obliterate supersedes and
archives, because conservation is a law here and not a preference.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ever import (
    E, State, Defect, Lang,
    e_z, e_val, e_equiv, excel, a_anchor,
    E_ZERO, E_CERTAIN, E_EXECUTE_FLOOR, E_PI_WIDTH_WARN,
    E_PI_WIDTH_ENUMERATE, E_ASCEND_POINTS, E_INTAKE,
)
from abstract import (
    Lambda, Closure, DepthExceeded, a_anchor_fn, find_measure,
    E_DEPTH_CEILING, chain,
)


# ═════════════════════════════════════════════
# Specifications — what a synthesised function must satisfy
# ═════════════════════════════════════════════

@dataclass
class Spec:
    """Examples are the specification. Nothing else is."""
    name: str
    params: List[str]
    examples: List[Tuple[List[Any], Any]]
    notes: str = ""

    def arity(self) -> int:
        return len(self.params)


@dataclass
class Candidate:
    """A synthesised body and how it fared."""
    body: str
    passed: int = 0
    total: int = 0
    confidence: int = 0
    cost: int = 0            # syntactic length; ultracode minimises this
    error: str = ""

    @property
    def satisfies(self) -> bool:
        return self.total > 0 and self.passed == self.total

    @property
    def fitness(self) -> float:
        """Confidence earned per unit of complexity.

        Two candidates that both satisfy the spec are not equal: the
        shorter one claims less and is therefore worth more.
        """
        if not self.total:
            return 0.0
        return (self.confidence / max(1, self.cost)) * (self.passed / self.total)


# ═════════════════════════════════════════════
# The grammar the synthesiser searches
# ═════════════════════════════════════════════

CONSTANTS = ["0", "1", "2", "3", "10"]
BINOPS    = ["+", "-", "*"]
CMPS      = ["<=", "<", "==", ">="]


def templates(params: List[str], name: str, depth: int) -> List[str]:
    """Bounded enumeration. Deliberately small.

    This synthesises short arithmetic and singly-recursive functions from
    Examples. It is not a general program synthesiser and does not claim
    to be. The bound is the honest part: the search space is stated, so
    what it cannot reach is stated too.
    """
    out: List[str] = []
    p = params[0] if params else "x"
    q = params[1] if len(params) > 1 else None

    atoms = list(params) + CONSTANTS

    # depth 0: identity and constants
    out.extend(atoms)

    # depth 1: single binary operation
    if depth >= 1:
        for a in atoms:
            for op in BINOPS:
                for b in atoms:
                    out.append(f"{a} {op} {b}")

    # depth 2: nested arithmetic, kept narrow
    if depth >= 2:
        for a in params:
            for op1 in BINOPS:
                for b in CONSTANTS:
                    for op2 in BINOPS:
                        for c in atoms:
                            out.append(f"({a} {op1} {b}) {op2} {c}")

    # recursion: the shape that covers factorial, sum, power, fib-like
    if depth >= 2 and name:
        for cmp in CMPS:
            for k in ["0", "1", "2"]:
                for base in CONSTANTS + list(params):
                    for op in BINOPS:
                        for dec in ["1", "2"]:
                            out.append(
                                f"if {p} {cmp} {k} then {base} "
                                f"else {p} {op} {name}({p} - {dec})")
                            if q:
                                out.append(
                                    f"if {p} {cmp} {k} then {q} "
                                    f"else {name}({p} - {dec}, {q} {op} {p})")
    return out


# ═════════════════════════════════════════════
# I — INTRODUCTION.  Bringing code into being.
# ═════════════════════════════════════════════

def i_implement(spec: Spec, depth: int = 2,
                budget: int = 6000) -> Tuple[E, List[Candidate]]:
    """IMPLEMENT — synthesise a function that satisfies a specification.

    This is the self-generating core. Given only Examples, search the
    bounded grammar for a body that reproduces every one of them.

    Returns a thread holding the winning closure, plus every candidate
    tried, because the failures are corpus too.
    """
    tried: List[Candidate] = []
    winner: Optional[Candidate] = None

    for body in templates(spec.params, spec.name, depth)[:budget]:
        lam = Lambda()
        lam.define(spec.name, spec.params, body)

        # an anchored measure lets recursive candidates run deep enough
        # to be judged at all
        fp = lam.globals[spec.name]
        if isinstance(fp.value, Closure) and fp.value.recursive \
                and fp.value.measure:
            lam.globals[spec.name] = a_anchor(fp)

        c = Candidate(body=body, cost=len(body.replace(" ", "")))
        for args, want in spec.examples:
            c.total += 1
            try:
                if lam.example(spec.name, args, want):
                    c.passed += 1
            except (DepthExceeded, RecursionError):
                pass
            except Exception as exc:            # a candidate may be nonsense
                c.error = str(exc)[:60]
        fin = lam.globals.get(spec.name)
        c.confidence = fin.confidence if fin else 0
        tried.append(c)

        if c.satisfies and (winner is None or c.fitness > winner.fitness):
            winner = c

    if winner is None:
        best = max(tried, key=lambda t: t.passed, default=None)
        got = f"{best.passed}/{best.total}" if best else "0/0"
        return e_z(spec.name,
                   f"synthesis found nothing satisfying the spec "
                   f"(best was {got})", Defect.UNBOUND), tried

    lam = Lambda()
    lam.define(spec.name, spec.params, winner.body)
    # The search anchored recursive candidates in order to judge them at
    # all. The winner has to come back on the same footing, or it
    # under-reports the very evidence it was selected on.
    fp = lam.globals[spec.name]
    if isinstance(fp.value, Closure) and fp.value.recursive and fp.value.measure:
        lam.globals[spec.name] = a_anchor(fp)
    for args, want in spec.examples:
        lam.example(spec.name, args, want)
    p = lam.globals[spec.name]

    # ── generalisation, not just fit ──
    #
    # A function that reproduces every example can still be wrong
    # everywhere else. Found by the notebook batch: from the first four
    # primes the search returned n + f(n-2), which gives 2,3,5,7 exactly
    # and then 10 where 11 belongs, and reported 235/256 while doing it.
    #
    # The language already knows how to judge this. Poll the other
    # candidates that satisfied the same examples on inputs nobody
    # supplied. Where they agree, the shape is determined by the
    # evidence. Where they scatter, the evidence did not pin it down and
    # the confidence must say so rather than reporting the fit alone.
    agreement = _consensus(spec, [c.body for c in tried if c.satisfies])
    if agreement is not None and agreement < 1.0:
        capped = max(1, int(p.confidence * agreement))
        if capped < p.confidence:
            p = e_val(spec.name, p.value, capped)
            p.reason = (f"implemented from {len(spec.examples)} examples: "
                        f"{winner.body} | capped to {capped}: satisfying "
                        f"solutions agree on only {agreement:.0%} of unseen "
                        f"inputs")
            return p, tried

    p.reason = (f"implemented from {len(spec.examples)} examples: "
                f"{winner.body}")
    return p, tried


UNSEEN = [5, 6, 7, 8, 9, 12]


def _consensus(spec: Spec, bodies: List[str]) -> Optional[float]:
    """How far the satisfying solutions agree beyond the evidence.

    1.0 means every satisfying candidate returns the same thing on every
    unseen probe: the examples determined the function. Lower means they
    diverge, and the spec underdetermined the answer.

    Returns None when there is nothing to compare against, because one
    candidate cannot corroborate itself.
    """
    if len(bodies) < 2:
        return None

    # Count IDEAS, not strings. Three candidates that differ only in
    # their base case are one solution wearing three hats, and one
    # solution cannot corroborate itself. This is what let the first
    # four primes come back at 235/256 in the notebook batch.
    try:
        from syntax import distinct_skeletons
        n_ideas, _ = distinct_skeletons(bodies)
        if n_ideas < 2:
            return 0.0          # no independent support whatsoever
    except Exception:
        pass

    seen = {tuple(a) for a, _ in spec.examples}
    probes = [n for n in UNSEEN if (n,) not in seen][:5]
    if not probes:
        return None

    scores: List[float] = []
    for probe in probes:
        votes: Dict[Any, int] = {}
        for body in bodies[:24]:            # bounded: this runs per synthesis
            lam = Lambda()
            lam.define(spec.name, spec.params, body)
            fp = lam.globals[spec.name]
            if isinstance(fp.value, Closure) and fp.value.recursive \
                    and fp.value.measure:
                lam.globals[spec.name] = a_anchor(fp)
            args = [probe] + [1] * (spec.arity() - 1)
            try:
                out = lam.apply(lam.globals[spec.name],
                                [e_val(f"a{i}", a, E_CERTAIN)
                                 for i, a in enumerate(args)], {}, 0)
                if not out.is_z:
                    votes[out.value] = votes.get(out.value, 0) + 1
            except Exception:
                continue
        if votes:
            total = sum(votes.values())
            scores.append(max(votes.values()) / total)

    return sum(scores) / len(scores) if scores else None


def i_integrate(a: E, b: E, name: str) -> E:
    """INTEGRATE — merge two threads into one that answers for both.

    Agreement corroborates under the verified law. Disagreement does not
    get averaged into a comfortable middle; it is reported as the
    conflict it is.
    """
    if a.is_z or b.is_z:
        return e_z(name, "cannot integrate through Z",
                   a.defect if a.is_z else b.defect)

    if isinstance(a.value, Closure) and isinstance(b.value, Closure):
        merged = Closure(
            name=name, params=a.value.params,
            body=a.value.body, env=dict(a.value.env),
            examples_passed=a.value.examples_passed + b.value.examples_passed,
            examples_failed=a.value.examples_failed + b.value.examples_failed,
            measure=a.value.measure or b.value.measure,
            recursive=a.value.recursive or b.value.recursive)
        c = excel(a.confidence, b.confidence)
        r = e_val(name, merged, c)
        r.reason = f"integrated {a.ident} with {b.ident}, evidence pooled"
        return r

    if a.value == b.value:
        r = e_val(name, a.value, excel(a.confidence, b.confidence))
        r.reason = f"integrated: {a.ident} and {b.ident} agree, corroborated"
        return r

    lo, hi = sorted([a.confidence, b.confidence])
    r = e_equiv(name, lo, hi)
    r.reason = (f"integrated: {a.ident} and {b.ident} disagree; "
                f"held open as {lo}..{hi}")
    return r


def i_isolate(p: E, part: str, name: str) -> E:
    """ISOLATE — lift a sub-expression out for independent verification.

    An isolated fragment starts unverified no matter how trusted its
    parent was. Trust does not transfer by extraction; the fragment has
    not been tested on its own.
    """
    if not isinstance(p.value, Closure):
        return e_z(name, "can only isolate from a function", Defect.MISBOUND)
    if part not in p.value.body:
        return e_z(name, f"'{part}' does not occur in {p.ident}",
                   Defect.UNBOUND)

    lam = Lambda()
    used = [v for v in p.value.params if re.search(rf'\b{v}\b', part)]
    lam.define(name, used or p.value.params, part)
    q = lam.globals[name]
    q.reason = (f"isolated from {p.ident}; unverified on its own "
                f"regardless of its parent's standing")
    return q


def i_interject(p: E, observer: Callable[[E], None], name: str) -> E:
    """INTERJECT — place an observer in the path without altering it.

    Interjection must be semantically invisible. It sees; it does not
    touch. The returned thread is equal to the original in value and
    confidence, and that equality is asserted in the tests.
    """
    if p.is_z:
        observer(p)
        return p
    q = E(**{**p.__dict__})
    q.ident = name
    observer(p)
    q.reason = f"observed at {name}; value and confidence unchanged"
    return q


def i_inject(p: E, bindings: Dict[str, E], name: str) -> E:
    """INJECT — substitute bindings into a function's captured scope.

    The injected function is capped at the weakest injected binding. You
    cannot make a function more trustworthy by feeding it something you
    trust less.
    """
    if not isinstance(p.value, Closure):
        return e_z(name, "can only inject into a function", Defect.MISBOUND)

    c = p.value
    env = dict(c.env)
    env.update(bindings)
    merged = Closure(name=name, params=c.params, body=c.body, env=env,
                     examples_passed=0, examples_failed=0,
                     measure=c.measure, recursive=c.recursive)
    floor = chain([p] + list(bindings.values()))
    r = e_val(name, merged, floor)
    r.reason = (f"injected {', '.join(bindings)} into {p.ident}; "
                f"capped at {floor} by the weakest binding")
    return r


# ═════════════════════════════════════════════
# O — OWNERSHIP.  Taking control of what exists.
# ═════════════════════════════════════════════

@dataclass
class Ledger:
    """The archive of what was owned, superseded and optimised.

    Obliterate does not delete. Conservation is a law in Ever, so the
    strongest thing available is supersession with the record kept.
    """
    owned: List[E] = field(default_factory=list)
    superseded: List[E] = field(default_factory=list)
    generations: int = 0


def o_own(p: E, ledger: Ledger) -> E:
    """OWN — claim accountability for a thread.

    Ownership is anchoring plus a record. An owned thread has someone
    answering for it, and the archive can say who and when.
    """
    if not p.is_cleared:
        return e_z(p.ident, "cannot own an uncleared thread",
                   p.defect or Defect.UNBOUND)
    q = a_anchor_fn(p) if isinstance(p.value, Closure) else a_anchor(p)
    if q.is_z:
        return q
    ledger.owned.append(q)
    q.reason = f"owned under anchor {q.anchor_id}; entered the ledger"
    return q


def o_overcome(broken: E, working: E, spec: Spec) -> Tuple[E, List[Candidate]]:
    """OVERCOME — surpass a failing thread, do not merely patch it.

    Emulate borrows a neighbour's pattern at a discount. Overcome is the
    stronger move: re-synthesise against the spec and keep the result
    only if it beats what was already there. If it cannot beat it, it
    says so rather than shipping a lateral move.
    """
    fresh, tried = i_implement(spec)
    if fresh.is_z:
        return e_z(broken.ident,
                   f"could not overcome: {fresh.reason}", Defect.UNBOUND), tried
    if fresh.confidence <= max(broken.confidence, working.confidence):
        return e_z(broken.ident,
                   f"synthesis reached {fresh.confidence}, not beating "
                   f"{max(broken.confidence, working.confidence)}",
                   Defect.MISBOUND), tried
    fresh.reason = (f"overcame {broken.ident} at {broken.confidence} "
                    f"with a fresh implementation at {fresh.confidence}")
    return fresh, tried


def o_obliterate(p: E, by: E, ledger: Ledger) -> E:
    """OBLITERATE — supersede. Never delete.

    The superseded thread becomes an EError: a boundary marker recording
    where the previous best stood and what replaced it. That is the most
    forceful operation conservation permits, and it is still not
    destruction.
    """
    marker = E(ident=p.ident, value=p.value, state=State.ERROR,
               defect=Defect.OVERBOUND, confidence=E_ZERO,
               lo=p.confidence, hi=p.confidence,
               reason=f"superseded by {by.ident} at {by.confidence}/256")
    ledger.superseded.append(marker)
    return marker


def o_optimize(cands: List[Candidate], spec: Spec) -> Tuple[E, Candidate]:
    """OPTIMIZE — choose by confidence earned per unit of complexity.

    Among candidates that all satisfy the spec, the shortest wins. A
    longer program that does the same work claims more and is worth
    less.
    """
    winners = [c for c in cands if c.satisfies]
    if not winners:
        return e_z(spec.name, "nothing satisfies the spec to optimise",
                   Defect.UNBOUND), Candidate(body="", cost=0)

    best = max(winners, key=lambda c: c.fitness)
    lam = Lambda()
    lam.define(spec.name, spec.params, best.body)
    fp = lam.globals[spec.name]
    if isinstance(fp.value, Closure) and fp.value.recursive and fp.value.measure:
        lam.globals[spec.name] = a_anchor(fp)
    for args, want in spec.examples:
        lam.example(spec.name, args, want)
    p = lam.globals[spec.name]
    p.reason = (f"optimised: {len(winners)} satisfying candidates, "
                f"kept cost {best.cost} at fitness {best.fitness:.2f}")
    return p, best


# ═════════════════════════════════════════════
# U — UNDERSTANDING.  Deconstruction and attack.
# ═════════════════════════════════════════════

def u_understand(p: E) -> E:
    """UNDERSTAND — derive a structural account of a thread."""
    if p.is_z:
        r = e_val(p.ident + "_understanding",
                  f"Z: {p.reason}", 200)
        r.reason = "understood as unknown, with its stated cause"
        return r

    if isinstance(p.value, Closure):
        c = p.value
        total = c.examples_passed + c.examples_failed
        acct = (f"fn {c.name}({', '.join(c.params)}) = {c.body} | "
                f"recursive={c.recursive} measure={c.measure} | "
                f"evidence {c.examples_passed}/{total} | "
                f"confidence {p.confidence}/256 | "
                f"{'anchored' if p.anchor_id else 'unanchored'} | "
                f"depth {'unbounded' if p.anchor_id and c.measure else E_DEPTH_CEILING}")
    else:
        acct = (f"{p.type_name()} {p.ident} = {p.value!r} | "
                f"confidence {p.confidence}/256 | state {p.state.name} | "
                f"{'executable' if p.can_execute else 'below the floor'}")

    r = e_val(p.ident + "_understanding", acct, 220)
    r.reason = "structural account derived from the thread itself"
    return r


ADVERSARIAL = [0, 1, -1, 2, 7, -7, 100, 1000]


def u_undermine(p: E, spec: Spec, probes: Optional[List[int]] = None) -> E:
    """UNDERMINE — attack a thread and report where it fails.

    This is the critic in the loop. Without it the system only ever
    confirms itself, and a system that cannot be surprised does not
    evolve.

    Returns Z when nothing breaks it, because "no counterexample found"
    is not a proof of correctness and must not be dressed as one.
    """
    if not isinstance(p.value, Closure):
        return e_z(p.ident, "can only undermine a function", Defect.MISBOUND)

    lam = Lambda()
    lam.define(spec.name, p.value.params, p.value.body)
    if p.anchor_id:
        lam.globals[spec.name] = a_anchor(lam.globals[spec.name])

    breaks: List[str] = []
    for probe in (probes or ADVERSARIAL):
        args = [probe] + [1] * (spec.arity() - 1)
        try:
            out = lam.apply(lam.globals[spec.name],
                            [e_val(f"a{i}", a, E_CERTAIN)
                             for i, a in enumerate(args)], {}, 0)
            if out.is_z:
                breaks.append(f"{args} -> Z ({out.reason})")
        except DepthExceeded:
            breaks.append(f"{args} -> depth exceeded")
        except RecursionError:
            breaks.append(f"{args} -> runaway recursion")
        except Exception as exc:
            breaks.append(f"{args} -> {type(exc).__name__}")

    if not breaks:
        return e_z(p.ident + "_attack",
                   "no counterexample found, which is not a proof",
                   Defect.UNBOUND)

    r = e_val(p.ident + "_attack", breaks, min(240, 120 + 20 * len(breaks)))
    r.reason = f"undermined: {len(breaks)} of {len(probes or ADVERSARIAL)} probes broke it"
    return r


def u_unwrap(p: E) -> List[E]:
    """UNWRAP — decompose a thread into its constituents.

    The inverse of integrate. Each part comes out unverified, for the
    same reason isolate does: a piece has not been tested as a piece.
    """
    if not isinstance(p.value, Closure):
        return [p]
    body = p.value.body
    parts: List[E] = []

    m = re.match(r'^if\s+(.+?)\s+then\s+(.+?)\s+else\s+(.+)$', body)
    if m:
        for label, frag in (("condition", m.group(1)),
                            ("then", m.group(2)), ("else", m.group(3))):
            q = e_val(f"{p.ident}.{label}", frag.strip(), E_INTAKE)
            q.reason = f"unwrapped from {p.ident}, unverified as a part"
            parts.append(q)
        return parts

    for i, frag in enumerate(re.split(r'\s*[-+*/]\s*', body)):
        if frag.strip():
            q = e_val(f"{p.ident}.{i}", frag.strip(), E_INTAKE)
            q.reason = f"unwrapped from {p.ident}, unverified as a part"
            parts.append(q)
    return parts or [p]


def u_ultracode(p: E, spec: Spec) -> E:
    """ULTRACODE — compress to the shortest form that still satisfies.

    Minimum description length. The shortest program that reproduces the
    evidence is the one that assumes least, and assuming least is what
    generalises.
    """
    if not isinstance(p.value, Closure):
        return e_z(p.ident, "can only ultracode a function", Defect.MISBOUND)

    original = len(p.value.body.replace(" ", ""))
    _, tried = i_implement(spec)
    sat = [c for c in tried if c.satisfies]
    if not sat:
        return e_z(p.ident, "no satisfying form to compress to",
                   Defect.UNBOUND)

    shortest = min(sat, key=lambda c: c.cost)
    if shortest.cost >= original:
        q = E(**{**p.__dict__})
        q.reason = (f"already minimal at cost {original}; "
                    f"nothing shorter satisfies the evidence")
        return q

    lam = Lambda()
    lam.define(spec.name, spec.params, shortest.body)
    fp2 = lam.globals[spec.name]
    if isinstance(fp2.value, Closure) and fp2.value.recursive and fp2.value.measure:
        lam.globals[spec.name] = a_anchor(fp2)
    for args, want in spec.examples:
        lam.example(spec.name, args, want)
    q = lam.globals[spec.name]
    q.reason = (f"ultracoded {original} -> {shortest.cost} "
                f"({shortest.body})")
    return q


# ═════════════════════════════════════════════
# The loop — self-generating, ever-evolving
# ═════════════════════════════════════════════

@dataclass
class Generation:
    n: int
    body: str
    confidence: int
    cost: int
    attacks: int
    note: str


class Evolver:
    """U -> I -> O, repeated, with the archive carried forward.

    Each generation understands the incumbent, attacks it, synthesises
    against the spec, compresses, and keeps the winner only if it beats
    what stood before. Losers are superseded into the ledger rather than
    discarded, so the record of what was tried survives the thing that
    won.
    """

    def __init__(self, spec: Spec, trace: bool = False):
        self.spec = spec
        self.ledger = Ledger()
        self.history: List[Generation] = []
        self.incumbent: Optional[E] = None
        self.satisfying: List[str] = []
        self.trace = trace

    def absorb(self, attack: E) -> int:
        """Turn a counterexample into a constraint.

        THIS is what makes the loop evolutionary rather than repetitive.
        A deterministic search re-run returns the same answer forever;
        the only thing that can change the next generation is a changed
        specification. So every probe that broke the incumbent becomes a
        new Example the next generation has to satisfy.

        Criticism does not merely score the work. It writes the next
        spec.
        """
        if attack.is_z or not isinstance(attack.value, list):
            return 0
        added = 0
        for line in attack.value:
            m = re.match(r'^\[(-?\d+)', str(line))
            if not m:
                continue
            probe = int(m.group(1))
            if any(args and args[0] == probe for args, _ in self.spec.examples):
                continue
            truth = self.oracle(probe)
            if truth is None:
                continue
            self.spec.examples.append(([probe], truth))
            added += 1
        return added

    def oracle(self, n: int) -> Optional[Any]:
        """Ground truth for a new probe, by consensus.

        Asking the incumbent is circular: the probes that matter are
        exactly the ones that broke it. So instead poll every candidate
        that satisfied the known examples. These were derived
        independently and agree on everything verified so far; where
        they also agree on a new input, that agreement is corroboration
        in precisely the sense the language already defines.

        Where they disagree, withhold. Inventing an expected answer
        would teach the corpus a fact nobody verified, which is the one
        thing Ever exists to prevent.
        """
        votes: Dict[Any, int] = {}
        for body in self.satisfying:
            lam = Lambda()
            lam.define(self.spec.name, self.spec.params, body)
            fp = lam.globals[self.spec.name]
            if isinstance(fp.value, Closure) and fp.value.recursive \
                    and fp.value.measure:
                lam.globals[self.spec.name] = a_anchor(fp)
            try:
                out = lam.apply(lam.globals[self.spec.name],
                                [e_val("a", n, E_CERTAIN)], {}, 0)
                if not out.is_z:
                    votes[out.value] = votes.get(out.value, 0) + 1
            except Exception:
                continue

        if not votes:
            return None
        total = sum(votes.values())
        value, count = max(votes.items(), key=lambda kv: kv[1])
        # the same bar the rest of the language uses for evidence
        if count < E_ASCEND_POINTS or count / total < 0.66:
            return None
        return value

    def step(self) -> Generation:
        n = len(self.history)

        # I — introduce
        fresh, tried = i_implement(self.spec)
        self.satisfying = [c.body for c in tried if c.satisfies]
        if fresh.is_z:
            g = Generation(n, "", 0, 0, 0, fresh.reason)
            self.history.append(g)
            return g

        # O — optimise across everything tried
        best, cand = o_optimize(tried, self.spec)
        if best.is_z:
            best, cand = fresh, Candidate(
                body=fresh.value.body,
                cost=len(fresh.value.body.replace(" ", "")))

        # U — compress, then attack
        tighter = u_ultracode(best, self.spec)
        if not tighter.is_z:
            best = tighter
        attack = u_undermine(best, self.spec)
        n_attacks = 0 if attack.is_z else len(attack.value)

        # O — own the winner, supersede the incumbent
        note = "first generation"
        if self.incumbent is not None:
            if best.confidence > self.incumbent.confidence or \
               (best.confidence == self.incumbent.confidence and
                    cand.cost < len(self.incumbent.value.body.replace(" ", ""))):
                o_obliterate(self.incumbent, best, self.ledger)
                note = f"superseded generation {n - 1}"
            else:
                note = "incumbent held; no improvement found"
                best = self.incumbent

        owned = o_own(best, self.ledger)
        self.incumbent = owned if not owned.is_z else best
        self.ledger.generations = n + 1

        # U feeds I: every counterexample becomes a constraint on the
        # next generation, so the search that runs next is not the
        # search that ran before.
        learned = self.absorb(attack)
        if learned:
            note += f"; absorbed {learned} counterexample(s)"

        body = best.value.body if isinstance(best.value, Closure) else ""
        g = Generation(n, body, best.confidence,
                       len(body.replace(" ", "")), n_attacks, note)
        self.history.append(g)
        if self.trace:
            print(f"  gen {n}: {body}  @{best.confidence}  {note}")
        return g

    def run(self, generations: int = 3) -> List[Generation]:
        for _ in range(generations):
            self.step()
        return self.history

    def report(self) -> str:
        out = ["", "  evolution", "  " + "\u2500" * 62]
        out.append(f"  {'gen':<5}{'conf':>6}{'cost':>6}{'atk':>5}  body")
        for g in self.history:
            body = g.body if len(g.body) <= 40 else g.body[:37] + "..."
            out.append(f"  {g.n:<5}{g.confidence:>6}{g.cost:>6}"
                       f"{g.attacks:>5}  {body}")
        out.append("")
        out.append(f"  owned {len(self.ledger.owned)}   "
                   f"superseded {len(self.ledger.superseded)}   "
                   f"generations {self.ledger.generations}")
        out.append("  nothing was deleted; superseded threads are boundary "
                   "markers")
        return "\n".join(out)


# ═════════════════════════════════════════════
# Demonstration
# ═════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 66)
    print("EVER — the vowel operators, running")
    print("=" * 66)

    spec = Spec("fact", ["n"], [([1], 1), ([2], 2), ([3], 6), ([4], 24)])

    print("\n\u25b8 I — IMPLEMENT: synthesise from examples alone\n")
    print(f"  spec: {spec.name}({', '.join(spec.params)}) from "
          f"{len(spec.examples)} examples, no body given")
    fn, tried = i_implement(spec)
    sat = [c for c in tried if c.satisfies]
    print(f"  searched {len(tried)} candidates, {len(sat)} satisfied")
    if not fn.is_z:
        print(f"  synthesised: {fn.value.body}")
        print(f"  confidence : {fn.confidence}/256")

    print("\n\u25b8 U — UNDERSTAND\n")
    print("  " + u_understand(fn).value)

    print("\n\u25b8 U — UNDERMINE: attack it\n")
    atk = u_undermine(fn, spec)
    if atk.is_z:
        print("  " + atk.reason)
    else:
        print(f"  {atk.reason}")
        for b in atk.value[:4]:
            print(f"    {b}")

    print("\n\u25b8 U — ULTRACODE: compress\n")
    print("  " + u_ultracode(fn, spec).reason)

    print("\n\u25b8 O — OWN\n")
    ledger = Ledger()
    print("  " + o_own(fn, ledger).reason)

    print("\n\u25b8 The loop\n")
    ev = Evolver(spec)
    ev.run(3)
    print(ev.report())
    print()
