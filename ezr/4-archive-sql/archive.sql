-- ============================================================
-- archive.sql — Ever / Tapestry, Layer 4 (SQL)
--
-- The archive. The corpus. C² — the archive correlating its own
-- correlations — requires persistence, so persistence lives here.
--
-- v2 stores what v1 could not: the payload, the anchor, and the defect
-- class. That turns the corpus from a log of confidence scores into a
-- record of actual bindings, which is what makes cross-language
-- continuity auditable rather than merely claimed.
--
-- Nothing is ever deleted. An EError is a boundary marker.
--
-- Codric Enterprise · Ricky (Dreid) · 2026
-- ============================================================

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
-- Constants. One row each. Every layer reads from here so drift is
-- impossible rather than merely discouraged.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ever_constant (
    name       TEXT PRIMARY KEY,
    value      INTEGER NOT NULL,
    derivation TEXT    NOT NULL
);

INSERT OR REPLACE INTO ever_constant (name, value, derivation) VALUES
    ('E_ZERO',               0,    'Z. zero-absolute.'),
    ('E_CERTAIN',            256,  '4^4. the states of a byte.'),
    ('E_EXECUTE_FLOOR',      128,  '256 / 2'),
    ('E_PI_WIDTH_WARN',      81,   'floor(256 / pi)'),
    ('E_PI_WIDTH_ENUMERATE', 25,   'floor(256 / pi^2)'),
    ('E_EMULATE_CEILING',    3,    'floor(pi)'),
    ('E_ASCEND_POINTS',      3,    'aligned points required to rise'),
    ('E_INTAKE',             120,  'what a literal is worth before evidence'),
    ('E_PHI_SCALED',         1618, 'phi * 1000');

-- ─────────────────────────────────────────────
-- Vocabularies
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ever_state (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, note TEXT NOT NULL);

INSERT OR REPLACE INTO ever_state (id, name, note) VALUES
    (0,'Z','unbound. unknown. contagious.'),
    (1,'Confident','bound, trusted 1..255'),
    (2,'Certain','bound, verified at 256. earned only.'),
    (3,'Equivalence','bound to a range. pi governs width.'),
    (4,'Expression','shape bound, value pending'),
    (5,'Emulating','running on a neighbour''s pattern'),
    (6,'Evolved','advanced through a closed force loop'),
    (7,'Anchored','identity pinned across translation'),
    (8,'Absent','not present. reason preserved.'),
    (9,'EError','misbound. archived as a boundary marker.');

-- The five ways a binding fails. Every structurally checkable error in
-- every language reduces to one of these.
CREATE TABLE IF NOT EXISTS ever_defect (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, note TEXT NOT NULL);

INSERT OR REPLACE INTO ever_defect (id, name, note) VALUES
    (0,'none','the binding stands'),
    (1,'unbound','name points at nothing'),
    (2,'misbound','name points at the wrong kind of thing'),
    (3,'unbounded','extent never delimited'),
    (4,'overbound','many names, one thing, no ordering'),
    (5,'orphaned','thing outlives every name that reaches it');

CREATE TABLE IF NOT EXISTS ever_lang (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    layer INTEGER, role TEXT NOT NULL);

INSERT OR REPLACE INTO ever_lang (id, name, layer, role) VALUES
    (0,'C',0,'the atom. memory. the thread struct.'),
    (1,'C++',1,'the phase engine. corroboration and conflict.'),
    (2,'Python',2,'the interpreter. Ever executes here.'),
    (3,'Ruby',3,'the DSL. the writable surface.'),
    (4,'SQL',4,'the archive. the corpus. persistence.'),
    (5,'Java',5,'the runtime. guardrails that travel.'),
    (6,'HTML',6,'the interface. hand written.'),
    (7,'Rust',NULL,'assimilation target'),
    (8,'Go',NULL,'assimilation target'),
    (9,'TypeScript',NULL,'assimilation target'),
    (10,'Swift',NULL,'assimilation target'),
    (11,'Ever',NULL,'native');

CREATE TABLE IF NOT EXISTS ever_type (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);

