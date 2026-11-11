package com.codric.ezr;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The runner. Layer 5's entry point, and the thing that makes this a runtime
 * rather than a library.
 *
 * <pre>
 *   java -cp out com.codric.ezr.Ezr program.ezr
 *   java -cp out com.codric.ezr.Ezr -e 'let x = 5 in x + 1'
 *   echo 'def main() = 6 * 7' | java -cp out com.codric.ezr.Ezr -
 * </pre>
 *
 * <p>Exit codes, matching {@code 2-interpreter-python/ezrun.py} exactly:
 * <strong>0</strong> a value, <strong>1</strong> a refusal (Z),
 * <strong>2</strong> input that would not compile. The output format matches
 * too — not for tidiness, but because {@code differential.py} compares the
 * two runners byte for byte, and a runtime nothing checks is a runtime
 * nobody should trust.
 */
public final class Ezr {

    public static final int EXIT_OK       = 0;
    public static final int EXIT_REFUSED  = 1;
    public static final int EXIT_BAD_INPUT = 2;

    private Ezr() { }

    public static void main(String[] args) {
        System.exit(run(args));
    }

    static int run(String[] argv) {
        String  file = null, expr = null, call = null;
        int     depth = 100;
        boolean quiet = false;
        List<String> examples = new ArrayList<>();
        List<String> anchors  = new ArrayList<>();

        for (int i = 0; i < argv.length; i++) {
            String a = argv[i];
            switch (a) {
                case "-h", "--help" -> { usage(System.out); return EXIT_OK; }
                case "-q", "--quiet" -> quiet = true;
                case "-e", "--eval" -> {
                    if (++i >= argv.length) return fail("-e needs an expression");
                    expr = argv[i];
                }
                case "-c", "--call" -> {
                    if (++i >= argv.length) return fail("-c needs an expression");
                    call = argv[i];
                }
                case "-x", "--example" -> {
                    if (++i >= argv.length) return fail("-x needs 'call = value'");
                    examples.add(argv[i]);
                }
                case "-a", "--anchor" -> {
                    if (++i >= argv.length) return fail("-a needs a function name");
                    anchors.add(argv[i]);
                }
                case "-d", "--depth" -> {
                    if (++i >= argv.length) return fail("-d needs a number");
                    try {
                        depth = Integer.parseInt(argv[i]);
                    } catch (NumberFormatException e) {
                        return fail("-d needs a number, got '" + argv[i] + "'");
                    }
                }
                default -> {
                    if (a.startsWith("-") && a.length() > 1 && !a.equals("-")) {
                        return fail("unknown option '" + a + "'");
                    }
                    if (file != null) return fail("more than one program given");
                    file = a;
                }
            }
        }
        if (file == null && expr == null) {
            return fail("one of the arguments file -e/--eval is required");
        }
        if (file != null && expr != null) {
            return fail("give a file or -e, not both");
        }

        String source, where;
        if (expr != null) {
            source = expr; where = "-e";
        } else if (file.equals("-")) {
            source = readAll(System.in); where = "<stdin>";
            if (source == null) return fail("cannot read stdin");
        } else {
            Path p = Path.of(file);
            if (Files.isDirectory(p)) {
                return fail(file + " is a directory, not a program");
            }
            if (!Files.exists(p)) return fail("no such file: " + file);
            try {
                source = Files.readString(p, StandardCharsets.UTF_8);
            } catch (IOException e) {
                return fail("cannot read " + file + ": " + e.getMessage());
            }
            where = file;
        }
        return execute(source, where, call, depth, quiet, examples, anchors);
    }

    /* ── the four stages ────────────────────────────────────────────── */

    static int execute(String source, String where, String call,
                       int depth, boolean quiet) {
        return execute(source, where, call, depth, quiet,
                       List.of(), List.of());
    }

