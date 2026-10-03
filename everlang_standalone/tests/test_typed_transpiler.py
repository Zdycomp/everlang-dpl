import os
import random
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from everlang.core.reinforced_archive import ReinforcedArchive
from everlang.transpiler import SuperTranspiler, TypedValue, infer
from everlang.transpiler.typed import escape_string, validate

CONFIG = {
    "cpu_allocation": 85.5,
    "active": True,
    "retries": 3,
    "offset": -7,
    "tiny": 1e-05,
    "huge": 1e+20,
    "protocols": ["tcp", "udp", "custom_mesh"],
    "weights": [1.5, 2.0],
    "ports": [80, 443],
    "flags": [True, False],
    "hostile": ['say "hi"\\now', "a\nb\rc", "$HOME ??= x", "tab\there", "nul\x00bell\x07"],
}


class TestInference(unittest.TestCase):
    def test_native_kinds(self):
        self.assertEqual(infer(85.5), TypedValue("Float", ("85.5",)))
        self.assertEqual(infer(True), TypedValue("Bool", ("true",)))
        self.assertEqual(infer(3), TypedValue("Int", ("3",)))
        self.assertEqual(infer(["tcp", "udp"]), TypedValue("List<Str>", ("tcp", "udp")))
        self.assertEqual(infer((1, 2)), TypedValue("List<Int>", ("1", "2")))

    def test_bool_is_not_an_int(self):
        self.assertEqual(infer([True]).kind, "List<Bool>")
        with self.assertRaises(ValueError):
            infer([1, True])

    def test_rejections(self):
        for bad in ("text", [], [1, 2.5], [[1]], [{"a": 1}], float("nan"), float("inf"), 2 ** 63, None, {"a": 1}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                infer(bad)

    def test_int_limit_is_symmetric(self):
        self.assertEqual(infer(-(2 ** 63 - 1)).items, (str(-(2 ** 63 - 1)),))
        with self.assertRaises(ValueError):
            infer(-(2 ** 63))

    def test_to_python_round_trips(self):
        for value in CONFIG.values():
            self.assertEqual(infer(value).to_python(), value)

    def test_validate_requires_canonical_text(self):
        for bad in (TypedValue("Int", ("007",)), TypedValue("Int", ("-0",)), TypedValue("Float", ("5",)),
                    TypedValue("Float", ("1.50",)), TypedValue("Float", ("1e999",)), TypedValue("Bool", ("True",)),
                    TypedValue("Str", ("x",)), TypedValue("List<Int>", ()), TypedValue("Int", ("1", "2"))):
            with self.assertRaises(ValueError, msg=repr(bad)):
                validate(bad)
        validate(TypedValue("Float", ("1e+20",)))


class TestRendering(unittest.TestCase):
    def setUp(self):
        self.t = SuperTranspiler()

    def test_float_is_a_native_float_everywhere(self):
        self.assertEqual(self.t.transpile_typed("cpu", 85.5, None, 200), {
            "DPL": "particle cpu : E<Float> = 85.5 @ confidence(200)",
            "KOTLIN": "val cpu: Double? = 85.5",
            "RUST": "let cpu: Option<f64> = Some(85.5);",
            "C_CLANG": "const double cpu = 85.5;",
            "GO": "var cpu float64 = 85.5",
            "GROOVY": "Double cpu = 85.5d // confidence(200)",
        })

    def test_list_keeps_its_structure(self):
        self.assertEqual(self.t.transpile_typed("protocols", ["tcp", "udp"], "List", 150), {
            "DPL": 'particle protocols : E<List> = ["tcp", "udp"] @ confidence(150)',
            "KOTLIN": 'val protocols: List<String>? = listOf("tcp", "udp")',
            "RUST": 'let protocols: Option<Vec<String>> = Some(vec!["tcp".to_string(), "udp".to_string()]);',
            "C_CLANG": 'const char* protocols[2] = {"tcp", "udp"};',
            "GO": 'var protocols []string = []string{"tcp", "udp"}',
            "GROOVY": 'List<String> protocols = ["tcp", "udp"] // confidence(150)',
        })

    def test_bool_and_int(self):
        r = self.t.transpile_typed("on", True, None, 1)
        self.assertEqual((r["KOTLIN"], r["GO"], r["C_CLANG"]), ("val on: Boolean? = true", "var on bool = true", "const bool on = true;"))
        r = self.t.transpile_typed("n", -7, None, 1)
        self.assertEqual((r["KOTLIN"], r["RUST"], r["GROOVY"]), ("val n: Long? = -7L", "let n: Option<i64> = Some(-7);", "Long n = -7L // confidence(1)"))

    def test_type_spec_only_reaches_dpl(self):
        r = self.t.transpile_typed("x", 1.5, "ratio", 9)
        self.assertEqual(r["DPL"], "particle x : E<ratio> = 1.5 @ confidence(9)")
        self.assertNotIn("ratio", "".join(v for k, v in r.items() if k != "DPL"))

    def test_string_escapes_per_language(self):
        s = 'q"b\\n\nr\r$??=\x01\t'
        self.assertEqual(escape_string("DPL", s), 'q\\"b\\\\n\\nr\\r$??=\x01\t')
        self.assertEqual(escape_string("KOTLIN", s), 'q\\"b\\\\n\\nr\\r\\$??=\\u0001\t')
        self.assertEqual(escape_string("GROOVY", s), escape_string("KOTLIN", s))
        self.assertEqual(escape_string("RUST", s), 'q\\"b\\\\n\\nr\\r$??=\\x01\t')
        self.assertEqual(escape_string("GO", s), escape_string("RUST", s))
        self.assertEqual(escape_string("C_CLANG", s), 'q\\"b\\\\n\\nr\\r$?\\?=\\001\t')
        self.assertEqual(escape_string("C_CLANG", "???"), "?\\?\\?")

    def test_custom_languages_are_not_typed(self):
        self.t.register_language("TOML", '{name} = "{val}"')
        self.assertNotIn("TOML", self.t.transpile_typed("x", 1, None, 1))

    def test_subset_transpiler_renders_its_own_languages(self):
        self.assertEqual(set(SuperTranspiler({"GO": "x"}).transpile_typed("x", 1, None, 1)), {"GO"})

    def test_transpile_value_routes_strings_to_templates(self):
        self.assertEqual(self.t.transpile_value("s", "v", None, 5), self.t.transpile("s", "v", "String", 5))
        self.assertEqual(self.t.transpile_value("f", 0.5, None, 5), self.t.transpile_typed("f", 0.5, None, 5))

    def test_legacy_transpile_is_unchanged(self):
        self.assertEqual(self.t.transpile("cpu", 85.5, "float", 200)["GO"], 'var cpu string = "85.5"')


def _program(lang):
    t = SuperTranspiler()
    lines = [t.transpile_typed(name, value, None, 200)[lang] for name, value in CONFIG.items()]
    names = list(CONFIG)
    if lang == "C_CLANG":
        uses = "".join(f"    (void){n};\n" for n in names)
        return ("#include <stdbool.h>\n" + "\n".join(lines) + "\nint main(void) {\n" + uses + "    return 0;\n}\n")
    if lang == "GO":
        return ("package main\n\n" + "\n".join(lines) + "\n\nfunc main() {\n"
                + "".join(f"\t_ = {n}\n" for n in names) + "}\n")
    if lang == "RUST":
        return ("#![allow(unused_variables)]\nfn main() {\n" + "".join(f"    {line}\n" for line in lines) + "}\n")
    raise AssertionError(lang)


class TestRenderingsCompile(unittest.TestCase):
    """Every typed rendering of CONFIG, hostile strings included, compiled by
    the real toolchain wherever it is installed."""

    def _compile(self, lang, filename, argv):
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        path = os.path.join(work, filename)
        with open(path, "w") as f:
            f.write(_program(lang))
        env = dict(os.environ, GOCACHE=os.path.join(work, "gocache"), GO111MODULE="off")
        proc = subprocess.run(argv(path, work), capture_output=True, text=True, cwd=work, env=env, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr + "\n" + _program(lang))

    @unittest.skipUnless(shutil.which("gcc"), "gcc not installed")
    def test_c(self):
        for std in ("c99", "c11"):  # c11 (ISO mode) is where trigraphs would bite
            self._compile("C_CLANG", "typed.c",
                          lambda p, w: ["gcc", f"-std={std}", "-Wall", "-Wextra", "-Werror", "-pedantic", "-o", os.path.join(w, "a"), p])

    @unittest.skipUnless(shutil.which("go"), "go not installed")
    def test_go(self):
        self._compile("GO", "typed.go", lambda p, w: ["go", "vet", p])

    @unittest.skipUnless(shutil.which("rustc"), "rustc not installed")
    def test_rust(self):
        self._compile("RUST", "typed.rs", lambda p, w: ["rustc", "-D", "warnings", "-o", os.path.join(w, "a"), p])


class TestConfigCommand(unittest.TestCase):
    def _run(self, text, suffix, *extra):
        import contextlib
        import io
        from everlang.transpiler.cli import transpile_config
        handle = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False)
        self.addCleanup(os.unlink, handle.name)
        handle.write(text)
        handle.close()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = transpile_config(handle.name, *extra)
        return code, out.getvalue(), err.getvalue()

    def test_json_flattens_and_keeps_types(self):
        code, out, err = self._run(
            '{"node": {"alpha": {"cpu": 85.5, "ports": [80, 443], "id": "n1"}}, "mods": [{"on": true}]}',
            ".json", 200, "GO")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), [
            "var node_alpha_cpu float64 = 85.5",
            "var node_alpha_ports []int64 = []int64{80, 443}",
            'var node_alpha_id string = "n1"',
            "var mods_0_on bool = true",
        ])

    def test_unsupported_leaves_are_reported_and_skipped(self):
        code, out, err = self._run('{"ok": 1, "mixed": [1, "a"], "empty": [], "deep": [[1]], "1-bad.key": 2}',
                                   ".json", 7, None)
        self.assertEqual(code, 1)
        self.assertIn("# ok  (Int)", out)
        self.assertIn("# _1_bad_key  (Int)", out)
        self.assertEqual(len(err.splitlines()), 3)
        self.assertIn("skipped mixed:", err)

    @unittest.skipUnless(__import__("importlib").util.find_spec("tomllib"), "tomllib needs Python 3.11+")
    def test_toml(self):
        code, out, _ = self._run('[a]\nflag = false\nw = [0.5]\n', ".toml", 1, "KOTLIN")
        self.assertEqual((code, out.splitlines()), (0, ["val a_flag: Boolean? = false",
                                                        "val a_w: List<Double>? = listOf(0.5)"]))


