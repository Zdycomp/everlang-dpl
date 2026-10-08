#!/usr/bin/env python3
"""
audit.py — finding the places where the documents and the code disagree.

The forge does this for stages 1 to 3 and does it well: twenty front
ends, half a million programs, every divergence a finding. It does not
look at stage 4 at all, and both of the last two real bugs were sitting
exactly there --

  * G1 says "evaluation is total, no exceptions, proven by
    construction". `fact(5)` raised DepthExceeded straight out of eval.
  * SEMANTICS.md 7 lists higher-order functions as missing. They work.

Neither needed cleverness to find. Both needed *someone to check the
claim against the thing*, which is a mechanical job, and this is that
job written down so it happens every run instead of when someone
thinks to look.

Variance is symmetric and both directions are reported:

  OVERSTATED   the documents promise something the code does not do.
               The dangerous kind -- somebody is relying on it.
  UNDERSTATED  the code does something the documents deny. Cheaper, but
               still a lie about the language, and it hides finished
               work from the people deciding what to build next.

A probe that cannot decide says so rather than guessing. An auditor
that reports a clean bill because it could not run is worse than no
auditor.

Codric Enterprise
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.abspath(os.path.join(HERE, ".."))

OVERSTATED = "OVERSTATED"
UNDERSTATED = "UNDERSTATED"
HOLDS = "holds"
UNDECIDED = "UNDECIDED"


@dataclass
class Finding:
    verdict: str
    claim: str
    source: str
    evidence: str

    def __str__(self) -> str:
        return f"[{self.verdict}] {self.claim}\n    {self.source}\n    {self.evidence}"


@dataclass
class Probe:
    """One documented claim, and a way to find out if it is true."""
    claim: str
    source: str
    check: Callable[[], Tuple[str, str]]

    def run(self) -> Finding:
        try:
            verdict, evidence = self.check()
        except Exception as exc:                       # noqa: BLE001
            verdict = UNDECIDED
            evidence = f"the probe itself failed: {type(exc).__name__}: {exc}"
        return Finding(verdict, self.claim, self.source, evidence)


# ═════════════════════════════════════════════
# Probes — the guarantees
# ═════════════════════════════════════════════

TOTALITY_INPUTS = [
    "fact(5)", "fact(50)", "1 / 0", "undefined(3)", "1 + true",
    "head([])", "len(5)", "[1, 2] + 3", "let x = 1 in y",
    "\"a\" * 2", "f(", "", "   ",
]


def probe_g1_totality() -> Tuple[str, str]:
    from abstract import Lambda
    lam = Lambda()
    lam.define("fact", ["n"], "if n <= 1 then 1 else n * fact(n - 1)")
    raised = []
    for src in TOTALITY_INPUTS:
        try:
            lam.eval(src, {}, 0, "audit")
        except Exception as exc:                       # noqa: BLE001
            raised.append(f"{src!r} raised {type(exc).__name__}")
    if raised:
        return OVERSTATED, (f"{len(raised)} of {len(TOTALITY_INPUTS)} inputs "
                            f"raised: " + "; ".join(raised[:3]))
    return HOLDS, f"{len(TOTALITY_INPUTS)} inputs, none raised"


def probe_g1_pipeline() -> Tuple[str, str]:
    from syntax import compile_ezr, eval_ast
    raised = []
    for src in TOTALITY_INPUTS:
        try:
            c = compile_ezr(src)
            if c.ok:
                eval_ast(c.ast, {}, {}, 0, limit=99)
        except Exception as exc:                       # noqa: BLE001
            raised.append(f"{src!r} raised {type(exc).__name__}")
    if raised:
        return OVERSTATED, "; ".join(raised[:3])
    return HOLDS, f"{len(TOTALITY_INPUTS)} inputs through the AST path, none raised"


def probe_t3_absolute_zero() -> Tuple[str, str]:
    from ever import E_CERTAIN, excel
    worst = max(excel(a, b) for a in range(0, 256, 5) for b in range(0, 256, 5))
    if worst >= E_CERTAIN:
        return OVERSTATED, f"excel reached {worst}, and Certain is {E_CERTAIN}"
    return HOLDS, (f"the hottest combination over the grid reaches {worst}, "
                   f"never {E_CERTAIN}")


def probe_g9_no_mutation() -> Tuple[str, str]:
    from ever import e_val
    from physics import push
    th = e_val("subject", 1, 200)
    before = (th.confidence, th.generation, th.reason)
    push(th, -50.0, "audit")
    after = (th.confidence, th.generation, th.reason)
    if before != after:
        return OVERSTATED, f"the original changed: {before} -> {after}"
    return HOLDS, "a force derives a new thread and leaves the original alone"


def probe_g3_entropy() -> Tuple[str, str]:
    from ever import e_val
    from physics import entropy
    from abstract import chain
    a, b = e_val("a", 1, 200), e_val("b", 1, 120)
    c = chain([a, b])
    if c > min(a.confidence, b.confidence):
        return OVERSTATED, f"chain produced {c} from {a.confidence},{b.confidence}"
    return HOLDS, (f"chaining {a.confidence} and {b.confidence} gives {c}; "
                   f"u rose from {entropy(a):.3f} to "
                   f"{(256 - c) / 256:.3f}")


# ═════════════════════════════════════════════
# Probes — the "Not yet specified" table
# ═════════════════════════════════════════════

def _semantics_gaps() -> List[str]:
    """Read section 7's table straight out of the document."""
    path = os.path.join(DOCS, "SEMANTICS.md")
    if not os.path.exists(path):
        return []
    text = open(path).read()
    m = re.search(r"##\s*7\.\s*Not yet specified(.*?)(?:\n##\s|\Z)",
                  text, re.S)
    if not m:
        return []
    # Only the first table in the section. Anything after it is
    # commentary -- including, at the time of writing, a table of rows
    # that used to be here and are not any more, which the auditor
    # would otherwise read as fresh claims and re-report forever.
    rows: List[str] = []
    started = False
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("|"):
            started = True
            if line.startswith("|---") or line.lower().startswith("| missing"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and cells[0]:
                rows.append(cells[0])
        elif started:
            break                  # the table ended
    return rows


def _accepts(src: str) -> bool:
    from syntax import compile_ezr
    return compile_ezr(src).ok


def probe_composite_data() -> Tuple[str, str]:
    if _accepts("[1, 2, 3]"):
        from syntax import compile_ezr, eval_ast
        c = compile_ezr("[1, 2, 3]")
        v = eval_ast(c.ast, {}, {}, 0, limit=9).value
        return UNDERSTATED, f"lists parse and evaluate: [1, 2, 3] -> {v}"
    return HOLDS, "no list literal in the grammar"


def probe_records() -> Tuple[str, str]:
    if _accepts("{x: 1}"):
        return UNDERSTATED, "a record literal parses"
    return HOLDS, "no record literal in the grammar"


def probe_transpiler() -> Tuple[str, str]:
    import glob
    emitters = glob.glob(os.path.join(DOCS, "**", "emit_*.py"),
                         recursive=True)
    if emitters:
        return UNDERSTATED, f"emitters exist: {emitters}"
    return HOLDS, "no target-language emitter on disk"


# ═════════════════════════════════════════════
# Probes — cross-stage agreement
# ═════════════════════════════════════════════

def probe_core_agreement() -> Tuple[str, str]:
    """Does the shipped interpreter accept what the ratified core does?

    This is the divergence class that had `syntax.py` refusing
    multi-definition programs while CORE.md said they were in.
    """
    cases = [
        ("def f(n) = n\ndef g(n) = n + 1", True, "several definitions"),
        ("[1, 2]", True, "a list"),
        ("let x = 1 in x", True, "a binding"),
        ("1 < 2 < 3", False, "chained comparison"),
        ("f(1,)", False, "trailing comma"),
        ("def d(n) = n\nd(1)", False, "trailing expression"),
        ("1 + let x = 2 in x", False, "let as an operand"),
    ]
    wrong = [f"{why}: expected {'accept' if want else 'refuse'}"
             for src, want, why in cases if _accepts(src) != want]
    if wrong:
        return OVERSTATED, ("the interpreter disagrees with the ratified "
                            "core on " + "; ".join(wrong))
    return HOLDS, f"agrees with the ratified core on {len(cases)} cases"


def probe_builtins() -> Tuple[str, str]:
    """The builtin set, against what CORE.md 1.2 says it is.

    An undocumented builtin is understatement of exactly the kind this
    auditor exists to catch: the language does something and no
    document admits it.
    """
    from syntax import BUILTINS
    path = os.path.join(DOCS, "CORE.md")
    if not os.path.exists(path):
        return UNDECIDED, "CORE.md is not where this expects it"
    text = open(path).read()
    documented = {b for b in BUILTINS if f"`{b}(" in text}
    missing = set(BUILTINS) - documented
    if missing:
        return UNDERSTATED, (f"implemented but undocumented: "
                             f"{', '.join(sorted(missing))}")
    return HOLDS, (f"all {len(BUILTINS)} builtins are documented: "
                   f"{', '.join(sorted(BUILTINS))}")


def probe_runner() -> Tuple[str, str]:
    """Can the core language be run at all, from a command line?

    This is the probe that would have caught the thing no test did.
    Lists, `let` and the builtins were implemented, agreed on by twenty
    front ends and covered by 87 assertions, and reachable only by
    importing `syntax` and calling `compile_ezr` by hand -- `ezr.py`
    runs a different language entirely. A feature you can only use by
    importing the implementation is not shipped, and every test in the
    suite passed the whole time.

    So this one shells out. It is the only probe here that leaves the
    process, and that is the point: it asks what a user gets.
    """
    import subprocess
    runner = os.path.join(HERE, "ezrun.py")
    if not os.path.exists(runner):
        return OVERSTATED, ("no runner for the core language: the "
                            "features are reachable only by importing "
                            "syntax.py")
    checks = [("-e", "[1, 2, 3]", "[1, 2, 3]"),
              ("-e", "let x = 5 in x + 1", "6"),
              ("-e", "len([1, 2])", "2")]
    for flag, src, want in checks:
        try:
            out = subprocess.run([sys.executable, runner, flag, src],
                                 capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            return UNDECIDED, f"could not run the runner: {exc}"
        if want not in out.stdout:
            return OVERSTATED, (f"{flag} {src!r} gave {out.stdout.strip()!r} "
                                f"{out.stderr.strip()[:60]!r}, wanted {want!r}")
    return HOLDS, (f"the core runs from a command line: "
                   f"{len(checks)} programs through ezrun.py")


def probe_integer_arithmetic() -> Tuple[str, str]:
    if _accepts("5 % 2") or _accepts("5 // 2"):
        return UNDERSTATED, "an integer operator parses"
    return HOLDS, "no modulo and no integer division, as stated"


def probe_law_reach() -> Tuple[str, str]:
    """Where the laws actually apply, against where CORE.md says.

    A law with no caller is a law nothing runs under, however well it
    is tested in isolation. `probe_physical_laws` verifies the algebra
    over a subsystem built for the occasion, which says nothing about
    whether ordinary evaluation ever touches it -- so this looks for
    callers instead of for correctness.
    """
    import glob
    users = set()
    for path in glob.glob(os.path.join(HERE, "*.py")):
        base = os.path.basename(path)
        if base in ("physics.py", "audit.py") or base.endswith("_test.py"):
            continue
        text = open(path).read()
        if "from physics import" in text or "import physics" in text:
            users.add(base)

    text = open(os.path.join(DOCS, "CORE.md")).read()
    claims_runtime = "the laws the language runs under" in text.lower()
    if claims_runtime and not users:
        return OVERSTATED, ("CORE.md says the language runs under the "
                            "laws, and nothing outside the tests imports "
                            "physics")
    if users:
        return HOLDS, (f"enforced at runtime in {', '.join(sorted(users))}; "
                       f"the rest are verified properties, and CORE.md 8 "
                       f"says so")
    return HOLDS, ("stated as properties and a facility, not as a layer "
                   "evaluation runs under")


def probe_physical_laws() -> Tuple[str, str]:
    from ever import e_val
    from physics import Subsystem, derive_from
    s = Subsystem("audit")
    a = s.admit(e_val("a", 1, 200))
    b = s.admit(e_val("b", 1, 120))
    out = derive_from(a, ident="out", confidence=120, reason="chained")
    s.derive([a, b], out)
    old = s.admit(e_val("old", 1, 90))
    s.supersede(old, out)
    broken = s.audit()
    if broken:
        return OVERSTATED, "; ".join(str(x) for x in broken)
    return HOLDS, ("conservation, entropy, absolute zero, inertia and "
                   "action-reaction all hold over a worked subsystem")


def probe_ultra_depth() -> Tuple[str, str]:
    """SEMANTICS.md 4.6 gives an anchored function unbounded depth."""
    from abstract import Lambda, a_anchor_fn, E_HARD_DEPTH
    from ultra import ultra_anchor, run_ultra
    lam = Lambda()
    lam.define("fact", ["n"], "if n <= 1 then 1 else n * fact(n - 1)")
    for arg, want in [(1, 1), (2, 2), (3, 6)]:
        lam.example("fact", [arg], want)
    lam.globals["fact"] = a_anchor_fn(lam.globals["fact"])
    plain = lam.eval("fact(1000)", {}, 0, "audit")
    ua, _ = ultra_anchor(lam.globals["fact"], lam.globals["fact"].value)
    lifted = run_ultra(ua, lam.eval, "fact(1000)", {}, 0, "audit")
    if plain.is_z and not lifted.is_z:
        return HOLDS, (f"depth 1000 refused unprovisioned, delivered under an "
                       f"ultra-anchor; EZR's own ceiling is {E_HARD_DEPTH}")
    if not plain.is_z:
        return HOLDS, "depth 1000 runs without provisioning"
    return OVERSTATED, ("anchored depth is documented as unbounded and is "
                        "refused even under an ultra-anchor")


#: Row in SEMANTICS.md section 7 -> the probe that decides it. Built
#: on call rather than at import so the order the probes happen to be
#: written in does not matter. A row with no probe is reported
#: undecided rather than assumed true -- "soundness proof" is the
#: honest example, since no test here establishes progress and
#: preservation.
def _gap_table():
    return {
        "composite data": probe_composite_data,
        "records": probe_records,
        "higher-order": probe_higher_order,
        "pattern matching": probe_pattern_matching,
        "static type": probe_static_types,
        "module system": probe_module_system,
        "formal grammar": probe_formal_grammar,
        "transpiler": probe_transpiler,
        "integer arithmetic": probe_integer_arithmetic,
    }


def gap_probes() -> List[Probe]:
    """One probe per row the document *currently* claims is missing.

    Driven by the table itself rather than by a list maintained beside
    it, so a row added back gets checked without anybody remembering to
    write a probe for it.
    """
    table = _gap_table()
    out: List[Probe] = []
    for row in _semantics_gaps():
        key = next((k for k in table if k in row.lower()), None)
        if key is None:
            out.append(Probe(
                f"{row} is missing", "SEMANTICS.md 7",
                lambda r=row: (UNDECIDED,
                               "no probe can decide this mechanically")))
        else:
            out.append(Probe(f"{row} is missing", "SEMANTICS.md 7",
                             table[key]))
    return out


def probe_higher_order() -> Tuple[str, str]:
    from abstract import Lambda
    lam = Lambda()
    lam.define("twice", ["g", "n"], "g(g(n))")
    lam.define("inc", ["n"], "n + 1")
    lam.define("dbl", ["n"], "n * 2")
    a = lam.eval("twice(inc, 5)", {}, 0, "audit")
    b = lam.eval("twice(dbl, 5)", {}, 0, "audit")
    if not a.is_z and not b.is_z and a.value == 7 and b.value == 20:
        return UNDERSTATED, (f"functions are arguments: twice(inc,5)={a.value}, "
                             f"twice(dbl,5)={b.value}")
    return HOLDS, "functions cannot be passed as arguments"


def probe_formal_grammar() -> Tuple[str, str]:
    path = os.path.join(DOCS, "7-forge", "GRAMMAR.ebnf")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        n = sum(1 for ln in open(path) if "=" in ln and not ln.startswith("("))
        return UNDERSTATED, (f"an EBNF grammar exists and is emitted from the "
                             f"parser's rule table ({n} productions)")
    return HOLDS, "no formal grammar on disk"


def probe_pattern_matching() -> Tuple[str, str]:
    if _accepts("match n with 0 -> 1"):
        return UNDERSTATED, "pattern matching parses"
    return HOLDS, "no pattern matching in the grammar"


def probe_module_system() -> Tuple[str, str]:
    if _accepts("import foo") or _accepts("module foo"):
        return UNDERSTATED, "a module form parses"
    return HOLDS, "one flat global namespace, as stated"


def probe_static_types() -> Tuple[str, str]:
    if _accepts("def f(n: num) = n"):
        return UNDERSTATED, "type annotations parse"
    return HOLDS, "checking is dynamic, as stated"


# ═════════════════════════════════════════════
# The suite
# ═════════════════════════════════════════════

def probes() -> List[Probe]:
    return [
        Probe("evaluation is total, no exceptions",
              "SEMANTICS.md G1 (string evaluator)", probe_g1_totality),
        Probe("evaluation is total, no exceptions",
              "SEMANTICS.md G1 (AST pipeline)", probe_g1_pipeline),
        Probe("confidence never rises except via Ascend or Excel",
              "SEMANTICS.md G3 / second law", probe_g3_entropy),
        Probe("no mutation",
              "SEMANTICS.md G9 / Newton I", probe_g9_no_mutation),
        Probe("Certain is unreachable by combination",
              "SEMANTICS.md T3 / third law", probe_t3_absolute_zero),
        Probe("the interpreter implements the ratified core",
              "CORE.md 1 and 2", probe_core_agreement),
        Probe("the builtins are the four CORE.md 1.2 states",
              "CORE.md 1.2", probe_builtins),
        Probe("the core language can be run from a command line",
              "CORE.md 1 / ezrun.py", probe_runner),
        Probe("the laws reach as far as CORE.md 8 says",
              "CORE.md 8", probe_law_reach),
        Probe("the six physical laws hold",
              "physics.py", probe_physical_laws),
        Probe("an anchored function has unbounded depth",
              "SEMANTICS.md 4.6", probe_ultra_depth),
    ]


def run(verbose: bool = True) -> List[Finding]:
    findings = [p.run() for p in probes() + gap_probes()]
    if not verbose:
        return findings

    print("\n" + "=" * 70)
    print("EZR — VARIANCE AUDIT")
    print("what the documents claim, against what the code does")
    print("=" * 70 + "\n")

    for f in findings:
        mark = {HOLDS: "  ok  ", OVERSTATED: " OVER ",
                UNDERSTATED: " UNDER", UNDECIDED: "  ??  "}[f.verdict]
        print(f"[{mark}] {f.claim}")
        print(f"          {f.source}")
        print(f"          {f.evidence}\n")

    over = [f for f in findings if f.verdict == OVERSTATED]
    under = [f for f in findings if f.verdict == UNDERSTATED]
    undec = [f for f in findings if f.verdict == UNDECIDED]
    print("-" * 70)
    print(f"  {len(findings)} claims checked")
    print(f"  {len(over)} overstated   (documented, not true)")
    print(f"  {len(under)} understated  (true, not documented)")
    print(f"  {len(undec)} undecided")
    print("-" * 70 + "\n")
    return findings


if __name__ == "__main__":
    fs = run()
    # Overstatement is the failure. Understatement is a documentation
    # debt and is reported without failing the run.
    sys.exit(1 if any(f.verdict == OVERSTATED for f in fs) else 0)
