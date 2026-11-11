package com.codric.ezr;

import java.util.List;
import java.util.Map;

import com.codric.ezr.Particle.Defect;
import com.codric.ezr.Particle.Lang;

/**
 * Layer 5's own assertions. Output format matches the other layers so that
 * {@code run.sh} can take the last two lines.
 *
 * <p>These check the Java runtime against SEMANTICS.md. They do not check it
 * against Python — that is {@code differential.py}'s job, and the two answer
 * different questions. A rule can be implemented consistently in both and
 * still be wrong; a rule can be right here and mis-transcribed there. Both
 * checks are needed.
 */
public final class RuntimeTest {

    private static int passed = 0;
    private static int failed = 0;

    public static void main(String[] args) {
        scale();
        chainRule();
        corroboration();
        theorems();
        examples();
        crossing();
        lexing();
        parsing();
        semantics();
        evaluation();
        totality();

        System.out.println();
        System.out.printf("  %d assertions, %d failed%n", passed + failed, failed);
        System.out.println(failed == 0
            ? "  layer 5 (Java runtime) OK"
            : "  layer 5 (Java runtime) FAILED");
        if (failed > 0) System.exit(1);
    }

    /* ── 1.1 the scale ──────────────────────────────────────────────── */

    private static void scale() {
        section("scale constants");
        eq(256, Particle.CERTAIN,       "CERTAIN is 4^4");
        eq(128, Particle.EXECUTE_FLOOR, "the execute floor is half of certain");
        eq(81,  Particle.PI_WARN,       "pi warn is floor(256/pi)");
        eq(25,  Particle.PI_ENUMERATE,  "pi enumerate is floor(256/pi^2)");
        eq(3,   Particle.DEPTH_CEILING, "the depth ceiling is floor(pi)");
        eq(120, Particle.INTAKE,        "external data enters at intake");
        eq(5,   Lang.JAVA.ordinal(),    "JAVA is language 5, as the C atom has it");

        ok(Particle.z(Defect.UNBOUND, "x").uncertainty() == 1.0, "u(Z) = 1");
        ok(Particle.certain(1.0).uncertainty() == 0.0,           "u(Certain) = 0");
        ok(!Particle.of(1.0, 127).canExecute(), "127 is below the execute floor");
        ok(Particle.of(1.0, 128).canExecute(),  "128 clears it");
    }

    /* ── 2.1 chain ──────────────────────────────────────────────────── */

    private static void chainRule() {
        section("chain — min");
        eq(120, Laws.chain(256, 120, 200), "a chain is its weakest link");
        eq(256, Laws.chain(256, 256),      "all certain stays certain");
        eq(0,   Laws.chain(0, 256),        "a Z in the chain floors it");
        eq(256, Laws.chain(),              "an empty chain is certain");
        // a ten-step chain over trusted inputs stays usable — the reason min
        // was chosen over the probabilistic rule
        int c = 200;
        for (int i = 0; i < 10; i++) c = Laws.chain(c, 200);
        eq(200, c, "ten chained steps at 200 stay at 200");
    }

    /* ── 2.2 corroborate ────────────────────────────────────────────── */

    private static void corroboration() {
        section("corroborate — multiplicative uncertainty");
        eq(184, Laws.corroborate(120, 120), "two intake witnesses reach 184");
        eq(256, Laws.corroborate(256, 256), "two certains are certain");
        eq(120, Laws.corroborate(0, 120),   "Z corroborates nothing away");
        ok(Laws.corroborate(255, 255) < Particle.CERTAIN,
           "combination caps one short of certain");

        // SEMANTICS.md 2.2 says the integer form c = a + b - floor(ab/256) is
        // "equivalently" u(a+b) = u(a)*u(b), verified 1089/1089, but does not
        // say which way the scale rounds. It is the CEILING: 120 with 120 is
        // 183.75 exactly, and the integer form gives 184. Pinned here because
        // "equivalently" is the kind of word that later gets read as floor,
        // and the two differ on 507 of those 1089 cells.
        boolean matchesCeiling = true;
        for (int a = 0; a <= 256; a += 8) {
            for (int b = 0; b <= 256; b += 8) {
                int got = Laws.corroborate(a, b);
                int want;
                if (a >= 256 && b >= 256) {
                    want = 256;
                } else {
                    double ua = (256 - a) / 256.0, ub = (256 - b) / 256.0;
                    want = Math.min(255, (int) Math.ceil(256 * (1 - ua * ub)));
                }
                if (got != want) matchesCeiling = false;
            }
        }
        ok(matchesCeiling,
           "the integer form is ceil(256*(1-ua*ub)) on all 1089 grid cells");
    }

