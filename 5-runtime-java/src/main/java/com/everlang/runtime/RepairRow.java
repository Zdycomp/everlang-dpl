package com.everlang.runtime;

/**
 * Immutable representation of one row of the {@code repairs} table in the
 * SQL archive (schema owned by the archive-sql phase):
 *
 * <pre>
 * CREATE TABLE repairs (
 *   id INTEGER,
 *   failing_signature TEXT,
 *   error_distance INTEGER,
 *   repaired_value TEXT,
 *   confidence INTEGER,
 *   quarantined INTEGER, -- 0 or 1
 *   created_at TEXT
 * );
 * </pre>
 *
 * Only the columns needed for auditing are carried here; {@code repaired_value}
 * and {@code created_at} are not required by the audit rule.
 */
public record RepairRow(
        long id,
        String failingSignature,
        int errorDistance,
        int confidence,
        boolean quarantined
) {
}