INSERT OR REPLACE INTO ever_type (id, name) VALUES
    (0,'void'),(1,'int'),(2,'real'),(3,'text'),
    (4,'bool'),(5,'list'),(6,'foreign');

-- ─────────────────────────────────────────────
-- Runs
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS run (
    run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    started_ms INTEGER NOT NULL,
    ended_ms   INTEGER,
    label      TEXT NOT NULL DEFAULT '',
    host_lang  INTEGER REFERENCES ever_lang(id)
);

-- ─────────────────────────────────────────────
-- The thread table. The corpus itself.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS thread (
    archive_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    state_id       INTEGER NOT NULL REFERENCES ever_state(id),
    type_id        INTEGER NOT NULL REFERENCES ever_type(id),
    lang_id        INTEGER NOT NULL REFERENCES ever_lang(id),
    defect_id      INTEGER NOT NULL DEFAULT 0 REFERENCES ever_defect(id),

    confidence     INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 256),
    lo             INTEGER NOT NULL CHECK (lo BETWEEN 0 AND 256),
    hi             INTEGER NOT NULL CHECK (hi BETWEEN 0 AND 256),

    -- the payload. v1 had nowhere to put this.
    val_text       TEXT,

    -- the anchor. 0 means unanchored.
    anchor_id      INTEGER NOT NULL DEFAULT 0,

    error_distance INTEGER NOT NULL DEFAULT 0,
    generation     INTEGER NOT NULL DEFAULT 0,
    ascend_points  INTEGER NOT NULL DEFAULT 0,

    born_ms        INTEGER NOT NULL,
    ident          TEXT    NOT NULL,
    reason         TEXT    NOT NULL DEFAULT '',
    run_id         INTEGER REFERENCES run(run_id),

    CHECK (lo <= hi)
);

CREATE INDEX IF NOT EXISTS idx_thread_ident  ON thread(ident);
CREATE INDEX IF NOT EXISTS idx_thread_state  ON thread(state_id);
CREATE INDEX IF NOT EXISTS idx_thread_lang   ON thread(lang_id);
CREATE INDEX IF NOT EXISTS idx_thread_anchor ON thread(anchor_id);
CREATE INDEX IF NOT EXISTS idx_thread_defect ON thread(defect_id);
CREATE INDEX IF NOT EXISTS idx_thread_conf   ON thread(confidence);

-- ─────────────────────────────────────────────
-- Anchors. The identity register that makes continuity auditable.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS anchor (
    anchor_id   INTEGER PRIMARY KEY,
    ident       TEXT    NOT NULL,
    pinned_at   INTEGER NOT NULL,
    pinned_conf INTEGER NOT NULL,
    val_text    TEXT,
    note        TEXT NOT NULL DEFAULT ''
);