    static int execute(String source, String where, String call,
                       int depth, boolean quiet,
                       List<String> examples, List<String> anchors) {
        Parser.Out parsed = Parser.parse(source);
        if (!parsed.ok()) {
            // stage names match the Python runner so the two are comparable
            String stage = parsed.error().reason.contains("character")
                        || parsed.error().reason.contains("unterminated")
                           ? "lex" : "parse";
            System.err.println("ezr: " + where + ": " + stage + ": "
                               + parsed.error().reason);
            return EXIT_BAD_INPUT;
        }

        Semantic.Analysis analysis = new Semantic().analyse(parsed.ast());
        if (!analysis.ok()) {
            System.err.println("ezr: " + where + ": semantic: "
                               + analysis.errors.get(0));
            return EXIT_BAD_INPUT;
        }

        Map<String, Eval.Fn> fns = Eval.definitions(parsed.ast());
        Ast ast = parsed.ast();

        Earned earned = earn(fns, examples, anchors, depth, where);
        if (earned.code != EXIT_OK) return earned.code;
        Trust trust = earned.trust;

        // a bare expression runs as it stands
        if (ast instanceof Ast.Prog p && p.expr() != null) {
            Eval ev = new Eval(fns, depth, trust);
            Particle r = ev.run(p.expr());
            return report(r, quiet, lift(r, ev, fns, trust, earned.tally));
        }

        // otherwise: --call wins, else main(), else say what is defined
        String entry = (call != null) ? call
                     : fns.containsKey("main") ? "main()" : null;
        if (entry == null) {
            List<String> names = new ArrayList<>(fns.keySet());
            System.err.println("ezr: " + where + " defines " + names
                + " and does not say what to run.\n"
                + "     Define main(), or pass --call 'expr'.");
            return EXIT_BAD_INPUT;
        }

        Parser.Out entryParse = Parser.parse(entry);
        if (!entryParse.ok()) {
            System.err.println("ezr: --call " + entry + ": parse: "
                               + entryParse.error().reason);
            return EXIT_BAD_INPUT;
        }
        Ast body = (entryParse.ast() instanceof Ast.Prog ep && ep.expr() != null)
                 ? ep.expr() : entryParse.ast();
        Eval ev = new Eval(fns, depth, trust);
        Particle r = ev.run(body);
        return report(r, quiet, lift(r, ev, fns, trust, earned.tally));
    }

    /** A Trust, or the exit code that says why there isn't one. */
    private record Earned(Trust trust, Map<String, int[]> tally, int code) { }

    /**
     * Turn Examples into confidence and anchors into earned depth.
     *
     * <p>Neither is source syntax. The forge settled the reserved words at
     * eight, and SEMANTICS.md states both as operations on a thread rather
     * than as things a program says about itself — so they arrive the way a
     * verification harness would supply them, from outside the program.
     */
    /** The requirement clause for a thread short of the execute floor. */
    static String needs(int passing, int total) {
        int k = Laws.witnessesNeeded(passing, total);
        if (k < 0) {
            return "no number of further witnesses within reason clears "
                 + Particle.EXECUTE_FLOOR + " from " + passing + " of " + total;
        }
        if (k == 0) return "nothing further is needed";
        return k + " more passing Example" + (k > 1 ? "s" : "")
             + " clears " + Particle.EXECUTE_FLOOR;
    }

    /**
     * The requirement clause for a function that cannot be anchored.
     * {@link Semantic#movements} has just computed how every parameter
     * moves; a refusal reading "no decreasing measure" is that computation
     * with its useful half thrown away. This puts it back.
     */
    static String whyNoMeasure(Ast.Def fn) {
        var moves = Semantic.movements(fn);
        if (moves == null) {
            return fn.name() + " does not call itself, so it has no measure "
                 + "to prove and needs no anchor";
        }
        var parts = new ArrayList<String>();
        moves.forEach((k, v) -> parts.add(k + " " + v));
        return "anchoring needs one parameter that strictly decreases in "
             + "every self-call; here " + String.join("; ", parts);
    }