    private static void theorems() {
        section("the three theorems");
        ok(Laws.zIsAbsorbing(200),                  "T1 — Z is absorbing");
        ok(Laws.corroborationCreatesNothing(120, 120), "T2 — corroboration creates nothing");
        ok(Laws.certainUnreachable(255, 255),       "T3 — certain unreachable by combination");
        ok(Laws.certainUnreachable(256, 256),       "T3 — but it may enter from outside");
    }

    /* ── 4.2 examples ───────────────────────────────────────────────── */

    private static void examples() {
        section("how a function earns confidence");
        eq(120, Laws.fromExamples(1, 1), "1/1 — one case proves nothing, still at intake");
        eq(183, Laws.fromExamples(2, 2), "2/2 clears the floor");
        eq(217, Laws.fromExamples(3, 3), "3/3");
        eq(235, Laws.fromExamples(4, 4), "4/4");
        eq(122, Laws.fromExamples(2, 3), "2/3 — a failure costs");
        ok(Laws.fromExamples(1, 1) < Particle.EXECUTE_FLOOR,
           "one example does not reach the execute floor");
    }

    /* ── G6 and G7 ──────────────────────────────────────────────────── */

    private static void crossing() {
        section("crossing a language boundary");
        Particle anchored = Particle.of(42.0, 200).anchored(7);
        Particle hopped = anchored;
        for (int i = 0; i < 5; i++) {
            hopped = Laws.assimilate(hopped, i % 2 == 0 ? Lang.PYTHON : Lang.JAVA);
        }
        eq(200, hopped.confidence, "G6 — anchored crosses 5 hops losslessly");

        Particle loose = Particle.of(42.0, 200);
        Particle l1 = Laws.assimilate(loose, Lang.PYTHON);
        eq(199, l1.confidence, "G7 — unanchored loses exactly 1 per hop");
        Particle l2 = Laws.assimilate(l1, Lang.RUBY);
        eq(198, l2.confidence, "G7 — and again on the next hop");

        eq(200, Laws.assimilate(loose, Lang.JAVA).confidence,
           "a hop to the same language is not a hop");
        ok(Laws.assimilate(Particle.z(Defect.UNBOUND, "x"), Lang.C).isZ(),
           "Z does not translate");
    }

    /* ── the front end ──────────────────────────────────────────────── */

    private static void lexing() {
        section("lexing");
        Lexer.Out o = Lexer.lex("1 + 2");
        ok(o.ok(), "a simple sum lexes");
        eq(4, o.tokens().size(), "three tokens and an EOF");

        eq(Lexer.Kind.CMP, first("a < b", 1).kind(),
           "a bare '<' is CMP — settled by doctrine after the scanners split 2-2");
        eq(Lexer.Kind.CMP, first("a <= b", 1).kind(), "'<=' is one token, not two");
        eq(Lexer.Kind.OP,  first("a + b", 1).kind(),  "'+' is OP");
        eq(Lexer.Kind.KW,  first("if x", 0).kind(),   "'if' is a keyword");
        eq(Lexer.Kind.NAME, first("iffy", 0).kind(),  "'iffy' is a name, not a keyword");
        eq(8, Lexer.KEYWORDS.size(), "eight reserved words, not nineteen");

        Lexer.Out bad = Lexer.lex("a $ b");
        ok(!bad.ok() && bad.error().defect == Defect.MISBOUND,
           "an illegal character is misbound");
        Lexer.Out open = Lexer.lex("\"never closed");
        ok(!open.ok() && open.error().defect == Defect.UNBOUNDED,
           "an unterminated string is unbounded, not misbound");

        ok(Lexer.lex("# just a comment\n1").ok(), "comments are dropped");
        // the trie scanner's historical bug: '$' as an end-of-token sentinel
        ok(!Lexer.lex("\"a $ b\"").tokens().isEmpty(),
           "'$' inside a string is content, not a sentinel");
    }

