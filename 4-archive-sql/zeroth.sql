-- ============================================================
-- zeroth.sql — 4Ever, Layer 4 (SQL) · the Zeroth Law
--
-- If two threads are each in equilibrium with a third, they are in
-- equilibrium with each other.
--
-- The law is prior to the First. The First Law says what happens when
-- evidence combines. The Zeroth says that confidence names a comparable
-- quantity at all. Thermodynamics numbered its laws the same way and
-- for the same reason: without transitive equilibrium there is no such
-- thing as temperature, only readings.
--
-- So equilibrium has to be an EQUIVALENCE relation. Proximity — a gap
-- narrower than floor(256/pi) — is reflexive and symmetric but NOT
-- transitive, and 969,840 of its 4,922,897 candidate triples break the
-- chain. Proximity cannot carry the law.
--
-- Equilibrium is therefore equality of BAND, and band is a total
-- function of confidence. "Same band" is the kernel of a function, and
-- the kernel of a function is an equivalence relation by construction
-- rather than by luck.
--
-- What this layer adds that the others cannot: the archive REFUSES to
-- record an anchored crossing that changed band. Elsewhere the law is a
-- predicate a caller may forget to consult. Here it is a constraint at
-- the storage boundary.
--
-- Load after archive.sql; ever_constant, thread and crossing come from
-- there.
--
-- Codric Enterprise · Ricky (Dreid) · 2026
-- ============================================================

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
-- The bands. Boundaries are the constants the scale already had — the
-- derivation column is stored so nobody has to take that on trust.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ever_band (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    lo          INTEGER NOT NULL,
    hi          INTEGER NOT NULL,
    derivation  TEXT NOT NULL,
    CHECK (lo <= hi),
    CHECK (lo >= 0 AND hi <= 256)
);

INSERT OR REPLACE INTO ever_band (id, name, lo, hi, derivation) VALUES
    (0, 'Z',           0,   0,   'zero-absolute. its own state, never a low band.'),
    (1, 'Vestigial',   1,   24,  'below floor(256 / pi^2) = 25. too thin to enumerate.'),
    (2, 'Approaching', 25,  80,  'below floor(256 / pi) = 81. approaching Z.'),
    (3, 'Subfloor',    81,  127, 'below 256 / 2 = 128. present, may not execute.'),
    (4, 'Executable',  128, 255, 'cleared to execute, not verified.'),
    (5, 'Certain',     256, 256, '4^4 exactly. earned, never inferred.');

-- The band of a confidence, as a join rather than a function — SQLite
-- has no user-defined functions without a host, and the whole point of
-- Layer 4 is that it answers for itself.
CREATE VIEW IF NOT EXISTS v_band AS
SELECT c.value AS confidence, b.id AS band_id, b.name AS band_name
FROM (WITH RECURSIVE n(value) AS (
          SELECT 0 UNION ALL SELECT value + 1 FROM n WHERE value < 256)
      SELECT value FROM n) c
JOIN ever_band b ON c.value BETWEEN b.lo AND b.hi;

-- ─────────────────────────────────────────────
-- Threads, in their bands
-- ─────────────────────────────────────────────

CREATE VIEW IF NOT EXISTS v_thread_band AS
SELECT t.archive_id,
       t.ident,
       t.lang_id,
       t.confidence,
       t.anchor_id,
       b.id   AS band_id,
       b.name AS band_name
FROM thread t
JOIN ever_band b ON t.confidence BETWEEN b.lo AND b.hi;

-- The equivalence classes themselves. This is what the law buys: a
-- partition you can actually group by.
CREATE VIEW IF NOT EXISTS v_equilibrium_class AS
SELECT b.id   AS band_id,
       b.name AS band_name,
       COUNT(t.archive_id)   AS threads,
       MIN(t.confidence)     AS lowest,
       MAX(t.confidence)     AS highest,
       COUNT(DISTINCT t.lang_id) AS langs
FROM ever_band b
LEFT JOIN thread t ON t.confidence BETWEEN b.lo AND b.hi
GROUP BY b.id, b.name
ORDER BY b.id;

-- ─────────────────────────────────────────────
-- The law under translation
--
-- An anchored thread crosses without loss, so its band holds. An
-- unanchored one pays 1 per crossing, which only bites when it stands
-- on the lowest value of its band — there, one hop demotes it, and two
-- threads that were comparable at home are not comparable abroad.
--
-- Anchoring is what makes the scale portable.
-- ─────────────────────────────────────────────

