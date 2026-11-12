#!/usr/bin/env python3
"""repair_test.py — Codric Layer 4 verification, repair schema.

Drives repair.sql through Python's sqlite3. The point of the suite is
not that the tables exist — it is that the database REFUSES the things
ReFix's JavaScript refuses. If an invariant only holds in one of the
two implementations, it is not an invariant, it is a convention.

Every `refuses(...)` case below has a matching throw in
7-refix-node/src/archive.js.
"""

import atexit
import os
import re
import shutil
import sqlite3
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# A fresh directory, never beside the source: the archive's invariant is that
# nothing is deleted, so this suite must not depend on deleting a repo file.
DB_DIR = tempfile.mkdtemp(prefix="repair-archive-")
atexit.register(shutil.rmtree, DB_DIR, True)
DB = os.path.join(DB_DIR, "repair.db")

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  ✓ {name}")
    else:
        failed += 1; print(f"  ✗ {name}")


def refuses(con, sql, params=()):
    """The corpus should refuse this. True if it did."""
    try:
        con.execute(sql, params); con.commit(); return False
    except sqlite3.DatabaseError:
        con.rollback(); return True


print("\n=== Codric Layer 4 (SQL) — the repair archive ===\n")

con = sqlite3.connect(DB)
con.executescript(open(os.path.join(HERE, "archive.sql")).read())
con.executescript(open(os.path.join(HERE, "repair.sql")).read())
con.execute("PRAGMA foreign_keys = ON")
con.commit()

