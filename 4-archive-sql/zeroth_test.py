#!/usr/bin/env python3
"""zeroth_test.py — 4Ever Layer 4 verification, the Zeroth Law.

Two jobs.

1. The law holds in SQL: bands partition the scale, and equilibrium is
   reflexive, symmetric and transitive over every value the archive can
   store.

2. The archive REFUSES what the law forbids. That is the thing this
   layer adds over the others — elsewhere equilibrium is a predicate a
   caller can forget to call; here it is a constraint.
"""

import atexit
import os
import shutil
import sqlite3
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# A fresh directory, never beside the source (see repair_test.py).
DB_DIR = tempfile.mkdtemp(prefix="zeroth-archive-")
atexit.register(shutil.rmtree, DB_DIR, True)
DB = os.path.join(DB_DIR, "zeroth.db")

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  ✓ {name}")
    else:
        failed += 1; print(f"  ✗ {name}")


def refusal(con, sql, params=()):
    try:
        con.execute(sql, params); con.commit(); return None
    except sqlite3.DatabaseError as e:
        con.rollback(); return str(e)


def refuses(con, sql, params=()):
    return refusal(con, sql, params) is not None


print("\n=== 4Ever Layer 4 (SQL) — the Zeroth Law ===\n")

con = sqlite3.connect(DB)
con.executescript(open(os.path.join(HERE, "archive.sql")).read())
con.executescript(open(os.path.join(HERE, "zeroth.sql")).read())
con.execute("PRAGMA foreign_keys = ON")
con.commit()

# ─────────────────────────────────────────────
print("The bands partition the scale")

bands = con.execute(
    "SELECT id, name, lo, hi FROM ever_band ORDER BY id").fetchall()
ok("six bands", len(bands) == 6)
ok("first is Z at exactly 0",       bands[0][1:] == ('Z', 0, 0))
ok("last is Certain at exactly 256", bands[5][1:] == ('Certain', 256, 256))

# Contiguous and non-overlapping — that is what makes band a function.
contiguous = all(bands[i][3] + 1 == bands[i + 1][2] for i in range(5))
ok("bands are contiguous, no gaps",   contiguous)
ok("bands start at 0",                bands[0][2] == 0)
ok("bands end at 256",                bands[5][3] == 256)

rows = con.execute("SELECT confidence, band_id FROM v_band").fetchall()
ok("v_band covers all 257 values",    len(rows) == 257)
ok("band is single-valued",
   len(rows) == len({c for c, _ in rows}) == 257)

# ─────────────────────────────────────────────
print("\nEquilibrium is an equivalence relation, over every value")

band_of = dict(rows)
S = range(0, 257)
ok("reflexive over all 257 values",
   all(band_of[a] == band_of[a] for a in S))
ok("symmetric over all 66,049 pairs",
   all((band_of[a] == band_of[b]) == (band_of[b] == band_of[a])
       for a in S for b in S))
ok("transitive over every triple",
   all(band_of[a] == band_of[c]
       for a in S for b in S if band_of[a] == band_of[b]
       for c in S if band_of[b] == band_of[c]))

# The relation the law replaces, measured rather than asserted.
W = 81
near = lambda a, b: abs(a - b) < W
viol = sum(1 for a in S for b in S if near(a, b)
             for c in S if near(b, c) and not near(a, c))
ok("proximity is reflexive",  all(near(a, a) for a in S))
ok("proximity is symmetric",  all(near(a, b) == near(b, a)
                                  for a in S for b in S))
ok("proximity is NOT transitive",              viol > 0)
ok("and it breaks 969,840 triples exactly",    viol == 969_840)

ok("Z is in equilibrium only with Z",
   sum(1 for c in S if band_of[c] == 0) == 1)
ok("Certain is in equilibrium only with Certain",
   sum(1 for c in S if band_of[c] == 5) == 1)
ok("255 and 256 are NOT in equilibrium",
   band_of[255] != band_of[256])
ok("but proximity would have said they were", near(255, 256))

# ─────────────────────────────────────────────
print("\nThe archive refuses what the law forbids")

con.execute("INSERT INTO run (started_ms, label) VALUES (1, 'zeroth')")
con.execute(
    "INSERT INTO anchor (anchor_id, ident, pinned_at, pinned_conf, note) "
    "VALUES (7001, 'total', 1, 200, 'test anchor')")
con.commit()

X = ("INSERT INTO crossing (anchor_id, thread_id, from_lang, to_lang, "
     "conf_before, conf_after, crossed_ms) VALUES (?,?,?,?,?,?,?)")

# A thread has to exist for the FK; borrow the archive's own shape.
con.execute(
    "INSERT INTO thread (archive_id, ident, state_id, type_id, lang_id, confidence, "
    "lo, hi, born_ms, reason, anchor_id) "
    "VALUES (901, 'total', 1, 1, 0, 128, 128, 128, 1, 'test', 7001)")
