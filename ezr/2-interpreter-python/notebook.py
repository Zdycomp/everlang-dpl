#!/usr/bin/env python3
"""
notebook.py — Ever / Tapestry, the notebook batch

Twelve cells. Most of them wrong on purpose.

Every cell states what SHOULD happen before Ever sees it, then Ever runs
for real, and the two are compared. A cell where Ever produces the right
answer for the wrong reason is scored as a miss, and a cell where Ever
refuses when refusing was correct is scored as a hit.

The point is not to make Ever look good. The point is to find out where
it is wrong, so the refinement layer knows what it is refining.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ever import (
    E, State, Defect, Lang, e_z, e_val,
    E_CERTAIN, E_EXECUTE_FLOOR, E_INTAKE,
)
from abstract import Lambda, Closure, a_anchor_fn, DepthExceeded
from vowels import (
    Spec, i_implement, i_integrate, o_overcome, o_optimize, Ledger,
    u_understand, u_undermine, u_ultracode, o_own, o_obliterate,
)
from checker import Translator, ELang, classify


# ═════════════════════════════════════════════
# A cell
# ═════════════════════════════════════════════

@dataclass
class Cell:
    n: int
    title: str
    kind: str                      # "synth" | "inspect"
    payload: Any
    should: str                    # stated before Ever runs
    check: Callable[[Any], bool]   # was Ever right?
    lang: Optional[ELang] = None

    # filled in by the run
    got: str = ""
    hit: bool = False
    detail: str = ""
    ms: int = 0


# ═════════════════════════════════════════════
# The twelve. Mostly wrong on purpose.
# ═════════════════════════════════════════════

BROKEN_C = """
#include <stdio.h>
int total(int *v, int n) {
    int sum = 0
    char buf[8];
    gets(buf);
    for (int i = 0; i <= n; i++) sum += v[i];
    return sum;
}
"""

BROKEN_SQL = """
SELECT * FROM accounts a JOIN ledger l
WHERE a.name = '" + userName + "';
DELETE FROM sessions;
DROP TABLE audit;
"""

BROKEN_PYTHON = """
def collect(items=[], raw=None):
    for line in raw.split(","):
        items.append(eval(line))
    try:
        return items
    except:
        pass
"""

BROKEN_JAVA = """
public class Cart {
    public boolean isOwner(String who) {
        String owner = null;
        if (who == "admin") { return true }
        return owner.equals(who);
    }
    public void run() { try { work(); } catch (Exception e) {} }
}
"""

BROKEN_RUBY = """
$cart_total = 0
def add_item(name, price)
  $cart_total += price
  rescue
  puts "added #{name}"
"""

BROKEN_HTML = """
<div class="checkout">
  <img src="lock.png">
  <form>
    <input placeholder="card number">
    <a href="/pay" target="_blank">Pay now</a>
  </form>
