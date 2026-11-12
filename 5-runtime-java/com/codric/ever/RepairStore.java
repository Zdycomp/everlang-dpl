package com.codric.ever;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * RepairStore.java — the runtime's repair registry, kept as a database.
 *
 * Three tables, one JSONL file each, in one directory:
 *
 *   repairs.jsonl   fixes: a failure reason, the fixture that repairs it,
 *                   the kind (cost), the strategy it is tied to (or none,
 *                   a wildcard), and where it came from. The same file the
 *                   ReFix archive and the Python registry read.
 *   errors.jsonl    every failure the repair operator was asked to heal.
 *                   The ReFix error shape (message, fingerprint, source),
 *                   so ReFix reads them too.
 *   events.jsonl    every heal or learn outcome: what was evaluated, what
 *                   was planned, what was executed, with confidences in and
 *                   out. The full history of the repair process.
 *
 * Every write is appended before the call returns, so a crash loses at most
 * the call in flight. A memory-only store (dir == null) keeps the same
 * tables without touching disk. Malformed lines are skipped and reported in
 * warnings(), never raised, the way the Python registry does it.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */
public final class RepairStore {

    public static final String REPAIRS = "repairs.jsonl";
    public static final String ERRORS  = "errors.jsonl";
    public static final String EVENTS  = "events.jsonl";

    public static final int KIND_PLAIN = 0;
    public static final int KIND_INFERRED = 1;
    public static final int E_REPAIR_PLAIN = 8;      // mirrors repair.py
    public static final int E_REPAIR_INFERRED = 32;  // mirrors repair.py

    /* ── records ── */

    /** A fix. strategy == null is a wildcard: it matches any strategy. */
    public static final class Fix {
        public final String id, failure, fixture, strategy, origin, note;
        public final int kind;
        public final long createdMs;

        Fix(String id, String failure, String fixture, int kind, String strategy,
            String origin, long createdMs, String note) {
            this.id = id; this.failure = failure; this.fixture = fixture;
            this.kind = kind; this.strategy = strategy; this.origin = origin;
            this.createdMs = createdMs; this.note = note;
        }

        public int cost() { return kind == KIND_PLAIN ? E_REPAIR_PLAIN : E_REPAIR_INFERRED; }

        public boolean wildcard() { return strategy == null; }

