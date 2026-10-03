package com.everlang.runtime;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Expected strings are the Python renderer's own output (tests/test_typed_transpiler.py). */
class TypedValueRendererTest {

    private static TranspileRow typed(long id, String name, String val, String typeSpec, String lang,
                                      String code, String kind) {
        return new TranspileRow(id, name, val, typeSpec, 200, lang, code, null, kind);
    }

    @Test
    void floatRendersWithNativeTypeEverywhere() {
        List<String> items = TypedValueRenderer.parse("Float", "85.5");
        assertEquals("particle cpu : E<Float> = 85.5 @ confidence(200)",
                TypedValueRenderer.render("DPL", "cpu", "Float", items, "Float", 200));
        assertEquals("val cpu: Double? = 85.5", TypedValueRenderer.render("KOTLIN", "cpu", "Float", items, "Float", 200));
        assertEquals("let cpu: Option<f64> = Some(85.5);", TypedValueRenderer.render("RUST", "cpu", "Float", items, "Float", 200));
        assertEquals("const double cpu = 85.5;", TypedValueRenderer.render("C_CLANG", "cpu", "Float", items, "Float", 200));
        assertEquals("var cpu float64 = 85.5", TypedValueRenderer.render("GO", "cpu", "Float", items, "Float", 200));
        assertEquals("Double cpu = 85.5d // confidence(200)", TypedValueRenderer.render("GROOVY", "cpu", "Float", items, "Float", 200));
    }

    @Test
    void listKeepsItsStructure() {
        List<String> items = TypedValueRenderer.parse("List<Str>", "[\"tcp\", \"udp\"]");
        assertEquals(List.of("tcp", "udp"), items);
        assertEquals("particle protocols : E<List> = [\"tcp\", \"udp\"] @ confidence(150)",
                TypedValueRenderer.render("DPL", "protocols", "List<Str>", items, "List", 150));
        assertEquals("val protocols: List<String>? = listOf(\"tcp\", \"udp\")",
                TypedValueRenderer.render("KOTLIN", "protocols", "List<Str>", items, "List", 150));
        assertEquals("let protocols: Option<Vec<String>> = Some(vec![\"tcp\".to_string(), \"udp\".to_string()]);",
                TypedValueRenderer.render("RUST", "protocols", "List<Str>", items, "List", 150));
        assertEquals("const char* protocols[2] = {\"tcp\", \"udp\"};",
                TypedValueRenderer.render("C_CLANG", "protocols", "List<Str>", items, "List", 150));
        assertEquals("var protocols []string = []string{\"tcp\", \"udp\"}",
                TypedValueRenderer.render("GO", "protocols", "List<Str>", items, "List", 150));
        assertEquals("List<String> protocols = [\"tcp\", \"udp\"] // confidence(150)",
                TypedValueRenderer.render("GROOVY", "protocols", "List<Str>", items, "List", 150));
    }

    @Test
    void intAndBoolSuffixes() {
        List<String> n = TypedValueRenderer.parse("Int", "-7");
        assertEquals("val n: Long? = -7L", TypedValueRenderer.render("KOTLIN", "n", "Int", n, "Int", 1));
        assertEquals("let n: Option<i64> = Some(-7);", TypedValueRenderer.render("RUST", "n", "Int", n, "Int", 1));
        assertEquals("Long n = -7L // confidence(1)", TypedValueRenderer.render("GROOVY", "n", "Int", n, "Int", 1));
        List<String> b = TypedValueRenderer.parse("Bool", "true");
        assertEquals("const bool on = true;", TypedValueRenderer.render("C_CLANG", "on", "Bool", b, "Bool", 1));
        assertEquals("var ports []int64 = []int64{80, 443}", TypedValueRenderer.render("GO", "ports", "List<Int>",
                TypedValueRenderer.parse("List<Int>", "[80, 443]"), "List", 1));
    }

    @Test
    void stringEscapesMatchPython() {
        String s = "q\"b\\n\nr\r$??=\u0001\t";
        assertEquals("q\\\"b\\\\n\\nr\\r$??=\u0001\t", TypedValueRenderer.escapeString("DPL", s));
        assertEquals("q\\\"b\\\\n\\nr\\r\\$??=\\u0001\t", TypedValueRenderer.escapeString("KOTLIN", s));
        assertEquals("q\\\"b\\\\n\\nr\\r$??=\\x01\t", TypedValueRenderer.escapeString("RUST", s));
        assertEquals("q\\\"b\\\\n\\nr\\r$?\\?=\\001\t", TypedValueRenderer.escapeString("C_CLANG", s));
        assertEquals("?\\?\\?", TypedValueRenderer.escapeString("C_CLANG", "???"));
    }

    @Test
    void dplStringLiteralsRoundTrip() {
        List<String> items = TypedValueRenderer.parse("List<Str>", "[\"say \\\"hi\\\"\\\\now\", \"a\\nb\\rc\"]");
        assertEquals(List.of("say \"hi\"\\now", "a\nb\rc"), items);
        assertEquals("[\"say \\\"hi\\\"\\\\now\", \"a\\nb\\rc\"]", TypedValueRenderer.dplLiteral("List<Str>", items));
    }

    @Test
    void malformedLiteralsAreRejected() {
        String[][] bad = {
                {"Int", "007"}, {"Int", "-0"}, {"Int", "9223372036854775808"}, {"Int", "-9223372036854775808"},
                {"Int", "1.5"}, {"Float", "5"}, {"Float", "1e999"}, {"Float", "nan"}, {"Bool", "True"},
                {"List<Int>", "[]"}, {"List<Int>", "[1,2]"}, {"List<Int>", "1, 2"}, {"List<Str>", "[\"a\" \"b\"]"},
                {"List<Str>", "[\"bad\\q\"]"}, {"List<Str>", "[\"open]"}, {"List<List<Int>>", "[[1]]"}, {"Str", "\"x\""},
        };
        for (String[] c : bad) {
            assertThrows(IllegalArgumentException.class, () -> TypedValueRenderer.parse(c[0], c[1]), c[0] + " " + c[1]);
        }
    }

    @Test
    void auditVerifiesCleanTypedRowsAndFlagsDrift() {
        TranspileRow clean = typed(1, "cpu", "85.5", "Float", "GO", "var cpu float64 = 85.5", "Float");
        TranspileRow quoted = typed(2, "cpu", "85.5", "Float", "GO", "var cpu string = \"85.5\"", "Float");
        TranspileRow list = typed(3, "p", "[\"tcp\"]", "List", "C_CLANG", "const char* p[1] = {\"tcp\"};", "List<Str>");
        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(clean, quoted, list));
        assertEquals(2, result.verifiedCount());
        assertEquals(1, result.mismatchedCount());
        assertEquals(2L, result.mismatches().get(0).id());
        assertEquals("var cpu float64 = 85.5", result.mismatches().get(0).expected());
    }

    @Test
    void typedRowProblemsAreMismatchesNotCrashes() {
        TranspileRow badLiteral = typed(1, "n", "seven", "Int", "GO", "var n int64 = seven", "Int");
        TranspileRow customLang = typed(2, "n", "7", "Int", "TOML", "n = 7", "Int");
        TranspileRow versioned = new TranspileRow(3, "n", "7", "Int", 200, "GO", "var n int64 = 7", 1, "Int");
        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(badLiteral, customLang, versioned));
        assertEquals(3, result.mismatchedCount());
        for (TranspileAuditor.Mismatch m : result.mismatches()) {
            assertTrue(m.expected().startsWith("<"), m.expected());
        }
    }
}
