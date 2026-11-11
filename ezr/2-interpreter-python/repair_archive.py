"""repair_archive.py — bridge Correction objects into the SQL repair table.

Every Correction produced by forgive.py now carries `.form`, `.kind`,
and `.name` (SEMANTICS.md §9). This module writes those into
`repair`, applies the schema on first use, and never invents any
data — a Correction whose form is empty is skipped rather than
archived with NULL, because §9.5 says prose alone counts toward
nothing and the schema does the same.

Constants come from ever_constant. Nothing is hard-coded here that
isn't already declared there.

Zero-dep. Stdlib sqlite3 only. Safe to import even if the archive
directory does not exist yet.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Iterable, List, Optional

HERE       = os.path.dirname(os.path.abspath(__file__))
ROOT       = os.path.normpath(os.path.join(HERE, ".."))
ARCHIVE_DB = os.path.join(ROOT, "4-archive-sql", "tapestry.db")
BASE_SQL   = os.path.join(ROOT, "4-archive-sql", "archive.sql")
REPAIR_SQL = os.path.join(ROOT, "4-archive-sql", "repair.sql")


# ─────────────────────────────────────────────
# Language ids — match ever_lang in archive.sql. Kept out of the
# schema-apply path so a caller pinning to Python does not need to
# know about the others.
# ─────────────────────────────────────────────

LANG_PYTHON = 2   # ever_lang.id where name = 'python'


def _apply_schema(con: sqlite3.Connection) -> None:
    """Idempotent. archive.sql defines ever_constant / ever_defect /
    ever_lang; repair.sql adds the repair tables and views. Both are
    CREATE IF NOT EXISTS or INSERT OR REPLACE, so replaying is
    harmless."""
    for path in (BASE_SQL, REPAIR_SQL):
        if os.path.exists(path):
            with open(path) as f:
                con.executescript(f.read())


def open_repair_archive(db_path: str = ARCHIVE_DB) -> Optional[sqlite3.Connection]:
    """Open the shared archive DB and ensure the repair schema is
    present. Returns None on failure — the caller decides whether that
    should block execution. Language runtime failures must not cascade
    from an archive read-only filesystem."""
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        con = sqlite3.connect(db_path)
        con.execute("PRAGMA foreign_keys = ON")
        _apply_schema(con)
        return con
    except Exception:
        return None


def _kind_id_for(con: sqlite3.Connection, name: str) -> int:
    """Resolve ever_repair.id from its canonical name. Correction.name
    matches these one-to-one by construction."""
    row = con.execute(
        "SELECT id FROM ever_repair WHERE name = ?", (name,)).fetchone()
    if row is None:
        # Every emission site in forgive.py names one of the seven
        # canonical repairs. An unknown name means someone added an
        # emission without extending §9.3. Fail loud rather than
        # archive garbage.
        raise KeyError(f"repair_archive: unknown Correction.name {name!r} — "
                       f"extend §9.3 and ever_repair before emitting it")
    return int(row[0])


def _cost_for(con: sqlite3.Connection, kind: int) -> int:
    """Read the cost from ever_repair_kind rather than importing a
    Python constant. One source of truth."""
    row = con.execute(
        "SELECT cost FROM ever_repair_kind WHERE id = ?", (kind,)).fetchone()
    if row is None:
        raise KeyError(f"repair_archive: unknown kind_id {kind}")
    return int(row[0])


def _e_certain(con: sqlite3.Connection) -> int:
    row = con.execute(
        "SELECT value FROM ever_constant WHERE name = 'E_CERTAIN'").fetchone()
    return int(row[0]) if row else 256


def archive_corrections(
    corrections: Iterable,
    source_ident: str,
    run_id: Optional[int] = None,
    conf_before: Optional[int] = None,
    con: Optional[sqlite3.Connection] = None,
) -> int:
    """Write each Correction as a (Failure, Fixture) pair.

    Returns the number of rows archived. A Correction with an empty
    `.form` is skipped — SEMANTICS.md §9.5. That is a deliberate loss:
    the counter reflects rows that CAN participate in recurrence.
    """
    close_after = False
    if con is None:
        con = open_repair_archive()
        if con is None:
            return 0
        close_after = True

    try:
        certain     = _e_certain(con)
        conf_before = certain if conf_before is None else conf_before
        now_ms      = int(time.time() * 1000)
        written     = 0

        for c in corrections:
            form = getattr(c, "form", "") or ""
            name = getattr(c, "name", "") or ""
            kind = int(getattr(c, "kind", 1))
            if not form or not name:
                continue                            # §9.5
            failure = getattr(c, "what",   "") or ""
            fixture = getattr(c, "became", "") or ""
            if not failure or not fixture:
                continue                            # CHECK would reject anyway

            repair_id_ref = _kind_id_for(con, name)
            cost          = _cost_for(con, kind)
            conf_after    = max(0, conf_before - cost)

            con.execute(
                "INSERT INTO repair("
                " run_id, lang_id, kind_id, repair_kind, source_ident,"
                " line_no, failure_text, fixture_text, fixture_form, reason,"
                " cost, conf_before, conf_after, archived_ms)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, LANG_PYTHON, kind, repair_id_ref, source_ident,
                 int(getattr(c, "line", 0)),
                 failure, fixture, form,
                 getattr(c, "reason", "") or "",
                 cost, conf_before, conf_after, now_ms))
            written += 1

        con.commit()
        return written
    finally:
        if close_after:
            con.close()


# ─────────────────────────────────────────────
# Recurrence-driven rule proposal. Same two gates as SEMANTICS.md §9.6
# and repair.sql:
#   1. cannot admit below E_EXECUTE_FLOOR
#   2. cannot admit if replay disagrees on any prior repair
# The SQL CHECK already enforces both — this function just performs
# the replay and records the result.
# ─────────────────────────────────────────────

def _const(con: sqlite3.Connection, name: str) -> int:
    row = con.execute(
        "SELECT value FROM ever_constant WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise KeyError(f"repair_archive: no ever_constant.{name}")
    return int(row[0])


def propose_rules(con: Optional[sqlite3.Connection] = None) -> List[dict]:
    """For every candidate in repair_candidate, propose a rule.
    Replay it against every archived repair on the same signature.
    Persist admitted OR rejected — never both, never neither."""
    close_after = False
    if con is None:
        con = open_repair_archive()
        if con is None:
            return []
        close_after = True

    try:
        floor   = _const(con, "E_EXECUTE_FLOOR")
        intake  = _const(con, "E_INTAKE")
        now_ms  = int(time.time() * 1000)

        candidates = con.execute(
            "SELECT repair_kind, fixture_form, seen "
            "FROM repair_candidate").fetchall()

        results: List[dict] = []
        for repair_kind, form, seen in candidates:
            priors = con.execute(
                "SELECT fixture_form FROM repair "
                "WHERE repair_kind = ? AND fixture_form IS NOT NULL",
                (repair_kind,)).fetchall()
            total   = len(priors)
            agreed  = sum(1 for (pf,) in priors if pf == form)

            if agreed != total:
                status, conf = "rejected", intake
                why = (f"replay disagreed: {total - agreed} of {total} "
                       f"prior repairs would change")
            else:
                status, conf, why = "admitted", floor, ""

            con.execute(
                "INSERT INTO repair_rule("
                " repair_kind, fixture_form, derived_from, status,"
                " confidence, replay_total, replay_agreed, rejected_why,"
                " proposed_ms, decided_ms)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (repair_kind, form, seen, status, conf,
                 total, agreed, why, now_ms, now_ms))
            results.append({
                "repair_kind": repair_kind, "fixture_form": form,
                "status": status, "confidence": conf,
                "replay_total": total, "replay_agreed": agreed,
                "rejected_why": why,
            })

        con.commit()
        return results
    finally:
        if close_after:
            con.close()