CREATE VIEW IF NOT EXISTS v_band_drift AS
SELECT x.crossing_id,
       x.thread_id,
       x.anchor_id,
       x.from_lang,
       x.to_lang,
       x.conf_before,
       x.conf_after,
       bb.name AS band_before,
       ba.name AS band_after,
       CASE WHEN x.anchor_id IS NULL OR x.anchor_id = 0
            THEN 'unanchored' ELSE 'anchored' END AS carriage
FROM crossing x
JOIN ever_band bb ON x.conf_before BETWEEN bb.lo AND bb.hi
JOIN ever_band ba ON x.conf_after  BETWEEN ba.lo AND ba.hi
WHERE bb.id <> ba.id;

-- Every thread that is one confidence point above a band floor is one
-- unanchored crossing away from being demoted. Naming them is cheaper
-- than discovering them.
CREATE VIEW IF NOT EXISTS v_at_risk AS
SELECT t.archive_id, t.ident, t.lang_id, t.confidence, b.name AS band_name
FROM thread t
JOIN ever_band b ON t.confidence BETWEEN b.lo AND b.hi
WHERE (t.anchor_id IS NULL OR t.anchor_id = 0)
  AND t.confidence = b.lo
  AND t.confidence > 1;

-- ============================================================
-- The invariant, enforced where a caller cannot skip it.
-- ============================================================

-- An anchor that does not hold a band is not an anchor. The existing
-- trg_anchor_holds refuses an anchored crossing that LOSES confidence;
-- this is the Zeroth Law form of the same idea, and it is the stronger
-- statement: what must be preserved is comparability, not merely the
-- number.
CREATE TRIGGER IF NOT EXISTS trg_zeroth_anchor_holds_band
BEFORE INSERT ON crossing FOR EACH ROW
WHEN NEW.anchor_id IS NOT NULL AND NEW.anchor_id > 0
 AND (SELECT b.id FROM ever_band b
       WHERE NEW.conf_before BETWEEN b.lo AND b.hi)
  <> (SELECT b.id FROM ever_band b
       WHERE NEW.conf_after  BETWEEN b.lo AND b.hi)
BEGIN
SELECT RAISE(ABORT,
    'anchored crossing changed band; the Zeroth Law does not survive it');
END;

-- A confidence outside 0..256 has no band, so it cannot be compared to
-- anything. Refusing it here keeps every view above total.
CREATE TRIGGER IF NOT EXISTS trg_zeroth_confidence_in_scale
BEFORE INSERT ON crossing FOR EACH ROW
WHEN NEW.conf_before < 0 OR NEW.conf_before > 256
  OR NEW.conf_after  < 0 OR NEW.conf_after  > 256
BEGIN
SELECT RAISE(ABORT, 'confidence outside 0..256 has no band');
END;

-- The bands partition the scale. Editing one to overlap another would
-- silently destroy transitivity everywhere above, so the table that
-- defines the law is closed to redefinition.
CREATE TRIGGER IF NOT EXISTS trg_zeroth_bands_are_a_partition
BEFORE UPDATE ON ever_band FOR EACH ROW
BEGIN
SELECT RAISE(ABORT,
    'band boundaries are derived from the scale and are not editable');
END;

-- INSERT OR REPLACE is a delete followed by an insert, so the two guards
-- above never see it. A row may enter only if it overlaps no other band
-- and does not redefine an existing one; an identical re-seed passes.
CREATE TRIGGER IF NOT EXISTS trg_zeroth_bands_insert_closed
BEFORE INSERT ON ever_band FOR EACH ROW
WHEN EXISTS (SELECT 1 FROM ever_band o
              WHERE o.id <> NEW.id AND o.lo <= NEW.hi AND NEW.lo <= o.hi)
  OR EXISTS (SELECT 1 FROM ever_band o
              WHERE o.id = NEW.id
                AND (o.name <> NEW.name OR o.lo <> NEW.lo
                     OR o.hi <> NEW.hi OR o.derivation <> NEW.derivation))
BEGIN
SELECT RAISE(ABORT,
    'bands may not overlap, and an existing band may not be redefined');
END;

CREATE TRIGGER IF NOT EXISTS trg_zeroth_no_delete_band
BEFORE DELETE ON ever_band FOR EACH ROW
BEGIN
SELECT RAISE(ABORT,
    'deleting a band would leave part of the scale uncomparable');
END;
