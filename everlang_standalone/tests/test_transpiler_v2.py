"""
Tests for SuperTranspilerV2: validation, escaping, type mapping, confidence variants.
"""
import unittest
from everlang.transpiler.super_transpiler_v2 import SuperTranspilerV2


class TestTranspilerV2Validation(unittest.TestCase):
    """Test input validation."""

    def setUp(self):
        self.transpiler = SuperTranspilerV2()

    def test_valid_inputs(self):
        """Valid inputs produce non-error output."""
        result = self.transpiler.transpile("x", "value", "str", 128)
        for code in result.values():
            self.assertNotIn("VALIDATION_ERROR", code)

    def test_invalid_identifier(self):
        """Invalid identifier names are caught."""
        result = self.transpiler.transpile("123invalid", "value", "str", 128)
        self.assertIn("VALIDATION_ERROR", result["DPL"])

    def test_empty_value(self):
        """Empty values are rejected."""
        result = self.transpiler.transpile("x", "", "str", 128)
        self.assertIn("VALIDATION_ERROR", result["DPL"])

    def test_value_too_long(self):
        """Values > 4096 bytes are rejected."""
        result = self.transpiler.transpile("x", "A" * 5000, "str", 128)
        self.assertIn("VALIDATION_ERROR", result["DPL"])

    def test_value_at_boundary(self):
        """Values exactly 4096 bytes are accepted."""
        result = self.transpiler.transpile("x", "A" * 4096, "str", 128)
        self.assertNotIn("VALIDATION_ERROR", result["DPL"])

    def test_invalid_type_spec(self):
        """Invalid type specs are caught."""
        result = self.transpiler.transpile("x", "val", "int!@#", 128)
        self.assertIn("VALIDATION_ERROR", result["DPL"])

    def test_confidence_out_of_bounds(self):
        """Confidence outside [0, 256] is rejected."""
        result = self.transpiler.transpile("x", "val", "str", 300)
        self.assertIn("VALIDATION_ERROR", result["DPL"])
        
        result = self.transpiler.transpile("x", "val", "str", -1)
        self.assertIn("VALIDATION_ERROR", result["DPL"])


class TestTranspilerV2Escaping(unittest.TestCase):
    """Test language-specific string escaping."""

    def setUp(self):
        self.transpiler = SuperTranspilerV2()

    def test_quote_escaping(self):
        """Quotes are escaped in output."""
        result = self.transpiler.transpile("config", 'path="test"', "str", 128)
        # All languages should escape quotes
        for code in result.values():
            if "VALIDATION_ERROR" not in code:
                self.assertIn('\\"', code)

    def test_backslash_escaping(self):
        """Backslashes are escaped."""
        result = self.transpiler.transpile("path", "C:\\Users\\test", "str", 128)
        for code in result.values():
            if "VALIDATION_ERROR" not in code:
                self.assertIn("\\\\", code)

    def test_newline_escaping(self):
        """Newlines are escaped."""
        result = self.transpiler.transpile("text", "line1\nline2", "str", 128)
        for code in result.values():
            if "VALIDATION_ERROR" not in code:
                self.assertIn("\\n", code)


class TestTranspilerV2TypeMapping(unittest.TestCase):
    """Test type mapping across languages."""

    def setUp(self):
        self.transpiler = SuperTranspilerV2()

    def test_int_type_mapping(self):
        """int type maps to language-native types."""
        result = self.transpiler.transpile("x", "42", "int", 200)
        
        # Check each language has correct mapped type
        self.assertIn("Int", result["KOTLIN"])      # Kotlin: Int
        self.assertIn("i64", result["RUST"])        # Rust: i64
        self.assertIn("int", result["C_CLANG"])     # C: int
        self.assertIn("int64", result["GO"])        # Go: int64

    def test_str_type_mapping(self):
        """str type maps to language-native types."""
        result = self.transpiler.transpile("x", "hello", "str", 200)
        
        self.assertIn("String", result["KOTLIN"])
        self.assertIn("String", result["RUST"])
        self.assertIn("char*", result["C_CLANG"])
        self.assertIn("string", result["GO"])

    def test_unknown_type_passthrough(self):
        """Unknown types map to language 'Any' type."""
        result = self.transpiler.transpile("x", "val", "CustomType", 128)
        # Unknown types map to default (Any/Object/etc)
        self.assertIn("Any", result["DPL"])
        self.assertIn("Object", result["GROOVY"])


