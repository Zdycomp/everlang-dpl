package com.everlang.runtime;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TranspileAuditorTest {

    @Test
    void cleanDplRowIsVerified() {
        TranspileRow row = new TranspileRow(1L, "x", "hello", "String", 200, "DPL",
                "particle x : E<String> = \"hello\" @ confidence(200)");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.total());
        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void cleanKotlinRowIsVerified() {
        TranspileRow row = new TranspileRow(2L, "x", "hello", "String", 200, "KOTLIN",
                "val x: String? = \"hello\"");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void cleanRustRowIsVerified() {
        TranspileRow row = new TranspileRow(3L, "x", "hello", "String", 200, "RUST",
                "let x: Option<String> = Some(\"hello\".to_string());");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void cleanCClangRowIsVerified() {
        TranspileRow row = new TranspileRow(4L, "x", "hello", "String", 200, "C_CLANG",
                "const char* x = \"hello\"; // Unchecked pointer");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void cleanGoRowIsVerified() {
        TranspileRow row = new TranspileRow(5L, "x", "hello", "String", 200, "GO",
                "var x string = \"hello\"");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void cleanGroovyRowIsVerified() {
        TranspileRow row = new TranspileRow(6L, "x", "hello", "String", 200, "GROOVY",
                "def x = \"hello\" as String // confidence(200)");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void corruptedRowIsCaughtAsMismatch() {
        TranspileRow row = new TranspileRow(7L, "x", "hello", "String", 200, "DPL",
                "particle x : E<String> = \"WRONG\" @ confidence(200)");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.total());
        assertEquals(0, result.verifiedCount());
        assertEquals(1, result.mismatchedCount());

        TranspileAuditor.Mismatch mismatch = result.mismatches().get(0);
        assertEquals(7L, mismatch.id());
        assertEquals("x", mismatch.name());
        assertEquals("DPL", mismatch.targetLanguage());
        assertEquals("particle x : E<String> = \"hello\" @ confidence(200)", mismatch.expected());
        assertEquals("particle x : E<String> = \"WRONG\" @ confidence(200)", mismatch.actual());
    }

    @Test
    void unknownLanguageIsTreatedAsVerified() {
        TranspileRow row = new TranspileRow(8L, "x", "hello", "String", 200, "PYTHON",
                "x = \"hello\"  # whatever this is");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.total());
        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void emptyListProducesZeroTotalsAndNoMismatches() {
        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of());

        assertEquals(0, result.total());
        assertEquals(0, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
        assertTrue(result.mismatches().isEmpty());
    }

    @Test
    void customTemplateRowIsVerified() {
        Map<String, String> custom = Map.of("SWIFT", "let {name}: {type_spec} = \"{val}\"");
        TranspileRow row = new TranspileRow(10L, "x", "hello", "String", 200, "SWIFT",
                "let x: String = \"hello\"");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), custom);

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void corruptedCustomTemplateRowIsMismatch() {
        Map<String, String> custom = Map.of("SWIFT", "let {name}: {type_spec} = \"{val}\"");
        TranspileRow row = new TranspileRow(11L, "x", "hello", "String", 200, "SWIFT",
                "let x: String = \"WRONG\"");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), custom);

        assertEquals(0, result.verifiedCount());
        assertEquals(1, result.mismatchedCount());
    }

    @Test
    void customTemplateWithConfPlaceholder() {
        Map<String, String> custom = Map.of("PYTHON", "{name} = \"{val}\"  # confidence={conf}");
        TranspileRow row = new TranspileRow(12L, "x", "hello", "String", 200, "PYTHON",
                "x = \"hello\"  # confidence=200");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), custom);

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void builtinTakesPrecedenceOverCustom() {
        Map<String, String> custom = Map.of("DPL", "wrong template {name} {val}");
        TranspileRow row = new TranspileRow(13L, "x", "hello", "String", 200, "DPL",
                "particle x : E<String> = \"hello\" @ confidence(200)");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), custom);

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void renderTemplateProducesCorrectOutput() {
        String result = TranspileAuditor.renderTemplate(
                "let {name}: {type_spec} = \"{val}\" // conf={conf}",
                "x", "hello", "String", 200);
        assertEquals("let x: String = \"hello\" // conf=200", result);
    }
}
