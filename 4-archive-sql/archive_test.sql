-- ============================================================
-- archive_test.sql — Ever Layer 4 verification
--
-- Proves the corpus enforces Ever's invariants itself, so that no
-- layer above can violate them even by accident.
-- ============================================================

.bail off
.headers off
.mode list

-- ── seed a run ──
INSERT INTO run (started_ms, label, host_lang)
VALUES (1754960000000, 'layer-4 verification', 4);

-- ── legal particles ──
INSERT INTO particle (state_id, lang_id, confidence, lo, hi, born_ms,
                      ident, reason, run_id)
VALUES (0, 2, 0, 0, 0, 1754960000001, 'ocr_text', 'OCR not run', 1),
       (1, 2, 180, 180, 180, 1754960000002, 'parsed_amount', '', 1),
       (1, 0, 200, 200, 200, 1754960000003, 'working_parse', '', 1),
       (1, 0, 40, 40, 40, 1754960000004, 'broken_parse', '', 1),
       (2, 4, 256, 256, 256, 1754960000005, 'schema_version', '', 1),
       (3, 3, 107, 100, 115, 1754960000006, 'severity', '', 1),
       (3, 3, 125, 50, 200, 1754960000007, 'wide_range', '', 1),
       (8, 5, 0, 80, 80, 1754960000008, 'null_deref', 'unguarded null', 1);

SELECT '--- particles stored ---';
SELECT COUNT(*) || ' particles'
FROM particle;

SELECT '';
SELECT '--- v_particle: pi status computed in SQL ---';
SELECT ident || ' | ' || state || ' | ' || lang || ' | conf ' || confidence
           || ' | width ' || width || ' | ' || pi_status
           || ' | exec ' || can_execute
FROM v_particle
ORDER BY archive_id;

SELECT '';
SELECT '--- invariant: Z cannot carry confidence ---';
INSERT INTO particle (state_id, lang_id, confidence, lo, hi, born_ms, ident)
VALUES (0, 2, 150, 150, 150, 1754960000009, 'illegal_z');
SELECT 'if you see this line without an ABORT above, the trigger failed';

SELECT '';
SELECT '--- invariant: Certain must be exactly 256 ---';
INSERT INTO particle (state_id, lang_id, confidence, lo, hi, born_ms, ident)
VALUES (2, 2, 250, 250, 250, 1754960000010, 'illegal_certain');
SELECT 'if you see this line without an ABORT above, the trigger failed';

SELECT '';
SELECT '--- invariant: emulate ceiling is int(pi) = 3 ---';
INSERT INTO particle (state_id, lang_id, confidence, lo, hi, born_ms,
                      ident, error_distance)
VALUES (5, 0, 110, 110, 110, 1754960000011, 'over_emulate', 4);
SELECT 'if you see this line without an ABORT above, the trigger failed';

SELECT '';
SELECT '--- legal emulate at distance 3 ---';
INSERT INTO particle (state_id, lang_id, confidence, lo, hi, born_ms,
                      ident, error_distance, reason)
VALUES (5, 0, 110, 110, 110, 1754960000012, 'broken_parse', 3,
        'emulating working_parse at distance 3');
SELECT 'stored: ' || ident || ' @ ' || confidence || ' distance '
           || error_distance
FROM particle
WHERE ident = 'broken_parse'
  AND state_id = 5;

SELECT '';
SELECT '--- invariant: nothing is ever deleted ---';
DELETE
FROM particle
WHERE ident = 'ocr_text';
SELECT 'ocr_text still present: ' ||
       (SELECT COUNT(*) FROM particle WHERE ident = 'ocr_text');

-- ── findings and teachings ──
INSERT INTO finding (archive_id, kind, message, line_no, weight, fix_hint)
SELECT archive_id, 'error', 'statement missing semicolon', 1, 40, 'append ;'
FROM particle
WHERE ident = 'broken_parse'
  AND state_id = 1;

INSERT INTO finding (archive_id, kind, message, line_no, weight, fix_hint)
SELECT archive_id,
       'error',
       'null used without a guard',
       1,
       65,
       'check != null or use Optional'
FROM particle
WHERE ident = 'null_deref';

INSERT INTO finding (archive_id, kind, message, line_no, weight, fix_hint)
SELECT archive_id, 'pattern', 'parameters typed', 1, 30, ''
FROM particle
WHERE ident = 'parsed_amount';

INSERT INTO teaching (error_message, lang_id, fix_template,
                      success_count, first_seen_ms)
VALUES ('statement missing semicolon', 0, 'append ; to the statement', 12,
        1754960000000),
       ('null used without a guard', 5, 'wrap in Optional or guard != null', 7,
        1754960000000);

