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

class TranspileAuditIntegrationTest {

    private Path dbFile;
    private Connection conn;

    @BeforeEach
    void setUp() throws IOException, SQLException {
        dbFile = Files.createTempFile("transpile-audit-test", ".db");
        conn = DriverManager.getConnection("jdbc:sqlite:" + dbFile);

        try (Statement st = conn.createStatement()) {
            st.execute("""
                    CREATE TABLE transpilations (
                        id INTEGER,
                        name TEXT,
                        val TEXT,
                        type_spec TEXT,
                        confidence INTEGER CHECK (confidence >= 0 AND confidence <= 256),
                        target_language TEXT,
                        rendered_code TEXT,
                        created_at TEXT
                    )
                    """);

            // Clean row: DPL template rendered correctly.
            st.execute("""
                    INSERT INTO transpilations (id, name, val, type_spec, confidence, target_language, rendered_code, created_at)
                    VALUES (1, 'x', 'hello', 'String', 200, 'DPL', 'particle x : E<String> = "hello" @ confidence(200)', '2026-01-01T00:00:00')
                    """);

            // Corrupted row: rendered_code does not match the DPL template.
            st.execute("""
                    INSERT INTO transpilations (id, name, val, type_spec, confidence, target_language, rendered_code, created_at)
                    VALUES (2, 'y', 'world', 'String', 200, 'DPL', 'particle y : E<String> = "WRONG" @ confidence(200)', '2026-01-01T00:00:01')
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
    void loadTranspilationsAndAuditFindsCorruptedRow() throws SQLException {
        List<TranspileRow> rows = TranspileAudit.loadTranspilations(conn);
        TranspileAuditor.AuditResult result = TranspileAuditor.audit(rows);

        assertEquals(2, result.total());
        assertEquals(1, result.mismatchedCount());
        assertEquals(1, result.verifiedCount());
    }
}
