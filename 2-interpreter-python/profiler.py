#!/usr/bin/env python3
"""
profiler.py — Ever / Tapestry, the Dynamic Profiler

═══════════════════════════════════════════════════════════════
WHAT THIS IS FOR
═══════════════════════════════════════════════════════════════

Ever exists to carry a beginner from where mainstream tooling left
them in the early 2000s to where it is now. The gap is not that
people cannot write `x = 1`. It is that nobody tells them what to
reach for next, so they stay on the constructs they already know and
the language never opens up.

Fixed difficulty settings do not solve this. "Beginner mode" is a
box someone ticks once and never revisits, and it is wrong the day
after they tick it.

So the system watches what they actually write. Every semantic pass
classifies the constructs in the source, and a Proficiency Score
moves with the evidence. The score is not a grade. It drives one
decision: HOW MUCH SCAFFOLDING TO SHOW. A novice gets worked
examples and full explanations. A fluent user gets the error and
nothing else, because the explanation is noise to them.

═══════════════════════════════════════════════════════════════
DESIGN DECISIONS
═══════════════════════════════════════════════════════════════

1. THE SCORE IS 0..256, NOT 0..100.
   Same scale as confidence. Ever already means one thing by
   "how much do we trust this on a 0..256 scale", and proficiency
   is exactly that claim about the user's command of the language.
   Two scales would have been two vocabularies for one idea.

2. IT MOVES BY EWMA, NOT LIFETIME AVERAGE.
   A lifetime average freezes. Someone who wrote 400 trivial lines
   in week one can never be read as advanced no matter what they
   write in week ten. Exponentially weighted moving average lets
   recent evidence dominate while keeping history as ballast.

3. IT RISES FASTER THAN IT FALLS (asymmetric alpha).
   Writing something hard is strong evidence you can. Writing
   something easy is weak evidence you cannot — experts write
   `let x = 1` constantly. So α_up > α_down. Without this, a
   fluent user who writes one simple script gets demoted and
   suddenly gets beginner scaffolding, which is insulting and
   makes the whole feature feel broken.

4. DIVERSITY COUNTS SEPARATELY FROM DIFFICULTY, BUT DOES NOT
   OUTRANK IT.
   Two distinct properties, deliberately not merged:

     - Repetition must not inflate. Writing recursion forty times is
       the same evidence as writing it once: a pasted snippet is one
       fact about its author, not forty. This falls out of scoring
       difficulty as a weighted MEAN, so counts cancel.
     - Range breaks ties WITHIN a tier. Six different intermediate
       constructs beat one intermediate construct repeated, because
       breadth at a level is what command of that level looks like.

   What diversity does NOT do is beat difficulty across tiers. A
   program that only recurses still outscores a broad sweep of
   intermediate work, and should: recursion is evidence of something
   the intermediate set does not demonstrate. An earlier draft of
   this module claimed the opposite and the test suite caught it.

5. UNUSED CONSTRUCTS ARE THE OUTPUT THAT MATTERS.
   The score tunes the interface. The construct-gap list is what
   actually helps: "you have never used a comparison operator" is
   the single most useful sentence this module can produce.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ─────────────────────────────────────────────
# SCALE — shared with confidence, deliberately
# ─────────────────────────────────────────────
P_MAX      = 256      # ceiling, same as E_CERTAIN
P_MIN      = 0
P_START    = 64       # where a brand new user begins: low, not zero.
                      # Zero would imply "we know they know nothing",
                      # which is a claim we have no evidence for.

ALPHA_UP   = 0.30     # how fast the score rises on strong evidence
ALPHA_DOWN = 0.10     # how slowly it falls on weak evidence
                      # 3:1 asymmetry — see design decision 3


class Tier(IntEnum):
    """What a construct demonstrates about its author."""
    SIMPLE       = 1   # you can store and show a value
    INTERMEDIATE = 2   # you can branch, compare, and factor out a function
    ADVANCED     = 3   # you can recurse, compose, and reason about trust

    @property
    def label(self) -> str:
        return {1: "simple", 2: "intermediate", 3: "advanced"}[int(self)]


@dataclass(frozen=True)
class Construct:
    """One thing a programmer can do, and what doing it demonstrates.

    weight separates constructs INSIDE a tier. Recursion and
    confidence-handling are both tier 3, but recursion is the harder
    idea and should move the score further.
    """
    key:     str
    tier:    Tier
    weight:  float
    label:   str
    teaches: str        # what mastering this unlocks — shown to the user


# ─────────────────────────────────────────────
# THE TAXONOMY
#
# Every construct Ever's semantic pass can observe, with its tier.
# This table is the whole judgment of the module; everything else is
# arithmetic over it. It is a table so it can be argued with and
# edited without touching logic.
# ─────────────────────────────────────────────
TAXONOMY: Dict[str, Construct] = {c.key: c for c in [
    # ── TIER 1: SIMPLE ────────────────────────────────────────
    Construct("lit_int",     Tier.SIMPLE, 1.0, "integer literal",
              "storing a whole number"),
    Construct("lit_real",    Tier.SIMPLE, 1.0, "decimal literal",
              "storing a fractional number"),
    Construct("lit_text",    Tier.SIMPLE, 1.0, "text literal",
              "storing words"),
    Construct("lit_bool",    Tier.SIMPLE, 1.1, "true/false literal",
              "storing a yes-or-no answer"),
    Construct("var_ref",     Tier.SIMPLE, 1.0, "variable reference",
              "reusing a value you named earlier"),
    Construct("bind_let",    Tier.SIMPLE, 1.0, "let binding",
              "giving a value a name"),
    Construct("arith",       Tier.SIMPLE, 1.2, "arithmetic",
              "combining numbers"),

    # ── TIER 2: INTERMEDIATE ──────────────────────────────────
    Construct("compare",     Tier.INTERMEDIATE, 1.4, "comparison",
              "asking whether one value relates to another"),
    Construct("branch",      Tier.INTERMEDIATE, 1.8, "if / then / else",
              "making the program take different paths"),
    Construct("fn_def",      Tier.INTERMEDIATE, 2.0, "function definition",
              "naming a procedure so you write it once"),
    Construct("fn_call",     Tier.INTERMEDIATE, 1.5, "function call",
              "reusing a procedure you wrote"),
    Construct("multi_param", Tier.INTERMEDIATE, 1.7, "multi-parameter function",
              "a procedure that takes several inputs"),
    Construct("nested_expr", Tier.INTERMEDIATE, 1.5, "nested expression",
              "building an expression out of expressions"),
    Construct("bind_ever",   Tier.INTERMEDIATE, 1.6, "ever binding",
              "a binding whose trust is tracked as it changes"),

    # ── TIER 3: ADVANCED ──────────────────────────────────────
    Construct("recursion",   Tier.ADVANCED, 3.0, "recursion",
              "a procedure defined in terms of itself"),
    Construct("composition", Tier.ADVANCED, 2.6, "function composition",
              "feeding one procedure's result into another"),
    Construct("nested_branch", Tier.ADVANCED, 2.4, "nested branching",
              "decisions inside decisions"),
    Construct("confidence",  Tier.ADVANCED, 2.8, "confidence handling",
              "reasoning about how much a value can be trusted"),
    Construct("zero_abs",    Tier.ADVANCED, 2.5, "zero-absolute (z)",
              "representing what is genuinely unknown"),
    Construct("aggregate",   Tier.ADVANCED, 2.3, "list / record",
              "structuring many values as one"),
    Construct("higher_order", Tier.ADVANCED, 3.0, "higher-order function",
              "a procedure that takes or returns a procedure"),
    Construct("anchor",      Tier.ADVANCED, 3.0, "anchoring",
              "proving a recursion terminates so it may exceed depth 3"),
    Construct("deep_nesting", Tier.ADVANCED, 2.0, "deep nesting",
              "holding several levels of structure in mind at once"),

    # ── added with and/or/not/for/while/index/field ──
    Construct("logic_op",    Tier.INTERMEDIATE, 1.5, "and / or",
              "combining two conditions into one"),
    Construct("negation",    Tier.INTERMEDIATE, 1.3, "not",
              "inverting a condition"),
    Construct("index",       Tier.ADVANCED, 2.2, "list indexing",
              "reaching into a list by position"),
    Construct("field",       Tier.ADVANCED, 2.2, "field access",
              "reaching into a record by name"),
    Construct("for_range",   Tier.ADVANCED, 2.6, "bounded for-loop",
              "repeating a computation a known number of times"),
    Construct("for_in",      Tier.ADVANCED, 2.6, "for-in loop",
              "repeating a computation once per list element"),
    Construct("while_loop",  Tier.ADVANCED, 2.9, "while-loop",
              "repeating a computation until a condition fails"),

    # ── added with sigmoid / mse / exp / dot ──
    Construct("ml_activation", Tier.ADVANCED, 2.7, "sigmoid",
              "squashing a value into a bounded, probability-like range"),
    Construct("ml_loss",     Tier.ADVANCED, 3.0, "mean squared error",
              "scoring how far predictions land from the truth"),
    Construct("ml_algebra",  Tier.ADVANCED, 2.4, "exp / dot",
              "the arithmetic a model is built from"),

    # ── added with extern/FFI ──
    Construct("extern_ffi",  Tier.ADVANCED, 3.0, "extern (FFI)",
              "calling real compiled code from another language"),
]}

TIER_MEMBERS: Dict[Tier, List[str]] = {}
for _k, _c in TAXONOMY.items():
    TIER_MEMBERS.setdefault(_c.tier, []).append(_k)


# ─────────────────────────────────────────────
# BANDS — what the score means, and what to DO about it
#
# The `scaffold` field is the point of the whole module. The score
# is only ever consulted to answer: how much help do we show?
# ─────────────────────────────────────────────
@dataclass(frozen=True)
class Band:
    low:      int
    high:     int
    name:     str
    scaffold: str
    describe: str

BANDS: List[Band] = [
    Band(0,   64,  "Novice",
         "full",
         "Show worked examples with every error. Name the concept, "
         "then show a two-line program that uses it correctly."),
    Band(65,  112, "Learner",
         "guided",
         "Explain errors in plain words and point at the next construct "
         "worth learning. Drop the worked examples."),
    Band(113, 168, "Practitioner",
         "hints",
         "State the error and one hint. Assume the vocabulary is known."),
    Band(169, 216, "Fluent",
         "terse",
         "State the error. No explanation unless asked."),
    Band(217, 256, "Architect",
         "silent",
         "Report position and message only. Surface structural "
         "observations the user may not have noticed."),
]

def band_for(score: int) -> Band:
    for b in BANDS:
        if b.low <= score <= b.high:
            return b
    return BANDS[-1] if score > 256 else BANDS[0]


# ─────────────────────────────────────────────
# OBSERVATION — one analysed program
# ─────────────────────────────────────────────
@dataclass
class Observation:
    """What a single semantic pass saw."""
    counts:     Dict[str, int] = field(default_factory=dict)
    max_depth:  int = 0
    node_count: int = 0
    errors:     int = 0

    def note(self, key: str, n: int = 1) -> None:
        if key in TAXONOMY:
            self.counts[key] = self.counts.get(key, 0) + n

    # ── the three signals a session produces ──

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def unique(self) -> int:
        return len(self.counts)

    def tier_totals(self) -> Dict[Tier, int]:
        out = {Tier.SIMPLE: 0, Tier.INTERMEDIATE: 0, Tier.ADVANCED: 0}
        for k, n in self.counts.items():
            out[TAXONOMY[k].tier] += n
        return out

    @property
    def simple_ratio(self) -> float:
        """The headline number: what fraction of what they wrote was
        tier-1. High ratio means they are staying in the shallow end."""
        t = self.tier_totals()
        tot = sum(t.values())
        return (t[Tier.SIMPLE] / tot) if tot else 1.0

    @property
    def advanced_ratio(self) -> float:
        t = self.tier_totals()
        tot = sum(t.values())
        return (t[Tier.ADVANCED] / tot) if tot else 0.0

    def session_score(self) -> float:
        """Score this one program on the 0..256 scale.

        Three components, deliberately separated:

          DIFFICULTY  weighted mean tier of what was written.
                      Answers: how hard is the hardest thing here?
          DIVERSITY   how many distinct constructs appeared, against
                      how many exist. Answers: is this range, or one
                      trick repeated?
          DEPTH       structural nesting. Answers: how much are they
                      holding in their head at once?

        Difficulty dominates (60%), because writing recursion is the
        strongest single signal available and no amount of breadth at
        an easier level substitutes for it. Diversity is 30% — enough
        to separate range from a repeated snippet within a tier,
        never enough to outrank a genuinely harder construct. Depth
        is 10%: it correlates with skill, but a deeply nested mess is
        not mastery, so it gets the smallest say.

        Note that counts cancel in the difficulty term because it is
        a MEAN. That is the property that stops forty copies of one
        line from reading as forty pieces of evidence.
        """
        if not self.counts:
            return float(P_START)

        # ── DIFFICULTY: weighted mean tier, normalised to 0..1 ──
        num = den = 0.0
        for k, n in self.counts.items():
            c = TAXONOMY[k]
            num += float(c.tier) * c.weight * n
            den += c.weight * n
        mean_tier = num / den if den else 1.0
        difficulty = (mean_tier - 1.0) / 2.0          # tier 1..3 → 0..1

        # ── DIVERSITY: unique constructs against the whole taxonomy ──
        # sqrt so early variety counts for more than the twentieth
        # distinct construct — the jump from 1 to 4 matters more than
        # from 16 to 19.
        diversity = math.sqrt(self.unique / len(TAXONOMY))

        # ── DEPTH: saturating at 8, past which it is not more skill ──
        depth = min(self.max_depth, 8) / 8.0

        raw = 0.60 * difficulty + 0.30 * diversity + 0.10 * depth
        return max(0.0, min(1.0, raw)) * P_MAX


# ─────────────────────────────────────────────
# THE PROFILE — persistent state across sessions
# ─────────────────────────────────────────────
@dataclass
class Profile:
    score:          float = float(P_START)
    sessions:       int   = 0
    lifetime:       Dict[str, int] = field(default_factory=dict)
    history:        List[float] = field(default_factory=list)
    first_seen:     float = field(default_factory=time.time)
    last_seen:      float = field(default_factory=time.time)

    # ── derived views ──
    @property
    def rounded(self) -> int:
        return int(round(self.score))

    @property
    def band(self) -> Band:
        return band_for(self.rounded)

    @property
    def scaffold(self) -> str:
        return self.band.scaffold

    def used(self, key: str) -> bool:
        return self.lifetime.get(key, 0) > 0

    def unused(self) -> List[str]:
        return [k for k in TAXONOMY if not self.used(k)]

    def trend(self, window: int = 5) -> str:
        """Direction of travel — worth more to the user than the
        absolute number, which is meaningless out of context."""
        if len(self.history) < 2:
            return "new"
        recent = self.history[-window:]
        if len(recent) < 2:
            return "steady"
        delta = recent[-1] - recent[0]
        if delta >  8: return "climbing"
        if delta < -8: return "easing"
        return "steady"


# ─────────────────────────────────────────────
# THE PROFILER
# ─────────────────────────────────────────────
class Profiler:
    """Tracks proficiency across sessions and answers the one question
    the rest of the system asks: how much scaffolding does this person
    need right now?"""

    def __init__(self, path: Optional[Path] = None,
                 profile: Optional[Profile] = None):
        self.path    = Path(path) if path else None
        self.profile = profile or self._load()

    # ── persistence ──
    def _load(self) -> Profile:
        if self.path and self.path.exists():
            try:
                d = json.loads(self.path.read_text())
                return Profile(**d)
            except Exception:
                pass
        return Profile()

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(self.profile), indent=2))

    # ── the core update ──
    def observe(self, obs: Observation) -> Profile:
        """Fold one program's evidence into the running score.

        This is where "dynamically shifting" actually happens. The
        asymmetric alpha is the important line: evidence of skill is
        taken more seriously than evidence of its absence, because
        writing something simple is not proof you cannot write
        something hard.
        """
        p = self.profile
        session = obs.session_score()

        alpha = ALPHA_UP if session > p.score else ALPHA_DOWN
        p.score = p.score * (1.0 - alpha) + session * alpha
        p.score = max(float(P_MIN), min(float(P_MAX), p.score))

        p.sessions += 1
        p.last_seen = time.time()
        p.history.append(round(p.score, 2))
        if len(p.history) > 200:
            p.history = p.history[-200:]
        for k, n in obs.counts.items():
            p.lifetime[k] = p.lifetime.get(k, 0) + n
        return p

    # ── what the rest of the system consumes ──

    def next_constructs(self, n: int = 3) -> List[Construct]:
        """The constructs to suggest next.

        Not the hardest unused ones — the ones just past where they
        are. Suggesting recursion to someone who has not yet used a
        comparison is how a tool teaches nobody anything.
        """
        p    = self.profile
        here = p.band
        # target the tier that matches the current band, then one above
        if   here.name in ("Novice",):        want = [Tier.SIMPLE, Tier.INTERMEDIATE]
        elif here.name in ("Learner",):       want = [Tier.INTERMEDIATE]
        elif here.name in ("Practitioner",):  want = [Tier.INTERMEDIATE, Tier.ADVANCED]
        else:                                 want = [Tier.ADVANCED]

        cands = [TAXONOMY[k] for k in p.unused() if TAXONOMY[k].tier in want]
        # easiest-first inside the target tier, so the next step is small
        cands.sort(key=lambda c: (int(c.tier), c.weight))
        if len(cands) < n:
            rest = [TAXONOMY[k] for k in p.unused() if TAXONOMY[k] not in cands]
            rest.sort(key=lambda c: (int(c.tier), c.weight))
            cands += rest
        return cands[:n]

    def scaffold_level(self) -> str:
        return self.profile.scaffold

    def explain_error(self, message: str, hint: str = "",
                      example: str = "") -> str:
        """Render one diagnostic at the right level of hand-holding.

        Same error, five presentations. This function is the entire
        user-visible payoff of the score.
        """
        lvl = self.scaffold_level()
        if lvl == "full":
            out = [message]
            if hint:    out.append(f"  What this means: {hint}")
            if example: out.append(f"  Working example:\n    {example}")
            return "\n".join(out)
        if lvl == "guided":
            return f"{message}\n  {hint}" if hint else message
        if lvl == "hints":
            short = hint.split(".")[0] if hint else ""
            return f"{message} ({short})" if short else message
        return message      # terse and silent both get the bare message

    # ── reporting ──
    def report(self) -> str:
        p = self.profile
        b = p.band
        bar_w   = 40
        filled  = int(bar_w * p.rounded / P_MAX)
        bar     = "█" * filled + "░" * (bar_w - filled)

        lines = [
            "",
            "═" * 58,
            "  PROFICIENCY PROFILE",
            "═" * 58,
            f"  Score     {p.rounded}/256   [{bar}]",
            f"  Band      {b.name}  ({b.scaffold} scaffolding)",
            f"  Sessions  {p.sessions}        Trend: {p.trend()}",
            "",
            f"  {b.describe}",
            "",
            "  ── construct usage ──",
        ]
        for tier in (Tier.SIMPLE, Tier.INTERMEDIATE, Tier.ADVANCED):
            keys  = TIER_MEMBERS[tier]
            used  = sum(1 for k in keys if p.used(k))
            total = sum(p.lifetime.get(k, 0) for k in keys)
            lines.append(f"  {tier.label:<13} {used}/{len(keys)} constructs   "
                         f"{total} uses")

        nxt = self.next_constructs(3)
        if nxt:
            lines += ["", "  ── try next ──"]
            for c in nxt:
                lines.append(f"  {c.label:<26} {c.teaches}")
        lines += ["═" * 58, ""]
        return "\n".join(lines)


# ─────────────────────────────────────────────
# AST CLASSIFICATION
#
# Bridges the parser's node types to the taxonomy. Kept here rather
# than inside Semantic so the taxonomy has exactly one consumer and
# the semantic pass stays about types and scope.
# ─────────────────────────────────────────────

def classify(node, obs: Optional[Observation] = None,
             depth: int = 0, fn_names: Optional[Set[str]] = None,
             in_branch: bool = False, in_call: bool = False) -> Observation:
    """Walk an Ever AST and record which constructs appear.

    Duck-typed against syntax.py's node classes so this module does
    not import the parser — the profiler must never be a reason the
    parser cannot change.
    """
    obs = obs or Observation()
    fn_names = fn_names if fn_names is not None else set()
    if node is None:
        return obs

    obs.node_count += 1
    obs.max_depth = max(obs.max_depth, depth)
    if depth >= 4:
        obs.note("deep_nesting")

    cls = type(node).__name__

    # ── literals ──
    if cls == "Num":
        is_float = False
        try:
            is_float = bool(node.is_float_literal())
        except Exception:
            is_float = isinstance(getattr(node, "value", 0), float)
        obs.note("lit_real" if is_float else "lit_int")
        return obs

    if cls == "Str":
        obs.note("lit_text");  return obs
    if cls == "Bool":
        obs.note("lit_bool");  return obs

    if cls == "Var":
        name = getattr(node, "name", "")
        if name == "z":
            obs.note("zero_abs")
        else:
            obs.note("var_ref")
        return obs

    # ── binary operators split by what they demonstrate ──
    if cls == "BinOp":
        op = getattr(node, "op", "")
        if op in {"<", ">", "<=", ">=", "==", "!="}:
            obs.note("compare")
        elif op in {"and", "or"}:
            obs.note("logic_op")
        else:
            obs.note("arith")
        left  = getattr(node, "left", None)
        right = getattr(node, "right", None)
        # an operand that is itself an operator = nested expression
        if type(left).__name__ in ("BinOp", "Call", "If") or \
           type(right).__name__ in ("BinOp", "Call", "If"):
            obs.note("nested_expr")
        classify(left,  obs, depth + 1, fn_names, in_branch, in_call)
        classify(right, obs, depth + 1, fn_names, in_branch, in_call)
        return obs

    # ── branching ──
    if cls == "If":
        obs.note("branch")
        if in_branch:
            obs.note("nested_branch")
        for part in ("cond", "then", "els", "other", "orelse"):
            sub = getattr(node, part, None)
            if sub is not None:
                classify(sub, obs, depth + 1, fn_names, True, in_call)
        return obs

    # ── application ──
    if cls == "Call":
        name = getattr(node, "name", "")
        if name == "sigmoid":
            obs.note("ml_activation")
        elif name == "mse":
            obs.note("ml_loss")
        elif name in ("exp", "dot"):
            obs.note("ml_algebra")
        else:
            obs.note("fn_call")
        if in_call:
            obs.note("composition")
        args = getattr(node, "args", []) or []
        for arg in args:
            if type(arg).__name__ == "Call":
                obs.note("composition")
            classify(arg, obs, depth + 1, fn_names, in_branch, True)
        return obs

    # ── abstraction ──
    if cls == "FnDef":
        obs.note("fn_def")
        params = getattr(node, "params", []) or []
        if len(params) > 1:
            obs.note("multi_param")
        name = getattr(node, "name", "")
        fn_names.add(name)
        body = getattr(node, "body", None)
        if _calls_itself(body, name):
            obs.note("recursion")
        classify(body, obs, depth + 1, fn_names, in_branch, in_call)
        return obs

    # ── aggregates and access, if the surface ever grows them ──
    if cls in ("ListLit", "RecordLit"):
        obs.note("aggregate")
        for item in (getattr(node, "items", []) or []):
            classify(item, obs, depth + 1, fn_names, in_branch, in_call)
        return obs
    if cls in ("Index", "Field"):
        obs.note("index" if cls == "Index" else "field")
        classify(getattr(node, "target", None), obs, depth + 1,
                 fn_names, in_branch, in_call)
        return obs

    if cls == "UnaryOp":
        obs.note("negation")
        classify(getattr(node, "operand", None), obs, depth + 1,
                 fn_names, in_branch, in_call)
        return obs

    if cls == "Extern":
        obs.note("extern_ffi")
        return obs

    if cls in ("ForRange", "ForIn", "While"):
        obs.note({"ForRange": "for_range", "ForIn": "for_in",
                 "While": "while_loop"}[cls])
        for attr in ("start", "end", "step", "seq", "cond", "body"):
            sub = getattr(node, attr, None)
            if sub is not None:
                classify(sub, obs, depth + 1, fn_names, in_branch, in_call)
        return obs

    # ── unknown node: walk anything that looks like a child ──
    for attr in ("left", "right", "cond", "then", "els", "body",
                 "value", "target", "expr"):
        sub = getattr(node, attr, None)
        if sub is not None and hasattr(sub, "__class__"):
            classify(sub, obs, depth + 1, fn_names, in_branch, in_call)
    return obs


def _calls_itself(node, name: str) -> bool:
    """Detect direct recursion — the single strongest signal."""
    if node is None or not name:
        return False
    if type(node).__name__ == "Call" and getattr(node, "name", "") == name:
        return True
    for attr in ("left", "right", "cond", "then", "els", "body",
                 "value", "target", "expr"):
        sub = getattr(node, attr, None)
        if sub is not None and _calls_itself(sub, name):
            return True
    for arg in (getattr(node, "args", []) or []):
        if _calls_itself(arg, name):
            return True
    return False


def observe_source_flags(obs: Observation, source: str) -> Observation:
    """Pick up constructs that live in statement syntax rather than in
    the expression AST, so `let` versus `ever` is not invisible."""
    for raw in (source or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("let "):    obs.note("bind_let")
        elif line.startswith("ever "): obs.note("bind_ever")
        if line.startswith("anchor ") or " anchor " in line:
            obs.note("anchor")
        if line.rstrip().endswith("= z") or " z " in f" {line} ":
            obs.note("zero_abs")
    return obs


if __name__ == "__main__":
    # Demonstration: three users, three trajectories.
    print("\nDYNAMIC PROFILER — worked demonstration\n" + "=" * 58)

    class N:  # minimal stand-in nodes
        def __init__(s, **kw): s.__dict__.update(kw)
    def Num(v):        n = N(value=v); n.__class__.__name__ = "Num"; return n
    print("(see profiler_test.py for the full battery)")
