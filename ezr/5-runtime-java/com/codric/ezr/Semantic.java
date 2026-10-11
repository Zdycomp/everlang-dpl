package com.codric.ezr;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * Stage 3 — scope resolution, arity checking and type inference, before a
 * single value is computed.
 *
 * <p>This stage is why {@code "ab" * 2} is refused rather than quietly
 * returning {@code "abab"}. Without it the language's {@code *} operator
 * would inherit whatever the host language does to a string and a number —
 * CPython repeats it — and EZR's {@code [OP-tau]} rule would be decided by an
 * implementation detail of the interpreter rather than by SEMANTICS.md. The
 * Java runtime has to do this check itself for exactly the same reason: the
 * JVM would throw instead, which is a different wrong answer.
 *
 * <p>Catching a defect here rather than at evaluation means the binding is
 * checked whether or not that branch ever runs.
 */
public final class Semantic {

    /** What a subexpression is known to hold. ANY means "not determined". */
    public enum Ty {
        NUM("a number"), TEXT("text"), BOOL("a bool"), ANY("any");
        private final String label;
        Ty(String label) { this.label = label; }
        public String label() { return label; }
    }

    /** The result of analysing one tree. */
    public static final class Analysis {
        public final List<String> errors = new ArrayList<>();
        public final Set<String>  free   = new TreeSet<>();
        public final Set<String>  calls  = new LinkedHashSet<>();
        public Ty      ty        = Ty.ANY;
        public boolean recursive = false;
        public String  measure   = null;
        public int     size      = 0;

        public boolean ok() { return errors.isEmpty(); }
    }

    private static final Set<String> COMPARE_OPS =
        Set.of("<", ">", "<=", ">=", "==", "!=");

    /** Names the evaluator answers without a definition. */
    public static final Set<String> BUILTINS =
        Set.of("show", "len", "head", "tail");

    private final Map<String, Integer> fns = new HashMap<>();

    public Semantic() { }

    /** Analyse a whole program. */
    public Analysis analyse(Ast node) {
        Analysis a = new Analysis();

        if (node instanceof Ast.Prog prog) {
            // Two passes. Every name and arity is registered before any body
            // is walked, so `def f(n) = g(n)` followed by `def g(n) = n`
            // resolves — a single pass would call g unbound purely because of
            // the order they happen to be written in.
            for (Ast.Def d : prog.defs()) fns.put(d.name(), d.params().size());

            for (Ast.Def d : prog.defs()) {
                Analysis inner = analyseDef(d);
                for (String msg : inner.errors) {
                    String tagged = "in " + d.name() + ": " + msg;
                    if (!a.errors.contains(tagged)) a.errors.add(tagged);
                }
                a.calls.addAll(inner.calls);
            }
            if (prog.expr() != null) {
                Analysis inner = analyseExpr(prog.expr(), new HashSet<>());
                a.ty = inner.ty;
                a.calls.addAll(inner.calls);
                for (String msg : inner.errors) {
                    if (!a.errors.contains(msg)) a.errors.add(msg);
                }
            } else if (prog.defs().size() == 1) {
                Analysis only = analyseDef(prog.defs().get(0));
                a.ty = only.ty; a.recursive = only.recursive; a.measure = only.measure;
            }
            a.size = Ast.size(prog);
            return a;
        }
        return analyseExpr(node, new HashSet<>());
    }

    private Analysis analyseDef(Ast.Def def) {
        fns.put(def.name(), def.params().size());
        Analysis a = analyseExpr(def.body(), new HashSet<>(def.params()));
        a.recursive = a.calls.contains(def.name());
        def.params().forEach(a.free::remove);
        if (a.recursive) a.measure = measure(def);
        a.size = Ast.size(def);
        for (String name : a.free) {
            String msg = "unbound name '" + name + "'";
            if (!a.errors.contains(msg)) a.errors.add(msg);
        }
        return a;
    }

