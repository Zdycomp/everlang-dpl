package com.everlang.runtime;

import java.sql.*;
import java.util.*;

/**
 * Read-only genomics audit: verifies sequence match integrity.
 * 
 * For each recorded match, recalculates confidence independently and
 * flags drift from stored values. Contract-enforcing auditor pattern.
 */
public class GenomicsAudit {

    private final Connection db;
    private int total_audited = 0;
    private int total_drift = 0;

    public GenomicsAudit(Connection db) {
        this.db = db;
    }

    /**
     * Audit all recorded sequence matches: verify confidence formula.
     * Formula (must match Python SequenceQueryEngine):
     *   confidence = min(256, 128 + (coverage * 100) + min(50, hit_count * 2))
     */
    public void auditAllMatches() throws SQLException {
        String query = """
            SELECT sm.id, sm.coverage, sm.kmer_matches, sm.confidence
            FROM sequence_matches sm
            """;

        try (Statement stmt = db.createStatement();
             ResultSet rs = stmt.executeQuery(query)) {

            while (rs.next()) {
                int id = rs.getInt("id");
                double coverage = rs.getDouble("coverage");
                int hit_count = rs.getInt("kmer_matches");
                int stored_confidence = rs.getInt("confidence");

                int computed_confidence = computeConfidence(coverage, hit_count);

                total_audited++;
                if (computed_confidence != stored_confidence) {
                    total_drift++;
                    System.out.printf("DRIFT: match_id=%d stored=%d computed=%d\n",
                        id, stored_confidence, computed_confidence);
                }
            }
        }
    }

    /**
     * Audit k-mer index metadata: verify statistical constraints.
     */
    public void auditIndices() throws SQLException {
        String query = """
            SELECT id, index_id, kmer_size, unique_kmers, total_kmers
            FROM kmer_indices
            """;

        try (Statement stmt = db.createStatement();
             ResultSet rs = stmt.executeQuery(query)) {

            while (rs.next()) {
                int id = rs.getInt("id");
                String index_id = rs.getString("index_id");
                int kmer_size = rs.getInt("kmer_size");
                int unique_kmers = rs.getInt("unique_kmers");
                int total_kmers = rs.getInt("total_kmers");

                List<String> errors = new ArrayList<>();

                if (kmer_size != 11) {
                    errors.add(String.format("kmer_size=%d (must be 11)", kmer_size));
                }
                if (unique_kmers <= 0) {
                    errors.add("unique_kmers<=0");
                }
                if (total_kmers < unique_kmers) {
                    errors.add(String.format("total_kmers=%d < unique_kmers=%d",
                        total_kmers, unique_kmers));
                }

                if (!errors.isEmpty()) {
                    total_drift++;
                    System.out.printf("INVALID_INDEX: %s errors=[%s]\n",
                        index_id, String.join(", ", errors));
                }
            }
        }
    }

    /**
     * Verify match strength classification matches coverage.
     * exact: ≥0.95, high: ≥0.85, medium: ≥0.70, low: <0.70
     */
    public void auditMatchStrength() throws SQLException {
        String query = """
            SELECT id, coverage, match_strength FROM sequence_matches
            """;

        try (Statement stmt = db.createStatement();
             ResultSet rs = stmt.executeQuery(query)) {

            while (rs.next()) {
                int id = rs.getInt("id");
                double coverage = rs.getDouble("coverage");
                String strength = rs.getString("match_strength");

                String expected = classifyMatch(coverage);
                if (!strength.equals(expected)) {
                    total_drift++;
                    System.out.printf("STRENGTH_MISMATCH: match_id=%d coverage=%.2f stored=%s expected=%s\n",
                        id, coverage, strength, expected);
                }
            }
        }
    }

    private int computeConfidence(double coverage, int hit_count) {
        int base = (int)(128 + (coverage * 100));
        int bonus = Math.min(50, hit_count * 2);
        return Math.min(256, Math.max(0, base + bonus));
    }

    private String classifyMatch(double coverage) {
        if (coverage >= 0.95) return "exact";
        if (coverage >= 0.85) return "high";
        if (coverage >= 0.70) return "medium";
        return "low";
    }

    public void printReport() {
        System.out.println("\n" + "=".repeat(70));
        System.out.println("  GENOMICS AUDIT REPORT");
        System.out.println("=".repeat(70));
        System.out.printf("Total matches audited: %d\n", total_audited);
        System.out.printf("Drift detections:     %d\n", total_drift);
        System.out.printf("Status: %s\n", total_drift == 0 ? "PASS" : "FAIL");
        System.out.println("=".repeat(70));
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("Usage: GenomicsAudit <db_path>");
            System.exit(1);
        }

        String dbPath = args[0];
        String url = "jdbc:sqlite:" + dbPath;

        try (Connection conn = DriverManager.getConnection(url)) {
            GenomicsAudit audit = new GenomicsAudit(conn);
            audit.auditIndices();
            audit.auditAllMatches();
            audit.auditMatchStrength();
            audit.printReport();

            System.exit(audit.total_drift == 0 ? 0 : 1);
        }
    }
}