        Map<String, Object> toJson() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("v", 1L);
            m.put("id", id);
            m.put("failure_text", failure);
            m.put("fixture_text", fixture);
            m.put("kind", (long) kind);
            if (strategy != null) m.put("strategy", strategy);
            m.put("origin", origin);
            m.put("created_ms", createdMs);
            m.put("note", note);
            return m;
        }
    }

    /** A failure the operator was asked to heal. */
    public static final class Error {
        public final String id, reason, ident, fingerprint, lang, runId;
        public final int confidence;
        public final long capturedMs;

        Error(String id, String reason, String ident, int confidence, String lang,
              String runId, long capturedMs, String fingerprint) {
            this.id = id; this.reason = reason; this.ident = ident;
            this.confidence = confidence; this.lang = lang; this.runId = runId;
            this.capturedMs = capturedMs; this.fingerprint = fingerprint;
        }

        Map<String, Object> toJson() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("v", 1L);
            m.put("error_id", id);
            m.put("captured_ms", capturedMs);
            m.put("run_id", runId);
            m.put("lang", lang);
            m.put("source_ident", ident);
            m.put("stage", "runtime");
            m.put("message", reason);
            m.put("context", "");
            m.put("fingerprint", fingerprint);
            m.put("confidence", (long) confidence);
            return m;
        }
    }

    /** One heal or learn outcome. */
    public static final class Event {
        public final String id, runId, op, ident, reason, strategy, action,
                fixture, detail;
        public final int confIn, confOut, cost;
        public final long tsMs;

        Event(String id, String runId, String op, String ident, String reason,
              String strategy, String action, int confIn, int confOut,
              String fixture, int cost, String detail, long tsMs) {
            this.id = id; this.runId = runId; this.op = op; this.ident = ident;
            this.reason = reason; this.strategy = strategy; this.action = action;
            this.confIn = confIn; this.confOut = confOut; this.fixture = fixture;
            this.cost = cost; this.detail = detail; this.tsMs = tsMs;
        }

        Map<String, Object> toJson() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("v", 1L);
            m.put("event_id", id);
            m.put("ts_ms", tsMs);
            m.put("run_id", runId);
            m.put("op", op);
            m.put("ident", ident);
            m.put("reason", reason);
            m.put("strategy", strategy);
            m.put("action", action);
            m.put("conf_in", (long) confIn);
            m.put("conf_out", (long) confOut);
            m.put("fixture", fixture);
            m.put("cost", (long) cost);
            m.put("detail", detail);
            return m;
        }
    }

    /* ── state ── */

    private final Path dir;                         // null: memory only
    private final List<Fix> fixes = new ArrayList<>();
    private final List<Error> errors = new ArrayList<>();
    private final List<Event> events = new ArrayList<>();
    private final List<String> warnings = new ArrayList<>();
    private long seq = 0;

    private RepairStore(Path dir) { this.dir = dir; }

    /** A store that lives only in memory. */
    public static RepairStore memory() { return new RepairStore(null); }

    /** A store in a directory, created if missing. Existing tables are loaded. */
    public static RepairStore open(Path dir) throws IOException {
        Files.createDirectories(dir);
        RepairStore s = new RepairStore(dir);
        s.load(dir.resolve(REPAIRS), s::loadFix);
        s.load(dir.resolve(ERRORS), s::loadError);
        s.load(dir.resolve(EVENTS), s::loadEvent);
        return s;
    }

    public Path dir() { return dir; }

    public synchronized List<String> warnings() { return new ArrayList<>(warnings); }

    /* ── reads: full access to the data ── */

    public synchronized List<Fix> fixes() { return new ArrayList<>(fixes); }
    public synchronized List<Error> errors() { return new ArrayList<>(errors); }
    public synchronized List<Event> events() { return new ArrayList<>(events); }

    /**
     * The fixes that could repair a reason under a strategy, in the order the
     * plan tries them: tied to this strategy first, then wildcards. A null key
     * (a strategy with no text) yields wildcards only.
     */
    public synchronized List<Fix> candidates(String reason, String strategyKey) {
        List<Fix> tied = new ArrayList<>(), wild = new ArrayList<>();
        for (Fix f : fixes) {
            if (!f.failure.equals(reason)) continue;
            if (f.strategy == null) wild.add(f);
            else if (strategyKey != null && f.strategy.equals(strategyKey)) tied.add(f);
        }
        tied.addAll(wild);
        return tied;
    }

    /** Errors whose reason no fix repairs yet: the design targets. */
    public synchronized List<Error> openErrors() {
        List<Error> open = new ArrayList<>();
        for (Error e : errors) {
            boolean fixed = false;
            for (Fix f : fixes) if (f.failure.equals(e.reason)) { fixed = true; break; }
            if (!fixed) open.add(e);
        }
        return open;
    }

    /** Count of events per action. */
    public synchronized Map<String, Integer> outcomeCounts() {
        Map<String, Integer> c = new TreeMap<>();
        for (Event e : events) c.merge(e.action, 1, Integer::sum);
        return c;
    }

    /** Count of errors per reason. */
    public synchronized Map<String, Integer> errorCounts() {
        Map<String, Integer> c = new TreeMap<>();
        for (Error e : errors) c.merge(e.reason, 1, Integer::sum);
        return c;
    }

    /* ── writes ── */

    /** Record a fix unless an identical one (same failure, fixture, kind and
     *  strategy) is already held. Returns the stored fix, or null if it was a duplicate. */
    public synchronized Fix addFix(String failure, String fixture, int kind,
                                   String strategy, String origin, String note)
            throws IOException {
        if (failure == null || failure.isEmpty())
            throw new IllegalArgumentException("a fix needs a failure reason");
        if (fixture == null || fixture.isEmpty())
            throw new IllegalArgumentException("a fix needs a fixture");
        if (kind != KIND_PLAIN && kind != KIND_INFERRED)
            throw new IllegalArgumentException("kind must be 0 or 1, got " + kind);
        for (Fix f : fixes)
            if (f.failure.equals(failure) && f.fixture.equals(fixture)
                    && f.kind == kind && eq(f.strategy, strategy)) return null;
        Fix f = new Fix(newId("fix"), failure, fixture, kind, strategy, origin,
                System.currentTimeMillis(), note == null ? "" : note);
        fixes.add(f);
        append(REPAIRS, f.toJson());
        return f;
    }

    public synchronized Error addError(String ident, String reason, int confidence,
                                       String lang, String runId) throws IOException {
        Error e = new Error(newId("err"), reason, ident, confidence, lang, runId,
                System.currentTimeMillis(), fingerprint(reason));
        errors.add(e);
        append(ERRORS, e.toJson());
        return e;
    }

    public synchronized Event addEvent(String runId, String op, String ident,
                                       String reason, String strategy, String action,
                                       int confIn, int confOut, String fixture,
                                       int cost, String detail) throws IOException {
        Event e = new Event(newId("evt"), runId, op, ident, reason, strategy, action,
                confIn, confOut, fixture, cost, detail, System.currentTimeMillis());
        events.add(e);
        append(EVENTS, e.toJson());
        return e;
    }

    /* ── internals ── */

    private interface LineLoader { void load(Map<String, Object> rec, int line) throws IllegalArgumentException; }

    private void load(Path file, LineLoader loader) throws IOException {
        if (!Files.exists(file)) return;
        List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            if (line.trim().isEmpty()) continue;
            try {
                loader.load(EverJson.object(line), i + 1);
            } catch (IllegalArgumentException ex) {
                warnings.add(file.getFileName() + ":" + (i + 1) + ": " + ex.getMessage());
            }
        }
    }

    private void loadFix(Map<String, Object> r, int line) {
        Object failure = r.get("failure_text"), fixture = r.get("fixture_text");
        if (!(failure instanceof String) || !(fixture instanceof String))
            throw new IllegalArgumentException("a fix needs failure_text and fixture_text");
        int kind = intOf(r.get("kind"), KIND_PLAIN);
        if (kind != KIND_PLAIN && kind != KIND_INFERRED)
            throw new IllegalArgumentException("kind must be 0 or 1");
        Object strategy = r.get("strategy");
        if (strategy != null && !(strategy instanceof String))
            throw new IllegalArgumentException("strategy must be text or absent");
        Object origin = r.get("origin");
        Object note = r.get("note");
        fixes.add(new Fix(stringOf(r.get("id"), "legacy-fix-" + line),
                (String) failure, (String) fixture, kind, (String) strategy,
                origin instanceof String ? (String) origin : "archive",
                longOf(r.get("created_ms"), 0L),
                note instanceof String ? (String) note : ""));
    }

    private void loadError(Map<String, Object> r, int line) {
        Object msg = r.get("message");
        if (!(msg instanceof String) || ((String) msg).isEmpty())
            throw new IllegalArgumentException("an error needs a message");
        String reason = (String) msg;
        errors.add(new Error(stringOf(r.get("error_id"), "legacy-err-" + line),
                reason, stringOf(r.get("source_ident"), ""),
                intOf(r.get("confidence"), 0), stringOf(r.get("lang"), ""),
                stringOf(r.get("run_id"), ""), longOf(r.get("captured_ms"), 0L),
                stringOf(r.get("fingerprint"), fingerprint(reason))));
    }

    private void loadEvent(Map<String, Object> r, int line) {
        Object action = r.get("action");
        if (!(action instanceof String))
            throw new IllegalArgumentException("an event needs an action");
        events.add(new Event(stringOf(r.get("event_id"), "legacy-evt-" + line),
                stringOf(r.get("run_id"), ""), stringOf(r.get("op"), ""),
                stringOf(r.get("ident"), ""), stringOf(r.get("reason"), ""),
                nullableString(r.get("strategy")), (String) action,
                intOf(r.get("conf_in"), 0), intOf(r.get("conf_out"), 0),
                nullableString(r.get("fixture")), intOf(r.get("cost"), 0),
                stringOf(r.get("detail"), ""), longOf(r.get("ts_ms"), 0L)));
    }

    private void append(String table, Map<String, Object> record) throws IOException {
        if (dir == null) return;
        Files.write(dir.resolve(table),
                (EverJson.write(record) + "\n").getBytes(StandardCharsets.UTF_8),
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    private String newId(String prefix) {
        return prefix + "-" + Long.toHexString(System.currentTimeMillis())
                + "-" + (++seq);
    }

    /** SHA-256 of the reason, first 16 hex digits: the grouping key for errors. */
    public static String fingerprint(String reason) {
        try {
            byte[] d = MessageDigest.getInstance("SHA-256")
                    .digest(reason.getBytes(StandardCharsets.UTF_8));
            StringBuilder b = new StringBuilder();
            for (int i = 0; i < 8; i++) b.append(String.format("%02x", d[i]));
            return b.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static boolean eq(String a, String b) {
        return a == null ? b == null : a.equals(b);
    }

    private static String stringOf(Object v, String dflt) {
        return v instanceof String ? (String) v : dflt;
    }

    private static String nullableString(Object v) {
        return v instanceof String ? (String) v : null;
    }

    private static int intOf(Object v, int dflt) {
        return v instanceof Long ? (int) (long) (Long) v
             : v instanceof Double ? (int) (double) (Double) v : dflt;
    }

    private static long longOf(Object v, long dflt) {
        return v instanceof Long ? (Long) v
             : v instanceof Double ? (long) (double) (Double) v : dflt;
    }
}