    static Earned earn(Map<String, Eval.Fn> fns, List<String> examples,
                       List<String> anchors, int depth, String where) {
        Trust trust = Trust.none();
        Map<String, int[]> tally = new LinkedHashMap<>();
        // canonical call source -> the answer already claimed for it
        Map<String, Object> seen = new LinkedHashMap<>();

        for (String spec : examples) {
            int cut = splitPoint(spec);
            if (cut < 0) {
                System.err.println("ezr: --example '" + spec
                                   + "': expected 'call = value'");
                return new Earned(null, null, EXIT_BAD_INPUT);
            }
            String callSrc = spec.substring(0, cut).trim();
            String wantSrc = spec.substring(cut + 1).trim();
            Parser.Out cc = Parser.parse(callSrc);
            Parser.Out wc = Parser.parse(wantSrc);
            if (!cc.ok() || !wc.ok()) {
                System.err.println("ezr: --example '" + spec
                                   + "': " + (!cc.ok() ? callSrc : wantSrc)
                                   + " does not compile");
                return new Earned(null, null, EXIT_BAD_INPUT);
            }
            String name = calledName(cc.ast());
            if (name == null || !fns.containsKey(name)) {
                System.err.println("ezr: --example '" + spec
                                   + "': names no defined function");
                return new Earned(null, null, EXIT_BAD_INPUT);
            }

            // Checked at the confidence earned so far, which is how the
            // third Example gets to be the one that clears the floor. A
            // depth-exceeded Example counts as a failure, or the ceiling
            // would be free.
            Particle got  = new Eval(fns, depth, trust).run(body(cc.ast()));
            Particle want = new Eval(Map.of(), depth, Trust.none())
                                .run(body(wc.ast()));
            boolean ok = !got.isZ() && !want.isZ()
                && (got.value == null ? want.value == null
                                      : got.value.equals(want.value));

            // [EXAMPLE] multiplies uncertainty across INDEPENDENT
            // witnesses, and the same case stated twice is one witness,
            // not two. Before this check it was two, in both runners:
            // `-x 'fact(1) = 1'` three times took fact from 120 to 183
            // to 217, exactly as three distinct cases would — real
            // confidence bought with no new evidence, which is the one
            // thing T2 says the algebra must never allow. Keyed on the
            // AST's own rendering, so `f(1,2)` and `f( 1 , 2 )` are
            // correctly the same witness and `f(1)` and `f(2)` are not.
            String key = Ast.render(body(cc.ast()));
            if (seen.containsKey(key)) {
                Object prior = seen.get(key);
                boolean same = prior == null ? want.value == null
                                             : prior.equals(want.value);
                if (!same) {
                    System.err.println("ezr: --example '" + spec + "': " + key
                        + " was already given "
                        + Particle.renderValue(prior) + " as its answer. "
                        + "Evidence that contradicts itself is not evidence.");
                    return new Earned(null, null, EXIT_BAD_INPUT);
                }
                continue;
            }
            seen.put(key, want.value);

            int[] t = tally.computeIfAbsent(name, k -> new int[2]);
            if (ok) t[0]++;
            t[1]++;
            trust.believe(name, Trust.fromExamples(t[0], t[1]));
        }

        for (String name : anchors) {
            Eval.Fn fn = fns.get(name);
            if (fn == null) {
                System.err.println("ezr: --anchor " + name
                                   + ": not defined in " + where);
                return new Earned(null, null, EXIT_BAD_INPUT);
            }
            int conf = trust.of(name);
            if (conf < Particle.EXECUTE_FLOOR) {
                // [ANCHOR-FN] wants a cleared thread. Anchoring an
                // unverified function would grant depth on no evidence.
                // The refusal carries the requirement: the same rule that
                // produced `conf` also answers how much more it takes.
                int[] pt = tally.getOrDefault(name, new int[2]);
                System.err.println("ezr: --anchor " + name + ": refused, "
                    + conf + "/256 is below the execute floor ("
                    + Particle.EXECUTE_FLOOR + "). " + needs(pt[0], pt[1]) + ".");
                return new Earned(null, null, EXIT_REFUSED);
            }
            Ast.Def def = new Ast.Def(fn.name(), fn.params(), fn.body());
            if (Semantic.measure(def) == null && recursive(def)) {
                // [ANCHOR-BOT], the rule that keeps the language honest: a
                // function can sit at 240/256 and still loop forever. Saying
                // only that is the refusal at its least useful, though — the
                // search that just failed knows which parameter went the
                // wrong way.
                System.err.println("ezr: --anchor " + name + ": refused, "
                    + "confidence proves trust, not termination. "
                    + whyNoMeasure(def) + ".");
                return new Earned(null, null, EXIT_REFUSED);
            }
            trust.anchor(name);
        }
        return new Earned(trust, tally, EXIT_OK);
    }

    /** The first '=' that is not part of ==, <=, >= or !=. */
    private static int splitPoint(String t) {
        for (int i = 0; i < t.length(); i++) {
            if (t.charAt(i) != '=') continue;
            if (i + 1 < t.length() && t.charAt(i + 1) == '=') continue;
            if (i > 0 && "=<>!".indexOf(t.charAt(i - 1)) >= 0) continue;
            return i;
        }
        return -1;
    }