    private static void parsing() {
        section("parsing");
        ok(Parser.parse("1 + 1").ok(), "an expression parses");
        ok(Parser.parse("def f(n) = n + 1").ok(), "a definition parses");
        ok(Parser.parse("def a(n) = n\ndef b(n) = n").ok(),
           "more than one definition is allowed — the forge settled that");

        // left associativity: a right-associative slip gives 9, not 5
        Ast sub = expr("10 - 3 - 2");
        ok(sub instanceof Ast.Bin b && b.left() instanceof Ast.Bin,
           "'-' is left-associative, so the left child is the nested one");

        ok(!Parser.parse("a < b < c").ok(), "chained comparison is outside the grammar");
        ok(!Parser.parse("f(1,)").ok(),     "a trailing comma is refused");
        ok(!Parser.parse("def f(n) = n\n1 + 1").ok(),
           "a trailing expression after definitions is refused — that grammar is ambiguous");
        ok(!Parser.parse("1 +").ok(), "running out of input is refused");
        eq(Defect.UNBOUNDED, Parser.parse("1 +").error().defect,
           "and it is unbounded, not misbound");

        eq(1, Ast.size(expr("n")),      "n is one node");
        eq(3, Ast.size(expr("n * 1")),  "n * 1 is three");
        eq(1, Ast.size(expr("((n))")),  "redundant parens vanish");

        // one idea in three hats — the cell 7 result, in Java
        String a = Ast.skeleton(expr("if n <= 0 then 1 else n + p(n - 2)"));
        String b = Ast.skeleton(expr("if n <  0 then 1 else n + p(n - 2)"));
        String c = Ast.skeleton(expr("if n <  1 then 1 else n + p(n - 2)"));
        ok(a.equals(b) && b.equals(c),
           "three 'independent' candidates collapse to one skeleton");
    }

    private static void semantics() {
        section("semantic analysis");
        ok(!analyse("def f(n) = n + missing").ok(), "an unbound name is caught");
        ok(analyse("def f(n) = g(n)\ndef g(n) = n").ok(),
           "forward references resolve — two passes, not one");
        ok(!analyse("def g(n) = if n then \"yes\" else 3").ok(),
           "branches that disagree are caught");
        ok(!analyse("def h(n) = n / 0").ok(),   "a literal division by zero is caught");
        ok(!analyse("\"ab\" * 2").ok(),
           "text does not multiply — the host language's answer never gets asked");
        ok(!analyse("true + true").ok(),        "bool arithmetic is caught");
        ok(analyse("\"a\" + \"b\"").ok(),       "but '+' over two texts is fine");
        ok(!analyse("def k(n) = f(n, n)\ndef f(n) = n").ok(), "arity is checked");

        eq("n", Semantic.measure(def("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)")),
           "a decreasing measure is found");
        eq("n", Semantic.measure(def("def deep(n) = deep((n) - 1)")),
           "and it sees through parentheses the string version missed");
        eq(null, Semantic.measure(def("def loop(n) = loop(n)")),
           "no decrease means no measure — refusing to guess is the point");
        eq(null, Semantic.measure(def("def up(n) = up(n + 1)")),
           "increasing is not decreasing");
    }

    /* ── evaluation ─────────────────────────────────────────────────── */

    private static void evaluation() {
        section("evaluation");
        eq("2",   value("1 + 1"),       "arithmetic");
        eq(256,   conf("1 + 1"),        "program constants are certain, not intake");
        eq("2",   value("4 / 2"),       "a whole quotient has no decimal point");
        eq("0.5", value("1 / 2"),       "a real one does");
        eq("5",   value("10 - 3 - 2"),  "left-associative subtraction");
        eq("7",   value("1 + 2 * 3"),   "multiplication binds tighter");
        eq("9",   value("(1 + 2) * 3"), "parentheses override that");
        eq("True",  value("1 < 2"),     "comparison");
        eq("False", value("2 < 1"),     "and it can be false");
        eq("ab",  value("\"a\" + \"b\""), "text concatenates");
        eq("6",   value("let x = 5 in x + 1"), "let binds");
        eq("[1, 2, 3]", value("[1, 2, 3]"),    "a list literal");
        eq("3",   value("len([1, 2, 3])"),     "len");
        eq("1",   value("head([1, 2, 3])"),    "head");
        eq("[2, 3]", value("tail([1, 2, 3])"), "tail");

        // the chain rule, over list elements
        eq(256, conf("[1, 2, 3]"), "a list of constants is certain");

        // 5.1 — lazy under a known condition. If the untaken arm ran, this
        // would recurse forever instead of returning 1.
        eq("1", runProgram("def f(n) = if n <= 1 then 1 else f(n - 1)", "f(3)"),
           "the untaken branch is not evaluated");

        // 5.2 — a Z condition spans, it does not collapse
        Particle span = evalExpr("if unknown then 1 else 3");
        ok(span.state == Particle.State.EQUIVALENCE, "an unknown condition spans");
        eq(1, span.lo, "the span starts at the lower arm");
        eq(3, span.hi, "and ends at the higher one");

        // [IF-AGREE] — both arms agree, so the ignorance is moot
        eq("7", value("if unknown then 7 else 7"), "agreeing arms make the unknown moot");

        // past the pi threshold it collapses
        ok(evalExpr("if unknown then 0 else 500").isZ(),
           "a span wider than the pi threshold collapses to Z");

        // G8 — a checked halt
        String deep = runProgram("def f(n) = f(n - 1)", "f(10)");
        ok(deep.startsWith("Z("), "unbounded recursion halts at the ceiling rather than hanging");
    }