</div>
"""


def build_cells() -> List[Cell]:
    return [
        # ── 1. a spec that contradicts itself ──
        Cell(1, "Contradictory spec: f(2) is both 4 and 5", "synth",
             Spec("f", ["n"], [([1], 2), ([2], 4), ([2], 5), ([3], 6)]),
             should="REFUSE — no function satisfies both f(2)=4 and f(2)=5",
             check=lambda r: r.is_z),

        # ── 2. a clean spec that should work ──
        Cell(2, "Clean spec: factorial", "synth",
             Spec("fact", ["n"], [([1], 1), ([2], 2), ([3], 6), ([4], 24)]),
             should="SYNTHESISE a recursive factorial above the floor",
             check=lambda r: (not r.is_z) and r.can_execute),

        # ── 3. broken C ──
        Cell(3, "Broken C: missing semicolon, gets(), off-by-one", "inspect",
             BROKEN_C, lang=ELang.C,
             should="FLAG missing semicolon and the gets() overflow",
             check=lambda t: any("semicolon" in e.message for e in t.errors)
                         and any("gets" in e.message for e in t.errors)),

        # ── 4. broken SQL ──
        Cell(4, "Broken SQL: injection, unbounded DELETE, DROP", "inspect",
             BROKEN_SQL, lang=ELang.SQL,
             should="FLAG the unbounded DELETE and the string concatenation",
             check=lambda t: any("without WHERE" in e.message for e in t.errors)
                         and any("concatenation" in e.message for e in t.errors)),

        # ── 5. ambiguous spec: identity and squaring both fit ──
        Cell(5, "Ambiguous spec: f(1)=1, f(2)=2 fits many functions", "synth",
             Spec("amb", ["n"], [([1], 1), ([2], 2)]),
             should="SYNTHESISE something, but the corpus should not agree "
                    "on unseen inputs",
             check=lambda r: not r.is_z),

        # ── 6. broken Python ──
        Cell(6, "Broken Python: mutable default, eval, bare except", "inspect",
             BROKEN_PYTHON, lang=ELang.PYTHON,
             should="FLAG the mutable default, eval, and the bare except",
             check=lambda t: any("mutable default" in e.message for e in t.errors)
                         and any("eval" in e.message for e in t.errors)),

        # ── 7. a spec Ever's grammar cannot express ──
        # The original expectation here was mine and it was wrong. Ever
        # was asked for a function fitting 2,3,5,7 and it found one:
        # n + f(n-2). That satisfies the spec exactly. It is not prime
        # after n=4, but nothing in the spec said prime. The honest test
        # is whether the confidence reflects that the evidence did not
        # pin the function down.
        Cell(7, "Underdetermined: first four primes, no rule given", "synth",
             Spec("prime", ["n"], [([1], 2), ([2], 3), ([3], 5), ([4], 7)]),
             should="FIT the four examples but REFUSE to certify: four "
                    "points and one idea determine nothing",
             check=lambda r: r.is_z or (not r.can_execute)),

        # ── 8. broken Java ──
        Cell(8, "Broken Java: null deref, == on strings, empty catch",
             "inspect", BROKEN_JAVA, lang=ELang.JAVA,
             should="FLAG the unguarded null and the string ==",
             check=lambda t: any("null used without a guard" in e.message
                                 for e in t.errors)
                         and any("compared with ==" in e.message
                                 for e in t.errors)),

        # ── 9. broken Ruby ──
        Cell(9, "Broken Ruby: missing end, global, bare rescue", "inspect",
             BROKEN_RUBY, lang=ELang.RUBY,
             should="FLAG the missing end and the global variable",
             check=lambda t: any("missing end" in e.message for e in t.errors)
                         and any("global" in e.message for e in t.errors)),

        # ── 10. triangular numbers, clean ──
        Cell(10, "Clean spec: triangular numbers", "synth",
             Spec("tri", ["n"], [([1], 1), ([2], 3), ([3], 6), ([4], 10)]),
             should="SYNTHESISE a recursive sum above the floor",
             check=lambda r: (not r.is_z) and r.can_execute),

        # ── 11. broken HTML ──
        Cell(11, "Broken HTML: no alt, unlabelled input, target=_blank",
             "inspect", BROKEN_HTML, lang=ELang.HTML,
             should="FLAG the missing alt and the noopener omission",
             check=lambda t: any("without alt" in e.message for e in t.errors)
                         and any("noopener" in e.message for e in t.errors)),

        # ── 12b. one example only: the cap must bite ──
        Cell(12, "Wrong arithmetic: doubling stated as 1,4,9,17", "synth",
             Spec("dbl", ["n"], [([1], 1), ([2], 4), ([3], 9), ([4], 17)]),
             should="REFUSE — 17 breaks the square pattern the rest implies",
             check=lambda r: r.is_z),

        # ── 13. a single example determines almost nothing ──
        Cell(13, "One example only: g(2)=6", "synth",
             Spec("g", ["n"], [([2], 6)]),
             should="FIT it, but cap confidence below the execute floor — "
                    "one point cannot determine a function",
             check=lambda r: (not r.is_z) and (not r.can_execute)),
    ]


# ═════════════════════════════════════════════
# The archive — cells persist
# ═════════════════════════════════════════════

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(HERE, "..", "archive", "notebook.db")


def open_archive() -> Optional[sqlite3.Connection]:
    try:
        os.makedirs(os.path.dirname(ARCHIVE), exist_ok=True)
        con = sqlite3.connect(ARCHIVE)
        con.executescript("""
        CREATE TABLE IF NOT EXISTS cell_run (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            cell_no   INTEGER NOT NULL,
            title     TEXT NOT NULL,
            kind      TEXT NOT NULL,
            expected  TEXT NOT NULL,
            got       TEXT NOT NULL,
            hit       INTEGER NOT NULL,
            detail    TEXT NOT NULL DEFAULT '',
            ms        INTEGER NOT NULL DEFAULT 0,
            ran_ms    INTEGER NOT NULL
        );
        """)
        con.commit()
        return con
    except Exception:
        return None


# ═════════════════════════════════════════════
# Running
# ═════════════════════════════════════════════

def run_synth(cell: Cell) -> None:
    spec: Spec = cell.payload
    t0 = time.time()
    fn, tried = i_implement(spec)
    cell.ms = int((time.time() - t0) * 1000)

    sat = [c for c in tried if c.satisfies]
    cell.hit = cell.check(fn)

    if fn.is_z:
        cell.got = "REFUSED"
        best = max((c.passed for c in tried), default=0)
        cell.detail = (f"{len(tried)} candidates, none satisfied "
                       f"(best {best}/{len(spec.examples)})")
    else:
        cell.got = f"SYNTHESISED @ {fn.confidence}/256"
        body = fn.value.body if isinstance(fn.value, Closure) else "?"
        cell.detail = f"{len(sat)}/{len(tried)} satisfied · {body}"

        # criticism, and only where there is something to criticise
        atk = u_undermine(fn, spec)
        if not atk.is_z:
            cell.detail += f" · undermined by {len(atk.value)} probe(s)"


def run_inspect(cell: Cell) -> None:
    t0 = time.time()
    tr = Translator().translate(cell.payload, ident=f"cell{cell.n}",
                                lang=cell.lang)
    cell.ms = int((time.time() - t0) * 1000)
    cell.hit = cell.check(tr)

    state = "Z" if tr.particle.is_z else "CONFIDENT"
    cell.got = f"{state} @ {tr.particle.confidence}/256"
    defects = sorted({classify(e.message) for e in tr.errors})
    cell.detail = (f"{len(tr.errors)} error(s), {len(tr.patterns)} pattern(s)"
                   + (f" · defects: {', '.join(defects)}" if defects else ""))


# ═════════════════════════════════════════════
# Report
# ═════════════════════════════════════════════

def main() -> int:
    cells = build_cells()
    con = open_archive()

    print("\n" + "=" * 74)
    print("EVER — NOTEBOOK BATCH · 12 cells, most of them wrong on purpose")
    print("=" * 74)

    for c in cells:
        print(f"\n\u25b8 CELL {c.n:>2} — {c.title}")
        print(f"   should : {c.should}")
        try:
            if c.kind == "synth":
                run_synth(c)
            else:
                run_inspect(c)
        except Exception as exc:
            c.got = "CRASHED"
            c.hit = False
            c.detail = f"{type(exc).__name__}: {str(exc)[:70]}"

        mark = "\u2713" if c.hit else "\u2717"
        print(f"   Ever   : {c.got}")
        print(f"   detail : {c.detail}")
        print(f"   verdict: {mark} {'as expected' if c.hit else 'MISS'}"
              f"   ({c.ms} ms)")

        if con:
            con.execute(
                "INSERT INTO cell_run (cell_no,title,kind,expected,got,hit,"
                "detail,ms,ran_ms) VALUES (?,?,?,?,?,?,?,?,?)",
                (c.n, c.title, c.kind, c.should, c.got, int(c.hit),
                 c.detail, c.ms, int(time.time() * 1000)))
    if con:
        con.commit()

    # ── scorecard ──
    hits = sum(1 for c in cells if c.hit)
    synth = [c for c in cells if c.kind == "synth"]
    insp = [c for c in cells if c.kind == "inspect"]

    print("\n" + "=" * 74)
    print("SCORECARD")
    print("=" * 74)
    print(f"\n  {'cell':<6}{'kind':<10}{'result':<26}{'verdict':<10}")
    print("  " + "\u2500" * 66)
    for c in cells:
        print(f"  {c.n:<6}{c.kind:<10}{c.got:<26}"
              f"{'hit' if c.hit else 'MISS':<10}")
    print("  " + "\u2500" * 66)
    print(f"\n  overall     {hits}/{len(cells)}")
    print(f"  synthesis   {sum(1 for c in synth if c.hit)}/{len(synth)}")
    print(f"  inspection  {sum(1 for c in insp if c.hit)}/{len(insp)}")

    misses = [c for c in cells if not c.hit]
    if misses:
        print("\n  MISSES — where Ever was wrong:\n")
        for c in misses:
            print(f"    cell {c.n}: {c.title}")
            print(f"      expected : {c.should}")
            print(f"      got      : {c.got} — {c.detail}")
    else:
        print("\n  no misses")

    if con:
        total = con.execute("SELECT COUNT(*) FROM cell_run").fetchone()[0]
        print(f"\n  archived: {total} cell runs across all sessions")
        con.close()

    print("\n" + "=" * 74 + "\n")
    return 0 if not misses else 1


if __name__ == "__main__":
    raise SystemExit(main())
