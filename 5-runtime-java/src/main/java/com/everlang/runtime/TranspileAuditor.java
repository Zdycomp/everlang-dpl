package com.everlang.runtime;

import java.util.ArrayList;
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
 * For a row whose {@code targetLanguage} is one of the six above, the matching
 * template is re-rendered from the row's own inputs and compared byte-for-byte
 * to {@code renderedCode}; a mismatch is any difference. The value is escaped
 * first for its language, as Python's {@code VALUE_ESCAPES} does: DPL escapes
 * backslash, double quote, newline and carriage return; the other five also escape
 * {@code $} (Kotlin, Groovy), other control characters and {@code ??} (C), per
 * {@code typed.py :: escape_string}.
 *
 * <p>A row stamped with a {@code templateVersion} is a custom-language row: it
 * is re-rendered from exactly that version in {@code custom_template_versions}
 * (keyed language → version → template). If that version is absent from the
 * history, the row's provenance is broken and it is a mismatch. A non-built-in
 * row with no version (written before versioning existed) is treated as
 * verified — no rule is invented for it.
 *
 * <p>A row with a {@code valueKind} is a typed rendering ({@code SuperTranspiler.transpile_typed}):
 * see {@link TypedValueRenderer}.
 */
public final class TranspileAuditor {

    private TranspileAuditor() {
    }

    public static AuditResult audit(List<TranspileRow> rows) {
        return audit(rows, Map.of());
    }

    public static AuditResult audit(List<TranspileRow> rows,
                                    Map<String, Map<Integer, String>> customTemplateVersions) {
        List<Mismatch> mismatches = new ArrayList<>();
        int verified = 0;

        for (TranspileRow row : rows) {
            String expected = expectedFor(row, customTemplateVersions);

            if (expected == null || expected.equals(row.renderedCode())) {
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
     * Returns the expected code for {@code row}, a {@code <...>} marker that can
     * never equal real output when the custom template is missing or invalid,
     * or {@code null} when no rule applies.
     */
    private static String expectedFor(TranspileRow row, Map<String, Map<Integer, String>> customTemplateVersions) {
        String name = row.name();
        String val = row.val();
        String typeSpec = row.typeSpec();
        int conf = row.confidence();

        if (row.targetLanguage() == null || name == null || val == null || typeSpec == null) {
            // Corrupted row: report it as a mismatch rather than crash the whole audit.
            return "<null column in row " + row.id() + ">";
        }
        if (row.valueKind() != null) {
            return expectedTyped(row);
        }
        String builtin = switch (row.targetLanguage()) {
            case "DPL" -> "particle " + name + " : E<" + typeSpec + "> = \"" + escapeDplValue(val) + "\" @ confidence(" + conf + ")";
            case "KOTLIN" -> "val " + name + ": " + typeSpec + "? = \"" + escape("KOTLIN", val) + "\"";
            case "RUST" -> "let " + name + ": Option<" + typeSpec + "> = Some(\"" + escape("RUST", val) + "\".to_string());";
            case "C_CLANG" -> "const char* " + name + " = \"" + escape("C_CLANG", val) + "\"; // Unchecked pointer";
            case "GO" -> "var " + name + " string = \"" + escape("GO", val) + "\"";
            case "GROOVY" -> "def " + name + " = \"" + escape("GROOVY", val) + "\" as " + typeSpec + " // confidence(" + conf + ")";
            default -> null;
        };
        if (builtin != null) {
            return builtin;
        }
        Integer version = row.templateVersion();
        if (version == null) {
            return null;
        }
        String template = customTemplateVersions.getOrDefault(row.targetLanguage(), Map.of()).get(version);
        if (template == null) {
            return "<missing custom template " + row.targetLanguage() + " v" + version + ">";
        }
        try {
            return renderTemplate(template, name, val, typeSpec, conf);
        } catch (IllegalArgumentException e) {
            return "<invalid custom template " + row.targetLanguage() + " v" + version + ": " + e.getMessage() + ">";
        }
    }

    /**
     * A typed row: {@code val} is parsed as a DPL literal of {@code valueKind} and re-rendered
     * by {@link TypedValueRenderer}. Only built-in languages render typed values, and a typed
     * row never carries a template version, so anything else is a mismatch.
     */
    private static String expectedTyped(TranspileRow row) {
        String kind = row.valueKind();
        if (row.templateVersion() != null) {
            return "<typed row " + row.id() + " has template_version " + row.templateVersion() + ">";
        }
        List<String> items;
        try {
            items = TypedValueRenderer.parse(kind, row.val());
        } catch (IllegalArgumentException e) {
            return "<invalid " + kind + " value in row " + row.id() + ": " + e.getMessage() + ">";
        }
        String expected = TypedValueRenderer.render(row.targetLanguage(), row.name(), kind, items,
                row.typeSpec(), row.confidence());
        return expected != null ? expected
                : "<typed row " + row.id() + " for non-built-in language " + row.targetLanguage() + ">";
    }

    /**
     * Mirrors {@code typed.py :: escape_string}, which Python's {@code VALUE_ESCAPES} applies to
     * {@code {val}} in the five non-DPL built-in templates (see {@link TypedValueRenderer#escapeString}).
     */
    private static String escape(String language, String val) {
        return TypedValueRenderer.escapeString(language, val);
    }

    /**
     * Mirrors {@code super_transpiler.py :: escape_dpl_value}: backslash first,
     * then double quote, newline and carriage return, so a DPL rendering reads back through the Python frontend.
     */
    static String escapeDplValue(String val) {
        return val.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r");
    }

    /**
     * Single-pass equivalent of Python's {@code template.format(name=..., val=...,
     * type_spec=..., conf=...)} for the bare-field subset that
     * {@code validate_template} allows: substituted values are never re-scanned,
     * and {@code {{}} / {@code }}} unescape to literal braces.
     */
    static String renderTemplate(String template, String name, String val, String typeSpec, int conf) {
        StringBuilder out = new StringBuilder(template.length() + 32);
        int i = 0;
        int n = template.length();
        while (i < n) {
            char c = template.charAt(i);
            if (c == '{') {
                if (i + 1 < n && template.charAt(i + 1) == '{') {
                    out.append('{');
                    i += 2;
                    continue;
                }
                int close = template.indexOf('}', i + 1);
                if (close < 0) {
                    throw new IllegalArgumentException("unclosed '{'");
                }
                String field = template.substring(i + 1, close);
                switch (field) {
                    case "name" -> out.append(name);
                    case "val" -> out.append(val);
                    case "type_spec" -> out.append(typeSpec);
                    case "conf" -> out.append(conf);
                    default -> throw new IllegalArgumentException("unsupported placeholder {" + field + "}");
                }
                i = close + 1;
            } else if (c == '}') {
                if (i + 1 < n && template.charAt(i + 1) == '}') {
                    out.append('}');
                    i += 2;
                    continue;
                }
                throw new IllegalArgumentException("single '}'");
            } else {
                out.append(c);
                i++;
            }
        }
        return out.toString();
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