    private Analysis analyseExpr(Ast node, Set<String> bound) {
        Analysis a = new Analysis();
        a.ty = walk(node, bound, a);
        a.size = Ast.size(node);
        for (String name : a.free) {
            String msg = "unbound name '" + name + "'";
            if (!a.errors.contains(msg)) a.errors.add(msg);
        }
        return a;
    }

    private Ty walk(Ast node, Set<String> bound, Analysis a) {
        return switch (node) {
            case Ast.Num  n -> Ty.NUM;
            case Ast.Str  n -> Ty.TEXT;
            case Ast.Bool n -> Ty.BOOL;

            case Ast.Var v -> {
                if (!bound.contains(v.name())) a.free.add(v.name());
                yield Ty.ANY;
            }

            case Ast.Bin b -> {
                Ty lt = walk(b.left(), bound, a);
                Ty rt = walk(b.right(), bound, a);
                if (COMPARE_OPS.contains(b.op())) {
                    if ((lt == Ty.TEXT || rt == Ty.TEXT) && lt != rt) {
                        a.errors.add("comparing " + lt.label() + " with " + rt.label());
                    }
                    a.ty = Ty.BOOL;
                    yield Ty.BOOL;
                }
                // arithmetic: text takes only '+', bool takes nothing
                checkOperand(lt, "left",  b.op(), a);
                checkOperand(rt, "right", b.op(), a);
                if (b.op().equals("/") && b.right() instanceof Ast.Num n
                        && n.value() == 0) {
                    a.errors.add("division by a literal zero");
                }
                a.ty = Ty.NUM;
                yield Ty.NUM;
            }

            case Ast.If f -> {
                Ty ct = walk(f.cond(), bound, a);
                if (ct == Ty.TEXT) a.errors.add("condition is text, not a truth value");
                Ty tt = walk(f.then(), bound, a);
                Ty et = walk(f.otherwise(), bound, a);
                if (tt != Ty.ANY && et != Ty.ANY && tt != et) {
                    a.errors.add("branches disagree: then is " + tt.label()
                                 + ", else is " + et.label());
                }
                a.ty = (tt == et) ? tt : Ty.ANY;
                yield a.ty;
            }

            case Ast.Lst l -> {
                for (Ast it : l.items()) walk(it, bound, a);
                yield Ty.ANY;
            }

            case Ast.Let l -> {
                walk(l.value(), bound, a);
                Set<String> inner = new HashSet<>(bound);
                inner.add(l.name());
                yield walk(l.body(), inner, a);
            }

            case Ast.Call c -> {
                a.calls.add(c.name());
                for (Ast arg : c.args()) walk(arg, bound, a);
                Integer expected = fns.get(c.name());
                if (expected != null && expected != c.args().size()) {
                    a.errors.add(c.name() + " takes " + expected
                                 + " argument(s), given " + c.args().size());
                }
                yield Ty.ANY;
            }

            case Ast.Def d -> {
                fns.put(d.name(), d.params().size());
                yield walk(d.body(), new HashSet<>(d.params()), a);
            }

            case Ast.Prog p -> Ty.ANY;   // handled by analyse()
        };
    }

    private static void checkOperand(Ty t, String side, String op, Analysis a) {
        if (t == Ty.TEXT && !op.equals("+")) {
            a.errors.add("cannot apply '" + op + "' to text on the " + side);
        }
        if (t == Ty.BOOL) {
            a.errors.add("cannot apply '" + op + "' to a bool on the " + side);
        }
    }

    /* ── the measure, SEMANTICS.md 4.5 ──────────────────────────────── */