    private static Ast body(Ast ast) {
        return (ast instanceof Ast.Prog p && p.expr() != null) ? p.expr() : ast;
    }

    private static String calledName(Ast ast) {
        return body(ast) instanceof Ast.Call c ? c.name() : null;
    }

    private static boolean recursive(Ast.Def def) {
        return calls(def.body(), def.name());
    }

    private static boolean calls(Ast n, String name) {
        if (n instanceof Ast.Call c && c.name().equals(name)) return true;
        return switch (n) {
            case Ast.Bin x  -> calls(x.left(), name) || calls(x.right(), name);
            case Ast.If x   -> calls(x.cond(), name) || calls(x.then(), name)
                               || calls(x.otherwise(), name);
            case Ast.Call x -> x.args().stream().anyMatch(a -> calls(a, name));
            case Ast.Let x  -> calls(x.value(), name) || calls(x.body(), name);
            case Ast.Lst x  -> x.items().stream().anyMatch(a -> calls(a, name));
            case Ast.Def x  -> calls(x.body(), name);
            case Ast.Prog x -> x.defs().stream().anyMatch(d -> calls(d, name));
            default -> false;
        };
    }

    /**
     * What would turn this refusal into an answer, or "" if nothing here
     * can say.
     *
     * <p>Only the depth ceiling is answered, because it is the only runtime
     * refusal whose cure is a thing the language already models. {@code 1/0}
     * has no requirement to state — no evidence makes dividing by zero work,
     * and inventing a suggestion for it would be worse than silence.
     */
    static String lift(Particle result, Eval ev, Map<String, Eval.Fn> fns,
                       Trust trust, Map<String, int[]> tally) {
        if (!result.isZ() || result.reason == null
                || !result.reason.contains("depth ceiling")) return "";
        String name = ev.ceilingName();
        Eval.Fn fn = (name == null) ? null : fns.get(name);
        if (fn == null) return "";
        if (trust.isAnchored(name)) {
            return name + " is anchored already and still ran out of depth at "
                 + Trust.HARD_DEPTH + "; its measure decreases too slowly "
                 + "for this input";
        }
        Ast.Def def = new Ast.Def(fn.name(), fn.params(), fn.body());
        String measure = Semantic.measure(def);
        if (measure == null) return whyNoMeasure(def);
        int conf = trust.of(name);
        if (conf < Particle.EXECUTE_FLOOR) {
            int[] pt = (tally == null) ? new int[2]
                     : tally.getOrDefault(name, new int[2]);
            return name + " decreases " + measure + " in every self-call, so "
                 + "it can be anchored — but anchoring needs the execute "
                 + "floor first, and it sits at " + conf + "/256. "
                 + needs(pt[0], pt[1]) + ", then pass -a " + name;
        }
        return name + " decreases " + measure + " in every self-call and sits "
             + "at " + conf + "/256, above the floor. Pass -a " + name
             + " to buy the depth";
    }

    /** Render the result the way ezrun.py does, and pick the exit code. */
    static int report(Particle result, boolean quiet, String requirement) {
        if (result.isZ()) {
            System.err.println("Z(" + result.defect + ") — " + result.reason);
            if (!requirement.isEmpty()) {
                // A refusal states what the language will not do. This states
                // what would make it willing — the same computation read the
                // other way round.
                System.err.println("       to lift it: " + requirement);
            }
            return EXIT_REFUSED;
        }
        if (quiet) {
            System.out.println(result.render());
        } else {
            System.out.println(result.render() + "  @ " + result.confidence
                               + "/" + Particle.CERTAIN);
        }
        return EXIT_OK;
    }

    /* ── plumbing ───────────────────────────────────────────────────── */

    private static int fail(String msg) {
        System.err.println("ezr: " + msg);
        return EXIT_BAD_INPUT;
    }

    private static String readAll(InputStream in) {
        try {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            return null;
        }
    }

    private static void usage(java.io.PrintStream out) {
        out.println("""
            usage: ezr [-h] [-e EXPR] [-c EXPR] [-d DEPTH] [-q] [file]

            Run an EZR program.

              file          program to run, or - for stdin
              -e, --eval    run one expression instead of a file
              -c, --call    which expression to run after the definitions
              -d, --depth   call-depth limit (default 100)
              -q, --quiet   print the value only, without its confidence

            Exit codes: 0 a value, 1 a refusal (Z), 2 would not compile.""");
    }
}
