package com.codric.ever;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Supplier;

/**
 * EverRepair.java — heal and learn for the Java runtime.
 *
 * The same process as the Python reference (scope.py / heal_order.py) and
 * the C TAC interpreter, against the same rules:
 *
 *   EVALUATE  read the primary. Confidence at or above the execute floor:
 *             keep it and stop. Otherwise it is a failure: record it as an
 *             error in the store, and note the reason and base confidence.
 *   PLAN      read the strategy (only now, as the Python reference does),
 *             then pick the first candidate fix: tied to the strategy, else
 *             a wildcard. No candidate, or one that cannot add trust
 *             (cost >= base), means the fallback.
 *   EXECUTE   run the chosen action. A repair that was chosen but cannot run
 *             gives z, never the fallback. A repaired 0 or false is a success.
 *
 * Every phase writes one trace line in the same words the Python layer uses,
 * and every outcome is written to the store's events table.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */
public final class EverRepair {

    public static final int E_INTAKE = 120;          // mirrors ever.py / tac.h

    public enum Action { KEEP, SUBSTITUTE, FALLBACK, FAILED, LEARNED }

    /* ── the trace: one line per phase, Python's wording ── */

    public static final class Trace {
        private final List<String> lines = new ArrayList<>();
        private int count = 0;

        public List<String> lines() { return Collections.unmodifiableList(lines); }

        public int count() { return count; }

        private String tag(String op, int n) { return op + "#" + n; }

        int evaluate(String op, boolean isZ, int conf, String reason, int base) {
            int n = ++count;
            String state = isZ ? "z" : "confidence " + conf + "/256";
            lines.add(tag(op, n) + " evaluate: " + state + ", reason '" + reason
                    + "', base " + base);
            return n;
        }

        void keep(String op, int n, int conf) {
            lines.add(tag(op, n) + " execute: KEEP → confidence " + conf + "/256");
        }

        void plan(String op, int n, String action, String why) {
            lines.add(tag(op, n) + " plan: " + action + " — " + why);
        }

        void finish(String op, int n, String action, int conf, String detail) {
            String tail = detail == null || detail.isEmpty() ? "" : " · " + detail;
            lines.add(tag(op, n) + " execute: " + action + " → confidence " + conf + "/256" + tail);
        }
    }

    /* ── fixtures: a repair's text, read as a value ── */

    /**
     * Reads a fixture the way the C layer reads one: true, false, z, an
     * integer, a real, or a double-quoted text. Anything else is not a value.
     * Returns null for text that is not a value (the unparsable case).
     */
    public static EParticle parseFixture(String ident, String text) {
        if (text == null) return null;
        String t = text.replaceAll("^[ \\t\\r\\n]+|[ \\t\\r\\n]+$", "");   // the C layer's whitespace
        if (t.equals("true"))  return EParticle.valued(ident, Boolean.TRUE, EParticle.CERTAIN, EParticle.Lang.EVER);
        if (t.equals("false")) return EParticle.valued(ident, Boolean.FALSE, EParticle.CERTAIN, EParticle.Lang.EVER);
        if (t.equals("z"))     return EParticle.z(ident, "fixture is z");
        if (t.length() >= 2 && t.startsWith("\"") && t.endsWith("\""))
            return EParticle.valued(ident, t.substring(1, t.length() - 1), EParticle.CERTAIN, EParticle.Lang.EVER);
        try {
            if (t.matches("-?\\d+"))
                return EParticle.valued(ident, Long.valueOf(t), EParticle.CERTAIN, EParticle.Lang.EVER);
            if (t.matches("-?\\d+\\.\\d+([eE][+-]?\\d+)?|-?\\d+[eE][+-]?\\d+"))
                return EParticle.valued(ident, Double.valueOf(t), EParticle.CERTAIN, EParticle.Lang.EVER);
        } catch (NumberFormatException ex) {
            return null;
        }
        return null;
    }

    /* ── arithmetic: the operations that produce z, with their reasons ── */

    public static EParticle div(EParticle a, EParticle b) {
        if (a.isZ()) return EParticle.z("div", a.reason());
        if (b.isZ()) return EParticle.z("div", b.reason());
        Object x = a.payload(), y = b.payload();
        if (!(x instanceof Number) || !(y instanceof Number))
            return EParticle.z("div", "division needs numbers");
        if (((Number) y).doubleValue() == 0.0)
            return EParticle.z("div", "division by zero");
        return numeric("div", (((Number) x).doubleValue()) / ((Number) y).doubleValue(),
                a.confidence(), b.confidence());
    }

    public static EParticle add(EParticle a, EParticle b) {
        if (a.isZ()) return EParticle.z("add", a.reason());
        if (b.isZ()) return EParticle.z("add", b.reason());
        Object x = a.payload(), y = b.payload();
        if (!(x instanceof Number) || !(y instanceof Number))
            return EParticle.z("add", "addition needs numbers");
        if (x instanceof Long && y instanceof Long)
            return EParticle.valued("add", (Long) x + (Long) y,
                    Math.min(a.confidence(), b.confidence()), EParticle.Lang.EVER);
        return numeric("add", ((Number) x).doubleValue() + ((Number) y).doubleValue(),
                a.confidence(), b.confidence());
    }