    /**
     * The parameter that strictly decreases in every self-call, or null.
     *
     * <p>Deliberately conservative and syntactic: {@code m - k} for k &gt; 0
     * and {@code m / k} for k &gt; 1 are the recognised forms. When decrease
     * cannot be proven the answer is null and the ceiling stays at
     * floor(pi) = 3. Refusing to guess is the point — a wrong termination
     * proof is worse than no proof.
     *
     * <p>On the tree this sees through parentheses and nesting that the old
     * string version missed: {@code deep((n) - 1)} is recognised.
     */
    public static String measure(Ast.Def fn) {
        List<Ast.Call> calls = new ArrayList<>();
        collectSelfCalls(fn.body(), fn.name(), calls);
        if (calls.isEmpty()) return null;

        List<String> params = fn.params();
        for (int idx = 0; idx < params.size(); idx++) {
            String p = params.get(idx);
            boolean good = true;
            for (Ast.Call call : calls) {
                if (idx >= call.args().size()) { good = false; break; }
                if (!decreases(call.args().get(idx), p)) { good = false; break; }
            }
            if (good) return p;
        }
        return null;
    }

    /**
     * How each parameter moves in every self-call, as a printable phrase.
     *
     * <p>The same walk {@link #measure} does — this one keeps what it
     * learned instead of collapsing it to a name or a null. When measure
     * returns null it knows, at that instant, that {@code i} went <em>up</em>
     * by one and {@code n} never moved, and it discards both. That
     * discarded half is the only part a person can act on.
     *
     * <p>Returns null when the function does not call itself: there is then
     * no measure question to answer.
     */
    public static java.util.LinkedHashMap<String, String> movements(Ast.Def fn) {
        List<Ast.Call> calls = new ArrayList<>();
        collectSelfCalls(fn.body(), fn.name(), calls);
        if (calls.isEmpty()) return null;

        var out = new java.util.LinkedHashMap<String, String>();
        List<String> params = fn.params();
        for (int idx = 0; idx < params.size(); idx++) {
            var how = new java.util.TreeSet<String>();
            for (Ast.Call call : calls) {
                if (idx >= call.args().size()) { how.add("not passed"); continue; }
                how.add(movement(call.args().get(idx), params.get(idx)));
            }
            out.put(params.get(idx), String.join(", ", how));
        }
        return out;
    }

    private static String movement(Ast arg, String param) {
        if (arg instanceof Ast.Var v && v.name().equals(param)) return "unchanged";
        if (arg instanceof Ast.Bin b
                && b.left() instanceof Ast.Var v && v.name().equals(param)
                && b.right() instanceof Ast.Num k) {
            double d = k.value();
            String n = Particle.renderValue(d);
            if (b.op().equals("-") && d > 0) return "decreases by " + n;
            if (b.op().equals("+") && d > 0) return "increases by " + n;
            if (b.op().equals("/") && d > 1) return "divides by " + n;
            if (b.op().equals("*") && d > 1) return "multiplies by " + n;
            return "changes by " + b.op() + " " + n;
        }
        return "not a simple step";
    }

    private static boolean decreases(Ast arg, String param) {
        if (!(arg instanceof Ast.Bin b)) return false;
        if (!(b.left() instanceof Ast.Var v) || !v.name().equals(param)) return false;
        if (!(b.right() instanceof Ast.Num k)) return false;
        if (b.op().equals("-") && k.value() > 0) return true;
        return b.op().equals("/") && k.value() > 1;
    }

    private static void collectSelfCalls(Ast n, String name, List<Ast.Call> out) {
        if (n instanceof Ast.Call c && c.name().equals(name)) out.add(c);
        for (Ast child : children(n)) collectSelfCalls(child, name, out);
    }

    private static List<Ast> children(Ast n) {
        return switch (n) {
            case Ast.Bin  x -> List.of(x.left(), x.right());
            case Ast.If   x -> List.of(x.cond(), x.then(), x.otherwise());
            case Ast.Call x -> List.copyOf(x.args());
            case Ast.Def  x -> List.of(x.body());
            case Ast.Let  x -> List.of(x.value(), x.body());
            case Ast.Lst  x -> List.copyOf(x.items());
            case Ast.Prog x -> {
                List<Ast> kids = new ArrayList<>(x.defs());
                if (x.expr() != null) kids.add(x.expr());
                yield kids;
            }
            case Ast.Num  x -> List.of();
            case Ast.Str  x -> List.of();
            case Ast.Bool x -> List.of();
            case Ast.Var  x -> List.of();
        };
    }
}
