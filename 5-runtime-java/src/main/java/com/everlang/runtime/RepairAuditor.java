package com.everlang.runtime;

import java.util.ArrayList;
import java.util.List;

/**
 * Pure (no JDBC, no I/O) re-derivation of the expected repair outcome for a
 * {@link RepairRow}, mirroring the Python source of truth:
 *
 * {@code everlang_standalone/everlang/core/archive.py :: EArchive.emulate_repair}
 *
 * <pre>
 * def emulate_repair(self, failing_signature, error_distance):
 *     if 1 &lt;= error_distance &lt;= 3:
 *         borrowed_conf = 250 - (error_distance * 30)
 *         return EParticle(f"EmulatedPattern&lt;{failing_signature}&gt;", borrowed_conf)
 *     return EParticle("Quarantined(Z)", 0)
 * </pre>
 *
 * This class does not invent any additional rule: if {@code 1 <= errorDistance <= 3}
 * the expected confidence is {@code 250 - errorDistance * 30} and the row is
 * expected to NOT be quarantined; otherwise the expected confidence is
 * {@code 0} and the row is expected to be quarantined.
 */
public final class RepairAuditor {

    private RepairAuditor() {
    }

    public static AuditResult audit(List<RepairRow> rows) {
        List<Mismatch> mismatches = new ArrayList<>();
        int verified = 0;

        for (RepairRow row : rows) {
            int expectedConfidence;
            boolean expectedQuarantined;
            if (row.errorDistance() >= 1 && row.errorDistance() <= 3) {
                expectedConfidence = 250 - (row.errorDistance() * 30);
                expectedQuarantined = false;
            } else {
                expectedConfidence = 0;
                expectedQuarantined = true;
            }

            boolean matches = expectedConfidence == row.confidence()
                    && expectedQuarantined == row.quarantined();

            if (matches) {
                verified++;
            } else {
                mismatches.add(new Mismatch(
                        row.id(),
                        row.failingSignature(),
                        expectedConfidence,
                        row.confidence(),
                        expectedQuarantined,
                        row.quarantined()
                ));
            }
        }

        return new AuditResult(rows.size(), verified, mismatches.size(), mismatches);
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
            String failingSignature,
            int expectedConfidence,
            int actualConfidence,
            boolean expectedQuarantined,
            boolean actualQuarantined
    ) {
    }
}
