-- ============================================================
-- repair.sql — Codric, Layer 4 (SQL) · the repair archive
--
-- Layer 7 (ReFix) keeps its archive as append-only JSONL so that a
-- single developer needs no database to start. This file is the same
-- schema expressed in the archive's own language: the shape a hosted
-- or team archive takes when the JSONL outgrows one machine.
--
-- The JSONL and this schema are the same contract. Every invariant
-- that src/archive.js enforces in JavaScript is enforced here by the
-- database, so a careless caller cannot skip it:
--
--   * a repair is a PAIR — neither half may be empty
--   * cost is DERIVED from kind, never supplied
--   * confidence never rises through a repair
--   * a rule cannot be admitted below E_EXECUTE_FLOOR
--   * a rule cannot be admitted if replay disagreed with any prior
--   * nothing is ever deleted — a rejected rule is a boundary marker
--
-- Recurrence counts DISTINCT SOURCES, not rows. Ten repairs in one
-- repository is one habit, not a rule.
--
-- Load after archive.sql; ever_constant and ever_lang come from there.
--
-- Codric Enterprise · Ricky (Dreid) · 2026
-- ============================================================

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
-- Repair constants. The two costs ReFix adds to the scale, derived
-- from E_CERTAIN exactly like every other constant in the corpus.
-- ─────────────────────────────────────────────

INSERT OR REPLACE INTO ever_constant (name, value, derivation) VALUES
    ('E_REPAIR_PLAIN',    8,  '256 / 32. a repair the signature stated outright.'),
    ('E_REPAIR_INFERRED', 32, '256 / 8. a repair inferred from captures; costs 4x.');

-- ─────────────────────────────────────────────
-- Kinds. The same partition as SEMANTICS §9.2 and constants.js KIND.
-- A plain repair is quoted from the failure. An inferred repair is
-- reconstructed from captures, which is a stronger claim, so it is
-- charged four times as much.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS repair_kind (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    cost        INTEGER NOT NULL,
    rationale   TEXT NOT NULL
);

INSERT OR REPLACE INTO repair_kind (id, name, cost, rationale) VALUES
    (0, 'plain',    8,  'the signature stated the fix; the archive only records it'),
    (1, 'inferred', 32, 'the fix was reconstructed from captures; a stronger claim');

-- ─────────────────────────────────────────────
-- Signatures. The authored corpus a failure is matched against.
-- Both template halves are required: a signature that can name a
-- failure but not its fixture is half a signature.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS repair_signature (
    signature_id  TEXT PRIMARY KEY,
    family        TEXT NOT NULL,
    kind          INTEGER NOT NULL REFERENCES repair_kind (id),
    lang          INTEGER REFERENCES ever_lang (id),
    match_re      TEXT NOT NULL,
    fixture_form  TEXT NOT NULL,      -- the shape, captures interpolated
    fixture_text  TEXT NOT NULL,      -- what a human is told to do
    authored_ms   INTEGER NOT NULL,
    CHECK (length(match_re)     > 0),
    CHECK (length(fixture_form) > 0),
    CHECK (length(fixture_text) > 0)
);

-- ─────────────────────────────────────────────
-- The repair. One row per accepted (Failure, Fixture) pair.
-- Append-only. This is the table the whole mechanism exists to fill.
--
-- fixture_form NULL is legal and load-bearing: it means "this repair
-- does not count toward recurrence". A repair whose shape could not
-- be generalised is still archived — it is simply not evidence for
-- a rule.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS repair (
    repair_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    archived_ms   INTEGER NOT NULL,
    run_id        INTEGER REFERENCES run (run_id),
    lang          INTEGER REFERENCES ever_lang (id),
    signature_id  TEXT NOT NULL REFERENCES repair_signature (signature_id),
    kind          INTEGER NOT NULL REFERENCES repair_kind (id),

    source_ident  TEXT NOT NULL,      -- which project produced it
    line_no       INTEGER NOT NULL DEFAULT 0,

    failure_text  TEXT NOT NULL,      -- the exact matched substring
    fixture_text  TEXT NOT NULL,      -- the repair, interpolated
    fixture_form  TEXT,               -- NULL = counts toward nothing
    reason        TEXT NOT NULL DEFAULT '',

    cost          INTEGER NOT NULL,
    conf_before   INTEGER NOT NULL,
    conf_after    INTEGER NOT NULL,

    -- A repair is a pair. Half a pair is not a repair.
    CHECK (length(failure_text) > 0),
    CHECK (length(fixture_text) > 0),
    CHECK (conf_before BETWEEN 0 AND 256),
    CHECK (conf_after  BETWEEN 0 AND 256),
    -- The one invariant that must hold in every implementation.
    CHECK (conf_after <= conf_before)
);