AUDIT_JAR = Path(__file__).resolve().parents[2] / "5-runtime-java" / "target" / "self-healing-runtime.jar"


def _random_value(rng):
    alphabet = 'ab"\\$?\n\r\t\x00\x1f é{}'
    scalar = rng.choice([
        lambda: rng.randint(-(2 ** 63 - 1), 2 ** 63 - 1),
        lambda: rng.randint(-1000, 1000),
        lambda: rng.uniform(-1e6, 1e6),
        lambda: rng.choice([1e-300, 1e300, 1e-05, 1e16, -0.0, 0.1, 123456789.125]),
        lambda: rng.random() < 0.5,
        lambda: "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8))),
    ])
    if rng.random() < 0.5:
        value = scalar()
        return [value] if isinstance(value, str) else value
    first = scalar()
    same = [x for x in (scalar() for _ in range(20)) if type(x) is type(first)]
    return [first] + same[:rng.randint(0, 4)]


@unittest.skipUnless(AUDIT_JAR.is_file() and shutil.which("java"),
                     "5-runtime-java jar not built (mvn -f 5-runtime-java/pom.xml package)")
class TestJavaAuditAgreesWithPython(unittest.TestCase):
    """Typed rows written by ReinforcedArchive must audit clean in 5-runtime-java's
    TranspileAudit, and a tampered row must not."""

    def _audit(self, db_path):
        return subprocess.run(["java", "-cp", str(AUDIT_JAR), "com.everlang.runtime.TranspileAudit", db_path],
                              capture_output=True, text=True, timeout=120)

    def test_random_and_hostile_values_audit_clean(self):
        db_path = str(Path(tempfile.mkdtemp()) / "typed.db")
        archive = ReinforcedArchive(cpp_binary_path="/nonexistent/verify_particle", sql_db_path=db_path)
        self.addCleanup(archive.close)
        rng = random.Random(7)
        for i, value in enumerate(list(CONFIG.values()) + [_random_value(rng) for _ in range(200)]):
            archive.transpile_typed_and_archive(f"v{i}", value, None, rng.randint(0, 256))
        archive.transpile_and_archive("plain", 'say "hi"', "String", 100)
        proc = self._audit(db_path)
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-2000:])
        self.assertIn("MISMATCHED=0", proc.stdout)

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("UPDATE transpilations SET rendered_code='var v0 string = \"85.5\"' "
                         "WHERE name='v0' AND target_language='GO'")
            conn.commit()
        finally:
            conn.close()
        proc = self._audit(db_path)
        self.assertEqual(proc.returncode, 1, proc.stdout[-2000:])
        self.assertIn("MISMATCHED=1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
