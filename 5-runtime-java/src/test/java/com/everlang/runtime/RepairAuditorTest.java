package com.everlang.runtime;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RepairAuditorTest {

    @Test
    void cleanMatchingRowIsVerifiedNotMismatched() {
        // error_distance=2 -> expected confidence = 250 - 2*30 = 190, quarantined=false
        RepairRow row = new RepairRow(1L, "ParseError_01", 2, 190, false);

        RepairAuditor.AuditResult result = RepairAuditor.audit(List.of(row));

        assertEquals(1, result.total());
        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
        assertTrue(result.mismatches().isEmpty());
    }

    @Test
    void largeErrorDistanceExpectsQuarantine() {
        // error_distance=5 -> outside 1..3, expected confidence=0, quarantined=true
        RepairRow row = new RepairRow(2L, "ParseError_02", 5, 0, true);

        RepairAuditor.AuditResult result = RepairAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void corruptedConfidenceIsCaughtAsMismatch() {
        // error_distance=2 -> expected confidence=190, but stored confidence=999
        RepairRow row = new RepairRow(3L, "ParseError_03", 2, 999, false);

        RepairAuditor.AuditResult result = RepairAuditor.audit(List.of(row));

        assertEquals(1, result.total());
        assertEquals(0, result.verifiedCount());
        assertEquals(1, result.mismatchedCount());

        RepairAuditor.Mismatch mismatch = result.mismatches().get(0);
        assertEquals(3L, mismatch.id());
        assertEquals("ParseError_03", mismatch.failingSignature());
        assertEquals(190, mismatch.expectedConfidence());
        assertEquals(999, mismatch.actualConfidence());
        assertEquals(false, mismatch.expectedQuarantined());
        assertEquals(false, mismatch.actualQuarantined());
    }

    @Test
    void corruptedQuarantineFlagIsCaughtAsMismatch() {
        // error_distance=2 -> expected quarantined=false, but stored quarantined=true
        RepairRow row = new RepairRow(4L, "ParseError_04", 2, 190, true);

        RepairAuditor.AuditResult result = RepairAuditor.audit(List.of(row));

        assertEquals(1, result.mismatchedCount());
        RepairAuditor.Mismatch mismatch = result.mismatches().get(0);
        assertEquals(false, mismatch.expectedQuarantined());
        assertEquals(true, mismatch.actualQuarantined());
    }

    @Test
    void emptyListProducesZeroTotalsAndNoMismatches() {
        RepairAuditor.AuditResult result = RepairAuditor.audit(List.of());

        assertEquals(0, result.total());
        assertEquals(0, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
        assertTrue(result.mismatches().isEmpty());
    }

    @Test
    void boundaryErrorDistanceOne() {
        // error_distance=1 -> expected confidence = 250 - 1*30 = 220, quarantined=false
        RepairRow row = new RepairRow(5L, "ParseError_05", 1, 220, false);

        RepairAuditor.AuditResult result = RepairAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void boundaryErrorDistanceThree() {
        // error_distance=3 -> expected confidence = 250 - 3*30 = 160, quarantined=false
        RepairRow row = new RepairRow(6L, "ParseError_06", 3, 160, false);

        RepairAuditor.AuditResult result = RepairAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }

    @Test
    void boundaryErrorDistanceFourIsOutsideRangeAndExpectsQuarantine() {
        // error_distance=4 -> just outside 1..3, expected confidence=0, quarantined=true
        RepairRow row = new RepairRow(7L, "ParseError_07", 4, 0, true);

        RepairAuditor.AuditResult result = RepairAuditor.audit(List.of(row));

        assertEquals(1, result.verifiedCount());
        assertEquals(0, result.mismatchedCount());
    }
}
