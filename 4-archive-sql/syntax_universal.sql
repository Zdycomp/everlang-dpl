-- ============================================================
-- syntax_universal.sql — 4ever, Layer 4 (SQL) · every syntax event, one query
--
-- Run from the repo root. Read-only: every archive is attached with
-- mode=ro and the view lives in the temp schema, so nothing is written.
--
--     sqlite3 :memory: < 4-archive-sql/syntax_universal.sql
--
-- Attaches all four 4ever archives and unions everything syntactic into
-- one stream, newest first. Each row says WHY it counts, in `basis` —
-- the first of these that holds:
--
--   stage   the lexer or parser refused: error_catch.stage 'lex' or
--           'parse', compile_ever's two syntax stages (syntax.py).
--           Definitive.
--   term    the text names a syntax error ("missing semicolon",
--           "unexpected token", ...: syntax_term below). Edit freely.
--   defect  only the structure says so: ever_defect 'unbounded', "extent
--           never delimited". 4ever files parse failures there
--           (syntax.py: e_z("parse", ..., Defect.UNBOUNDED)) and so does
--           the inspector for a missing `;` or `end` — but so is a DELETE
--           without WHERE, which a person would call semantic. For
--           syntax only: WHERE basis IN ('stage', 'term').
--
-- Missing archive file = "unable to open database": nothing is created.
-- Codric Enterprise · Ricky (Dreid) · 2026
-- ============================================================

ATTACH 'file:4-archive-sql/tapestry.db?mode=ro' AS tap;   -- corpus: threads, findings, teachings
ATTACH 'file:4-archive-sql/repair.db?mode=ro'   AS rep;   -- error catches, repairs, rules
ATTACH 'file:4-archive-sql/zeroth.db?mode=ro'   AS zer;   -- band-checked threads
ATTACH 'file:archive/notebook.db?mode=ro'       AS nb;    -- notebook cell runs

DROP VIEW IF EXISTS temp.v_syntax;

CREATE TEMP VIEW v_syntax AS
WITH
-- Text that names syntax. Lower-case LIKE patterns. Avoid bare short
-- stems: '%eof%' would match "thereof", '%lex%' would match "complex".
syntax_term (pattern) AS (
    VALUES ('%syntax%'), ('%parse%'), ('%lexer%'), ('%lexical%'), ('%tokeni%'),
           ('%unexpected token%'), ('%unexpected end%'), ('%end of file%'),
           ('%missing semicolon%'), ('%missing end%'), ('%unterminated%'),
           ('%unclosed%'), ('%unbalanced%'), ('%indent%')
),

-- archive.sql is loaded into all three archive databases, so its tables
-- exist in each; `db` keeps the rows of one apart from the others.
threads AS (
    SELECT 'tapestry' AS db, archive_id, lang_id, defect_id, confidence, born_ms, ident, reason
    FROM tap.thread
    UNION ALL
    SELECT 'repair', archive_id, lang_id, defect_id, confidence, born_ms, ident, reason
    FROM rep.thread
    UNION ALL
    SELECT 'zeroth', archive_id, lang_id, defect_id, confidence, born_ms, ident, reason
    FROM zer.thread
),

findings AS (
    SELECT 'tapestry' AS db, finding_id, thread_id, kind, defect_id, message, line_no, fix_hint
    FROM tap.finding
    UNION ALL
    SELECT 'repair', finding_id, thread_id, kind, defect_id, message, line_no, fix_hint
    FROM rep.finding
    UNION ALL
    SELECT 'zeroth', finding_id, thread_id, kind, defect_id, message, line_no, fix_hint
    FROM zer.finding
),

teachings AS (
    SELECT 'tapestry' AS db, teaching_id, lang_id, defect_id, error_message, fix_template, first_seen_ms
    FROM tap.teaching
    UNION ALL
    SELECT 'repair', teaching_id, lang_id, defect_id, error_message, fix_template, first_seen_ms
    FROM rep.teaching
    UNION ALL
    SELECT 'zeroth', teaching_id, lang_id, defect_id, error_message, fix_template, first_seen_ms
    FROM zer.teaching
),