# ─────────────────────────────────────────────
print("Schema")
names = lambda t: [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type=? ORDER BY name", (t,))]
tables, views, triggers = names('table'), names('view'), names('trigger')
ok("repair table exists",           "repair" in tables)
ok("repair_rule table exists",      "repair_rule" in tables)
ok("repair_signature table exists", "repair_signature" in tables)
ok("repair_kind vocabulary",        "repair_kind" in tables)
ok("candidate view exists",         "v_repair_candidate" in views)
ok("replay view exists",            "v_repair_replay" in views)
ok("rule ledger view exists",       "v_repair_rule" in views)
ok("error catch table exists",     "error_catch" in tables)
ok("error catch view exists",      "v_error_catch" in views)
ok("error recurrence view exists", "v_error_recurrence" in views)
ok("nine repair triggers",
   len([t for t in triggers if "repair" in t or "rule" in t]) == 9)

# ─────────────────────────────────────────────
print("\nConstants agree with 7-refix-node/src/constants.js")
K = dict(con.execute("SELECT name, value FROM ever_constant"))
ok("E_CERTAIN 256",         K['E_CERTAIN'] == 256)
ok("E_EXECUTE_FLOOR 128",   K['E_EXECUTE_FLOOR'] == 128)
ok("E_INTAKE 120",          K['E_INTAKE'] == 120)
ok("E_ASCEND_POINTS 3",     K['E_ASCEND_POINTS'] == 3)
ok("E_REPAIR_PLAIN 8",      K['E_REPAIR_PLAIN'] == 8)
ok("E_REPAIR_INFERRED 32",  K['E_REPAIR_INFERRED'] == 32)
ok("plain cost = 256/32",   K['E_REPAIR_PLAIN'] == 256 // 32)
ok("inferred cost = 256/8", K['E_REPAIR_INFERRED'] == 256 // 8)
ok("inferred costs 4x plain",
   K['E_REPAIR_INFERRED'] == 4 * K['E_REPAIR_PLAIN'])

JS_CONSTANTS = os.path.join(HERE, "..", "7-refix-node", "src", "constants.js")
with open(JS_CONSTANTS) as f:
    JS = {n: int(v) for n, v in re.findall(r"^\s*(E_[A-Z_]+):\s*(\d+),", f.read(), re.M)}
ok("constants.js declares the seven ReFix constants", len(JS) == 7)
ok("every constants.js name exists in ever_constant", all(n in K for n in JS))
ok("constants.js agrees with ever_constant on every value",
   all(K[n] == v for n, v in JS.items() if n in K))

# ─────────────────────────────────────────────
print("\nSignatures")
con.execute(
    "INSERT INTO repair_signature (signature_id,family,kind,lang,match_re,"
    "fixture_form,fixture_text,authored_ms) VALUES "
    "('agp_too_old','agp',1,5,'requires Android Gradle plugin',"
    "'agp>={want}','Upgrade AGP to 8.5.2',1)")
con.execute(
    "INSERT INTO repair_signature (signature_id,family,kind,lang,match_re,"
    "fixture_form,fixture_text,authored_ms) VALUES "
    "('sdk_not_found','sdk',0,5,'SDK location not found',"
    "'sdk.dir','Set sdk.dir in local.properties',1)")
con.commit()
ok("two signatures stored",
   con.execute("SELECT COUNT(*) FROM repair_signature").fetchone()[0] == 2)
ok("signature with empty fixture refused", refuses(con,
    "INSERT INTO repair_signature (signature_id,family,kind,lang,match_re,"
    "fixture_form,fixture_text,authored_ms) VALUES "
    "('half','x',0,5,'boom','','',1)"))

# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
print("\nError catches")
con.execute("INSERT INTO error_catch (captured_ms,source_ident,stage,message,context,fingerprint) VALUES (?,?,?,?,?,?)",
            (30, 'repo-error', 'compile', 'SDK location not found', 'gradle stderr', 'deadbeef'))
con.commit()
ok("error catch is archived", con.execute("SELECT COUNT(*) FROM error_catch").fetchone()[0] == 1)
ok("error recurrence is queryable", con.execute("SELECT seen FROM v_error_recurrence WHERE fingerprint='deadbeef'").fetchone()[0] == 1)
ok("error catch delete refused", refuses(con, "DELETE FROM error_catch WHERE error_id=1"))
ok("error catch update refused", refuses(con, "UPDATE error_catch SET message='changed' WHERE error_id=1"))

# ─────────────────────────────────────────────
print("\nA repair is a pair")
INS = ("INSERT INTO repair (archived_ms,lang,signature_id,kind,source_ident,"
       "line_no,failure_text,fixture_text,fixture_form,reason,cost,"
       "conf_before,conf_after) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)")

con.execute(INS, (10, 5, 'agp_too_old', 1, 'repo-a', 3,
                  'requires Android Gradle plugin 8.5.2',
                  'Upgrade AGP to 8.5.2', 'agp>=8.5.2', '', 32, 256, 224))
con.commit()
ok("inferred repair archived",
   con.execute("SELECT COUNT(*) FROM repair").fetchone()[0] == 1)

ok("empty failure_text refused", refuses(con, INS,
    (11, 5, 'agp_too_old', 1, 'repo-a', 3, '', 'fix', 'f', '', 32, 256, 224)))
ok("empty fixture_text refused", refuses(con, INS,
    (11, 5, 'agp_too_old', 1, 'repo-a', 3, 'boom', '', 'f', '', 32, 256, 224)))
ok("unknown kind refused", refuses(con, INS,
    (11, 5, 'agp_too_old', 7, 'repo-a', 3, 'boom', 'fix', 'f', '', 32, 256, 224)))
ok("unknown signature refused", refuses(con, INS,
    (11, 5, 'no_such_sig', 1, 'repo-a', 3, 'boom', 'fix', 'f', '', 32, 256, 224)))

# ─────────────────────────────────────────────
print("\nCost is derived, not supplied")
ok("plain repair priced as inferred is refused", refuses(con, INS,
    (12, 5, 'sdk_not_found', 0, 'repo-a', 1, 'SDK location not found',
     'Set sdk.dir', 'sdk.dir', '', 32, 256, 224)))
ok("inferred repair priced as plain is refused", refuses(con, INS,
    (12, 5, 'agp_too_old', 1, 'repo-a', 1, 'boom', 'fix', 'f', '', 8, 256, 248)))
ok("conf_after not equal to conf_before - cost is refused", refuses(con, INS,
    (12, 5, 'agp_too_old', 1, 'repo-a', 1, 'boom', 'fix', 'f', '', 32, 256, 200)))

print("\nConfidence never rises through a repair")
ok("rising confidence refused", refuses(con, INS,
    (13, 5, 'agp_too_old', 1, 'repo-a', 1, 'boom', 'fix', 'f', '', 32, 100, 132)))
ok("conf_before over 256 refused", refuses(con, INS,
    (13, 5, 'agp_too_old', 1, 'repo-a', 1, 'boom', 'fix', 'f', '', 32, 300, 268)))

# Four inferred repairs land exactly on the execute floor: 256 - 4*32 = 128.
con.execute(INS, (14, 5, 'agp_too_old', 1, 'repo-b', 3, 'boom', 'fix',
                  'agp>=8.5.2', '', 32, 224, 192))
con.execute(INS, (15, 5, 'agp_too_old', 1, 'repo-c', 3, 'boom', 'fix',
                  'agp>=8.5.2', '', 32, 192, 160))
con.execute(INS, (16, 5, 'agp_too_old', 1, 'repo-c', 4, 'boom', 'fix',
                  'agp>=8.5.2', '', 32, 160, 128))
con.commit()
ok("four inferred repairs land on E_EXECUTE_FLOOR",
   con.execute("SELECT conf_after FROM repair ORDER BY repair_id DESC LIMIT 1"
               ).fetchone()[0] == K['E_EXECUTE_FLOOR'])
ok("floor is not breached by a fifth", 256 - 5 * 32 < K['E_EXECUTE_FLOOR'])

# ─────────────────────────────────────────────
print("\nRecurrence counts distinct sources, not rows")
cands = con.execute(
    "SELECT signature_id, seen, distinct_sources FROM v_repair_candidate"
).fetchall()
ok("one candidate cleared the threshold", len(cands) == 1)
ok("candidate is the AGP fixture", cands[0][0] == 'agp_too_old')
ok("four rows behind it", cands[0][1] == 4)
ok("three distinct sources", cands[0][2] == K['E_ASCEND_POINTS'])

# A repair with a NULL fixture_form counts toward nothing.
con.execute(INS, (17, 5, 'sdk_not_found', 0, 'repo-d', 1,
                  'SDK location not found', 'Set sdk.dir', None, '', 8, 256, 248))
con.execute(INS, (18, 5, 'sdk_not_found', 0, 'repo-e', 1,
                  'SDK location not found', 'Set sdk.dir', None, '', 8, 248, 240))
con.execute(INS, (19, 5, 'sdk_not_found', 0, 'repo-f', 1,
                  'SDK location not found', 'Set sdk.dir', None, '', 8, 240, 232))
con.commit()
ok("null fixture_form never becomes a candidate",
   con.execute("SELECT COUNT(*) FROM v_repair_candidate").fetchone()[0] == 1)
ok("but the repairs are still archived",
   con.execute("SELECT COUNT(*) FROM repair").fetchone()[0] == 7)

# ─────────────────────────────────────────────
print("\nReplay gate")
rt, ra = con.execute(
    "SELECT replay_total, replay_agreed FROM v_repair_replay").fetchone()
ok("replay is unanimous so far", rt == ra == 4)

RULE = ("INSERT INTO repair_rule (proposed_ms,decided_ms,signature_id,"
        "fixture_form,derived_from,status,confidence,replay_total,"
        "replay_agreed,rejected_why) VALUES (?,?,?,?,?,?,?,?,?,?)")

con.execute(RULE, (20, 20, 'agp_too_old', 'agp>=8.5.2', 4,
                   'admitted', 128, 4, 4, ''))
con.commit()
ok("unanimous replay admits at E_EXECUTE_FLOOR",
   con.execute("SELECT confidence FROM repair_rule WHERE status='admitted'"
               ).fetchone()[0] == K['E_EXECUTE_FLOOR'])

ok("admission below the floor refused", refuses(con, RULE,
    (21, 21, 'agp_too_old', 'agp>=9.0.0', 4, 'admitted', 120, 4, 4, '')))
ok("admission on disagreeing replay refused", refuses(con, RULE,
    (21, 21, 'agp_too_old', 'agp>=9.0.0', 4, 'admitted', 128, 4, 3, '')))
ok("agreed above total refused", refuses(con, RULE,
    (21, 21, 'agp_too_old', 'agp>=9.0.0', 4, 'replayed', 120, 4, 9, '')))
ok("rejection without a reason refused", refuses(con, RULE,
    (21, 21, 'agp_too_old', 'agp>=9.0.0', 4, 'rejected', 120, 4, 1, '')))
ok("invalid status refused", refuses(con, RULE,
    (21, 21, 'agp_too_old', 'agp>=9.0.0', 4, 'maybe', 120, 4, 4, '')))

# A rejected rule is kept forever, with its reason.
con.execute(RULE, (22, 22, 'agp_too_old', 'agp>=9.0.0', 4, 'rejected', 120,
                   4, 1, 'replay disagreed: 3 of 4 prior repairs would change'))
con.commit()
ok("rejected rule is preserved with its reason",
   con.execute("SELECT rejected_why FROM repair_rule WHERE status='rejected'"
               ).fetchone()[0].startswith('replay disagreed'))
ok("ledger shows both outcomes",
   con.execute("SELECT COUNT(*) FROM v_repair_rule").fetchone()[0] == 2)

# ─────────────────────────────────────────────
print("\nNothing is ever deleted, nothing is ever edited")
ok("DELETE on repair refused",
   refuses(con, "DELETE FROM repair WHERE repair_id = 1"))
ok("DELETE on repair_rule refused",
   refuses(con, "DELETE FROM repair_rule WHERE rule_id = 1"))
ok("UPDATE on repair refused",
   refuses(con, "UPDATE repair SET fixture_text = 'x' WHERE repair_id = 1"))
ok("rejected rule survives the delete attempt",
   con.execute("SELECT COUNT(*) FROM repair_rule WHERE status='rejected'"
               ).fetchone()[0] == 1)

# ─────────────────────────────────────────────
print("\nCorrelation — C², the archive asking about itself")
fam = dict((r[0], r[2]) for r in con.execute(
    "SELECT family, kind, repairs FROM v_repair_by_family"))
ok("agp family counted",  fam.get('agp') == 4)
ok("sdk family counted",  fam.get('sdk') == 3)

print("\nPersistence across connections")
con.close()
con2 = sqlite3.connect(DB)
ok("repairs survive reconnect",
   con2.execute("SELECT COUNT(*) FROM repair").fetchone()[0] == 7)
ok("candidate view recomputes on reconnect",
   con2.execute("SELECT COUNT(*) FROM v_repair_candidate").fetchone()[0] == 1)
ok("admitted rule survives reconnect",
   con2.execute("SELECT COUNT(*) FROM repair_rule WHERE status='admitted'"
                ).fetchone()[0] == 1)
con2.close()

print(f"\n=== Layer 4 (repair): {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
