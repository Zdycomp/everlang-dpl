import unittest

from everlang.transpiler import SuperTranspiler, LANGUAGE_TEMPLATES, escape_dpl_value, validate_template


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

    def test_dpl_escapes_quotes_and_backslashes(self):
        out = self.t.transpile("x", 'say "hi" \\ ok', "T", 100)
        self.assertEqual(out["DPL"], 'particle x : E<T> = "say \\"hi\\" \\\\ ok" @ confidence(100)')

    def test_only_dpl_values_are_escaped(self):
        out = self.t.transpile("x", 'a"b', "T", 100)
        self.assertEqual(out["GO"], 'var x string = "a"b"')

    def test_escape_backslash_before_quote(self):
        self.assertEqual(escape_dpl_value('\\"'), '\\\\\\"')

    def test_values_containing_braces_do_not_break_formatting(self):
        # str.format on the template (not the value) means a value containing
        # literal braces is inserted verbatim, not re-interpreted.
        out = self.t.transpile("x", "{not a field}", "T", 100)
        self.assertIn("{not a field}", out["GO"])


class TestRegisterLanguage(unittest.TestCase):
    def setUp(self):
        self.t = SuperTranspiler()

    def test_register_adds_language_to_transpile_output(self):
        self.t.register_language("SWIFT", 'let {name}: {type_spec} = "{val}"')
        out = self.t.transpile("x", "hello", "String", 200)
        self.assertIn("SWIFT", out)
        self.assertEqual(out["SWIFT"], 'let x: String = "hello"')

    def test_register_preserves_builtin_languages(self):
        self.t.register_language("TYPESCRIPT", 'const {name}: {type_spec} = "{val}";')
        out = self.t.transpile("x", "v", "T", 100)
        self.assertEqual(len(out), 7)
        self.assertIn("DPL", out)
        self.assertIn("TYPESCRIPT", out)

    def test_register_uppercases_language_name(self):
        self.t.register_language("swift", 'let {name} = "{val}"')
        self.assertIn("SWIFT", self.t.templates)

    def test_register_with_conf_placeholder(self):
        self.t.register_language("PYTHON", '{name} = "{val}"  # confidence={conf}')
        out = self.t.transpile("x", "v", "T", 200)
        self.assertEqual(out["PYTHON"], 'x = "v"  # confidence=200')

    def test_register_missing_name_raises(self):
        with self.assertRaises(ValueError):
            self.t.register_language("BAD", 'just a string with {val}')

    def test_register_missing_val_raises(self):
        with self.assertRaises(ValueError):
            self.t.register_language("BAD", 'let {name} = something')

    def test_register_invalid_placeholder_raises(self):
        with self.assertRaises(ValueError):
            self.t.register_language("BAD", '{name} = {val} {unknown_field}')

    def test_unregister_removes_custom_language(self):
        self.t.register_language("SWIFT", 'let {name} = "{val}"')
        self.assertTrue(self.t.unregister_language("SWIFT"))
        out = self.t.transpile("x", "v", "T", 100)
        self.assertNotIn("SWIFT", out)

    def test_register_builtin_name_raises(self):
        with self.assertRaises(ValueError):
            self.t.register_language("dpl", 'particle {name} = "{val}"')
        self.assertEqual(self.t.templates["DPL"], LANGUAGE_TEMPLATES["DPL"])

    def test_unregister_builtin_returns_false(self):
        self.assertFalse(self.t.unregister_language("DPL"))
        self.assertIn("DPL", self.t.templates)

    def test_unregister_nonexistent_returns_false(self):
        self.assertFalse(self.t.unregister_language("NONEXISTENT"))

    def test_custom_languages_property(self):
        self.assertEqual(self.t.custom_languages, {})
        self.t.register_language("SWIFT", 'let {name} = "{val}"')
        self.assertEqual(set(self.t.custom_languages.keys()), {"SWIFT"})

    def test_builtin_languages_property(self):
        builtins = self.t.builtin_languages
        self.assertEqual(set(builtins.keys()), {"DPL", "KOTLIN", "RUST", "C_CLANG", "GO", "GROOVY"})

    def test_register_overwrite_custom_language(self):
        self.t.register_language("SWIFT", 'let {name} = "{val}"')
        self.t.register_language("SWIFT", 'var {name}: {type_spec} = "{val}"')
        out = self.t.transpile("x", "hello", "String", 100)
        self.assertEqual(out["SWIFT"], 'var x: String = "hello"')

    def test_multiple_custom_languages(self):
        self.t.register_language("SWIFT", 'let {name} = "{val}"')
        self.t.register_language("TYPESCRIPT", 'const {name}: {type_spec} = "{val}";')
        self.t.register_language("PYTHON", '{name} = "{val}"')
        out = self.t.transpile("x", "v", "str", 100)
        self.assertEqual(len(out), 9)


class TestValidateTemplate(unittest.TestCase):
    def test_valid_minimal_template(self):
        validate_template('{name} = "{val}"')

    def test_valid_full_template(self):
        validate_template('{name}: {type_spec} = "{val}" // {conf}')

    def test_missing_name_raises(self):
        with self.assertRaises(ValueError):
            validate_template('x = "{val}"')

    def test_missing_val_raises(self):
        with self.assertRaises(ValueError):
            validate_template('{name} = something')

    def test_unknown_placeholder_raises(self):
        with self.assertRaises(ValueError):
            validate_template('{name} = {val} {bogus}')

    def test_format_spec_rejected(self):
        with self.assertRaises(ValueError):
            validate_template('{name} = "{val}" {conf:>5}')

    def test_conversion_rejected(self):
        with self.assertRaises(ValueError):
            validate_template('{name!r} = "{val}"')

    def test_attribute_access_rejected(self):
        with self.assertRaises(ValueError):
            validate_template('{name.upper} = "{val}"')

    def test_positional_field_rejected(self):
        with self.assertRaises(ValueError):
            validate_template('{name} = "{val}" {}')

    def test_lone_brace_rejected(self):
        with self.assertRaises(ValueError):
            validate_template('{name} = "{val}" }')

    def test_escaped_braces_allowed(self):
        validate_template('{{"{name}": "{val}"}}')

    def test_escaped_placeholder_does_not_count_as_required(self):
        with self.assertRaises(ValueError):
            validate_template('{{name}} = "{val}"')


if __name__ == "__main__":
    unittest.main()
