package com.everlang.runtime;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

/**
 * Read-only CLI entry point. Cross-checks persisted repair records in the
 * SQL archive ({@code tapestry.db}) against the documented repair formula
 * (see {@link RepairAuditor}), independently of whatever wrote them.
 *
 * This class never writes to the database: it opens a plain connection and
 * issues a single SELECT, no transaction is started.
 */
public final class SelfHealingAudit {

    private SelfHealingAudit() {
    }

    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("USAGE: SelfHealingAudit <path-to-tapestry.db>");
            System.exit(2);
            return;
        }

        String dbPath = args[0];
        List<RepairRow> rows;

        try (Connection conn = DriverManager.getConnection("jdbc:sqlite:" + dbPath)) {
            rows = loadRepairs(conn);
        } catch (SQLException e) {
            System.err.println("ERROR: " + e.getMessage());
            System.exit(2);
            return;
        }

        RepairAuditor.AuditResult result = RepairAuditor.audit(rows);

        System.out.println("TOTAL=" + result.total()
                + " VERIFIED=" + result.verifiedCount()
                + " MISMATCHED=" + result.mismatchedCount());

        for (RepairAuditor.Mismatch m : result.mismatches()) {
            System.out.println("MISMATCH id=" + m.id()
                    + " signature=" + m.failingSignature()
                    + " expected_confidence=" + m.expectedConfidence()
                    + " actual_confidence=" + m.actualConfidence()
                    + " expected_quarantined=" + m.expectedQuarantined()
                    + " actual_quarantined=" + m.actualQuarantined());
        }

        System.exit(result.mismatchedCount() == 0 ? 0 : 1);
    }

    /**
     * Reads all rows from the {@code repairs} table via a read-only SELECT.
     * Package-visible/static for direct unit/integration testing without
     * going through {@code main}.
     */
    static List<RepairRow> loadRepairs(Connection conn) throws SQLException {
        List<RepairRow> rows = new ArrayList<>();
        String sql = "SELECT id, failing_signature, error_distance, confidence, quarantined FROM repairs";
        try (PreparedStatement ps = conn.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                rows.add(new RepairRow(
                        rs.getLong("id"),
                        rs.getString("failing_signature"),
                        rs.getInt("error_distance"),
                        rs.getInt("confidence"),
                        rs.getInt("quarantined") != 0
                ));
            }
        }
        return rows;
    }
}