CREATE INDEX IF NOT EXISTS ix_repair_form
    ON repair (signature_id, fixture_form);
CREATE INDEX IF NOT EXISTS ix_repair_source
    ON repair (source_ident);

-- ─────────────────────────────────────────────
-- Rules. A fixture that recurred across distinct sources may be
-- proposed as a rule. It is born at E_INTAKE — below the execute
-- floor — and rises only by surviving replay against the entire
-- archive.
--
-- A rejected rule is kept forever with its reason, exactly as an
-- EError is kept. Knowing which generalisations failed is the part
-- of the corpus that is expensive to rebuild.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS repair_rule (
    rule_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_ms   INTEGER NOT NULL,
    decided_ms    INTEGER,
    signature_id  TEXT NOT NULL REFERENCES repair_signature (signature_id),
    fixture_form  TEXT NOT NULL,
    derived_from  INTEGER NOT NULL,   -- repairs behind the proposal
    status        TEXT NOT NULL,
    confidence    INTEGER NOT NULL,
    replay_total  INTEGER NOT NULL DEFAULT 0,
    replay_agreed INTEGER NOT NULL DEFAULT 0,
    rejected_why  TEXT NOT NULL DEFAULT '',

    CHECK (status IN ('proposed','replayed','admitted','rejected')),
    CHECK (confidence BETWEEN 0 AND 256),
    CHECK (length(fixture_form) > 0),
    CHECK (replay_agreed <= replay_total)
);

-- ─────────────────────────────────────────────
-- Views
-- ─────────────────────────────────────────────

-- Recurrence. The gate ReFix calls `candidates`. Distinct sources,
-- not distinct rows — the whole point of the threshold is that the
-- same mistake was made by people who were not talking to each other.
CREATE VIEW IF NOT EXISTS v_repair_candidate AS
SELECT r.signature_id,
       r.fixture_form,
       COUNT(*)                        AS seen,
       COUNT(DISTINCT r.source_ident)  AS distinct_sources,
       COUNT(DISTINCT r.lang)          AS distinct_langs,
       MIN(r.archived_ms)              AS first_ms,
       MAX(r.archived_ms)              AS last_ms
FROM repair r
WHERE r.fixture_form IS NOT NULL
GROUP BY r.signature_id, r.fixture_form
HAVING COUNT(DISTINCT r.source_ident) >=
       (SELECT value FROM ever_constant WHERE name = 'E_ASCEND_POINTS');

-- What replay would say right now, for every candidate. A rule may
-- only be admitted when agreed = total.
CREATE VIEW IF NOT EXISTS v_repair_replay AS
SELECT c.signature_id,
       c.fixture_form,
       (SELECT COUNT(*) FROM repair p
         WHERE p.signature_id = c.signature_id
           AND p.fixture_form IS NOT NULL)              AS replay_total,
       (SELECT COUNT(*) FROM repair p
         WHERE p.signature_id = c.signature_id
           AND p.fixture_form = c.fixture_form)         AS replay_agreed
FROM v_repair_candidate c;

-- The rule ledger, admitted and rejected alike. Rejections are not
-- filtered out; they are the cheapest lesson in the corpus.
CREATE VIEW IF NOT EXISTS v_repair_rule AS
SELECT rr.rule_id,
       rr.signature_id,
       s.family,
       k.name AS kind,
       rr.fixture_form,
       rr.status,
       rr.confidence,
       rr.derived_from,
       rr.replay_agreed || '/' || rr.replay_total AS replay,
       rr.rejected_why,
       rr.proposed_ms,
       rr.decided_ms
FROM repair_rule rr
JOIN repair_signature s ON s.signature_id = rr.signature_id
JOIN repair_kind      k ON k.id           = s.kind
ORDER BY rr.proposed_ms;