SELECT '';
SELECT '--- v_recurring_error: what recurs, and do we know the fix ---';
SELECT message || ' [' || lang || '] x' || occurrences
           || ' | ' || teaching_status
           || CASE
                  WHEN known_fix IS NOT NULL
                      THEN ' -> ' || known_fix
                  ELSE '' END
FROM v_recurring_error;

SELECT '';
SELECT '--- v_confidence_by_lang: where the corpus is thin ---';
SELECT lang || ' | n=' || particles || ' | avg ' || avg_confidence
           || ' | Z ' || z_percent || '%'
FROM v_confidence_by_lang;

SELECT '';
SELECT '--- v_boundary: where the edge of the known sat ---';
SELECT ident || ' [' || lang || '] failed at ' || failed_at
           || ' — ' || reason
FROM v_boundary;

-- ── phase events ──
INSERT INTO phase_event (left_id, right_id, outcome, occurred_ms, note)
SELECT (SELECT archive_id FROM particle WHERE ident = 'working_parse'),
       (SELECT archive_id FROM particle WHERE ident = 'parsed_amount'),
       'Excel',
       1754960000020,
       '200 and 180 combine';

INSERT INTO phase_event (left_id, right_id, outcome, low_edge, high_edge,
                         occurred_ms, note)
SELECT (SELECT archive_id FROM particle WHERE ident = 'broken_parse' AND state_id = 1),
       (SELECT archive_id FROM particle WHERE ident = 'working_parse'),
       'Expel',
       NULL,
       NULL,
       1754960000021,
       'ratio 5x is dominance';

INSERT INTO phase_event (left_id, right_id, outcome, occurred_ms, note)
SELECT (SELECT archive_id FROM particle WHERE ident = 'ocr_text'),
       (SELECT archive_id FROM particle WHERE ident = 'parsed_amount'),
       'Blocked',
       1754960000022,
       'Z contagion';

SELECT '';
SELECT '--- v_phase_summary: is the spectrum constructive ---';
SELECT outcome || ' | ' || events || ' events | ' || percent || '%'
FROM v_phase_summary;

-- ── a closed force loop ──
INSERT INTO particle (state_id, lang_id, confidence, lo, hi, born_ms,
                      ident, run_id)
VALUES (1, 2, 170, 170, 170, 1754960000030, 'parser', 1),
       (1, 2, 175, 175, 175, 1754960000031, 'parser', 1),
       (1, 2, 180, 180, 180, 1754960000032, 'parser', 1);

INSERT INTO particle (state_id, lang_id, confidence, lo, hi, born_ms,
                      ident, generation, reason, run_id)
VALUES (6, 2, 175, 175, 175, 1754960000033, 'parser', 1,
        'evolved from 3 aligned points, spread 10', 1);

INSERT INTO force_loop (ident, point_1_id, point_2_id, point_3_id,
                        spread, closed, evolved_id, direction, closed_ms)
SELECT 'parser',
       (SELECT archive_id FROM particle WHERE ident = 'parser' AND confidence = 170),
       (SELECT archive_id
        FROM particle
        WHERE ident = 'parser'
          AND confidence = 175
          AND state_id = 1),
       (SELECT archive_id FROM particle WHERE ident = 'parser' AND confidence = 180),
       10,
       1,
       (SELECT archive_id FROM particle WHERE ident = 'parser' AND state_id = 6),
       'up',
       1754960000033;

SELECT '';
SELECT '--- v_evolution: did constructs advance ---';
SELECT ident || ' | ' || point_1 || ' -> ' || point_2 || ' -> ' || point_3
           || ' | spread ' || spread || ' | evolved to ' || evolved_to
           || ' | gen ' || generation || ' | ' || direction
FROM v_evolution;

UPDATE run
SET ended_ms = 1754960000099
WHERE run_id = 1;

SELECT '';
SELECT '--- v_corpus_growth: proof the archive is learning ---';
SELECT 'run ' || run_id || ' [' || label || '] | +' || particles_added
           || ' particles | ' || z_added || ' Z | avg ' || avg_confidence
           || ' | ' || teachings_known || ' teachings'
FROM v_corpus_growth;

SELECT '';
SELECT '--- corpus totals ---';
SELECT 'particles: ' || (SELECT COUNT(*) FROM particle);
SELECT 'findings:  ' || (SELECT COUNT(*) FROM finding);
SELECT 'teachings: ' || (SELECT COUNT(*) FROM teaching);
SELECT 'phase events: ' || (SELECT COUNT(*) FROM phase_event);
SELECT 'closed loops: ' || (SELECT COUNT(*) FROM force_loop WHERE closed = 1);
