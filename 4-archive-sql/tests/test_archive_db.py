import multiprocessing
import os
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import archive_db
from archive_db import SqlArchive


def _save_many(db_path, worker):
    """Runs in a separate process: separate connections race for versions."""
    archive = SqlArchive(db_path)
    try:
        return [archive.save_custom_template("TOML", f"w{worker}_{i} {{name}} {{val}}") for i in range(40)]
    finally:
        archive.close()


class TestSqlArchiveSchema(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_tapestry.db")
        self.archive = SqlArchive(self.db_path)

    def tearDown(self):
        self.archive.close()

    def test_tables_exist(self):
        cur = self.archive._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        names = {row[0] for row in cur.fetchall()}
        expected = {"boundary_markers", "repairs", "evolved_vectors", "rejected_writes"}
        self.assertTrue(expected.issubset(names))


class TestSqlArchiveRecording(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_tapestry.db")
        self.archive = SqlArchive(self.db_path)

    def tearDown(self):
        self.archive.close()

    def test_record_boundary_marker(self):
        row_id = self.archive.record_boundary_marker("ctx", "val", 200, "reason")
        cur = self.archive._conn.execute(
            "SELECT context, value, confidence, reason FROM boundary_markers WHERE id=?",
            (row_id,),
        )
        row = cur.fetchone()
        self.assertEqual(row, ("ctx", "val", 200, "reason"))

    def test_record_repair(self):
        row_id = self.archive.record_repair("sig", 2, "repaired_val", 190, False)
        cur = self.archive._conn.execute(
            "SELECT failing_signature, error_distance, repaired_value, confidence, quarantined "
            "FROM repairs WHERE id=?",
            (row_id,),
        )
        row = cur.fetchone()
        self.assertEqual(row, ("sig", 2, "repaired_val", 190, 0))

    def test_record_evolved_vector(self):
        row_id = self.archive.record_evolved_vector(1.5, 2.0, 3.0, 4.0)
        cur = self.archive._conn.execute(
            "SELECT vector, action_success, reaction_data, force FROM evolved_vectors WHERE id=?",
            (row_id,),
        )
        row = cur.fetchone()
        self.assertEqual(row, (1.5, 2.0, 3.0, 4.0))

    def test_record_rejected_write(self):
        row_id = self.archive.record_rejected_write("boundary_markers", "bad confidence", "{'x': 1}")
        cur = self.archive._conn.execute(
            "SELECT table_name, reason, payload FROM rejected_writes WHERE id=?",
            (row_id,),
        )
        row = cur.fetchone()
        self.assertEqual(row, ("boundary_markers", "bad confidence", "{'x': 1}"))

    def test_value_coerced_to_str(self):
        row_id = self.archive.record_boundary_marker("ctx", 12345, 100, "reason")
        cur = self.archive._conn.execute(
            "SELECT value FROM boundary_markers WHERE id=?", (row_id,)
        )
        self.assertEqual(cur.fetchone()[0], "12345")

    def test_record_transpilation(self):
        row_id = self.archive.record_transpilation(
            "my_var", "42", "int", 200, "java", "int my_var = 42;"
        )
        cur = self.archive._conn.execute(
            "SELECT name, val, type_spec, confidence, target_language, rendered_code "
            "FROM transpilations WHERE id=?",
            (row_id,),
        )
        row = cur.fetchone()
        self.assertEqual(
            row, ("my_var", "42", "int", 200, "java", "int my_var = 42;")
        )

    def test_record_transpilation_multiline_rendered_code(self):
        rendered_code = "public class Foo {\n    int x = 1;\n    void bar() {\n        return;\n    }\n}"
        row_id = self.archive.record_transpilation(
            "foo", "1", "object", 150, "java", rendered_code
        )
        cur = self.archive._conn.execute(
            "SELECT rendered_code FROM transpilations WHERE id=?", (row_id,)
        )
        self.assertEqual(cur.fetchone()[0], rendered_code)


class TestSqlArchiveConstraints(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_tapestry.db")
        self.archive = SqlArchive(self.db_path)

    def tearDown(self):
        self.archive.close()

    def test_boundary_marker_confidence_out_of_range_raises(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.archive.record_boundary_marker("ctx", "val", 300, "reason")

    def test_repair_confidence_out_of_range_raises(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.archive.record_repair("sig", 2, "val", -1, False)

    def test_transpilation_confidence_out_of_range_raises(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.archive.record_transpilation("name", "val", "type", 300, "java", "code")

    def test_quarantined_bool_roundtrips_as_int(self):
        row_id_true = self.archive.record_repair("sig", 2, "val", 190, True)
        row_id_false = self.archive.record_repair("sig", 2, "val", 190, False)

        cur = self.archive._conn.execute(
            "SELECT quarantined FROM repairs WHERE id=?", (row_id_true,)
        )
        value_true = cur.fetchone()[0]
        cur = self.archive._conn.execute(
            "SELECT quarantined FROM repairs WHERE id=?", (row_id_false,)
        )
        value_false = cur.fetchone()[0]

        self.assertEqual(value_true, 1)
        self.assertEqual(value_false, 0)
        self.assertIsInstance(value_true, int)
        self.assertIsInstance(value_false, int)


class TestSqlArchiveCustomTemplates(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_tapestry.db")
        self.archive = SqlArchive(self.db_path)

    def tearDown(self):
        self.archive.close()

    def test_save_returns_version_one_and_loads_it(self):
        self.assertEqual(self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"'), 1)
        self.assertEqual(self.archive.load_custom_templates(), {"SWIFT": (1, 'let {name} = "{val}"')})

    def test_changed_template_creates_new_version_and_keeps_old(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        self.assertEqual(self.archive.save_custom_template("SWIFT", 'var {name} = "{val}"'), 2)
        self.assertEqual(self.archive.load_custom_templates()["SWIFT"], (2, 'var {name} = "{val}"'))
        self.assertEqual(self.archive.load_template_history("SWIFT"), [
            (1, 'let {name} = "{val}"', False),
            (2, 'var {name} = "{val}"', True),
        ])

    def test_resaving_active_template_is_noop(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        self.assertEqual(self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"'), 1)
        self.assertEqual(len(self.archive.load_template_history("SWIFT")), 1)

    def test_delete_retires_but_keeps_history(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        self.assertTrue(self.archive.retire_custom_template("SWIFT"))
        self.assertEqual(self.archive.load_custom_templates(), {})
        self.assertEqual(self.archive.load_template_history("SWIFT"), [(1, 'let {name} = "{val}"', False)])

    def test_reregister_after_delete_continues_numbering(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        self.archive.retire_custom_template("SWIFT")
        self.assertEqual(self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"'), 2)

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.archive.retire_custom_template("NONEXISTENT"))

    def test_load_empty_returns_empty_dict(self):
        self.assertEqual(self.archive.load_custom_templates(), {})

    def test_at_most_one_active_version_per_language(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        with self.assertRaises(sqlite3.IntegrityError):
            self.archive._conn.execute(
                "INSERT INTO custom_template_versions (language, version, template, active) "
                "VALUES ('SWIFT', 9, 'x', 1)"
            )

    def test_transpilation_records_template_version(self):
        row_id = self.archive.record_transpilation("x", "v", "T", 200, "SWIFT", 'let x = "v"', template_version=3)
        builtin_id = self.archive.record_transpilation("x", "v", "T", 200, "GO", 'var x string = "v"')
        rows = dict(self.archive._conn.execute("SELECT id, template_version FROM transpilations").fetchall())
        self.assertEqual(rows[row_id], 3)
        self.assertIsNone(rows[builtin_id])


class TestSqlArchiveValueKind(unittest.TestCase):
    def setUp(self):
        self.archive = SqlArchive(os.path.join(tempfile.mkdtemp(), "k.db"))
        self.addCleanup(self.archive.close)

    def test_typed_row_records_its_kind(self):
        typed_id = self.archive.record_transpilation("cpu", "85.5", "Float", 200, "GO", "var cpu float64 = 85.5",
                                                     value_kind="Float")
        plain_id = self.archive.record_transpilation("cpu", "85.5", "Float", 200, "GO", 'var cpu string = "85.5"')
        rows = dict(self.archive._conn.execute("SELECT id, value_kind FROM transpilations").fetchall())
        self.assertEqual(rows, {typed_id: "Float", plain_id: None})

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.archive.record_transpilation("x", "1", "T", 1, "GO", "var x int64 = 1", value_kind="List<List<Int>>")

    def test_typed_row_cannot_carry_a_template_version(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.archive.record_transpilation("x", "1", "T", 1, "TOML", "x = 1", template_version=1, value_kind="Int")


class TestGenomicsRecorders(unittest.TestCase):
    def setUp(self):
        self.archive = SqlArchive(os.path.join(tempfile.mkdtemp(), "g.db"))
        self.addCleanup(self.archive.close)
        self.conn = self.archive._conn

    def test_valid_index_and_query_are_recorded(self):
        self.assertIsNotNone(archive_db.record_kmer_index(self.conn, "idx", 11, 5, 10, 100))
        qid = archive_db.record_sequence_query(self.conn, "idx", "ATCG", 5, 0.7, 1, 0.2)
        self.assertIsNotNone(archive_db.record_sequence_match(self.conn, qid, 3, 2, 0.5, 120, "high"))

    def test_constraint_violation_raises_and_rolls_back(self):
        with self.assertRaises(sqlite3.IntegrityError):
            archive_db.record_kmer_index(self.conn, "bad", 12, 5, 10, 100)  # kmer_size must be 11
        self.assertFalse(self.conn.in_transaction)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM kmer_indices").fetchone()[0], 0)

    def test_match_for_missing_query_raises(self):
        with self.assertRaises(sqlite3.IntegrityError):
            archive_db.record_sequence_match(self.conn, 999, 3, 2, 0.5, 120, "high")


class TestSqlArchiveMigration(unittest.TestCase):
    def test_pre_versioning_transpilations_table_gains_template_version(self):
        db_path = os.path.join(tempfile.mkdtemp(), "old.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE transpilations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
            "val TEXT NOT NULL, type_spec TEXT NOT NULL, confidence INTEGER NOT NULL, "
            "target_language TEXT NOT NULL, rendered_code TEXT NOT NULL, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO transpilations (name, val, type_spec, confidence, target_language, rendered_code) "
            "VALUES ('x', 'v', 'T', 200, 'GO', 'var x string = \"v\"')"
        )
        conn.commit()
        conn.close()

        archive = SqlArchive(db_path)
        self.addCleanup(archive.close)
        cols = {r[1] for r in archive._conn.execute("PRAGMA table_info(transpilations)")}
        self.assertIn("template_version", cols)
        self.assertIn("value_kind", cols)
        self.assertEqual(archive._conn.execute("SELECT COUNT(*) FROM transpilations").fetchone()[0], 1)
        archive.record_transpilation("y", "v", "T", 200, "SWIFT", "let y", template_version=1)
        archive.record_transpilation("z", "1", "T", 200, "GO", "var z int64 = 1", value_kind="Int")
        with self.assertRaises(sqlite3.IntegrityError):
            archive.record_transpilation("w", "1", "T", 200, "GO", "w", value_kind="Nope")

    def test_versioned_table_without_value_kind_gains_it(self):
        db_path = os.path.join(tempfile.mkdtemp(), "v1.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE transpilations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
            "val TEXT NOT NULL, type_spec TEXT NOT NULL, confidence INTEGER NOT NULL, "
            "target_language TEXT NOT NULL, rendered_code TEXT NOT NULL, created_at TEXT, "
            "template_version INTEGER)"
        )
        conn.commit()
        conn.close()
        archive = SqlArchive(db_path)
        self.addCleanup(archive.close)
        archive.record_transpilation("z", "true", "Bool", 200, "GO", "var z bool = true", value_kind="Bool")
        with self.assertRaises(sqlite3.IntegrityError):
            archive.record_transpilation("t", "1", "T", 200, "TOML", "t", template_version=2, value_kind="Int")

    def test_legacy_custom_templates_become_version_one(self):
        db_path = os.path.join(tempfile.mkdtemp(), "legacy.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE custom_templates (language TEXT PRIMARY KEY, template TEXT NOT NULL, created_at TEXT)")
        conn.execute("INSERT INTO custom_templates (language, template) VALUES ('TOML', '{name} = \"{val}\"')")
        conn.commit()
        conn.close()

        for _ in range(2):  # reopening must not duplicate the retrofit
            archive = SqlArchive(db_path)
            self.assertEqual(archive.load_custom_templates(), {"TOML": (1, '{name} = "{val}"')})
            self.assertEqual(len(archive.load_template_history("TOML")), 1)
            archive.close()

    def test_concurrent_processes_get_distinct_versions(self):
        db_path = os.path.join(tempfile.mkdtemp(), "race.db")
        SqlArchive(db_path).close()
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(4) as pool:
            results = pool.starmap(_save_many, [(db_path, i) for i in range(4)])
        versions = [v for batch in results for v in batch]
        self.assertEqual(sorted(versions), list(range(1, 4 * 40 + 1)))

    def test_reopening_migrated_db_is_idempotent(self):
        db_path = os.path.join(tempfile.mkdtemp(), "t.db")
        SqlArchive(db_path).close()
        SqlArchive(db_path).close()


class TestSqlArchiveThreadSafety(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_tapestry.db")
        self.archive = SqlArchive(self.db_path)

    def tearDown(self):
        self.archive.close()

    def test_concurrent_boundary_marker_writes(self):
        num_threads = 8
        calls_per_thread = 20
        errors = []

        def worker(idx):
            try:
                for i in range(calls_per_thread):
                    self.archive.record_boundary_marker(
                        f"ctx-{idx}", f"val-{i}", 100, "concurrent"
                    )
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])

        cur = self.archive._conn.execute("SELECT COUNT(*) FROM boundary_markers")
        count = cur.fetchone()[0]
        self.assertEqual(count, num_threads * calls_per_thread)


if __name__ == "__main__":
    unittest.main()
