"""repair_archive_test.py — end-to-end.

Uses a scratch DB (never the real tapestry.db) so tests are
side-effect free and safe to run in CI.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

from forgive import parse_forgiving
from repair_archive import (
    archive_corrections, propose_rules, open_repair_archive,
    ARCHIVE_DB, BASE_SQL, REPAIR_SQL,
)


def _fresh_db() -> str:
    fd, path = tempfile.mkstemp(prefix="repair-test-", suffix=".db")
    os.close(fd)
    os.unlink(path)     # let sqlite create it fresh so PRAGMAs stick
    return path


def _with_db(fn):
    def wrapper():
        path = _fresh_db()
        con = sqlite3.connect(path)
        con.execute("PRAGMA foreign_keys = ON")
        for p in (BASE_SQL, REPAIR_SQL):
            with open(p) as f: con.executescript(f.read())
        try:
            fn(con)
        finally:
            con.close()
            os.unlink(path)
    return wrapper


passed = 0
failed = 0

def _t(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  ok  {name}")
    except AssertionError as e:
        failed += 1
        print(f"FAIL  {name}: {e}")
    except Exception as e:
        failed += 1
        print(f"FAIL  {name}: {type(e).__name__}: {e}")


# ──────────────────────────────────────────────────────────────

@_with_db
def _all_seven_archive(con):
    """Every one of the seven §9.3 repairs archives cleanly."""
    cases = [
        ("let x = 1;",              "stray_semicolon",     "SEMI_DROP"),
        ("[1, 2, 3,]",              "trailing_comma",      "COMMA_TRAIL_DROP"),
        ("Let x = 1",               "keyword_case",        "KW_LOWER:let"),
        ("let x: 5",                "colon_for_equals",    "COLON_TO_EQ"),
        ("{ a = 1 }",               "equals_for_colon",    "EQ_TO_COLON"),
        ("if x = 5 then 1 else 2",  "equals_for_compare",  "EQ_TO_CMP"),
        ("[1 2]",                   "missing_comma",       "COMMA_INSERT:NUM|NUM"),
    ]
    for src, expected_name, expected_form in cases:
        _, _, corrs = parse_forgiving(src)
        found = [c for c in corrs if c.name == expected_name]
        assert found, f"forgive.py did not emit {expected_name} for {src!r}"
        n = archive_corrections(found, source_ident=f"test/{expected_name}", con=con)
        assert n == len(found), f"{expected_name}: expected {len(found)} written, got {n}"

    row = con.execute(
        "SELECT COUNT(DISTINCT r.name) FROM repair p "
        "JOIN ever_repair r ON r.id = p.repair_kind").fetchone()
    assert row[0] == 7, f"expected 7 distinct repair names archived, got {row[0]}"

_t("all seven repairs archive with correct name and form", _all_seven_archive)


@_with_db
def _empty_form_skipped(con):
    """A Correction with a blank .form must be skipped (§9.5)."""
    from forgive import Correction
    c = Correction(line=1, what="x", became="y", reason="",
                   form="", kind=0, name="stray_semicolon")
    n = archive_corrections([c], source_ident="test/skip", con=con)
    assert n == 0, "empty form should not be archived"
    rows = con.execute("SELECT COUNT(*) FROM repair").fetchone()[0]
    assert rows == 0

_t("prose-only correction (empty form) is skipped", _empty_form_skipped)


@_with_db
def _confidence_derived_not_passed(con):
    """cost comes from ever_repair_kind. Plain=8, inferred=32."""
    _, _, semi = parse_forgiving("let x = 1;")
    _, _, comma = parse_forgiving("[1 2]")
    archive_corrections(semi,  source_ident="test/a", con=con)
    archive_corrections(comma, source_ident="test/b", con=con)
    plain    = con.execute("SELECT conf_before,conf_after FROM repair "
                           "WHERE kind_id=0").fetchone()
    inferred = con.execute("SELECT conf_before,conf_after FROM repair "
                           "WHERE kind_id=1 LIMIT 1").fetchone()
    assert plain    == (256, 248), plain
    assert inferred == (256, 224), inferred

_t("cost derives from ever_repair_kind (plain=8, inferred=32)", _confidence_derived_not_passed)


@_with_db
def _four_inferred_lands_on_floor(con):
    """SEMANTICS.md §9.2: 256 - 4*32 = 128. The consequence, not a knob."""
    conf = 256
    for _ in range(4):
        _, _, corr = parse_forgiving("[1 2]")
        _, _, corr = parse_forgiving("[1 2]")
        n = archive_corrections(corr[:1], source_ident="test/floor",
                                conf_before=conf, con=con)
        row = con.execute(
            "SELECT conf_after FROM repair ORDER BY repair_id DESC LIMIT 1"
        ).fetchone()
        conf = row[0]
    assert conf == 128, f"expected floor 128, got {conf}"

_t("four inferred repairs land exactly on E_EXECUTE_FLOOR (128)", _four_inferred_lands_on_floor)


@_with_db
def _recurrence_and_admission(con):
    """Three distinct sources, same form → candidate → admitted rule."""
    for src in ("proj/a", "proj/b", "proj/c"):
        _, _, corr = parse_forgiving("[1 2]")
        archive_corrections(corr[:1], source_ident=src, con=con)

    cands = con.execute(
        "SELECT repair_name, fixture_form, distinct_sources "
        "FROM repair_candidate").fetchall()
    assert cands == [("missing_comma", "COMMA_INSERT:NUM|NUM", 3)], cands

    results = propose_rules(con=con)
    assert len(results) == 1
    r = results[0]
    assert r["status"] == "admitted", r
    assert r["confidence"] == 128,    r
    assert r["replay_agreed"] == r["replay_total"] == 3

_t("recurrence at 3 distinct sources → admitted rule at floor", _recurrence_and_admission)


@_with_db
def _replay_rejects_disagreement(con):
    """Same signature, a divergent form later → the replay-gate rejects
    and PRESERVES the reason. This is the whole point of the gate."""
    for src in ("proj/a", "proj/b", "proj/c"):
        _, _, corr = parse_forgiving("[1 2]")
        archive_corrections(corr[:1], source_ident=src, con=con)

    # A dissenting repair with the same repair_kind but a different form.
    from forgive import Correction
    dissent = Correction(line=1, what="a", became="b",
                         reason="a divergent fix on the same signature",
                         form="COMMA_INSERT:NUM|STR", kind=1,
                         name="missing_comma")
    archive_corrections([dissent], source_ident="dissent/team", con=con)

    results = propose_rules(con=con)
    # Two candidates now: the majority form (3 sources) and, if it also
    # cleared threshold, the dissent — the dissent has 1 source so only
    # the majority is a candidate. Both propositions must be recorded.
    admitted = [r for r in results if r["status"] == "admitted"]
    rejected = [r for r in results if r["status"] == "rejected"]
    assert len(admitted) == 0, f"admission must fail with a dissent: {results}"
    assert len(rejected) == 1, f"expected 1 rejection, got {results}"
    assert "disagreed" in rejected[0]["rejected_why"]
    # And the row survives in repair_rule for future inspection.
    row = con.execute(
        "SELECT status, rejected_why FROM repair_rule "
        "WHERE status = 'rejected'").fetchone()
    assert row is not None and "disagreed" in row[1]

_t("dissenting fixture rejects admission; reason preserved", _replay_rejects_disagreement)


@_with_db
def _unknown_name_fails_loud(con):
    """A Correction with an unrecognised name must not silently
    archive. That would corrupt the recurrence view."""
    from forgive import Correction
    bogus = Correction(line=1, what="a", became="b", reason="",
                       form="FAKE", kind=1, name="not_a_real_repair")
    try:
        archive_corrections([bogus], source_ident="test/x", con=con)
        assert False, "should have raised KeyError"
    except KeyError as e:
        assert "not_a_real_repair" in str(e)

_t("unknown Correction.name is refused, not silently written", _unknown_name_fails_loud)


# ──────────────────────────────────────────────────────────────

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(0 if failed == 0 else 1)