    private static EParticle numeric(String ident, double v, int ca, int cb) {
        return EParticle.valued(ident, v, Math.min(ca, cb), EParticle.Lang.EVER);
    }

    /* ── helpers shared by heal and learn ── */

    /** A strategy's text, or null when it is not text. */
    public static String strategyKey(EParticle s) {
        if (s == null || s.isZ()) return null;
        Object v = s.payload();
        return v instanceof String ? (String) v : null;
    }

    /** max(0, min(base, value) - cost): what a repair leaves of the value's trust. */
    public static int repairConfidence(int base, int valueConf, int cost) {
        return Math.max(0, Math.min(base, valueConf) - cost);
    }

    private static int baseOf(EParticle p) {
        return p.isZ() ? E_INTAKE : p.confidence();
    }

    /* ── heal ── */

    /**
     * heal (primary) using (strategy) fallback (fallback).
     *
     * @param ident    the name the result carries
     * @param strategy evaluated only when a repair is needed
     * @param fallback evaluated only when no repair applies
     */
    public static EParticle heal(EParticle primary, String ident,
                                 Supplier<EParticle> strategy,
                                 Supplier<EParticle> fallback,
                                 RepairStore store, String runId, Trace tr) {
        return operate("heal", primary, ident, strategy, null, fallback, store, runId, tr);
    }

    /**
     * learn (primary) using (strategy) fix (fixture): primary while it can
     * execute; otherwise the fixture, archived as the repair for the failure
     * under this strategy once the fixture itself can execute.
     *
     * @param fixtureSource the fixture as written, the text that is archived
     * @param fixture       the fixture's value
     */
    public static EParticle learn(EParticle primary, String ident,
                                  Supplier<EParticle> strategy,
                                  String fixtureSource, EParticle fixture,
                                  RepairStore store, String runId, Trace tr) {
        return operate("learn", primary, ident, strategy, fixtureSource, () -> fixture,
                store, runId, tr);
    }

    private static EParticle operate(String op, EParticle primary, String ident,
                                     Supplier<EParticle> strategy, String learnSource,
                                     Supplier<EParticle> fallbackOrFixture,
                                     RepairStore store, String runId, Trace tr) {
        try {
            return run(op, primary, ident, strategy, learnSource, fallbackOrFixture,
                    store, runId, tr);
        } catch (IOException ex) {
            throw new UncheckedIOException("repair store write failed", ex);
        }
    }

    private static EParticle run(String op, EParticle primary, String ident,
                                 Supplier<EParticle> strategy, String learnSource,
                                 Supplier<EParticle> fallbackOrFixture,
                                 RepairStore store, String runId, Trace tr)
            throws IOException {
        int conf = primary.confidence();
        boolean isZ = primary.isZ();
        boolean trusted = conf >= EParticle.EXECUTE_FLOOR;
        String reason = trusted ? "" : (isZ ? primary.reason() : "low confidence");
        int base = baseOf(primary);
        int n = tr.evaluate(op, isZ, conf, reason, base);

        if (trusted) {
            tr.keep(op, n, conf);
            store.addEvent(runId, op, ident, "", null, "KEEP", conf, conf, null, 0,
                    "");
            return primary;
        }
        store.addError(ident, reason, conf, EParticle.Lang.EVER.name(), runId);

        if (learnSource != null) return learnBody(op, n, ident, reason, conf, base,
                strategy, learnSource, fallbackOrFixture.get(), store, runId, tr);

        EParticle sv = strategy.get();
        String key = strategyKey(sv);
        String under = key != null ? " under strategy '" + key + "'" : " (strategy has no text)";
        List<RepairStore.Fix> cands = store.candidates(reason, key);

        String action, why;
        RepairStore.Fix chosen = cands.isEmpty() ? null : cands.get(0);
        if (chosen == null) {
            action = "FALLBACK";
            why = "no archived repair for '" + reason + "'" + under;
        } else if (base - chosen.cost() <= 0) {
            action = "FALLBACK";
            why = "repair costs " + chosen.cost() + " against base " + base
                    + ": it cannot add trust";
        } else {
            action = "SUBSTITUTE";
            why = "archived fixture '" + chosen.fixture + "', cost " + chosen.cost() + under;
        }
        tr.plan(op, n, action, why);

        if (chosen == null || base - chosen.cost() <= 0) {
            EParticle fb = fallbackOrFixture.get();
            int fconf = fb.confidence();
            tr.finish(op, n, "FALLBACK", fconf, why);
            store.addEvent(runId, op, ident, reason, key, "FALLBACK", conf, fconf,
                    null, chosen == null ? 0 : chosen.cost(), why);
            return fb;
        }

        int cost = chosen.cost();
        EParticle value = parseFixture(ident, chosen.fixture);
        String failed = null;
        if (value == null) failed = "archived fixture unparsable";
        else if (value.isZ()) failed = "archived fixture evaluated to z";
        int out = failed == null ? repairConfidence(base, value.confidence(), cost) : 0;
        if (failed == null && out <= 0) failed = "repair left no confidence";
        if (failed != null) {
            tr.finish(op, n, "FAILED", 0, failed);
            store.addEvent(runId, op, ident, reason, key, "FAILED", conf, 0,
                    chosen.fixture, cost, failed);
            return EParticle.z(ident, failed);
        }
        tr.finish(op, n, "SUBSTITUTE", out, why);
        store.addEvent(runId, op, ident, reason, key, "SUBSTITUTE", conf, out,
                chosen.fixture, cost, why);
        return EParticle.valued(ident, value.payload(), out, EParticle.Lang.EVER);
    }