-- Every crossing between languages. This is the audit trail for
-- "code continuity across any language."
CREATE TABLE IF NOT EXISTS crossing (
    crossing_id INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_id   INTEGER REFERENCES anchor(anchor_id),
    thread_id   INTEGER NOT NULL REFERENCES thread(archive_id),
    from_lang   INTEGER NOT NULL REFERENCES ever_lang(id),
    to_lang     INTEGER NOT NULL REFERENCES ever_lang(id),
    conf_before INTEGER NOT NULL,
    conf_after  INTEGER NOT NULL,
    val_before  TEXT,
    val_after   TEXT,
    crossed_ms  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_crossing_anchor ON crossing(anchor_id);

-- ─────────────────────────────────────────────
-- Findings, teachings, phase events, force loops
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS finding (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id  INTEGER NOT NULL REFERENCES thread(archive_id),
    kind       TEXT NOT NULL CHECK (kind IN ('error','pattern')),
    defect_id  INTEGER NOT NULL DEFAULT 0 REFERENCES ever_defect(id),
    message    TEXT NOT NULL,
    line_no    INTEGER NOT NULL DEFAULT 0,
    weight     INTEGER NOT NULL DEFAULT 0,
    fix_hint   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_finding_thread  ON finding(thread_id);
CREATE INDEX IF NOT EXISTS idx_finding_defect  ON finding(defect_id);

CREATE TABLE IF NOT EXISTS teaching (
    teaching_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    error_message   TEXT    NOT NULL,
    lang_id         INTEGER NOT NULL REFERENCES ever_lang(id),
    defect_id       INTEGER NOT NULL DEFAULT 0 REFERENCES ever_defect(id),
    fix_template    TEXT    NOT NULL,
    applied_count   INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    first_seen_ms   INTEGER NOT NULL,
    last_applied_ms INTEGER,
    UNIQUE (error_message, lang_id)
);

CREATE TABLE IF NOT EXISTS phase_event (
    phase_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    left_id     INTEGER NOT NULL REFERENCES thread(archive_id),
    right_id    INTEGER NOT NULL REFERENCES thread(archive_id),
    outcome     TEXT NOT NULL CHECK (outcome IN
                    ('Excel','Expel','Repel','Conflict','Blocked')),
    same_value  INTEGER NOT NULL DEFAULT 0,
    result_id   INTEGER REFERENCES thread(archive_id),
    low_edge    INTEGER,
    high_edge   INTEGER,
    occurred_ms INTEGER NOT NULL,
    note        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS force_loop (
    loop_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ident      TEXT NOT NULL,
    point_1_id INTEGER REFERENCES thread(archive_id),
    point_2_id INTEGER REFERENCES thread(archive_id),
    point_3_id INTEGER REFERENCES thread(archive_id),
    spread     INTEGER,
    closed     INTEGER NOT NULL DEFAULT 0,
    evolved_id INTEGER REFERENCES thread(archive_id),
    direction  TEXT CHECK (direction IN ('up','down','flat')),
    closed_ms  INTEGER
);

-- ============================================================
-- Views. C² — the archive correlating its own correlations.
-- ============================================================

CREATE VIEW IF NOT EXISTS v_thread AS
SELECT
    t.archive_id,
    s.name AS state, y.name AS type, l.name AS lang, d.name AS defect,
    t.ident, t.val_text AS value, t.confidence, t.lo, t.hi,
    (t.hi - t.lo) AS width,
    CASE
        WHEN (t.hi - t.lo) > (SELECT value FROM ever_constant
                              WHERE name='E_PI_WIDTH_WARN') THEN 'APPROACHING_Z'
        WHEN (t.hi - t.lo) > (SELECT value FROM ever_constant
                              WHERE name='E_PI_WIDTH_ENUMERATE') THEN 'ENUMERATE'
        ELSE 'ACCEPTABLE'
    END AS pi_status,
    CASE WHEN s.name IN ('Z','EError','Absent') THEN 0
         WHEN t.confidence > 0 THEN 1 ELSE 0 END AS cleared,
    CASE WHEN s.name IN ('Z','EError','Absent') THEN 0
         WHEN t.confidence >= (SELECT value FROM ever_constant
                               WHERE name='E_EXECUTE_FLOOR') THEN 1
         ELSE 0 END AS can_execute,
    t.anchor_id,
    CASE WHEN t.anchor_id > 0 THEN 1 ELSE 0 END AS anchored,
    t.error_distance, t.generation, t.ascend_points, t.reason, t.run_id
FROM thread t
JOIN ever_state  s ON s.id = t.state_id
JOIN ever_type   y ON y.id = t.type_id
JOIN ever_lang   l ON l.id = t.lang_id
JOIN ever_defect d ON d.id = t.defect_id;

-- Continuity audit: did an anchored thread keep its value and its
-- confidence across every language it crossed?
CREATE VIEW IF NOT EXISTS v_continuity AS
SELECT
    a.anchor_id,
    a.ident,
    a.val_text                       AS pinned_value,
    a.pinned_conf,
    COUNT(c.crossing_id)             AS crossings,
    GROUP_CONCAT(lf.name || '->' || lt.name, ' ') AS path,
    MIN(c.conf_after)                AS lowest_after,
    SUM(CASE WHEN c.val_before IS NOT c.val_after THEN 1 ELSE 0 END)
                                     AS value_changes,
    SUM(c.conf_before - c.conf_after) AS total_confidence_lost,
    CASE
        WHEN SUM(CASE WHEN c.val_before IS NOT c.val_after THEN 1 ELSE 0 END) > 0
            THEN 'VALUE DRIFT'
        WHEN SUM(c.conf_before - c.conf_after) > 0 THEN 'CONFIDENCE DRIFT'
        ELSE 'HELD'
    END AS verdict
FROM anchor a
LEFT JOIN crossing c  ON c.anchor_id = a.anchor_id
LEFT JOIN ever_lang lf ON lf.id = c.from_lang
LEFT JOIN ever_lang lt ON lt.id = c.to_lang
GROUP BY a.anchor_id;

-- Which of the five defects dominate, and in which language
CREATE VIEW IF NOT EXISTS v_defect_profile AS
SELECT
    d.name AS defect, l.name AS lang,
    COUNT(*) AS occurrences,
    ROUND(AVG(t.confidence),1) AS avg_confidence_at_failure
FROM thread t
JOIN ever_defect d ON d.id = t.defect_id
JOIN ever_lang   l ON l.id = t.lang_id
WHERE t.defect_id <> 0
GROUP BY d.name, l.name
ORDER BY occurrences DESC;

CREATE VIEW IF NOT EXISTS v_recurring_error AS
SELECT
    f.message, l.name AS lang, d.name AS defect,
    COUNT(*) AS occurrences,
    MAX(te.fix_template) AS known_fix,
    CASE WHEN MAX(te.teaching_id) IS NULL THEN 'UNTAUGHT' ELSE 'TAUGHT' END
        AS teaching_status
FROM finding f
JOIN thread t     ON t.archive_id = f.thread_id
JOIN ever_lang l  ON l.id = t.lang_id
JOIN ever_defect d ON d.id = f.defect_id
LEFT JOIN teaching te
       ON te.error_message = f.message AND te.lang_id = t.lang_id
WHERE f.kind = 'error'
GROUP BY f.message, l.name, d.name
ORDER BY occurrences DESC;

CREATE VIEW IF NOT EXISTS v_confidence_by_lang AS
SELECT
    l.name AS lang, COUNT(*) AS threads,
    ROUND(AVG(t.confidence),1) AS avg_confidence,
    SUM(CASE WHEN s.name='Z' THEN 1 ELSE 0 END) AS z_count,
    SUM(CASE WHEN t.anchor_id>0 THEN 1 ELSE 0 END) AS anchored_count,
    ROUND(100.0*SUM(CASE WHEN s.name='Z' THEN 1 ELSE 0 END)/COUNT(*),1)
        AS z_percent
FROM thread t
JOIN ever_lang  l ON l.id = t.lang_id
JOIN ever_state s ON s.id = t.state_id
GROUP BY l.name
ORDER BY avg_confidence DESC;

CREATE VIEW IF NOT EXISTS v_boundary AS
SELECT t.ident, l.name AS lang, d.name AS defect,
       t.lo AS failed_at, t.reason, t.born_ms, t.run_id
FROM thread t
JOIN ever_state  s ON s.id = t.state_id
JOIN ever_lang   l ON l.id = t.lang_id
JOIN ever_defect d ON d.id = t.defect_id
WHERE s.name = 'EError'
ORDER BY t.born_ms DESC;

CREATE VIEW IF NOT EXISTS v_phase_summary AS
SELECT outcome,
       COUNT(*) AS events,
       SUM(same_value) AS with_agreement,
       ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM phase_event),1) AS percent
FROM phase_event
GROUP BY outcome
ORDER BY events DESC;

CREATE VIEW IF NOT EXISTS v_evolution AS
SELECT fl.ident, fl.spread, fl.direction,
       p1.confidence AS point_1, p2.confidence AS point_2,
       p3.confidence AS point_3, pe.confidence AS evolved_to,
       pe.generation, fl.closed_ms
FROM force_loop fl
LEFT JOIN thread p1 ON p1.archive_id = fl.point_1_id
LEFT JOIN thread p2 ON p2.archive_id = fl.point_2_id
LEFT JOIN thread p3 ON p3.archive_id = fl.point_3_id
LEFT JOIN thread pe ON pe.archive_id = fl.evolved_id
WHERE fl.closed = 1
ORDER BY fl.closed_ms DESC;

CREATE VIEW IF NOT EXISTS v_corpus_growth AS
SELECT r.run_id, r.label, r.started_ms,
       COUNT(t.archive_id) AS threads_added,
       SUM(CASE WHEN s.name='Z' THEN 1 ELSE 0 END) AS z_added,
       SUM(CASE WHEN t.anchor_id>0 THEN 1 ELSE 0 END) AS anchored_added,
       ROUND(AVG(t.confidence),1) AS avg_confidence,
       (SELECT COUNT(*) FROM teaching) AS teachings_known
FROM run r
LEFT JOIN thread t     ON t.run_id = r.run_id
LEFT JOIN ever_state s ON s.id = t.state_id
GROUP BY r.run_id
ORDER BY r.run_id;

-- ============================================================
-- Triggers. Ever's invariants, enforced by the database so no layer
-- above can violate them even by accident.
-- ============================================================

CREATE TRIGGER IF NOT EXISTS trg_z_must_be_zero
BEFORE INSERT ON thread FOR EACH ROW
WHEN NEW.state_id = 0 AND NEW.confidence <> 0
BEGIN SELECT RAISE(ABORT,'Z thread cannot carry confidence'); END;

CREATE TRIGGER IF NOT EXISTS trg_certain_is_256
BEFORE INSERT ON thread FOR EACH ROW
WHEN NEW.state_id = 2 AND NEW.confidence <> 256
BEGIN SELECT RAISE(ABORT,'Certain must be exactly 256'); END;

CREATE TRIGGER IF NOT EXISTS trg_emulate_ceiling
BEFORE INSERT ON thread FOR EACH ROW
WHEN NEW.state_id = 5 AND NEW.error_distance >
     (SELECT value FROM ever_constant WHERE name='E_EMULATE_CEILING')
BEGIN SELECT RAISE(ABORT,'error distance exceeds emulate ceiling'); END;

-- An anchor on an uncleared binding propagates a lie into every language
-- it touches, so the corpus refuses to store one.
CREATE TRIGGER IF NOT EXISTS trg_no_anchor_on_uncleared
BEFORE INSERT ON thread FOR EACH ROW
WHEN NEW.anchor_id > 0 AND (NEW.state_id IN (0,8,9) OR NEW.confidence = 0)
BEGIN SELECT RAISE(ABORT,'cannot anchor an uncleared binding'); END;

-- Ascend requires three aligned points. More than three is a counting bug.
CREATE TRIGGER IF NOT EXISTS trg_ascend_points_bound
BEFORE INSERT ON thread FOR EACH ROW
WHEN NEW.ascend_points >
     (SELECT value FROM ever_constant WHERE name='E_ASCEND_POINTS')
BEGIN SELECT RAISE(ABORT,'ascend points exceed the required count'); END;

-- An anchored crossing that loses confidence is a broken anchor.
CREATE TRIGGER IF NOT EXISTS trg_anchor_holds
BEFORE INSERT ON crossing FOR EACH ROW
WHEN NEW.anchor_id IS NOT NULL AND NEW.anchor_id > 0
 AND NEW.conf_after < NEW.conf_before
BEGIN SELECT RAISE(ABORT,'anchored crossing must not lose confidence'); END;

CREATE TRIGGER IF NOT EXISTS trg_no_delete_thread
BEFORE DELETE ON thread FOR EACH ROW
BEGIN SELECT RAISE(ABORT,
    'threads are never deleted; an EError is a boundary marker'); END;

CREATE TRIGGER IF NOT EXISTS trg_no_delete_teaching
BEFORE DELETE ON teaching FOR EACH ROW
BEGIN SELECT RAISE(ABORT,'teachings are never deleted'); END;

CREATE TRIGGER IF NOT EXISTS trg_no_delete_anchor
BEFORE DELETE ON anchor FOR EACH ROW
BEGIN SELECT RAISE(ABORT,'anchors are never deleted'); END;
