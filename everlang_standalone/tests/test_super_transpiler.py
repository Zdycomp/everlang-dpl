import unittest

from everlang.transpiler import SuperTranspiler, LANGUAGE_TEMPLATES


class TestSuperTranspiler(unittest.TestCase):
    def setUp(self):
        self.t = SuperTranspiler()

    def test_default_templates_cover_six_languages(self):
        self.assertEqual(
            set(LANGUAGE_TEMPLATES.keys()),
            {"DPL", "KOTLIN", "RUST", "C_CLANG", "GO", "GROOVY"},
        )

    def test_transpile_renders_every_configured_language(self):
        out = self.t.transpile("txRate", "0.025", "float", 190)
        self.assertEqual(set(out.keys()), set(LANGUAGE_TEMPLATES.keys()))
        for rendered in out.values():
            self.assertIn("txRate", rendered)
            self.assertIn("0.025", rendered)

    def test_dpl_template_unchanged_from_original_benchmark(self):
        out = self.t.transpile("x", "v", "T", 100)
        self.assertEqual(out["DPL"], 'particle x : E<T> = "v" @ confidence(100)')

    def test_kotlin_template_unchanged_from_original_benchmark(self):
        out = self.t.transpile("x", "v", "String", 100)
        self.assertEqual(out["KOTLIN"], 'val x: String? = "v"')

    def test_rust_template_unchanged_from_original_benchmark(self):
        out = self.t.transpile("x", "v", "String", 100)
        self.assertEqual(out["RUST"], 'let x: Option<String> = Some("v".to_string());')

    def test_c_clang_template_unchanged_from_original_benchmark(self):
        out = self.t.transpile("x", "v", "T", 100)
        self.assertEqual(out["C_CLANG"], 'const char* x = "v"; // Unchecked pointer')

    def test_go_template_unchanged_from_original_benchmark(self):
        out = self.t.transpile("x", "v", "T", 100)
        self.assertEqual(out["GO"], 'var x string = "v"')

    def test_groovy_template_is_valid_shaped_groovy(self):
        out = self.t.transpile("x", "v", "BigDecimal", 100)
        self.assertEqual(out["GROOVY"], 'def x = "v" as BigDecimal // confidence(100)')

    def test_compute_syntax_distance_zero_for_identical(self):
        self.assertEqual(self.t.compute_syntax_distance("abc", "abc"), 0)

    def test_compute_syntax_distance_nonzero_for_different(self):
        d = self.t.compute_syntax_distance("abc", "abcdefgh")
        self.assertEqual(d, abs(3 - 8) % 5 + 1)

    def test_custom_templates_override_defaults(self):
        custom = SuperTranspiler(templates={"SWIFT": "let {name} = \"{val}\""})
        out = custom.transpile("x", "v", "T", 100)
        self.assertEqual(out, {"SWIFT": 'let x = "v"'})

    def test_values_containing_braces_do_not_break_formatting(self):
        # str.format on the template (not the value) means a value containing
        # literal braces is inserted verbatim, not re-interpreted.
        out = self.t.transpile("x", "{not a field}", "T", 100)
        self.assertIn("{not a field}", out["GO"])


if __name__ == "__main__":
    unittest.main()