con.commit()

ok("anchored crossing that holds its band is accepted", not refuses(
    con, X, (7001, 901, 0, 5, 200, 200, 2)))

ok("anchored crossing that changes band is REFUSED", refuses(
    con, X, (7001, 901, 0, 5, 128, 127, 3)))

ok("anchored crossing across the Certain edge is REFUSED", refuses(
    con, X, (7001, 901, 0, 5, 256, 255, 4)))

# 127 to 128 gains confidence, so the older anchor trigger lets it pass.
# Only the band law refuses it, and the message says so.
ok("anchored crossing into the next band is refused by the band law",
   "Zeroth Law" in (refusal(con, X, (7001, 901, 0, 5, 127, 128, 8)) or ""))

ok("confidence above 256 is REFUSED", refuses(
    con, X, (7001, 901, 0, 5, 300, 300, 5)))

ok("negative confidence is REFUSED", refuses(
    con, X, (None, 901, 0, 5, -1, -1, 6)))

# The unanchored case is legal and visible, not forbidden. Drift that
# is recorded is the point; drift that is silent is the failure.
ok("unanchored crossing that changes band is allowed", not refuses(
    con, X, (None, 901, 0, 5, 128, 127, 7)))
ok("and it shows up as drift",
   con.execute("SELECT COUNT(*) FROM v_band_drift").fetchone()[0] == 1)
ok("recorded as unanchored",
   con.execute("SELECT carriage FROM v_band_drift").fetchone()[0]
   == 'unanchored')
ok("naming the bands it moved between",
   con.execute("SELECT band_before, band_after FROM v_band_drift"
               ).fetchone() == ('Executable', 'Subfloor'))

print("\nThe law's own table is closed")
ok("UPDATE on a band is refused", refuses(
    con, "UPDATE ever_band SET hi = 300 WHERE id = 5"))
ok("DELETE on a band is refused", refuses(
    con, "DELETE FROM ever_band WHERE id = 1"))
ok("overlapping band still refused after the attempts",
   con.execute("SELECT hi FROM ever_band WHERE id = 5").fetchone()[0] == 256)
ok("INSERT OR REPLACE that moves a boundary is REFUSED", refuses(
    con, "INSERT OR REPLACE INTO ever_band (id, name, lo, hi, derivation) "
         "VALUES (5, 'Certain', 200, 256, 'x')"))
ok("INSERT OR REPLACE that leaves a gap is REFUSED", refuses(
    con, "INSERT OR REPLACE INTO ever_band (id, name, lo, hi, derivation) "
         "VALUES (4, 'Executable', 128, 250, 'x')"))
ok("a new overlapping band is REFUSED", refuses(
    con, "INSERT INTO ever_band (id, name, lo, hi, derivation) "
         "VALUES (9, 'Probe', 200, 230, 'x')"))
ok("the bands still partition the scale after the attempts",
   con.execute("SELECT COUNT(*), COUNT(DISTINCT confidence) FROM v_band"
               ).fetchone() == (257, 257))

print("\nCorrelation")
ok("thread lands in Executable",
   con.execute("SELECT band_name FROM v_thread_band WHERE archive_id = 901"
               ).fetchone()[0] == 'Executable')
ok("equilibrium classes are enumerable",
   con.execute("SELECT COUNT(*) FROM v_equilibrium_class").fetchone()[0] == 6)

# A thread sitting exactly on a band floor, unanchored, is one hop from
# demotion. The archive can name those before they travel.
con.execute(
    "INSERT INTO thread (archive_id, ident, state_id, type_id, lang_id, confidence, "
    "lo, hi, born_ms, reason, anchor_id) "
    "VALUES (902, 'edge', 1, 1, 0, 128, 128, 128, 1, 'on the floor', 0)")
con.commit()
ok("an unanchored thread on a band floor is flagged at risk",
   con.execute("SELECT ident FROM v_at_risk").fetchone()[0] == 'edge')
ok("the anchored one is not flagged",
   con.execute("SELECT COUNT(*) FROM v_at_risk").fetchone()[0] == 1)

print("\nPersistence")
con.close()
con2 = sqlite3.connect(DB)
ok("bands survive reconnect",
   con2.execute("SELECT COUNT(*) FROM ever_band").fetchone()[0] == 6)
ok("drift survives reconnect",
   con2.execute("SELECT COUNT(*) FROM v_band_drift").fetchone()[0] == 1)
con2.executescript(open(os.path.join(HERE, "zeroth.sql")).read())
ok("reloading the law keeps six bands and 257 single-valued rows",
   con2.execute("SELECT COUNT(*) FROM ever_band").fetchone()[0] == 6
   and con2.execute("SELECT COUNT(*), COUNT(DISTINCT confidence) FROM v_band"
                    ).fetchone() == (257, 257))
con2.close()

print(f"\n=== Layer 4 (zeroth): {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
