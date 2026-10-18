package com.codric.ever;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * RepairSuite.java — the repair suite: full access to every heal and repair
 * record, and the scenarios that check the process end to end.
 *
 * Commands (the default is run):
 *
 *   run                              the scenario suite, on a fresh store
 *   summary   <dir>                  counts for every table and outcome
 *   errors    <dir>                  every recorded failure
 *   fixes     <dir>                  every fix, with origin, kind, strategy
 *   events    <dir>                  every heal, learn and design outcome
 *   open      <dir>                  errors that no fix repairs yet
 *   verify    <dir>                  integrity of the store's data
 *   design    <dir> <failure> <strategy|-> <fixture> <kind> [note]
 *   export    <dir> <file>           every table, as one JSON document
 *
 * Exit status is 0 when the suite passes or a command succeeds, 1 otherwise.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */
public final class RepairSuite {

    static int passed = 0, failed = 0;

    static void ok(String name, boolean cond) {
        if (cond) { passed++; System.out.println("  ✓ " + name); }
        else      { failed++; System.out.println("  ✗ " + name); }
    }

    public static void main(String[] args) throws Exception {
        String cmd = args.length == 0 ? "run" : args[0];
        switch (cmd) {
            case "run":     System.exit(runSuite()); break;
            case "summary": summary(open(args, 1)); break;
            case "errors":  errors(open(args, 1)); break;
            case "fixes":   fixes(open(args, 1)); break;
            case "events":  events(open(args, 1)); break;
            case "open":    openErrors(open(args, 1)); break;
            case "verify":  System.exit(verify(open(args, 1))); break;
            case "design":  System.exit(designCmd(args)); break;
            case "export":  export(open(args, 1), args[2]); break;
            default:
                System.err.println("unknown command: " + cmd);
                System.exit(2);
        }
    }

    private static RepairStore open(String[] args, int at) throws IOException {
        if (args.length <= at) throw new IllegalArgumentException("a store directory is required");
        return RepairStore.open(Paths.get(args[at]));
    }

    /* ─────────────── data access ─────────────── */

    static void summary(RepairStore s) {
        System.out.println("store      : " + (s.dir() == null ? "(memory)" : s.dir()));
        System.out.println("fixes      : " + s.fixes().size());
        System.out.println("errors     : " + s.errors().size());
        System.out.println("events     : " + s.events().size());
        System.out.println("open errors: " + s.openErrors().size());
        System.out.println("outcomes   : " + s.outcomeCounts());
        System.out.println("by reason  : " + s.errorCounts());
        System.out.println("warnings   : " + s.warnings().size());
    }

    static void errors(RepairStore s) {
        for (RepairStore.Error e : s.errors())
            System.out.println(e.id + "\t" + e.capturedMs + "\t" + e.confidence + "\t"
                    + e.lang + "\t" + e.ident + "\t" + e.reason + "\t" + e.fingerprint);
    }

    static void fixes(RepairStore s) {
        for (RepairStore.Fix f : s.fixes())
            System.out.println(f.id + "\t" + f.origin + "\tkind " + f.kind + " cost " + f.cost()
                    + "\t" + f.failure + "\t-> " + f.fixture + "\tstrategy "
                    + (f.strategy == null ? "(wildcard)" : "'" + f.strategy + "'"));
    }

    static void events(RepairStore s) {
        for (RepairStore.Event e : s.events())
            System.out.println(e.id + "\t" + e.op + "\t" + e.action + "\t" + e.confIn
                    + " -> " + e.confOut + "\t" + e.reason + "\t" + e.detail);
    }

    static void openErrors(RepairStore s) {
        for (RepairStore.Error e : s.openErrors())
            System.out.println(e.id + "\t" + e.reason + "\t(no fix yet)");
    }

    static int designCmd(String[] args) throws IOException {
        if (args.length < 6)
            throw new IllegalArgumentException(
                    "design <dir> <failure> <strategy|-> <fixture> <kind> [note]");
        RepairStore s = RepairStore.open(Paths.get(args[1]));
        String strategy = args[3].equals("-") ? null : args[3];
        String note = args.length > 6 ? args[6] : "";
        EverRepair.Verdict v = EverRepair.design(s, "design-cli", args[2], strategy,
                args[4], Integer.parseInt(args[5]), note);
        System.out.println((v.accepted ? "ACCEPTED" : "REJECTED") + ": " + v.reason);
        return v.accepted ? 0 : 1;
    }