    /* ── G1 ─────────────────────────────────────────────────────────── */

    private static void totality() {
        section("G1 — evaluation is total");
        String[] hostile = {
            "1 / 0", "head([])", "tail([])", "len(3)", "nope(1)", "x",
            "[1, 2, 3] + 1", "if 1 then 2 else \"three\"", "len([1,2], [3])",
            "show(1, 2)", "0 / 0", "\"a\" < 1",
        };
        boolean allTotal = true;
        for (String src : hostile) {
            try {
                Particle p = evalExpr(src);
                if (p == null) allTotal = false;
            } catch (Throwable t) {
                allTotal = false;
                System.out.println("    threw on: " + src + " -> " + t);
            }
        }
        ok(allTotal, "every hostile input returns a particle, none throws");

        // and the front end is total too
        String[] junk = { "", "((((", "\"", "$", "def", "let in", "]]]", "if" };
        boolean frontTotal = true;
        for (String src : junk) {
            try {
                Parser.Out o = Parser.parse(src);
                if (o.ok() == (o.error() != null)) frontTotal = false;
            } catch (Throwable t) {
                frontTotal = false;
                System.out.println("    front end threw on: " + src + " -> " + t);
            }
        }
        ok(frontTotal, "every junk input parses to a result or a Z, none throws");
    }

    /* ── helpers ────────────────────────────────────────────────────── */

    private static Lexer.Tok first(String src, int n) {
        return Lexer.lex(src).tokens().get(n);
    }

    private static Ast expr(String src) {
        Ast a = Parser.parse(src).ast();
        return (a instanceof Ast.Prog p && p.expr() != null) ? p.expr() : a;
    }

    private static Ast.Def def(String src) {
        return ((Ast.Prog) Parser.parse(src).ast()).defs().get(0);
    }

    private static Semantic.Analysis analyse(String src) {
        Parser.Out o = Parser.parse(src);
        if (!o.ok()) {
            Semantic.Analysis a = new Semantic.Analysis();
            a.errors.add("parse: " + o.error().reason);
            return a;
        }
        return new Semantic().analyse(o.ast());
    }

    private static Particle evalExpr(String src) {
        Parser.Out o = Parser.parse(src);
        if (!o.ok()) return o.error();
        return new Eval(Map.of(), 100).run(o.ast());
    }

    private static String value(String src) { return evalExpr(src).render(); }
    private static int    conf(String src)  { return evalExpr(src).confidence; }

    private static String runProgram(String defs, String entry) {
        Parser.Out prog = Parser.parse(defs);
        if (!prog.ok()) return "parse failed: " + prog.error().reason;
        Map<String, Eval.Fn> fns = Eval.definitions(prog.ast());
        Parser.Out call = Parser.parse(entry);
        if (!call.ok()) return "parse failed: " + call.error().reason;
        Particle r = new Eval(fns, Particle.DEPTH_CEILING).run(call.ast());
        return r.isZ() ? "Z(" + r.defect + ")" : r.render();
    }

    /* ── the tiny assertion shim ────────────────────────────────────── */

    private static void section(String name) {
        System.out.println();
        System.out.println("  " + name);
    }

    private static void ok(boolean cond, String what) {
        if (cond) { passed++; System.out.println("    ok    " + what); }
        else      { failed++; System.out.println("    FAIL  " + what); }
    }

    private static void eq(Object want, Object got, String what) {
        boolean same = (want == null) ? got == null : want.equals(got);
        if (same) { passed++; System.out.println("    ok    " + what); }
        else {
            failed++;
            System.out.println("    FAIL  " + what + "  (want " + want
                               + ", got " + got + ")");
        }
    }

    private RuntimeTest() { }
}
