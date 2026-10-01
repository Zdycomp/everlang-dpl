import sqlite3
import tempfile
import unittest
from pathlib import Path

from everlang.core.archive import EArchive
from everlang.core.particle import EParticle
from everlang.core.reinforced_archive import ReinforcedArchive

REPO_ROOT = Path(__file__).resolve().parents[2]
CPP_BINARY = REPO_ROOT / "1-phase-cpp" / "bin" / "verify_particle"
SQL_DIR = REPO_ROOT / "4-archive-sql"


class TestReinforcedArchiveFallback(unittest.TestCase):
    """With no C++ binary and no SQL module reachable, behavior must be
    identical to plain EArchive (this is the 'reinforcement is optional,
    self-healing never depends on it' guarantee)."""

    def setUp(self):
        self.plain = EArchive()
        self.reinforced = ReinforcedArchive(
            cpp_binary_path="/nonexistent/verify_particle",
            sql_module_dir="/nonexistent/sql_dir",
        )

    def test_reports_unavailable(self):
        self.assertFalse(self.reinforced.cpp_verifier_available)
        self.assertFalse(self.reinforced.sql_available)

    def test_log_boundary_marker_does_not_raise(self):
        p = EParticle("Alpha", 220)
        # Must not raise even though both backends are unreachable.
        self.reinforced.log_boundary_marker("ctx", p, "reason")
        self.assertEqual(len(self.reinforced.boundary_markers), 1)

    def test_emulate_repair_matches_plain_archive(self):
        for error_distance in (1, 2, 3, 5):
            a = self.plain.emulate_repair("Sig", error_distance)
            b = self.reinforced.emulate_repair("Sig", error_distance)
            self.assertEqual(a.confidence, b.confidence)
            self.assertEqual(a.is_z(), b.is_z())

    def test_calculate_evolve_vector_matches_plain_archive(self):
        a = self.plain.calculate_evolve_vector(1.0, 2.0, 4.0)
        b = self.reinforced.calculate_evolve_vector(1.0, 2.0, 4.0)
        self.assertEqual(a, b)

    def test_calculate_evolve_vector_noop_matches(self):
        a = self.plain.calculate_evolve_vector(1.0, 0.0, 4.0)
        b = self.reinforced.calculate_evolve_vector(1.0, 0.0, 4.0)
        self.assertEqual(a, b)
        self.assertEqual(b, 0.0)


@unittest.skipUnless(CPP_BINARY.is_file(), "1-phase-cpp not built (run `make -C 1-phase-cpp`)")
@unittest.skipUnless(SQL_DIR.is_dir(), "4-archive-sql phase not present")
class TestReinforcedArchiveIntegration(unittest.TestCase):
    """End-to-end against the real C++ verifier and a temp SQLite db."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = str(Path(self._tmpdir) / "test_tapestry.db")
        self.archive = ReinforcedArchive(sql_db_path=self.db_path)
        self.addCleanup(self.archive.close)

    def _rows(self, table):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(f"SELECT * FROM {table}").fetchall()
        finally:
            conn.close()

    def test_available(self):
        self.assertTrue(self.archive.cpp_verifier_available)
        self.assertTrue(self.archive.sql_available)

    def test_valid_write_persists_to_boundary_markers(self):
        p = EParticle("Alpha", 220)
        self.archive.log_boundary_marker("ctx", p, "reason")
        rows = self._rows("boundary_markers")
        self.assertEqual(len(rows), 1)
        self.assertEqual(self._rows("rejected_writes"), [])

    def test_oversized_value_is_rejected_not_persisted(self):
        # 1-phase-cpp/verify_particle rejects any value over 4096 bytes,
        # a check EParticle itself never performs.
        huge = EParticle("X" * 5000, 220)
        self.archive.log_boundary_marker("ctx", huge, "reason")
        self.assertEqual(self._rows("boundary_markers"), [])
        rejected = self._rows("rejected_writes")
        self.assertEqual(len(rejected), 1)
        self.assertIn("VALUE_TOO_LONG", rejected[0][2])  # reason column

    def test_empty_value_is_rejected_not_persisted(self):
        empty = EParticle("", 220)
        self.archive.log_boundary_marker("ctx", empty, "reason")
        self.assertEqual(self._rows("boundary_markers"), [])
        rejected = self._rows("rejected_writes")
        self.assertEqual(len(rejected), 1)
        self.assertIn("VALUE_EMPTY", rejected[0][2])

    def test_emulate_repair_persists_with_documented_formula(self):
        particle = self.archive.emulate_repair("ParseError_02", 2)
        self.assertEqual(particle.confidence, 250 - 2 * 30)
        rows = self._rows("repairs")
        self.assertEqual(len(rows), 1)
        # columns: id, failing_signature, error_distance, repaired_value, confidence, quarantined, created_at
        self.assertEqual(rows[0][1], "ParseError_02")
        self.assertEqual(rows[0][2], 2)
        self.assertEqual(rows[0][4], 190)
        self.assertEqual(rows[0][5], 0)

    def test_emulate_repair_quarantine_persists(self):
        particle = self.archive.emulate_repair("ParseError_09", 9)
        self.assertTrue(particle.is_z())
        rows = self._rows("repairs")
        self.assertEqual(rows[0][4], 0)
        self.assertEqual(rows[0][5], 1)

    def test_calculate_evolve_vector_persists(self):
        vector = self.archive.calculate_evolve_vector(1.0, 2.0, 4.0)
        rows = self._rows("evolved_vectors")
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0][1], vector)

    def test_transpile_and_archive_persists_every_language(self):
        rendered = self.archive.transpile_and_archive("txRate", "0.025", "float", 190)
        self.assertEqual(len(rendered), 6)  # DPL, KOTLIN, RUST, C_CLANG, GO, GROOVY
        rows = self._rows("transpilations")
        self.assertEqual(len(rows), 6)
        # columns: id, name, val, type_spec, confidence, target_language, rendered_code, created_at
        persisted_by_lang = {r[5]: r[6] for r in rows}
        self.assertEqual(persisted_by_lang, rendered)
        self.assertEqual(self._rows("rejected_writes"), [])

    def test_transpile_and_archive_rejects_oversized_rendering(self):
        # A huge value makes every rendered snippet exceed verify_particle's
        # 4096-byte-per-call budget, so every language is rejected, not persisted.
        huge = "X" * 5000
        rendered = self.archive.transpile_and_archive("n", huge, "T", 200)
        self.assertEqual(len(rendered), 6)  # transpiler itself is unaffected
        self.assertEqual(self._rows("transpilations"), [])
        rejected = self._rows("rejected_writes")
        self.assertEqual(len(rejected), 6)
        for row in rejected:
            self.assertEqual(row[1], "transpilations")
            self.assertIn("VALUE_TOO_LONG", row[2])


if __name__ == "__main__":
    unittest.main()
