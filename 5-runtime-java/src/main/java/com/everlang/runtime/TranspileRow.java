package com.everlang.runtime;

/**
 * Immutable representation of one row of the {@code transpilations} table in
 * the SQL archive (schema owned by the archive-sql phase):
 *
 * <pre>
 * CREATE TABLE transpilations (
 *   id INTEGER,
 *   name TEXT,
 *   val TEXT,
 *   type_spec TEXT,
 *   confidence INTEGER, -- the only CHECK-constrained column
 *   target_language TEXT,
 *   rendered_code TEXT,
 *   created_at TEXT,
 *   template_version INTEGER -- NULL for built-in languages and pre-versioning rows
 * );
 * </pre>
 *
 * Only the columns needed for auditing are carried here; {@code created_at}
 * is not required by the audit rule.
 */
public record TranspileRow(
        long id,
        String name,
        String val,
        String typeSpec,
        int confidence,
        String targetLanguage,
        String renderedCode,
        Integer templateVersion
) {
    public TranspileRow(long id, String name, String val, String typeSpec, int confidence,
                        String targetLanguage, String renderedCode) {
        this(id, name, val, typeSpec, confidence, targetLanguage, renderedCode, null);
    }
}