    static void export(RepairStore s, String file) throws IOException {
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("fixes", s.fixes().stream().map(RepairStore.Fix::toJson).toList());
        doc.put("errors", s.errors().stream().map(RepairStore.Error::toJson).toList());
        doc.put("events", s.events().stream().map(RepairStore.Event::toJson).toList());
        doc.put("warnings", new ArrayList<>(s.warnings()));
        Path out = Paths.get(file);
        Files.write(out, (EverJson.write(doc) + "\n").getBytes(StandardCharsets.UTF_8));
        System.out.println("exported " + s.fixes().size() + " fixes, " + s.errors().size()
                + " errors, " + s.events().size() + " events to " + out);
    }

    /* ─────────────── verify: the store's data is consistent ─────────────── */

    static int verify(RepairStore s) {
        List<String> errs = new ArrayList<>(), warns = new ArrayList<>();
        for (RepairStore.Fix f : s.fixes()) {
            if (f.failure.isEmpty()) errs.add("fix " + f.id + " has no failure reason");
            if (f.fixture.isEmpty()) errs.add("fix " + f.id + " has no fixture");
            if (f.kind != 0 && f.kind != 1) errs.add("fix " + f.id + " kind " + f.kind);
            if (EverRepair.parseFixture("v", f.fixture) == null)
                warns.add("fix " + f.id + " fixture does not read as a value (it will FAIL)");
        }
        for (RepairStore.Error e : s.errors()) {
            if (!e.fingerprint.equals(RepairStore.fingerprint(e.reason)))
                errs.add("error " + e.id + " fingerprint does not match its reason");
        }
        java.util.Set<String> actions = java.util.Set.of(
                "KEEP", "SUBSTITUTE", "FALLBACK", "FAILED", "LEARNED", "ACCEPTED", "REJECTED");
        for (RepairStore.Event e : s.events()) {
            if (!actions.contains(e.action)) errs.add("event " + e.id + " action " + e.action);
            if (e.confIn < 0 || e.confIn > 256 || e.confOut < 0 || e.confOut > 256)
                errs.add("event " + e.id + " confidence out of range");
            if (e.action.equals("SUBSTITUTE") && e.fixture != null && !e.detail.startsWith("not archived")) {
                boolean backed = false;
                for (RepairStore.Fix f : s.fixes())
                    if (f.fixture.equals(e.fixture) && f.failure.equals(e.reason)
                            && (f.strategy == null || f.strategy.equals(e.strategy))) { backed = true; break; }
                if (!backed) errs.add("event " + e.id + " used fixture '" + e.fixture
                        + "' that no fix for '" + e.reason + "' holds");
            }
        }
        for (String w : s.warnings()) warns.add("load: " + w);
        for (String w : warns) System.out.println("warning: " + w);
        for (String e : errs) System.out.println("error:   " + e);
        System.out.println(errs.isEmpty() ? "verify: OK" : "verify: " + errs.size() + " error(s)");
        return errs.isEmpty() ? 0 : 1;
    }

    /* ─────────────── the scenario suite ─────────────── */

    static EParticle num(long v) { return EParticle.valued("n", v, EParticle.CERTAIN, EParticle.Lang.EVER); }
    static EParticle text(String v) { return EParticle.valued("s", v, EParticle.CERTAIN, EParticle.Lang.EVER); }
    static EParticle conf(Object v, int c) { return EParticle.valued("c", v, c, EParticle.Lang.EVER); }

    static final class Run {
        final EParticle value;
        final List<String> trace;
        Run(EParticle value, List<String> trace) { this.value = value; this.trace = trace; }

        String action() {
            String last = "";
            for (String line : trace) {
                int at = line.indexOf(" execute: ");
                if (at >= 0) {
                    String rest = line.substring(at + 10);
                    last = rest.substring(0, rest.indexOf(' '));
                }
            }
            return last;
        }
    }

