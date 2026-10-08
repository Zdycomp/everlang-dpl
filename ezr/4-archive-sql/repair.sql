-- ============================================================
-- repair.sql — Ever / Tapestry, Layer 4 (SQL)
--
-- Forgiveness, archived.
--
-- Every healing E performs is two things, never one:
--
--   Failure — the problem.  What the source actually said.
--   Fixture — the solution. What E bound in its place.
--
-- Both are recorded, every time, unconditionally. A Fixture with no
-- Failure is an invention. A Failure with no Fixture is a refusal.
-- Neither is a repair, and neither is archived alone.
--
-- Nothing is ever deleted. A repair that was later proved wrong stays
-- in the archive as a boundary marker, same as an EError.
--
-- Depends on archive.sql (ever_constant, ever_defect, ever_lang, run).
--
-- Codric Enterprise · Ricky (Dreid) · 2026
-- ============================================================

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
-- Cost constants. Added to ever_constant so every layer reads one
-- source and drift stays impossible.
--
-- Derived, not chosen: E_CERTAIN is 256 (4^4). An unambiguous repair
-- costs 256/32 = 8. An inferential repair costs 256/8 = 32. The
-- consequence falls out rather than being tuned — four inferential
-- repairs land a binding at exactly E_EXECUTE_FLOOR (128). The fifth
-- puts it below the floor, where it must not run unexamined.
-- ─────────────────────────────────────────────

INSERT OR REPLACE INTO ever_constant (name, value, derivation) VALUES
    ('E_REPAIR_PLAIN',      8,  '256 / 32. an unambiguous repair.'),
    ('E_REPAIR_INFERRED',  32,  '256 / 8. an inferential repair.'),
    ('E_REPAIR_RECUR',      3,  'E_ASCEND_POINTS. aligned repairs required to rise.');

-- ─────────────────────────────────────────────
-- How a repair is reached.
--
-- plain      — the source could only have meant one thing. Removing a
--              trailing comma or lowercasing a keyword deletes noise.
--              Nothing is guessed.
-- inferred   — E supplied something that was not written. An inserted
--              comma or a rewritten operator is a claim about intent.
--              It is usually right. It is still a claim.
--
-- The distinction is the whole point. Charging both the same rate
-- would say that removing a semicolon and inventing a comma carry
-- equal risk, and they do not.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ever_repair_kind (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    cost INTEGER NOT NULL,
    note TEXT NOT NULL);

INSERT OR REPLACE INTO ever_repair_kind (id, name, cost, note) VALUES
    (0,'plain',    8,  'noise removed. one reading was possible.'),
    (1,'inferred', 32, 'structure supplied. intent was assumed.');

-- The seven repairs forgive.py can currently perform. Each one is
-- enumerated here rather than inferred from its message text, so a
-- second implementation in another language is measured against this
-- table and not against Python's wording.

CREATE TABLE IF NOT EXISTS ever_repair (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    kind_id   INTEGER NOT NULL REFERENCES ever_repair_kind(id),
    defect_id INTEGER NOT NULL DEFAULT 0 REFERENCES ever_defect(id),
    note      TEXT NOT NULL);

INSERT OR REPLACE INTO ever_repair (id, name, kind_id, defect_id, note) VALUES
    (1,'trailing_comma',    0, 0, 'a comma before a closer separates nothing'),
    (2,'stray_semicolon',   0, 0, 'E needs no statement terminator'),
    (3,'keyword_case',      0, 0, 'a name spelled exactly like a keyword'),
    (4,'colon_for_equals',  1, 2, 'let/ever bind with =, not :'),
    (5,'equals_for_colon',  1, 2, 'fields inside { } are name: value'),
    (6,'equals_for_compare',1, 2, '= is legal only after let/ever NAME or a def parameter list'),
    (7,'missing_comma',     1, 3, 'two values adjacent inside a collection');

