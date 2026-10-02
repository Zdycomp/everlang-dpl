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

        Map<String, String> customTemplates;

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
     * Reads all custom language templates from the {@code custom_templates}
     * table. Returns an empty map if the table does not exist (pre-upgrade DBs).
     */
    static Map<String, String> loadCustomTemplates(Connection conn) {
        Map<String, String> templates = new HashMap<>();
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT language, template FROM custom_templates");
             ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                templates.put(rs.getString("language"), rs.getString("template"));
            }
        } catch (SQLException e) {
            // Table may not exist in older DBs — that's fine, no custom templates.
        }
        return templates;
    }

    /**
     * Reads all rows from the {@code transpilations} table via a read-only
     * SELECT. Package-visible/static for direct unit/integration testing
     * without going through {@code main}.
     */
    static List<TranspileRow> loadTranspilations(Connection conn) throws SQLException {
        List<TranspileRow> rows = new ArrayList<>();
        String sql = "SELECT id, name, val, type_spec, confidence, target_language, rendered_code FROM transpilations";
        try (PreparedStatement ps = conn.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                rows.add(new TranspileRow(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getString("val"),
                        rs.getString("type_spec"),
                        rs.getInt("confidence"),
                        rs.getString("target_language"),
                        rs.getString("rendered_code")
                ));
            }
        }
        return rows;
    }
}
