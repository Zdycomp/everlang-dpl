package com.everlang.runtime;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
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
    void dplValueQuotesAndBackslashesAreEscaped() {
        // Byte-for-byte what super_transpiler.py renders for val = say "hi" \ ok
        TranspileRow row = new TranspileRow(20L, "x", "say \"hi\" \\ ok", "T", 100, "DPL",
                "particle x : E<T> = \"say \\\"hi\\\" \\\\ ok\" @ confidence(100)");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void dplNewlineAndCarriageReturnAreEscaped() {
        TranspileRow row = new TranspileRow(23L, "x", "a\nb\rc", "T", 100, "DPL",
                "particle x : E<T> = \"a\\nb\\rc\" @ confidence(100)");

        assertEquals(1, TranspileAuditor.audit(List.of(row)).verifiedCount());
    }

    @Test
    void nullColumnIsMismatchNotCrash() {
        TranspileRow nullLanguage = new TranspileRow(24L, "x", "v", "T", 100, null, "anything");
        TranspileRow nullValue = new TranspileRow(25L, "x", null, "T", 100, "DPL", "anything");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(nullLanguage, nullValue));

        assertEquals(2, result.mismatchedCount());
        assertEquals("<null column in row 24>", result.mismatches().get(0).expected());
    }

    @Test
    void unescapedDplRowWrittenBeforeEscapingIsFlagged() {
        TranspileRow row = new TranspileRow(21L, "x", "a\"b", "T", 100, "DPL",
                "particle x : E<T> = \"a\"b\" @ confidence(100)");

        assertEquals(1, TranspileAuditor.audit(List.of(row)).mismatchedCount());
    }

    @Test
    void onlyDplValuesAreEscaped() {
        TranspileRow row = new TranspileRow(22L, "x", "a\"b", "T", 100, "GO", "var x string = \"a\"b\"");

        assertEquals(1, TranspileAuditor.audit(List.of(row)).verifiedCount());
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

    private static final Map<String, Map<Integer, String>> SWIFT_V1_V2 = Map.of("SWIFT", Map.of(
            1, "let {name} = \"{val}\"",
            2, "let {name}: {type_spec} = \"{val}\""));

    @Test
    void customRowIsVerifiedAgainstItsStampedVersion() {
        TranspileRow row = new TranspileRow(10L, "x", "hello", "String", 200, "SWIFT",
                "let x: String = \"hello\"", 2);

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), SWIFT_V1_V2);

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void rowFromOlderVersionStillVerifiesAfterTemplateEdit() {
        TranspileRow oldRow = new TranspileRow(11L, "x", "hello", "String", 200, "SWIFT",
                "let x = \"hello\"", 1);
        TranspileRow newRow = new TranspileRow(12L, "x", "hello", "String", 200, "SWIFT",
                "let x: String = \"hello\"", 2);

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(oldRow, newRow), SWIFT_V1_V2);

        assertEquals(2, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void corruptedCustomRowIsMismatch() {
        TranspileRow row = new TranspileRow(13L, "x", "hello", "String", 200, "SWIFT",
                "let x: String = \"WRONG\"", 2);

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), SWIFT_V1_V2);

        assertEquals(1, result.mismatchedCount());
        assertEquals("let x: String = \"hello\"", result.mismatches().get(0).expected());
    }

    @Test
    void rowStampedWithMissingVersionIsMismatch() {
        TranspileRow row = new TranspileRow(14L, "x", "hello", "String", 200, "SWIFT",
                "let x = \"hello\"", 3);

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), SWIFT_V1_V2);

        assertEquals(1, result.mismatchedCount());
        assertEquals("<missing custom template SWIFT v3>", result.mismatches().get(0).expected());
    }

    @Test
    void rowForDeletedLanguageHistoryIsMismatch() {
        TranspileRow row = new TranspileRow(15L, "x", "hello", "String", 200, "TOML",
                "[x]\nvalue = \"hello\"", 1);

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), SWIFT_V1_V2);

        assertEquals(1, result.mismatchedCount());
    }

    @Test
    void unversionedCustomRowIsTreatedAsVerified() {
        TranspileRow row = new TranspileRow(16L, "x", "hello", "String", 200, "SWIFT",
                "anything at all");

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), SWIFT_V1_V2);

        assertEquals(1, result.verifiedCount());
    }

    @Test
    void invalidStoredTemplateIsMismatchNotCrash() {
        Map<String, Map<Integer, String>> custom = Map.of("BAD", Map.of(1, "{name} {bogus}"));
        TranspileRow row = new TranspileRow(17L, "x", "hello", "String", 200, "BAD", "x ?", 1);

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), custom);

        assertEquals(1, result.mismatchedCount());
        assertTrue(result.mismatches().get(0).expected().startsWith("<invalid custom template BAD v1"));
    }

    @Test
    void builtinTakesPrecedenceOverCustom() {
        Map<String, Map<Integer, String>> custom = Map.of("DPL", Map.of(1, "wrong template {name} {val}"));
        TranspileRow row = new TranspileRow(18L, "x", "hello", "String", 200, "DPL",
                "particle x : E<String> = \"hello\" @ confidence(200)", 1);

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(List.of(row), custom);

        assertEquals(1, result.verifiedCount());
    }

    @Test
    void renderTemplateSubstitutesAllFields() {
        assertEquals("let x: String = \"hello\" // conf=200", TranspileAuditor.renderTemplate(
                "let {name}: {type_spec} = \"{val}\" // conf={conf}", "x", "hello", "String", 200));
    }

    @Test
    void renderTemplateNeverRescansSubstitutedValues() {
        // Python's str.format inserts values verbatim; a chained String.replace
        // would expand the "{type_spec}" inside val and report false drift.
        assertEquals("x = \"{type_spec}\" : T", TranspileAuditor.renderTemplate(
                "{name} = \"{val}\" : {type_spec}", "x", "{type_spec}", "T", 1));
    }

    @Test
    void renderTemplateUnescapesDoubledBraces() {
        assertEquals("{x} = {\"v\"}", TranspileAuditor.renderTemplate(
                "{{{name}}} = {{\"{val}\"}}", "x", "v", "T", 1));
        assertEquals("{name}", TranspileAuditor.renderTemplate("{{name}}", "x", "v", "T", 1));
    }

    @Test
    void renderTemplateRejectsUnsupportedPlaceholder() {
        assertThrows(IllegalArgumentException.class,
                () -> TranspileAuditor.renderTemplate("{name:>5}", "x", "v", "T", 1));
        assertThrows(IllegalArgumentException.class,
                () -> TranspileAuditor.renderTemplate("{name} }", "x", "v", "T", 1));
    }
}