    static Run heal(RepairStore s, EParticle primary, String strategy, EParticle fallback) {
        return healWith(s, primary, text(strategy), fallback);
    }

    static Run healWith(RepairStore s, EParticle primary, EParticle strategy, EParticle fallback) {
        EverRepair.Trace tr = new EverRepair.Trace();
        EParticle out = EverRepair.heal(primary, "x", () -> strategy, () -> fallback,
                s, "suite", tr);
        return new Run(out, tr.lines());
    }

    static Run learn(RepairStore s, EParticle primary, String strategy,
                     String fixtureSource, EParticle fixture) {
        return learnWith(s, primary, text(strategy), fixtureSource, fixture);
    }

    static Run learnWith(RepairStore s, EParticle primary, EParticle strategy,
                         String fixtureSource, EParticle fixture) {
        EverRepair.Trace tr = new EverRepair.Trace();
        EParticle out = EverRepair.learn(primary, "x", () -> strategy,
                fixtureSource, fixture, s, "suite", tr);
        return new Run(out, tr.lines());
    }

    static EParticle divZero() {
        return EverRepair.div(num(1), num(0));
    }

    static boolean is(EParticle p, Object payload, int c) {
        return p.payload() == null ? payload == null
                : p.payload().equals(payload) && p.confidence() == c;
    }

    /** A fresh scratch directory for one run: under $EVER_SUITE_DIR, else build/repair-suite
     *  in the working directory. The system temp directory is not used, because some
     *  sandboxes deny it. */
    static Path scratchDir() throws IOException {
        String env = System.getenv("EVER_SUITE_DIR");
        Path base = env != null ? Paths.get(env) : Paths.get("build", "repair-suite");
        Files.createDirectories(base);
        return Files.createTempDirectory(base, "run-");
    }

    static void deleteTree(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (java.util.stream.Stream<Path> walk = Files.walk(root)) {
            List<Path> all = walk.sorted(java.util.Comparator.reverseOrder()).toList();
            for (Path p : all) Files.delete(p);
        }
    }

