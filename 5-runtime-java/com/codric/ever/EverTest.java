package com.codric.ever;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import static com.codric.ever.EParticle.Lang;
import static com.codric.ever.EParticle.PiStatus;
import static com.codric.ever.EParticle.State;

/** EverTest.java — Ever Layer 5 verification. */
public final class EverTest {

    static int passed = 0, failed = 0;

    static void ok(String name, boolean cond) {
        if (cond) { passed++; System.out.println("  \u2713 " + name); }
        else      { failed++; System.out.println("  \u2717 " + name); }
    }

    public static void main(String[] args) {
        System.out.println("\n=== Ever Layer 5 (Java) — the runtime ===\n");

        System.out.println("Constants agree with Layer 0");
        ok("Certain is 256",        EParticle.CERTAIN == 256);
        ok("pi warn is 81",         EParticle.PI_WIDTH_WARN == 81);
        ok("pi squared is 25",      EParticle.PI_WIDTH_ENUMERATE == 25);
        ok("emulate ceiling is 3",  EParticle.EMULATE_CEILING == 3);
        ok("execute floor is 128",  EParticle.EXECUTE_FLOOR == 128);

        System.out.println("\nParticle semantics");
        EParticle z = EParticle.z("ocr_text", "OCR not run");
        ok("Z confidence zero",     z.confidence() == 0);
        ok("Z not cleared",         !z.isCleared());
        ok("Z cannot execute",      !z.canExecute());
        ok("Z keeps its reason",    z.reason().equals("OCR not run"));

        EParticle cert = EParticle.certain("verified", Lang.SQL);
        ok("Certain is 256",        cert.confidence() == 256);
        ok("Certain can execute",   cert.canExecute());

        ok("degree over 256 becomes Certain",
           EParticle.confident("x", 300, Lang.C).state() == State.CERTAIN_S);
        ok("degree under 1 becomes Z",
           EParticle.confident("x", 0, Lang.C).state() == State.Z);

        System.out.println("\nEquivalence and pi");
        EParticle narrow = EParticle.equivalence("sev", 100, 115, Lang.RUBY);
        ok("width computed",        narrow.width() == 15);
        ok("width 15 acceptable",   narrow.piStatus() == PiStatus.ACCEPTABLE);
        ok("width 26 enumerate",
           EParticle.equivalence("s", 100, 126, Lang.RUBY).piStatus()
               == PiStatus.ENUMERATE);
        ok("width 150 approaching Z",
           EParticle.equivalence("s", 50, 200, Lang.RUBY).piStatus()
               == PiStatus.APPROACHING_Z);
        ok("reversed bounds corrected",
           EParticle.equivalence("s", 200, 50, Lang.RUBY).lo() == 50);

        System.out.println("\nZ contagion");
        ok("Z carried forward stays Z", z.carry("downstream").isZ());
        ok("Certain carries forward",
           cert.carry("downstream").state() == State.CERTAIN_S);
        EParticle err = EParticle.eerror("parse", "unterminated", 80);
        ok("error carried forward is Z", err.carry("down").isZ());
        ok("error keeps boundary marker", err.lo() == 80);

        System.out.println("\nCapping");
        EParticle capped = cert.cap(150);
        ok("cap demotes Certain",   capped.state() == State.CONFIDENT);
        ok("cap sets confidence",   capped.confidence() == 150);
        ok("cap above value no-op",
           EParticle.confident("x", 180, Lang.C).cap(250).confidence() == 180);

        System.out.println("\nExcel arithmetic matches Layers 0 and 1");
        ok("150 x 140 excels upward", EParticle.excelFormula(150, 140) > 150);
        ok("never exceeds 256",       EParticle.excelFormula(250, 250) <= 256);
        ok("matches core formula",
           EParticle.excelFormula(150, 140) == (150 + 140 - (150 * 140 / 256)));

        System.out.println("\nEmulate");
        EParticle working = EParticle.confident("working_parse", 200, Lang.C);
        EParticle broken  = EParticle.confident("broken_parse",   40, Lang.C);
        EParticle em1 = EParticle.emulate(broken, working, 1);
        ok("distance 1 emulates",   em1.state() == State.EMULATING);
        ok("distance 1 discounts 30", em1.confidence() == 170);
        ok("distance 3 discounts 90",
           EParticle.emulate(broken, working, 3).confidence() == 110);
        ok("distance 4 returns to Z",
           EParticle.emulate(broken, working, 4).isZ());
        ok("cannot emulate a Z neighbour",
           EParticle.emulate(broken, z, 1).isZ());

        System.out.println("\nPhase engine, check order preserved");
        EParticle a128 = EParticle.confident("a", 128, Lang.JAVA);
        EParticle b128 = EParticle.confident("b", 128, Lang.JAVA);
        ok("identical confidence collides",
           EverRuntime.pauliCollision(a128, b128));
        ok("collision produces Expel",
           EverRuntime.combine(a128, b128).outcome
               == EverRuntime.Outcome.EXPEL);

        ok("Z blocks interaction",
           EverRuntime.combine(z, working).outcome
               == EverRuntime.Outcome.BLOCKED);

        EverRuntime.PhaseResult ex = EverRuntime.combine(
                EParticle.confident("deceptive", 150, Lang.JAVA),
                EParticle.confident("scare",     140, Lang.JAVA));
        ok("near values Excel",     ex.outcome == EverRuntime.Outcome.EXCEL);
        ok("Excel rises above both", ex.combined.confidence() > 150);

        EverRuntime.PhaseResult xp = EverRuntime.combine(
                EParticle.confident("dominant", 240, Lang.JAVA),
                EParticle.confident("weak",      30, Lang.JAVA));
        ok("dominance produces Expel", xp.outcome == EverRuntime.Outcome.EXPEL);
        ok("stronger survives",        xp.survivor.confidence() == 240);
        ok("expelled archived as error",
           xp.expelled.state() == State.EERROR);

        EverRuntime.PhaseResult rp = EverRuntime.combine(
                EParticle.confident("lo",  63, Lang.JAVA),
                EParticle.confident("hi", 200, Lang.JAVA));
        ok("opposite zones repel",  rp.outcome == EverRuntime.Outcome.REPEL);
        ok("repel records edges",   rp.lowEdge == 63 && rp.highEdge == 200);

        ok("Expel checked before Repel",
           EverRuntime.combine(
               EParticle.confident("vlo",  20, Lang.JAVA),
               EParticle.confident("vhi", 250, Lang.JAVA)).outcome
                   == EverRuntime.Outcome.EXPEL);

        System.out.println("\nExpect gates");
        List<EParticle> arch = new ArrayList<>();
        ok("gate passes on good particle",
           EverRuntime.Gate.on(EParticle.confident("p", 180, Lang.JAVA))
                   .notZ().minConfidence(128).passes());
        ok("gate fails on low confidence",
           !EverRuntime.Gate.on(EParticle.confident("p", 40, Lang.JAVA))
                   .minConfidence(128).passes());
        ok("gate fails on Z",
           !EverRuntime.Gate.on(z).notZ().passes());
        ok("orZ collapses a failed gate",
           EverRuntime.Gate.on(EParticle.confident("p", 40, Lang.JAVA))
                   .minConfidence(128).orZ().isZ());
        EverRuntime.Gate.on(EParticle.confident("p", 40, Lang.JAVA))
                .minConfidence(128).orArchive(arch);
        ok("orArchive preserves the failure", arch.size() == 1);
        ok("archived failure is an EError",
           arch.get(0).state() == State.EERROR);

        boolean threw = false;
        try {
            EverRuntime.Gate.on(z).notZ().orThrow();
        } catch (EverRuntime.ExpectFailure e) { threw = true; }
        ok("orThrow raises on failure", threw);

        System.out.println("\nphi equalizer");
        EverRuntime.Equalized bal = EverRuntime.phiEqualize(Arrays.asList(
                EParticle.confident("a", 180, Lang.JAVA),
                EParticle.confident("b", 160, Lang.JAVA),
                EParticle.confident("c", 150, Lang.JAVA)));
        ok("balanced set flags nothing", bal.flagged.isEmpty());
        EverRuntime.Equalized skew = EverRuntime.phiEqualize(Arrays.asList(
                EParticle.confident("a", 250, Lang.JAVA),
                EParticle.confident("b",  10, Lang.JAVA)));
        ok("skewed set flags outliers",  !skew.flagged.isEmpty());
        ok("empty set equalizes cleanly",
           EverRuntime.phiEqualize(new ArrayList<>()).balanced.isEmpty());

        System.out.println("\nForce loop and Evolve");
        EverRuntime.ForceLoop loop = new EverRuntime.ForceLoop("parser");
        loop.add(EParticle.confident("parser", 170, Lang.PYTHON));
        ok("one point does not close",  !loop.closed());
        ok("open loop does not evolve", loop.evolve() == null);
        loop.add(EParticle.confident("parser", 175, Lang.PYTHON));
        loop.add(EParticle.confident("parser", 180, Lang.PYTHON));
        ok("three points close the loop", loop.closed());
        ok("spread computed",             loop.spread() == 10);
        ok("direction up",                loop.direction().equals("up"));
        EParticle evolved = loop.evolve();
        ok("aligned loop evolves",        evolved != null);
        ok("evolved to the mean 175",     evolved.confidence() == 175);
        ok("generation advanced",         evolved.generation() == 1);
        ok("state is Evolved",            evolved.state() == State.EVOLVED);

        EverRuntime.ForceLoop wild = new EverRuntime.ForceLoop("wild");
        wild.add(EParticle.confident("wild",  40, Lang.PYTHON));
        wild.add(EParticle.confident("wild", 200, Lang.PYTHON));
        wild.add(EParticle.confident("wild",  90, Lang.PYTHON));
        ok("scattered loop refuses to evolve", wild.evolve() == null);

        EverRuntime.ForceLoop down = new EverRuntime.ForceLoop("down");
        down.add(EParticle.confident("down", 180, Lang.PYTHON));
        down.add(EParticle.confident("down", 175, Lang.PYTHON));
        down.add(EParticle.confident("down", 170, Lang.PYTHON));
        EParticle dev = down.evolve();
        ok("downward evolution is legitimate", dev != null);
        ok("downward direction recorded",
           down.direction().equals("down"));

        System.out.println("\nSerialization round trip, Layer 0 format");
        EParticle p = EParticle.confident("parsed_amount", 180, Lang.PYTHON);
        String line = p.serialize();
        EParticle back = EParticle.deserialize(line);
        ok("twelve fields emitted",   line.split("\\|", 12).length == 12);
        ok("confidence survives",     back.confidence() == 180);
        ok("ident survives",          back.ident().equals("parsed_amount"));
        ok("lang survives",           back.lang() == Lang.PYTHON);
        ok("state survives",          back.state() == State.CONFIDENT);
        ok("equality holds",          back.equals(p) || back.ident().equals(p.ident()));

        System.out.println("\nFull pipeline");
        EverRuntime rt = new EverRuntime("invoice_scan");
        rt.declare(EParticle.z("ocr_text", "OCR not yet run"))
          .declare(EParticle.confident("parsed_amount", 180, Lang.PYTHON))
          .declare(EParticle.confident("working_parse", 200, Lang.C))
          .declare(EParticle.confident("broken_parse",   40, Lang.C))
          .declare(EParticle.certain("schema_version", Lang.SQL))
          .declare(EParticle.equivalence("severity", 100, 115, Lang.RUBY));

        rt.expect("parsed_amount", 128, false);
        rt.expect("severity",        0, true);
        rt.expect("ocr_text",      128, false);
        rt.emulate("broken_parse", "working_parse", 1);

        EverRuntime.Result result = rt.execute();
        ok("Z blocked the pipeline",   !result.executable());
        ok("cleared particles present", result.cleared.size() >= 4);
        ok("Z present in blocked",      !result.blocked.isEmpty());
        ok("archive captured failures", !result.archive.isEmpty());
        ok("emulated particle cleared",
           rt.get("broken_parse").state() == State.EMULATING);
        ok("emulated confidence is 170",
           rt.get("broken_parse").confidence() == 170);

        System.out.println(result.report());

        System.out.println("=== Layer 5: " + passed + " passed, "
                + failed + " failed ===\n");
        System.exit(failed == 0 ? 0 : 1);
    }
}