class TestTranspilerV2ConfidenceVariants(unittest.TestCase):
    """Test confidence-aware template selection."""

    def setUp(self):
        self.transpiler = SuperTranspilerV2()

    def test_high_confidence_variant(self):
        """High confidence (≥200) uses optimistic variant."""
        result = self.transpiler.transpile("x", "val", "str", 240)
        self.assertIn("TRUSTED", result["DPL"])

    def test_medium_confidence_variant(self):
        """Medium confidence (50-200) uses standard variant."""
        result = self.transpiler.transpile("x", "val", "str", 128)
        # Should have normal comment but not TRUSTED or VERIFY
        self.assertNotIn("TRUSTED", result["DPL"])
        self.assertNotIn("VERIFY BEFORE USE", result["DPL"])

    def test_low_confidence_variant(self):
        """Low confidence (≤50) uses defensive variant."""
        result = self.transpiler.transpile("x", "val", "str", 30)
        self.assertIn("VERIFY BEFORE USE", result["DPL"])

    def test_rust_confidence_variants(self):
        """Rust has different variants per confidence."""
        result_high = self.transpiler.transpile("x", "val", "str", 240)
        result_low = self.transpiler.transpile("x", "val", "str", 30)
        
        # High conf should have String, Low should have Result
        self.assertIn("String", result_high["RUST"])
        self.assertIn("Result", result_low["RUST"])


class TestTranspilerV2Caching(unittest.TestCase):
    """Test template caching efficiency."""

    def setUp(self):
        self.transpiler = SuperTranspilerV2()

    def test_cache_hit_same_args(self):
        """Identical calls hit cache."""
        stats_before = self.transpiler.stats()["cache_size"]
        
        self.transpiler.transpile("x", "val", "str", 128)
        stats_after_1 = self.transpiler.stats()["cache_size"]
        
        self.transpiler.transpile("x", "val", "str", 128)
        stats_after_2 = self.transpiler.stats()["cache_size"]
        
        self.assertEqual(stats_after_1, stats_after_2, "Cache should not grow on hit")
        self.assertGreater(stats_after_1, stats_before, "Cache should grow on new args")

    def test_cache_miss_different_args(self):
        """Different args miss cache."""
        self.transpiler.transpile("x", "val1", "str", 128)
        size_1 = self.transpiler.stats()["cache_size"]
        
        self.transpiler.transpile("x", "val2", "str", 128)
        size_2 = self.transpiler.stats()["cache_size"]
        
        self.assertGreater(size_2, size_1, "Cache should grow on different args")


class TestTranspilerV2SyntaxDistance(unittest.TestCase):
    """Test refined syntax distance metric."""

    def setUp(self):
        self.transpiler = SuperTranspilerV2()

    def test_identical_patterns(self):
        """Identical patterns have distance 0."""
        dist = self.transpiler.compute_syntax_distance("abc", "abc")
        self.assertEqual(dist, 0)

    def test_different_lengths(self):
        """Different lengths increase distance."""
        dist = self.transpiler.compute_syntax_distance("a", "abcdefghij")
        self.assertGreater(dist, 0)

    def test_comment_weight(self):
        """Comments are weighted heavily."""
        dist1 = self.transpiler.compute_syntax_distance(
            'val x = "test"',
            'val x = "test" // comment'
        )
        dist2 = self.transpiler.compute_syntax_distance(
            'val x = "test"',
            'val y = "test"'  # Different var name, same length
        )
        # Comment difference should be weighted more than structural
        self.assertGreater(dist1, dist2)


class TestTranspilerV2Stats(unittest.TestCase):
    """Test statistics and introspection."""

    def setUp(self):
        self.transpiler = SuperTranspilerV2()

    def test_stats_structure(self):
        """Stats return expected keys."""
        stats = self.transpiler.stats()
        
        self.assertIn("languages_supported", stats)
        self.assertIn("cache_size", stats)
        self.assertIn("languages", stats)
        self.assertIn("high_confidence_variants", stats)
        self.assertIn("low_confidence_variants", stats)

    def test_languages_count(self):
        """All 6 languages supported."""
        stats = self.transpiler.stats()
        self.assertEqual(stats["languages_supported"], 6)
        self.assertEqual(len(stats["languages"]), 6)


if __name__ == "__main__":
    unittest.main()
