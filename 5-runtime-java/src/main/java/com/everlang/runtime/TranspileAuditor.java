package com.everlang.runtime;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Pure (no JDBC, no I/O) re-derivation of the expected rendered code for a
 * {@link TranspileRow}, mirroring the Python source of truth:
 *
 * {@code everlang_standalone/everlang/transpiler/super_transpiler.py :: LANGUAGE_TEMPLATES}
 *
 * <pre>
 * LANGUAGE_TEMPLATES: Dict[str, str] = {
 *     "DPL": "particle {name} : E&lt;{type_spec}&gt; = \"{val}\" @ confidence({conf})",
 *     "KOTLIN": "val {name}: {type_spec}? = \"{val}\"",
 *     "RUST": "let {name}: Option&lt;{type_spec}&gt; = Some(\"{val}\".to_string());",
 *     "C_CLANG": "const char* {name} = \"{val}\"; // Unchecked pointer",
 *     "GO": "var {name} string = \"{val}\"",
 *     "GROOVY": "def {name} = \"{val}\" as {type_spec} // confidence({conf})",
 * }
 * </pre>
 *
 * This class does not invent any additional rule: for a row whose
 * {@code targetLanguage} is one of the six above, the matching template is
 * re-rendered from the row's own {@code name}/{@code val}/{@code typeSpec}/
 * {@code confidence} and compared byte-for-byte to {@code renderedCode}; a
 * mismatch is any difference. Custom language templates loaded from the
 * {@code custom_templates} table are also verified the same way. A row whose
 * {@code targetLanguage} is neither built-in nor custom is treated as
 * automatically verified (not mismatched).
 */
public final class TranspileAuditor {

    private TranspileAuditor() {
    }

    public static AuditResult audit(List<TranspileRow> rows) {
        return audit(rows, Map.of());
    }

    public static AuditResult audit(List<TranspileRow> rows, Map<String, String> customTemplates) {
        List<Mismatch> mismatches = new ArrayList<>();
        int verified = 0;

        for (TranspileRow row : rows) {
            String expected = render(row, customTemplates);

            if (expected == null) {
                verified++;
                continue;
            }

            if (expected.equals(row.renderedCode())) {
                verified++;
            } else {
                mismatches.add(new Mismatch(
                        row.id(),
                        row.name(),
                        row.targetLanguage(),
                        expected,
                        row.renderedCode()
                ));
            }
        }

        return new AuditResult(rows.size(), verified, mismatches.size(), mismatches);
    }

    /**
     * Renders the expected code for {@code row} per its {@code targetLanguage},
     * or {@code null} if the language is neither a built-in nor a custom template.
     */
    private static String render(TranspileRow row, Map<String, String> customTemplates) {
        String name = row.name();
        String val = row.val();
        String typeSpec = row.typeSpec();
        int conf = row.confidence();

        String builtin = switch (row.targetLanguage()) {
            case "DPL" -> "particle " + name + " : E<" + typeSpec + "> = \"" + val + "\" @ confidence(" + conf + ")";
            case "KOTLIN" -> "val " + name + ": " + typeSpec + "? = \"" + val + "\"";
            case "RUST" -> "let " + name + ": Option<" + typeSpec + "> = Some(\"" + val + "\".to_string());";
            case "C_CLANG" -> "const char* " + name + " = \"" + val + "\"; // Unchecked pointer";
            case "GO" -> "var " + name + " string = \"" + val + "\"";
            case "GROOVY" -> "def " + name + " = \"" + val + "\" as " + typeSpec + " // confidence(" + conf + ")";
            default -> null;
        };
        if (builtin != null) {
            return builtin;
        }
        String template = customTemplates.get(row.targetLanguage());
        if (template == null) {
            return null;
        }
        return renderTemplate(template, name, val, typeSpec, conf);
    }

    /**
     * Renders a custom template using the same placeholder convention as
     * Python's str.format: {name}, {val}, {type_spec}, {conf}.
     */
    static String renderTemplate(String template, String name, String val, String typeSpec, int conf) {
        return template
                .replace("{name}", name)
                .replace("{val}", val)
                .replace("{type_spec}", typeSpec)
                .replace("{conf}", String.valueOf(conf));
    }

    public record AuditResult(
            int total,
            int verifiedCount,
            int mismatchedCount,
            List<Mismatch> mismatches
    ) {
    }

    public record Mismatch(
            long id,
            String name,
            String targetLanguage,
            String expected,
            String actual
    ) {
    }
}
