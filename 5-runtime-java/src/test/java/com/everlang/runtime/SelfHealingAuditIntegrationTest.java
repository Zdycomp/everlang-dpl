package com.everlang.runtime;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SelfHealingAuditIntegrationTest {

    private Path dbFile;
    private Connection conn;

    @BeforeEach
    void setUp() throws IOException, SQLException {
        dbFile = Files.createTempFile("self-healing-audit-test", ".db");
        conn = DriverManager.getConnection("jdbc:sqlite:" + dbFile);

        try (Statement st = conn.createStatement()) {
            st.execute("""
                    CREATE TABLE repairs (
                        id INTEGER,
                        failing_signature TEXT,
                        error_distance INTEGER,
                        repaired_value TEXT,
                        confidence INTEGER,
                        quarantined INTEGER,
                        created_at TEXT
                    )
                    """);

            // Clean row: error_distance=2 -> confidence=190, quarantined=0
            st.execute("""
                    INSERT INTO repairs (id, failing_signature, error_distance, repaired_value, confidence, quarantined, created_at)
                    VALUES (1, 'ParseError_01', 2, 'EmulatedPattern<ParseError_01>', 190, 0, '2026-01-01T00:00:00')
                    """);

            // Corrupted row: error_distance=2 should be confidence=190/quarantined=0, but stored wrong.
            st.execute("""
                    INSERT INTO repairs (id, failing_signature, error_distance, repaired_value, confidence, quarantined, created_at)
                    VALUES (2, 'ParseError_02', 2, 'EmulatedPattern<ParseError_02>', 999, 1, '2026-01-01T00:00:01')
                    """);
        }
    }

    @AfterEach
    void tearDown() throws SQLException, IOException {
        if (conn != null) {
            conn.close();
        }
        Files.deleteIfExists(dbFile);
    }

    @Test
    void loadRepairsAndAuditFindsCorruptedRow() throws SQLException {
        List<RepairRow> rows = SelfHealingAudit.loadRepairs(conn);
        RepairAuditor.AuditResult result = RepairAuditor.audit(rows);

        assertEquals(2, result.total());
        assertEquals(1, result.mismatchedCount());
        assertEquals(1, result.verifiedCount());
    }
}