    private static EParticle learnBody(String op, int n, String ident, String reason,
                                       int conf, int base, Supplier<EParticle> strategy,
                                       String source, EParticle fixture,
                                       RepairStore store, String runId, Trace tr)
            throws IOException {
        int fconf = fixture.confidence();
        String action, detail;
        String key = null;
        if (fixture.isZ()) {
            // a fixture that is z repairs nothing: the repair failed
            String why = "fixture evaluated to z; nothing archived";
            tr.finish(op, n, "FAILED", 0, why);
            store.addEvent(runId, op, ident, reason, null, "FAILED", conf, 0, source, 0, why);
            return EParticle.z(ident, why);
        }
        if (fconf >= EParticle.EXECUTE_FLOOR) {
            key = strategyKey(strategy.get());
            if (key == null) {
                action = "SUBSTITUTE";
                detail = "not archived: strategy must be text";
            } else {
                store.addFix(reason, source, RepairStore.KIND_PLAIN, key, "learned",
                        "learned by " + op + " at " + ident);
                action = "LEARNED";
                detail = "archived '" + source + "' for strategy '" + key + "'";
            }
        } else {
            action = "SUBSTITUTE";
            detail = "not archived: fixture confidence " + fconf + " below the floor";
        }
        int out = Math.min(base, fconf);
        tr.finish(op, n, action, out, detail);
        store.addEvent(runId, op, ident, reason, key, action, conf, out, source, 0, detail);
        return EParticle.valued(ident, fixture.payload(), out, EParticle.Lang.EVER);
    }

    /* ── design ── */

    /** The verdict on one designed fix. */
    public static final class Verdict {
        public final boolean accepted;
        public final String reason;
        public final RepairStore.Fix fix;

        Verdict(boolean accepted, String reason, RepairStore.Fix fix) {
            this.accepted = accepted; this.reason = reason; this.fix = fix;
        }
    }

    /**
     * Design a fix for a failure reason. The fixture must read as a value
     * (not z, not unparsable), the kind must be 0 or 1, and an identical fix
     * must not already be held. Accepted fixes are stored with origin
     * "designed"; every verdict, accepted or not, is an event.
     *
     * @param strategy the strategy it is tied to, or null for a wildcard
     */
    public static Verdict design(RepairStore store, String runId, String failure,
                                 String strategy, String fixture, int kind, String note) {
        try {
            String rejected = null;
            if (failure == null || failure.trim().isEmpty())
                rejected = "a design needs a failure reason";
            else if (fixture == null || fixture.trim().isEmpty())
                rejected = "a design needs a fixture";
            else if (kind != RepairStore.KIND_PLAIN && kind != RepairStore.KIND_INFERRED)
                rejected = "kind must be 0 or 1";
            EParticle value = rejected == null ? parseFixture("design", fixture) : null;
            if (rejected == null && value == null)
                rejected = "fixture does not read as a value";
            if (rejected == null && value.isZ())
                rejected = "a fixture that is z repairs nothing";
            RepairStore.Fix fix = null;
            if (rejected == null) {
                fix = store.addFix(failure, fixture, kind, strategy, "designed", note);
                if (fix == null) rejected = "an identical fix is already held";
            }
            boolean ok = rejected == null;
            String f = failure == null ? "" : failure;
            store.addEvent(runId, "design", f, f, strategy,
                    ok ? "ACCEPTED" : "REJECTED", 0, 0,
                    fixture, kind == RepairStore.KIND_PLAIN ? RepairStore.E_REPAIR_PLAIN
                            : RepairStore.E_REPAIR_INFERRED,
                    ok ? "designed fix stored" : rejected);
            return new Verdict(ok, ok ? "designed fix stored" : rejected, fix);
        } catch (IOException ex) {
            throw new UncheckedIOException("repair store write failed", ex);
        }
    }

    private EverRepair() {}
}
