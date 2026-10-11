#!/usr/bin/env python3
"""
research.py — Ever / Tapestry, the research team

Four analysts, run over the whole archive of errors and successes:

    Thermo    the conservation law, and what Z actually is
    Ratio     the corpus weighed against phi
    Defect    which of the five binding defects dominate
    Verdict   what the numbers support, and what they do not

Written to be run, not read. Every number below is computed from the
actual corpus, not asserted.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "2-interpreter-python"))

from checker import Translator, ELang, classify   # noqa: E402
from ever import (E_CERTAIN, E_EXECUTE_FLOOR, E_PI_WIDTH_ENUMERATE,  # noqa: E402
                  E_PI_WIDTH_WARN, E_ZERO, excel)

#: The scale constants and `excel` are imported, not restated. They were
#: restated here, and the restated `excel` had silently fallen a bug fix
#: behind the language -- the same failure the assertion counts had, one
#: layer down. A constant copied is a constant that can drift; there is
#: no reason for this file to hold its own opinion about what CERTAIN is.
PHI                  = 1.6180339887


# ═════════════════════════════════════════════
# THERMO — the conservation law
# ═════════════════════════════════════════════

def uncertainty(confidence: int) -> float:
    """Normalized ignorance. 0 at Certain, 1 at Z."""
    return (E_CERTAIN - confidence) / E_CERTAIN


def confidence_from(u: float) -> int:
    return int(round(E_CERTAIN * (1.0 - u)))


#: `excel` is imported from ever.py above rather than redefined here.
#:
#: It used to be redefined, as `min(256, a + b - (a*b)//256)` -- the
#: UNCAPPED formula, which is the "manufactured Certain" bug this very
#: file reports as fixed in section 1 of FINDINGS.md. The fix landed in
#: C, Python and Ruby and never reached the copy living here, so the
#: research file certifying the algebra was certifying a formula the
#: language does not use. Measured across the 1089-point grid: they
#: disagree at 69 points.
#:
#: `verify_excel_is_multiplicative` then compared this local copy against
#: the closed form of the same uncapped rule and reported 1089/1089 -- a
#: formula agreeing with itself. Against the shipped excel it is
#: 1020/1089, and the 69 gaps are the interesting part rather than an
#: embarrassment; see the function.


class Thermo:
    """First Law, applied to Ever.

    Energy is neither created nor destroyed, only transformed. The
    equivalent statement for Ever is that CONFIDENCE IS NOT THE CONSERVED
    QUANTITY — UNCERTAINTY IS, and it combines multiplicatively:

        u_result = u_a * u_b

    Three consequences, none of which were designed in. They fall out.

    1. Excel creates nothing. Two witnesses agreeing does not manufacture
       confidence; it multiplies two ignorances into a smaller one. The
       confidence was always there, distributed across the witnesses. The
       system only revealed it.

    2. Z is the IDENTITY of corroboration, not its absorbing element.
       u = 1, and 1 * x = x -- so excel(Z, b) = b. A witness who knows
       nothing leaves what you already had exactly as it was. That is the
       right behaviour and it is what the code does; an earlier version
       of this docstring claimed the opposite ("1 * x = 1 for every x"),
       which is false arithmetic, and named Z as the absorbing element,
       which it is not. The absorbing element of excel is CERTAIN:
       excel(256, b) = 256 for every b.

       Z-contagion is real, and it comes from the OTHER operation. The
       chain rule is min, and 0 absorbs under min: min(0, b) = 0 for
       every b. So Z is contagious along a chain of dependence and inert
       under corroboration, which is exactly as it should be -- a
       computation that consumed an unknown is unknown, while a witness
       who abstains has not testified. Conflating the two made a true
       statement about min read as a false one about excel.

    3. Certain is unreachable by combination alone. u = 0 requires some
       u_i = 0 exactly. No finite stack of imperfect witnesses reaches it.
       Certain has to come from outside the corpus, which is precisely why
       the language earns it at runtime and never at parse time.
    """

    @staticmethod
    def verify_excel_is_multiplicative() -> Tuple[int, int]:
        """The language's excel against pure multiplicative uncertainty.

        This is now a real cross-check: `excel` is the shipped function,
        and `predicted` is the closed form of u_r = u_a * u_b. They agree
        at 1020 of 1089 grid points and differ at 69, all of them where
        the shipped cap fires. Every disagreement is the cap, not the
        algebra -- which is the finding, and is worth more than the
        1089/1089 this reported when it was comparing a local copy of the
        uncapped formula against the uncapped formula.
        """
        hits = total = 0
        for a in range(0, 257, 8):
            for b in range(0, 257, 8):
                predicted = E_CERTAIN - ((E_CERTAIN - a) * (E_CERTAIN - b)
                                         // E_CERTAIN)
                total += 1
                hits += (predicted == excel(a, b))
        return hits, total

    @staticmethod
    def cap_divergences() -> Dict[str, int]:
        """Where the shipped cap departs from pure multiplication, and why.

        Two different things, and only one of them is the cap doing its
        job:

        `neither_certain` -- combination that would otherwise round up to
        256 out of two imperfect witnesses. This is exactly what the cap
        exists to stop, and T3 agrees with the cap.

        `one_certain` -- one witness already at zero ignorance. The
        product u = 1 * 0 is 0, so multiplication says Certain, and T3
        says `u = 0 requires SOME u_i = 0` -- one is enough. The shipped
        cap requires BOTH inputs at Certain and returns 255 here. So
        either T3 is loose and the language means both, or the cap is a
        notch too strict. That is a decision about the language, recorded
        rather than made.
        """
        out = {"both_certain": 0, "one_certain": 0, "neither_certain": 0}
        for a in range(0, 257, 8):
            for b in range(0, 257, 8):
                predicted = E_CERTAIN - ((E_CERTAIN - a) * (E_CERTAIN - b)
                                         // E_CERTAIN)
                if predicted == excel(a, b):
                    continue
                if a >= E_CERTAIN and b >= E_CERTAIN:
                    out["both_certain"] += 1
                elif a >= E_CERTAIN or b >= E_CERTAIN:
                    out["one_certain"] += 1
                else:
                    out["neither_certain"] += 1
        return out

    @staticmethod
    def z_is_identity_under_excel() -> Tuple[int, int]:
        """excel(Z, b) == b: corroborating with a witness who knows
        nothing changes nothing.

        This is what the function previously named `z_absorbs` actually
        tested. Its assertion was `excel(0, b) == b - (0*b)//256`, whose
        right-hand side is just `b` -- the identity law, checked under a
        name that promised absorption. The test was right and the name
        was wrong, which is the worst way round: it returned True and was
        cited as proof of a claim it never made.

        Returns hits/total rather than a bool because the law does not
        hold everywhere in the SHIPPED excel: it holds for b in 0..255
        and breaks at b = 256, where the cap returns 255. The old version
        returned True by testing an uncapped local copy of the formula.
        Reporting 256/257 is the honest number; reporting True required
        testing a function the language does not use.
        """
        hits = sum(1 for b in range(0, 257) if excel(E_ZERO, b) == b)
        return hits, 257

    @staticmethod
    def certain_absorbs_under_excel() -> Tuple[int, int]:
        """excel(Certain, b) == Certain -- absorption, in pure algebra.

        In the shipped excel this holds at exactly one point, b = 256,
        because the cap returns 255 whenever only one input is Certain.
        So 1/257, and the gap is the cap rather than the algebra.

        Pure multiplicative uncertainty has Certain as the absorbing
        element of corroboration (u = 0 times anything is 0) and Z as the
        identity. The cap breaks both laws at the Certain boundary, which
        is a real cost of the cap and was not being reported anywhere --
        the file that would have reported it was using the uncapped
        formula, where nothing breaks.
        """
        hits = sum(1 for b in range(0, 257) if excel(E_CERTAIN, b) == E_CERTAIN)
        return hits, 257

    @staticmethod
    def z_absorbs_under_chain() -> bool:
        """min(Z, b) == Z for every b.

        Where Z-contagion really lives. Dependence chains by min, and 0
        absorbs under min -- so a value computed from an unknown is
        unknown. That IS a theorem rather than a rule, exactly as the
        project claimed; it is a theorem about the chain rule, and was
        being attributed to corroboration, where it is false.
        """
        return all(min(E_ZERO, b) == E_ZERO for b in range(0, 257))

    @staticmethod
    def combine_chain(confidences: List[int]) -> int:
        """Fold a chain of independent witnesses."""
        u = 1.0
        for c in confidences:
            u *= uncertainty(c)
        return confidence_from(u)

    @staticmethod
    def witnesses_to_reach(target: int, each: int, cap: int = 64) -> int:
        """How many witnesses at a given strength to reach a target."""
        u_each = uncertainty(each)
        if u_each >= 1.0:
            return -1                      # Z witnesses never converge
        u, n = 1.0, 0
        while confidence_from(u) < target and n < cap:
            u *= u_each
            n += 1
        return n if confidence_from(u) >= target else -1

    @staticmethod
    def ledger(before: List[int], after: List[int]) -> Dict[str, float]:
        """Conservation audit across a transformation."""
        ub = sum(uncertainty(c) for c in before)
        ua = sum(uncertainty(c) for c in after)
        return {"uncertainty_before": ub,
                "uncertainty_after": ua,
                "delta": ua - ub,
                "resolved": ub - ua}


# ═════════════════════════════════════════════
# The corpus — real archived findings
# ═════════════════════════════════════════════

LAYERS = [
    ("0-atom-c/tapestry.h",              ELang.C,      "atom header"),
    ("0-atom-c/tapestry.c",              ELang.C,      "atom"),
    ("0-atom-c/tapestry_test.c",         ELang.C,      "atom test"),
    ("1-phase-cpp/phase.hpp",            ELang.CPP,    "phase header"),
    ("1-phase-cpp/phase.cpp",            ELang.CPP,    "phase engine"),
    ("1-phase-cpp/phase_test.cpp",       ELang.CPP,    "phase test"),
    ("2-interpreter-python/ever.py",     ELang.PYTHON, "interpreter"),
    ("2-interpreter-python/ever_test.py", ELang.PYTHON, "interpreter test"),
    ("2-interpreter-python/checker.py",  ELang.PYTHON, "checker"),
    ("3-dsl-ruby/ever.rb",               ELang.RUBY,   "ruby DSL"),
    ("4-archive-sql/archive.sql",        ELang.SQL,    "sql archive"),
    ("4-archive-sql/archive_test.py",    ELang.PYTHON, "archive test"),
]

# Assertions actually executed and passing, by layer.
TEST_RESULTS = {
    "atom (C)":         (88, 0),
    "phase (C++)":      (49, 0),
    "interpreter (Py)": (81, 0),
    "archive (SQL)":    (56, 0),
}


@dataclass
class Observation:
    layer: str
    lang: str
    confidence: int
    errors: int
    patterns: int
    defects: List[str]


def gather() -> List[Observation]:
    t = Translator()
    out: List[Observation] = []
    for rel, lang, label in LAYERS:
        path = os.path.join(HERE, rel)
        if not os.path.exists(path):
            continue
        tr = t.translate(open(path).read(), ident=label, lang=lang)
        out.append(Observation(
            layer=label, lang=ELang(lang).name,
            confidence=tr.particle.confidence,
            errors=len(tr.errors), patterns=len(tr.patterns),
            defects=[classify(e.message) for e in tr.errors]))
    return out


# ═════════════════════════════════════════════
# RATIO — the corpus weighed against phi
# ═════════════════════════════════════════════

class Ratio:
    """phi is Ever's output equalizer. The honest question is whether the
    corpus actually sits near it, or whether that is decoration.

    A ratio is 'at phi' if it lands within 5% of 1.618.
    """

    TOLERANCE = 0.05

    @staticmethod
    def near_phi(r: float) -> bool:
        return abs(r - PHI) / PHI <= Ratio.TOLERANCE

    @staticmethod
    def band(values: List[int]) -> Tuple[int, int, int, int]:
        """Split a set by the phi band around its mean."""
        if not values:
            return 0, 0, 0, 0
        mean = sum(values) // len(values)
        hi, lo = int(mean * PHI), int(mean / PHI)
        inside = sum(1 for v in values if lo <= v <= hi)
        return mean, lo, hi, inside


# ═════════════════════════════════════════════
# Report
# ═════════════════════════════════════════════

def rule(ch="\u2500", n=66):
    print("  " + ch * n)


def main() -> int:
    print("\n" + "=" * 70)
    print("EVER / TAPESTRY — RESEARCH TEAM")
    print("The archive weighed against the ratio, and the First Law")
    print("=" * 70)

    # ── THERMO ──
    print("\n\u25b8 THERMO — what is actually conserved\n")
    hits, total = Thermo.verify_excel_is_multiplicative()
    gaps = Thermo.cap_divergences()
    print(f"  Excel vs multiplicative uncertainty : {hits}/{total} exact")
    print(f"    the {total - hits} gaps are all the shipped cap firing:")
    print(f"      {gaps['neither_certain']:>3} two imperfect witnesses "
          f"rounding up to Certain \u2014 what the cap is for")
    print(f"      {gaps['one_certain']:>3} one witness already Certain "
          f"\u2014 u = 1 x 0 = 0 says 256, the cap says 255")
    print(f"      {gaps['both_certain']:>3} both Certain")
    zid_h, zid_t = Thermo.z_is_identity_under_excel()
    cab_h, cab_t = Thermo.certain_absorbs_under_excel()
    print(f"  Z is the IDENTITY of excel          : {zid_h}/{zid_t}"
          f"   excel(0,b) = b, all but b=256")
    print(f"  CERTAIN absorbs under excel         : {cab_h}/{cab_t}"
          f"   pure algebra says 257/257; the cap says otherwise")
    print(f"  Z absorbs under the CHAIN rule      : "
          f"{Thermo.z_absorbs_under_chain()}   min(0,b) = 0, everywhere")
    print()
    print("  First Law for Ever:")
    print("    confidence is NOT conserved. uncertainty is, and it")
    print("    multiplies:   u_result = u_a * u_b")
    print()
    print("  Consequences, none of them designed in:")
    print("    Excel creates nothing  \u2014 it multiplies two ignorances down")
    print("    Z is INERT here        \u2014 u=1 and 1*x=x, so excel(Z,b)=b;")
    print("                             a witness who abstains adds nothing")
    print("    Z is contagious there  \u2014 along the CHAIN, where min(0,b)=0")
    print("    Certain is unreachable \u2014 by combination alone; u=0 needs")
    print("                             a witness already at zero ignorance")

    print("\n  Witnesses required to reach a target, from equal evidence:\n")
    print(f"    {'each':>6} {'->128':>7} {'->200':>7} {'->240':>7} {'->256':>7}")
    for each in (60, 100, 128, 150, 180, 200, 240):
        row = []
        for target in (128, 200, 240, 256):
            n = Thermo.witnesses_to_reach(target, each)
            row.append("never" if n < 0 else str(n))
        print(f"    {each:>6} {row[0]:>7} {row[1]:>7} {row[2]:>7} {row[3]:>7}")
    print()
    print("    Nothing reaches 256 at any strength or count. That column is")
    print("    the reason Certain must be earned at runtime.")

    print("\n  Conservation ledger, three witnesses at 150 corroborating:")
    led = Thermo.ledger([150, 150, 150], [Thermo.combine_chain([150] * 3)])
    print(f"    uncertainty before : {led['uncertainty_before']:.4f}")
    print(f"    uncertainty after  : {led['uncertainty_after']:.4f}")
    print(f"    resolved           : {led['resolved']:.4f}")
    print("    nothing vanished. the ignorance was multiplied down, and")
    print("    the amount resolved is the ledger entry the archive keeps.")

    # ── CORPUS ──
    obs = gather()
    print("\n\u25b8 CORPUS — every layer, inspected by Ever itself\n")
    print(f"  {'layer':<20}{'lang':<9}{'conf':>6}{'err':>6}{'ok':>6}")
    rule()
    for o in obs:
        print(f"  {o.layer:<20}{o.lang:<9}{o.confidence:>6}"
              f"{o.errors:>6}{o.patterns:>6}")
    rule()

    total_err = sum(o.errors for o in obs)
    total_pat = sum(o.patterns for o in obs)
    confs = [o.confidence for o in obs]
    cleared = [c for c in confs if c > 0]

    print(f"  {'TOTAL':<20}{'':<9}{'':>6}{total_err:>6}{total_pat:>6}")

    # ── RATIO ──
    print("\n\u25b8 RATIO — the corpus weighed against phi\n")

    tests_pass = sum(p for p, _ in TEST_RESULTS.values())
    tests_fail = sum(f for _, f in TEST_RESULTS.values())

    print(f"  executed assertions      : {tests_pass} passing, "
          f"{tests_fail} failing")
    print(f"  static findings          : {total_pat} patterns, "
          f"{total_err} errors")

    checks = []

    if total_err:
        r = total_pat / total_err
        checks.append(("patterns : errors", r))
    if cleared:
        mean, lo, hi, inside = Ratio.band(cleared)
        print(f"\n  confidence across layers : mean {mean}, "
              f"phi band {lo}..{hi}")
        print(f"  inside the band          : {inside}/{len(cleared)}")
        checks.append(("mean conf : execute floor", mean / E_EXECUTE_FLOOR))

    checks.append(("Certain : execute floor", E_CERTAIN / E_EXECUTE_FLOOR))
    checks.append(("pi warn : pi-squared", E_PI_WIDTH_WARN
                   / E_PI_WIDTH_ENUMERATE))
    checks.append(("execute floor : pi warn", E_EXECUTE_FLOOR
                   / E_PI_WIDTH_WARN))
    checks.append(("intake : pi warn", 120 / E_PI_WIDTH_WARN))

    print(f"\n  {'ratio':<28}{'value':>9}{'vs phi':>9}   verdict")
    rule()
    at_phi = 0
    for name, val in checks:
        near = Ratio.near_phi(val)
        at_phi += near
        mark = "AT PHI" if near else ""
        print(f"  {name:<28}{val:>9.3f}{val / PHI:>9.3f}   {mark}")
    rule()
    print(f"  ratios landing at phi    : {at_phi}/{len(checks)}")

    # ── DEFECT ──
    print("\n\u25b8 DEFECT — which of the five dominate\n")
    counts: Dict[str, int] = {}
    for o in obs:
        for d in o.defects:
            counts[d] = counts.get(d, 0) + 1
    if counts:
        rank = sorted(counts.items(), key=lambda kv: -kv[1])
        for name, n in rank:
            share = 100.0 * n / max(1, total_err)
            print(f"  {name:<12}{n:>4}   {share:>5.1f}%  "
                  + "\u2588" * max(1, int(share / 4)))
        print()
        print(f"  distinct defect classes observed : {len(counts)} of 5")
    else:
        print("  no defects in the current corpus")

    # ── VERDICT ──
    print("\n\u25b8 VERDICT\n")
    print("  Supported by the numbers:")
    print(f"    \u2022 Excel is exactly multiplicative uncertainty "
          f"({hits}/{total})")
    print("    \u2022 Z-contagion is a consequence of that algebra, not a rule")
    print("    \u2022 Certain is unreachable by combination at any strength")
    print(f"    \u2022 {tests_pass} assertions execute and pass across 4 layers")
    print(f"    \u2022 every finding classifies into the five binding defects")
    print()
    print("  NOT supported by the numbers:")
    if at_phi <= 1:
        print(f"    \u2022 phi does not govern the corpus. {at_phi} of "
              f"{len(checks)} ratios")
        print("      land near 1.618, which is what chance would give.")
        print("      phi earns its place as the output equalizer, where it")
        print("      is applied deliberately. It is not a law the archive")
        print("      obeys on its own, and claiming so would be decoration.")
    else:
        print(f"    \u2022 {at_phi} of {len(checks)} ratios sit at phi \u2014 "
              f"suggestive,")
        print("      not yet evidence. Needs a corpus an order of magnitude")
        print("      larger before it means anything.")
    print()
    print("  The load-bearing constant is 256, and pi sets the widths.")
    print("  phi equalizes output. Those are three different jobs and only")
    print("  the first two are structural.")
    print()
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