-- Every source in one shape. `kind` is whatever the source calls its
-- sort of event: a compile stage, a finding kind, a signature family,
-- a notebook cell kind.
event AS (
    -- the corpus: bindings, failed or not
    SELECT t.db, 'thread' AS source, t.archive_id AS row_id, t.born_ms AS at_ms,
           t.lang_id, t.defect_id, NULL AS kind,
           t.ident || CASE WHEN t.reason <> '' THEN ': ' || t.reason ELSE '' END AS message,
           NULL AS fix, t.confidence
    FROM threads AS t

    UNION ALL
    -- what the inspector found, timed and placed by its thread
    SELECT f.db, 'finding', f.finding_id, t.born_ms, t.lang_id, f.defect_id, f.kind,
           f.message || CASE WHEN f.line_no > 0 THEN ' (line ' || f.line_no || ')' ELSE '' END,
           NULLIF(f.fix_hint, ''), t.confidence
    FROM findings AS f
    LEFT JOIN threads AS t
           ON t.db = f.db AND t.archive_id = f.thread_id

    UNION ALL
    -- what the archive learned to say about an error
    SELECT g.db, 'teaching', g.teaching_id, g.first_seen_ms, g.lang_id, g.defect_id, NULL,
           g.error_message, g.fix_template, NULL
    FROM teachings AS g

    UNION ALL
    -- failures caught before any repair is trusted
    SELECT 'repair', 'error_catch', e.error_id, e.captured_ms, e.lang, NULL, e.stage,
           e.message || CASE WHEN e.context <> '' THEN ' — ' || e.context ELSE '' END,
           rr.fixture_form, NULL
    FROM rep.error_catch AS e
    LEFT JOIN rep.repair_rule AS rr
           ON rr.rule_id = e.resolved_by

    UNION ALL
    -- accepted (failure, fixture) pairs
    SELECT 'repair', 'repair', r.repair_id, r.archived_ms, r.lang, NULL, sig.family,
           r.failure_text || CASE WHEN r.reason <> '' THEN ' — ' || r.reason ELSE '' END,
           r.fixture_text, r.conf_after
    FROM rep.repair AS r
    INNER JOIN rep.repair_signature AS sig
            ON sig.signature_id = r.signature_id

    UNION ALL
    -- the notebook's inspections of broken code ("Broken C: ...")
    SELECT 'notebook', 'cell_run', c.id, c.ran_ms,
           (SELECT l.id FROM tap.ever_lang AS l
             WHERE c.title LIKE 'Broken %:%'
               AND l.name = substr(c.title, 8, instr(c.title, ':') - 8)),
           -- detail lists the cell's defects as text; keep the one that matters here
           CASE WHEN c.detail LIKE '%defects:%unbounded%'
                THEN (SELECT d.id FROM tap.ever_defect AS d WHERE d.name = 'unbounded') END,
           c.kind,
           c.title || ' · ' || c.detail, NULL,
           CASE WHEN instr(c.got, '@') > 0 AND instr(c.got, '/256') > instr(c.got, '@')
                THEN CAST(trim(substr(c.got, instr(c.got, '@') + 1,
                                      instr(c.got, '/256') - instr(c.got, '@') - 1)) AS INTEGER)
           END
    FROM nb.cell_run AS c
    WHERE c.kind = 'inspect'          -- 'synth' cells are function synthesis, not syntax
),

classified AS (
    SELECT e.*,
           CASE
               WHEN e.source = 'error_catch' AND e.kind IN ('lex', 'parse') THEN 'stage'
               WHEN EXISTS (SELECT 1 FROM syntax_term AS st WHERE lower(e.message) LIKE st.pattern) THEN 'term'
               WHEN e.defect_id = (SELECT d.id FROM tap.ever_defect AS d WHERE d.name = 'unbounded') THEN 'defect'
           END AS basis
    FROM event AS e
)

SELECT c.db, c.source, c.row_id, c.at_ms,
       datetime(c.at_ms / 1000, 'unixepoch') AS at_utc,
       l.name AS lang, d.name AS defect, c.kind, c.basis,
       c.message, c.fix, c.confidence
FROM classified AS c
LEFT JOIN tap.ever_lang   AS l ON l.id = c.lang_id
LEFT JOIN tap.ever_defect AS d ON d.id = c.defect_id
WHERE c.basis IS NOT NULL;

-- ── The stream ─────────────────────────────────────────────
.headers on
.mode column
SELECT db, source, row_id, at_utc, lang, defect, kind, basis, message, fix, confidence
FROM v_syntax
ORDER BY at_ms DESC, db, source, row_id;
