package com.everlang.runtime;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Read-only CLI entry point. Cross-checks persisted transpilation records in
 * the SQL archive ({@code tapestry.db}) against the documented language
 * templates (see {@link TranspileAuditor}), independently of whatever wrote
 * them.
 *
 * This class never writes to the database: it opens a plain connection and
 * issues a single SELECT, no transaction is started.
 *
 * Not wired as the jar's default Main-Class (that remains
 * {@link SelfHealingAudit}); invoke via the fully-qualified classpath:
 * {@code java -cp target/self-healing-runtime.jar com.everlang.runtime.TranspileAudit <db>}.
 */
public final class TranspileAudit {

    private TranspileAudit() {
    }

    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("USAGE: TranspileAudit <path-to-tapestry.db>");
            System.exit(2);
            return;
        }

        String dbPath = args[0];
        List<TranspileRow> rows;

        Map<String, Map<Integer, String>> customTemplates;

        try (Connection conn = DriverManager.getConnection("jdbc:sqlite:" + dbPath)) {
            rows = loadTranspilations(conn);
            customTemplates = loadCustomTemplates(conn);
        } catch (SQLException e) {
            System.err.println("ERROR: " + e.getMessage());
            System.exit(2);
            return;
        }

        TranspileAuditor.AuditResult result = TranspileAuditor.audit(rows, customTemplates);

        System.out.println("TOTAL=" + result.total()
                + " VERIFIED=" + result.verifiedCount()
                + " MISMATCHED=" + result.mismatchedCount());

        for (TranspileAuditor.Mismatch m : result.mismatches()) {
            System.out.println("MISMATCH id=" + m.id()
                    + " name=" + m.name()
                    + " target_language=" + m.targetLanguage()
                    + " expected=" + m.expected()
                    + " actual=" + m.actual());
        }

        System.exit(result.mismatchedCount() == 0 ? 0 : 1);
    }

    /**
     * Reads every version — active and retired — from
     * {@code custom_template_versions} as language → version → template.
     * Retired versions are required to audit rows archived before a template
     * was edited. Returns an empty map if the table does not exist (older DBs);
     * any other read failure propagates, so {@code main} exits 2 rather than
     * reporting every versioned row as a false mismatch.
     */
    static Map<String, Map<Integer, String>> loadCustomTemplates(Connection conn) throws SQLException {
        Map<String, Map<Integer, String>> templates = new HashMap<>();
        if (!hasTable(conn, "custom_template_versions")) {
            return templates;
        }
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT language, version, template FROM custom_template_versions");
             ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                templates.computeIfAbsent(rs.getString("language"), k -> new HashMap<>())
                        .put(rs.getInt("version"), rs.getString("template"));
            }
        }
        return templates;
    }

    /**
     * Reads all rows from the {@code transpilations} table via a read-only
     * SELECT. Package-visible/static for direct unit/integration testing
     * without going through {@code main}. Databases created before
     * {@code template_version} or {@code value_kind} existed load with nulls.
     */
    static List<TranspileRow> loadTranspilations(Connection conn) throws SQLException {
        List<TranspileRow> rows = new ArrayList<>();
        boolean versioned = hasColumn(conn, "transpilations", "template_version");
        boolean typed = hasColumn(conn, "transpilations", "value_kind");
        String sql = "SELECT id, name, val, type_spec, confidence, target_language, rendered_code"
                + (versioned ? ", template_version" : "")
                + (typed ? ", value_kind" : "")
                + " FROM transpilations";
        try (PreparedStatement ps = conn.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                Integer version = null;
                if (versioned) {
                    int v = rs.getInt("template_version");
                    version = rs.wasNull() ? null : v;
                }
                rows.add(new TranspileRow(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getString("val"),
                        rs.getString("type_spec"),
                        rs.getInt("confidence"),
                        rs.getString("target_language"),
                        rs.getString("rendered_code"),
                        version,
                        typed ? rs.getString("value_kind") : null
                ));
            }
        }
        return rows;
    }

    private static boolean hasTable(Connection conn, String table) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?")) {
            ps.setString(1, table);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next();
            }
        }
    }

    private static boolean hasColumn(Connection conn, String table, String column) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT 1 FROM pragma_table_info(?) WHERE name=?")) {
            ps.setString(1, table);
            ps.setString(2, column);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next();
            }
        }
    }
}
