import os
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from archive_db import SqlArchive


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

    def test_save_and_load_custom_template(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        templates = self.archive.load_custom_templates()
        self.assertEqual(templates, {"SWIFT": 'let {name} = "{val}"'})

    def test_upsert_overwrites_existing(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        self.archive.save_custom_template("SWIFT", 'var {name} = "{val}"')
        templates = self.archive.load_custom_templates()
        self.assertEqual(templates["SWIFT"], 'var {name} = "{val}"')

    def test_delete_custom_template(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        self.assertTrue(self.archive.delete_custom_template("SWIFT"))
        self.assertEqual(self.archive.load_custom_templates(), {})

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.archive.delete_custom_template("NONEXISTENT"))

    def test_load_empty_returns_empty_dict(self):
        self.assertEqual(self.archive.load_custom_templates(), {})

    def test_multiple_templates(self):
        self.archive.save_custom_template("SWIFT", 'let {name} = "{val}"')
        self.archive.save_custom_template("TYPESCRIPT", 'const {name} = "{val}";')
        templates = self.archive.load_custom_templates()
        self.assertEqual(len(templates), 2)
        self.assertIn("SWIFT", templates)
        self.assertIn("TYPESCRIPT", templates)


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