-- Where the corpus is actually being spent.
CREATE VIEW IF NOT EXISTS v_repair_by_family AS
SELECT s.family,
       k.name                   AS kind,
       COUNT(*)                 AS repairs,
       COUNT(DISTINCT r.source_ident) AS sources,
       SUM(r.cost)              AS total_cost,
       ROUND(AVG(r.conf_after), 1) AS mean_conf_after
FROM repair r
JOIN repair_signature s ON s.signature_id = r.signature_id
JOIN repair_kind      k ON k.id           = r.kind
GROUP BY s.family, k.name
ORDER BY repairs DESC;

-- ============================================================
-- Triggers. The invariants, enforced at the storage boundary so that
-- no layer above can violate them even by accident.
-- ============================================================

-- Cost is derived from kind. A caller does not get to price its own
-- repair — that is how a corpus drifts.
CREATE TRIGGER IF NOT EXISTS trg_repair_cost_derived
BEFORE INSERT ON repair FOR EACH ROW
WHEN NEW.cost <> (SELECT cost FROM repair_kind WHERE id = NEW.kind)
BEGIN
SELECT RAISE(ABORT, 'repair cost must be derived from kind, not supplied');
END;

-- conf_after is not a free field either.
CREATE TRIGGER IF NOT EXISTS trg_repair_conf_derived
BEFORE INSERT ON repair FOR EACH ROW
WHEN NEW.conf_after <> MAX(0, NEW.conf_before - NEW.cost)
BEGIN
SELECT RAISE(ABORT, 'conf_after must equal max(0, conf_before - cost)');
END;

-- Confidence never rises through a repair. Fixing a thing does not
-- make the archive more certain about it than it was.
CREATE TRIGGER IF NOT EXISTS trg_repair_no_rise
BEFORE INSERT ON repair FOR EACH ROW
WHEN NEW.conf_after > NEW.conf_before
BEGIN
SELECT RAISE(ABORT, 'confidence cannot rise through a repair');
END;

-- A rule cannot be admitted below the execute floor.
CREATE TRIGGER IF NOT EXISTS trg_rule_floor
BEFORE INSERT ON repair_rule FOR EACH ROW
WHEN NEW.status = 'admitted' AND NEW.confidence <
     (SELECT value FROM ever_constant WHERE name = 'E_EXECUTE_FLOOR')
BEGIN
SELECT RAISE(ABORT, 'rule cannot be admitted below E_EXECUTE_FLOOR');
END;

-- A rule cannot be admitted if replay changed any prior outcome.
CREATE TRIGGER IF NOT EXISTS trg_rule_replay_unanimous
BEFORE INSERT ON repair_rule FOR EACH ROW
WHEN NEW.status = 'admitted' AND NEW.replay_agreed <> NEW.replay_total
BEGIN
SELECT RAISE(ABORT, 'rule cannot be admitted when replay disagreed');
END;

-- A rejection without a reason teaches nothing.
CREATE TRIGGER IF NOT EXISTS trg_rule_rejection_has_reason
BEFORE INSERT ON repair_rule FOR EACH ROW
WHEN NEW.status = 'rejected' AND length(NEW.rejected_why) = 0
BEGIN
SELECT RAISE(ABORT, 'a rejected rule must carry its reason');
END;

-- Nothing is deleted. Not a repair, not a rule, not a rejection.
CREATE TRIGGER IF NOT EXISTS trg_no_delete_repair
BEFORE DELETE ON repair FOR EACH ROW
BEGIN
SELECT RAISE(ABORT,
    'repairs are never deleted; the archive is the product');
END;

CREATE TRIGGER IF NOT EXISTS trg_no_delete_repair_rule
BEFORE DELETE ON repair_rule FOR EACH ROW
BEGIN
SELECT RAISE(ABORT,
    'rules are never deleted; a rejected rule is a boundary marker');
END;

-- A repair may not be edited after the fact. Append-only means
-- append-only, or the archive is a draft rather than a record.
CREATE TRIGGER IF NOT EXISTS trg_no_update_repair
BEFORE UPDATE ON repair FOR EACH ROW
BEGIN
SELECT RAISE(ABORT, 'repairs are append-only; archive a new row instead');
END;