-- ─────────────────────────────────────────────
-- The pair. One row per healing, both halves present.
--
-- failure_text  — verbatim, what was written.
-- fixture_text  — verbatim, what was bound instead.
-- fixture_form  — the same solution as a structured edit rather than
--                 prose. NULL until a repair has been given one.
--                 Nothing can be regenerated from a sentence; this
--                 column is what makes a Fixture executable, and it
--                 is the gate on everything downstream.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS repair (
    repair_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER REFERENCES run(run_id),
    lang_id      INTEGER NOT NULL REFERENCES ever_lang(id),
    kind_id      INTEGER NOT NULL REFERENCES ever_repair_kind(id),
    repair_kind  INTEGER NOT NULL REFERENCES ever_repair(id),

    source_ident TEXT    NOT NULL,
    line_no      INTEGER NOT NULL DEFAULT 0,

    failure_text TEXT    NOT NULL,
    fixture_text TEXT    NOT NULL,
    fixture_form TEXT,
    reason       TEXT    NOT NULL,

    cost         INTEGER NOT NULL,
    conf_before  INTEGER NOT NULL CHECK (conf_before BETWEEN 0 AND 256),
    conf_after   INTEGER NOT NULL CHECK (conf_after  BETWEEN 0 AND 256),

    thread_id    INTEGER REFERENCES thread(archive_id),
    archived_ms  INTEGER NOT NULL,

    -- neither half may be empty. a repair is a pair or it is not a repair.
    CHECK (length(failure_text) > 0),
    CHECK (length(fixture_text) > 0),
    CHECK (conf_after <= conf_before)
);

CREATE INDEX IF NOT EXISTS idx_repair_kind   ON repair(repair_kind);
CREATE INDEX IF NOT EXISTS idx_repair_lang   ON repair(lang_id);
CREATE INDEX IF NOT EXISTS idx_repair_fail   ON repair(failure_text);
CREATE INDEX IF NOT EXISTS idx_repair_form   ON repair(fixture_form);

-- ─────────────────────────────────────────────
-- Recurrence. The only honest basis for generating a rule.
--
-- A Failure shape that has resolved to the SAME Fixture form, across
-- independent sources, at least E_ASCEND_POINTS times, is a candidate.
-- Fewer than that is a coincidence with a sample size.
--
-- Repairs whose fixture_form is NULL are excluded on purpose: prose
-- cannot be replayed, so it cannot be counted toward a rule.
-- ─────────────────────────────────────────────

CREATE VIEW IF NOT EXISTS repair_recurrence AS
SELECT
    r.repair_kind,
    k.name                        AS repair_name,
    r.fixture_form,
    COUNT(*)                      AS seen,
    COUNT(DISTINCT r.source_ident) AS distinct_sources,
    COUNT(DISTINCT r.lang_id)     AS distinct_langs,
    MIN(r.archived_ms)            AS first_ms,
    MAX(r.archived_ms)            AS last_ms
FROM repair r
JOIN ever_repair k ON k.id = r.repair_kind
WHERE r.fixture_form IS NOT NULL
GROUP BY r.repair_kind, r.fixture_form;

-- A candidate is a recurrence that has cleared the threshold on
-- distinct sources, not merely on total count. Ten repairs in one
-- file is one author's habit, not a language rule.

CREATE VIEW IF NOT EXISTS repair_candidate AS
SELECT v.*
FROM repair_recurrence v
WHERE v.distinct_sources >= (SELECT value FROM ever_constant
                             WHERE name = 'E_REPAIR_RECUR');

-- ─────────────────────────────────────────────
-- Generated rules. Born below the execute floor.
--
-- A rule synthesised from the archive does not heal anything on the
-- day it is written. It is proposed, replayed against every repair
-- already recorded, and only admitted if it changes no prior outcome.
-- Until then it sits at E_INTAKE, beneath E_EXECUTE_FLOOR, inert.
--
-- status: proposed → replayed → admitted, or → rejected (kept forever,
-- with the reason, because a rejected rule is a boundary marker).
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS repair_rule (
    rule_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    repair_kind   INTEGER NOT NULL REFERENCES ever_repair(id),
    fixture_form  TEXT    NOT NULL,
    derived_from  INTEGER NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'proposed'
                  CHECK (status IN ('proposed','replayed','admitted','rejected')),
    confidence    INTEGER NOT NULL DEFAULT 120
                  CHECK (confidence BETWEEN 0 AND 256),
    replay_total  INTEGER NOT NULL DEFAULT 0,
    replay_agreed INTEGER NOT NULL DEFAULT 0,
    rejected_why  TEXT    NOT NULL DEFAULT '',
    proposed_ms   INTEGER NOT NULL,
    decided_ms    INTEGER,

    -- a rule may not be admitted while it sits below the floor, and
    -- may not reach the floor without unanimous replay agreement.
    CHECK (status <> 'admitted' OR confidence >= 128),
    CHECK (status <> 'admitted' OR replay_agreed = replay_total)
);

CREATE INDEX IF NOT EXISTS idx_rule_status ON repair_rule(status);