    static int runSuite() {
        Path dir = null;
        try {
            dir = scratchDir();
            RepairStore s = RepairStore.open(dir);
            System.out.println("\n=== Ever Repair Suite (Java) — store " + dir + " ===\n");

            System.out.println("Process: keep, plan, execute");
            Run keep = heal(s, num(100), "plain", num(0));
            ok("a trusted primary is kept at its own confidence", is(keep.value, 100L, 256));
            ok("keep writes one trace line per phase",
                    keep.trace.size() == 2 && keep.action().equals("KEEP"));

            s.addFix("division by zero", "1", 0, "plain", "designed", "suite");
            s.addFix("division by zero", "2", 0, "other", "designed", "suite");
            s.addFix("division by zero", "3", 0, null, "designed", "suite");
            Run sub = heal(s, divZero(), "plain", num(50));
            ok("strategy 'plain' selects its tied fix (1 at 112)", is(sub.value, 1L, 112));
            ok("trace evaluate line matches the Python layer",
                    sub.trace.get(0).equals("heal#1 evaluate: z, reason 'division by zero', base 120"));
            ok("trace plan line names the fixture and strategy",
                    sub.trace.get(1).equals("heal#1 plan: SUBSTITUTE — archived fixture '1', cost 8 under strategy 'plain'"));
            ok("trace execute line carries confidence and detail",
                    sub.trace.get(2).equals("heal#1 execute: SUBSTITUTE → confidence 112/256 · archived fixture '1', cost 8 under strategy 'plain'"));
            ok("strategy 'other' selects its tied fix (2 at 112)", is(heal(s, divZero(), "other", num(50)).value, 2L, 112));
            ok("an unmatched strategy takes the wildcard (3 at 112)", is(heal(s, divZero(), "nope", num(50)).value, 3L, 112));

            RepairStore tiedOnly = RepairStore.memory();
            tiedOnly.addFix("division by zero", "1", 0, "plain", "designed", "");
            tiedOnly.addFix("division by zero", "2", 0, "other", "designed", "");
            Run miss = heal(tiedOnly, divZero(), "nope", num(50));
            ok("no wildcard and no tie: the fallback runs (50 at 256)", is(miss.value, 50L, 256));
            ok("that fallback is traced as FALLBACK", miss.action().equals("FALLBACK"));

            RepairStore empty = RepairStore.memory();
            ok("no archived repair at all: the fallback runs", is(heal(empty, divZero(), "plain", num(50)).value, 50L, 256));

            System.out.println("\nFixture values and failures");
            RepairStore fx = RepairStore.memory();
            fx.addFix("division by zero", "not an expression", 0, null, "designed", "");
            Run unparsable = heal(fx, divZero(), "plain", num(50));
            ok("an unparsable fixture is z, never the fallback", unparsable.value.isZ());
            ok("an unparsable fixture is FAILED", unparsable.action().equals("FAILED"));

            RepairStore zf = RepairStore.memory();
            zf.addFix("division by zero", "z", 0, null, "designed", "");
            ok("a fixture that is z is FAILED, not the fallback", heal(zf, divZero(), "plain", num(50)).value.isZ());

            RepairStore zero = RepairStore.memory();
            zero.addFix("division by zero", "0", 0, null, "designed", "");
            ok("a fixture of 0 succeeds (0 at 112)", is(heal(zero, divZero(), "plain", num(50)).value, 0L, 112));

            RepairStore fls = RepairStore.memory();
            fls.addFix("division by zero", "false", 0, null, "designed", "");
            ok("a fixture of false succeeds (false at 112)", is(heal(fls, divZero(), "plain", num(50)).value, Boolean.FALSE, 112));

            RepairStore real = RepairStore.memory();
            real.addFix("division by zero", "2.5", 0, null, "designed", "");
            ok("a real fixture succeeds (2.5 at 112)", is(heal(real, divZero(), "plain", num(50)).value, 2.5, 112));

            RepairStore quoted = RepairStore.memory();
            quoted.addFix("division by zero", "\"ok\"", 0, null, "designed", "");
            ok("a quoted text fixture reads as its text", is(heal(quoted, divZero(), "plain", num(50)).value, "ok", 112));

            System.out.println("\nFailure shapes");
            RepairStore one = RepairStore.memory();
            one.addFix("division by zero", "1", 0, null, "designed", "");
            ok("a nested failure (1/0)+1 carries its reason and is repaired",
                    is(heal(one, EverRepair.add(divZero(), num(1)), "plain", num(50)).value, 1L, 112));
            ok("5/0 is the same reason and is repaired too",
                    is(heal(one, EverRepair.div(num(5), num(0)), "plain", num(50)).value, 1L, 112));
            RepairStore low = RepairStore.memory();
            low.addFix("low confidence", "7", 0, null, "designed", "");
            ok("a low-confidence primary is repaired under 'low confidence' (7 at 117)",
                    is(heal(low, conf(9L, 125), "plain", num(50)).value, 7L, 117));
            ok("a repair that cannot add trust (cost >= base) is refused",
                    heal(low, conf(9L, 5), "plain", num(50)).action().equals("FALLBACK"));

            System.out.println("\nLearn");
            RepairStore ln = RepairStore.memory();
            Run learned = learn(ln, divZero(), "plain", "7", num(7));
            ok("learn archives the fixture under its strategy (7 at 120)", is(learned.value, 7L, 120));
            ok("the learned fix is stored, origin 'learned', tied to 'plain'",
                    ln.fixes().size() == 1 && ln.fixes().get(0).origin.equals("learned")
                            && "plain".equals(ln.fixes().get(0).strategy));
            ok("a heal with the same strategy now uses it", is(heal(ln, divZero(), "plain", num(50)).value, 7L, 112));
            ok("a different strategy does not", is(heal(ln, divZero(), "nope", num(50)).value, 50L, 256));
            Run nonText = learnWith(ln, divZero(), num(5), "8", num(8));
            ok("learn with a non-text strategy archives nothing new", ln.fixes().size() == 1);
            ok("and says why: strategy must be text",
                    nonText.trace.get(nonText.trace.size() - 1).contains("not archived: strategy must be text"));

            System.out.println("\nErrors and events are data");
            ok("the store holds exactly the 3 failures it was asked to heal (errors)", s.errors().size() == 3);
            ok("the store holds exactly the 4 heals it was asked to run (events)",
                    s.events().stream().filter(e -> e.op.equals("heal")).count() == 4);
            ok("the outcomes are counted: 1 KEEP, 3 SUBSTITUTE",
                    s.outcomeCounts().getOrDefault("KEEP", 0) == 1
                    && s.outcomeCounts().getOrDefault("SUBSTITUTE", 0) == 3);

            System.out.println("\nDesign");
            RepairStore d = RepairStore.memory();
            ok("a value fixture is accepted",
                    EverRepair.design(d, "suite", "boom", "plain", "5", 0, "ok").accepted);
            ok("the accepted design is stored with origin 'designed'",
                    d.fixes().size() == 1 && d.fixes().get(0).origin.equals("designed"));
            ok("a fixture that is z is rejected",
                    !EverRepair.design(d, "suite", "boom", null, "z", 0, "").accepted);
            ok("unparsable text is rejected",
                    !EverRepair.design(d, "suite", "boom", null, "not an expression", 0, "").accepted);
            ok("an identical fix is rejected",
                    !EverRepair.design(d, "suite", "boom", "plain", "5", 0, "").accepted);
            ok("a kind other than 0 or 1 is rejected",
                    !EverRepair.design(d, "suite", "boom", null, "5", 2, "").accepted);
            ok("every design verdict is an event",
                    d.events().stream().filter(e -> e.op.equals("design")).count() == 5);
            ok("open errors name the reasons that no fix repairs yet",
                    s.openErrors().stream().allMatch(e -> s.candidates(e.reason, null).isEmpty()));

            System.out.println("\nPersistence and compatibility");
            RepairStore reopened = RepairStore.open(dir);
            ok("reopening the store reloads every fix", reopened.fixes().size() == s.fixes().size());
            ok("reopening the store reloads every error", reopened.errors().size() == s.errors().size());
            ok("reopening the store reloads every event", reopened.events().size() == s.events().size());
            ok("a reopened store loads without warnings", reopened.warnings().isEmpty());
            ok("the store verifies clean", verify(reopened) == 0);

            Path repo = Paths.get("7-refix-node", "repairs.jsonl");
            if (Files.exists(repo)) {
                // a copy: the suite writes events, and the real archive must not change
                Path copy = dir.resolve("refix-copy");
                Files.createDirectories(copy);
                Files.copy(repo, copy.resolve(RepairStore.REPAIRS),
                        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                RepairStore archive = RepairStore.open(copy);
                ok("the ReFix archive loads (3 records, no warnings)",
                        archive.fixes().size() == 3 && archive.warnings().isEmpty());
                ok("the ReFix archive repairs 1/0 to 1 at 112",
                        is(heal(archive, divZero(), "plain", num(50)).value, 1L, 112));
            }

            Path junk = dir.resolve("junk-check");
            Files.createDirectories(junk);
            Files.write(junk.resolve(RepairStore.REPAIRS), (
                    "this is not json\n[1, 2, 3]\n"
                    + "{\"failure_text\": \"division by zero\"}\n"
                    + "{\"failure_text\": \"division by zero\", \"fixture_text\": \"1\", \"kind\": 0}\n")
                    .getBytes(StandardCharsets.UTF_8));
            RepairStore messy = RepairStore.open(junk);
            ok("malformed lines are skipped and reported", messy.warnings().size() == 3);
            ok("the valid line is still loaded", messy.fixes().size() == 1);

            String tricky = "a \"quoted\" \\ back\nnew\tline é";
            Object round = EverJson.parse(EverJson.quote(tricky));
            ok("JSON strings round-trip quotes, backslashes and newlines", tricky.equals(round));

            System.out.println("\n=== Repair suite: " + passed + " passed, " + failed + " failed ===\n");
            return failed == 0 ? 0 : 1;
        } catch (IOException ex) {
            System.out.println("suite could not run: " + ex);
            return 1;
        } finally {
            try {
                deleteTree(dir);
            } catch (IOException ex) {
                System.out.println("warning: could not remove " + dir + ": " + ex);
            }
        }
    }

    private RepairSuite() {}
}
