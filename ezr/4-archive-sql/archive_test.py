#!/usr/bin/env python3
"""archive_test.py — Ever / Tapestry Layer 4 verification.

Drives archive.sql through Python's sqlite3 so the layer verifies without
requiring the sqlite3 CLI. The SQL under test is unchanged.
"""

import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "tapestry.db")

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


def refuses(con, sql, params=()):
    """The corpus should refuse this. True if it did."""
    try:
        con.execute(sql, params); con.commit(); return False
    except sqlite3.DatabaseError:
        con.rollback(); return True


print("\n=== Tapestry Layer 4 (SQL) — the archive ===\n")

if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
con.executescript(open(os.path.join(HERE, "archive.sql")).read())
con.execute("PRAGMA foreign_keys = ON")
con.commit()

print("Schema")
names = lambda t: [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type=? ORDER BY name", (t,))]
tables, views, triggers = names('table'), names('view'), names('trigger')
ok("thread table exists",     "thread" in tables)
ok("anchor table exists",     "anchor" in tables)
ok("crossing table exists",   "crossing" in tables)
ok("defect vocabulary",       "ever_defect" in tables)
ok("nine correlation views",  len(views) == 9)
ok("nine invariant triggers", len(triggers) == 9)

print("\nConstants agree with the C atom")
K = dict(con.execute("SELECT name, value FROM ever_constant"))
ok("Certain 256",        K['E_CERTAIN'] == 256)
ok("execute floor 128",  K['E_EXECUTE_FLOOR'] == 128)
ok("pi warn 81",         K['E_PI_WIDTH_WARN'] == 81)
ok("pi squared 25",      K['E_PI_WIDTH_ENUMERATE'] == 25)
ok("emulate ceiling 3",  K['E_EMULATE_CEILING'] == 3)
ok("ascend points 3",    K['E_ASCEND_POINTS'] == 3)
ok("intake 120",         K['E_INTAKE'] == 120)

print("\nThe five defects are named")
D = dict(con.execute("SELECT name, id FROM ever_defect"))
for d in ("unbound", "misbound", "unbounded", "overbound", "orphaned"):
    ok(f"{d} present", d in D)

print("\nSeed corpus with payloads")
con.execute("INSERT INTO run (started_ms,label,host_lang) "
            "VALUES (1754960000000,'layer-4 verification',4)")
rows = [
    (0,0,2,1,  0,  0,  0, None,      0, 1754960000001,'ocr_text','OCR not run'),
    (1,1,2,0,180,180,180,'500',      0, 1754960000002,'total',''),
    (1,3,3,0,200,200,200,'Codric',   0, 1754960000003,'name',''),
    (2,1,4,0,256,256,256,'1',        0, 1754960000004,'schema_version',''),
    (3,1,3,0,107,100,115,'107',      0, 1754960000005,'severity',''),
    (3,1,3,0,125, 50,200,'125',      0, 1754960000006,'wide_range',''),
    (9,1,5,2,  0, 80, 80,None,       0, 1754960000007,'null_deref','unguarded null'),
    (7,1,2,0,200,200,200,'500',   7001, 1754960000008,'anchored_total',''),
]
con.executemany(
    "INSERT INTO thread (state_id,type_id,lang_id,defect_id,confidence,lo,hi,"
    "val_text,anchor_id,born_ms,ident,reason,run_id) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)", rows)
con.commit()
ok("eight threads stored",
   con.execute("SELECT COUNT(*) FROM thread").fetchone()[0] == 8)
ok("payload stored",
   con.execute("SELECT val_text FROM thread WHERE ident='total'"
               ).fetchone()[0] == '500')
ok("text payload stored",
   con.execute("SELECT val_text FROM thread WHERE ident='name'"
               ).fetchone()[0] == 'Codric')

print("\nInvariants enforced at the storage boundary")
ok("Z cannot carry confidence", refuses(con,
    "INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,born_ms,"
    "ident) VALUES (0,1,2,150,150,150,1,'illegal_z')"))
ok("Certain must be 256", refuses(con,
    "INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,born_ms,"
    "ident) VALUES (2,1,2,250,250,250,1,'illegal_certain')"))
ok("emulate beyond int(pi) refused", refuses(con,
    "INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,born_ms,"
    "ident,error_distance) VALUES (5,1,0,110,110,110,1,'over_emu',4)"))
ok("confidence above 256 refused", refuses(con,
    "INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,born_ms,"
    "ident) VALUES (1,1,2,300,300,300,1,'over_scale')"))
ok("lo above hi refused", refuses(con,
    "INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,born_ms,"
    "ident) VALUES (3,1,2,100,200,50,1,'inverted')"))
ok("cannot anchor a Z", refuses(con,
    "INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,born_ms,"
    "ident,anchor_id) VALUES (0,1,2,0,0,0,1,'anchored_z',900)"))
ok("cannot anchor an EError", refuses(con,
    "INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,born_ms,"
    "ident,anchor_id) VALUES (9,1,2,0,0,0,1,'anchored_err',901)"))
ok("ascend points bounded", refuses(con,
    "INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,born_ms,"
    "ident,ascend_points) VALUES (1,1,2,150,150,150,1,'over_ascend',4)"))
ok("threads never deleted", refuses(con,
    "DELETE FROM thread WHERE ident='ocr_text'"))
ok("thread survived the delete",
   con.execute("SELECT COUNT(*) FROM thread WHERE ident='ocr_text'"
               ).fetchone()[0] == 1)

print("\nv_thread computes pi status and executability in SQL")
vt = {r[0]: r for r in con.execute(
    "SELECT ident,pi_status,can_execute,cleared,anchored,value FROM v_thread")}
ok("severity acceptable",     vt['severity'][1] == 'ACCEPTABLE')
ok("wide range approaching Z", vt['wide_range'][1] == 'APPROACHING_Z')
ok("Z not cleared",           vt['ocr_text'][3] == 0)
ok("Z cannot execute",        vt['ocr_text'][2] == 0)
ok("180 can execute",         vt['total'][2] == 1)
ok("EError not cleared",      vt['null_deref'][3] == 0)
ok("anchored flagged",        vt['anchored_total'][4] == 1)
ok("value surfaced in view",  vt['total'][5] == '500')

print("\nContinuity audit — the claim, made auditable")
con.execute("INSERT INTO anchor (anchor_id,ident,pinned_at,pinned_conf,"
            "val_text,note) VALUES (7001,'anchored_total',1754960000008,200,"
            "'500','pinned for cross-language carry')")
tid = con.execute("SELECT archive_id FROM thread WHERE ident='anchored_total'"
                  ).fetchone()[0]
hops = [(2,7),(7,10),(10,5),(5,8),(8,9)]   # Python->Rust->Swift->Java->Go->TS
for i,(a,b) in enumerate(hops):
    con.execute("INSERT INTO crossing (anchor_id,thread_id,from_lang,to_lang,"
                "conf_before,conf_after,val_before,val_after,crossed_ms) "
                "VALUES (7001,?,?,?,200,200,'500','500',?)",
                (tid,a,b,1754960000010+i))
con.commit()

cont = con.execute("SELECT crossings,value_changes,total_confidence_lost,"
                   "verdict FROM v_continuity WHERE anchor_id=7001").fetchone()
ok("five crossings recorded",  cont[0] == 5)
ok("no value drift",           cont[1] == 0)
ok("no confidence lost",       cont[2] == 0)
ok("verdict HELD",             cont[3] == 'HELD')
ok("anchored crossing that loses confidence is refused", refuses(con,
    "INSERT INTO crossing (anchor_id,thread_id,from_lang,to_lang,conf_before,"
    "conf_after,val_before,val_after,crossed_ms) "
    f"VALUES (7001,{tid},2,7,200,199,'500','500',1)"))
ok("anchors are never deleted", refuses(con, "DELETE FROM anchor"))

print("\nUnanchored drift is visible")
con.execute("INSERT INTO thread (state_id,type_id,lang_id,confidence,lo,hi,"
            "val_text,born_ms,ident,run_id) "
            "VALUES (1,1,2,200,200,200,'500',1754960000030,'loose_total',1)")
lid = con.execute("SELECT archive_id FROM thread WHERE ident='loose_total'"
                  ).fetchone()[0]
conf = 200
for i,(a,b) in enumerate(hops):
    con.execute("INSERT INTO crossing (anchor_id,thread_id,from_lang,to_lang,"
                "conf_before,conf_after,val_before,val_after,crossed_ms) "
                "VALUES (NULL,?,?,?,?,?,'500','500',?)",
                (lid,a,b,conf,conf-1,1754960000040+i))
    conf -= 1
con.commit()
lost = con.execute("SELECT SUM(conf_before-conf_after) FROM crossing "
                   "WHERE anchor_id IS NULL").fetchone()[0]
ok("unanchored lost 5 across 5 hops", lost == 5)
ok("anchoring is the measurable difference", lost > cont[2])

print("\nDefect profile")
con.execute("INSERT INTO finding (thread_id,kind,defect_id,message,weight,"
            "fix_hint) SELECT archive_id,'error',2,'null used without a guard',"
            "65,'use Optional' FROM thread WHERE ident='null_deref'")
con.execute("INSERT INTO finding (thread_id,kind,defect_id,message,weight) "
            "SELECT archive_id,'pattern',0,'parameters typed',30 FROM thread "
            "WHERE ident='total'")
con.execute("INSERT INTO teaching (error_message,lang_id,defect_id,"
            "fix_template,success_count,first_seen_ms) VALUES "
            "('null used without a guard',5,2,'wrap in Optional',7,1)")
con.commit()
prof = list(con.execute("SELECT defect,lang,occurrences FROM v_defect_profile"))
ok("defect profile populated", len(prof) >= 1)
rec = list(con.execute("SELECT message,teaching_status FROM v_recurring_error"))
ok("recurring error taught", any(r[1] == 'TAUGHT' for r in rec))

print("\nPhase events record agreement")
a_id = con.execute("SELECT archive_id FROM thread WHERE ident='total'").fetchone()[0]
b_id = con.execute("SELECT archive_id FROM thread WHERE ident='loose_total'").fetchone()[0]
con.execute("INSERT INTO phase_event (left_id,right_id,outcome,same_value,"
            "occurred_ms,note) VALUES (?,?,'Excel',1,1,'both hold 500')",
            (a_id,b_id))
con.execute("INSERT INTO phase_event (left_id,right_id,outcome,same_value,"
            "occurred_ms,note) VALUES (?,?,'Blocked',0,2,'Z contagion')",
            (con.execute("SELECT archive_id FROM thread WHERE ident='ocr_text'"
                         ).fetchone()[0], a_id))
con.commit()
ph = {r[0]: (r[1], r[2]) for r in con.execute(
    "SELECT outcome,events,with_agreement FROM v_phase_summary")}
ok("Excel recorded with agreement", ph['Excel'] == (1, 1))
ok("Blocked recorded",              ph['Blocked'][0] == 1)
ok("invalid outcome refused", refuses(con,
    "INSERT INTO phase_event (left_id,right_id,outcome,occurred_ms) "
    f"VALUES ({a_id},{b_id},'Explode',3)"))

print("\nPersistence across connections")
con.close()
con2 = sqlite3.connect(DB)
ok("threads survive reconnect",
   con2.execute("SELECT COUNT(*) FROM thread").fetchone()[0] == 9)
ok("anchors survive reconnect",
   con2.execute("SELECT COUNT(*) FROM anchor").fetchone()[0] == 1)
ok("crossings survive reconnect",
   con2.execute("SELECT COUNT(*) FROM crossing").fetchone()[0] == 10)
ok("continuity verdict persists",
   con2.execute("SELECT verdict FROM v_continuity WHERE anchor_id=7001"
                ).fetchone()[0] == 'HELD')
con2.close()

print(f"\n=== Layer 4: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
