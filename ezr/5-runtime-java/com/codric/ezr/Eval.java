package com.codric.ezr;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.codric.ezr.Particle.Defect;

/**
 * Stage 4 — execution over the tree.
 *
 * <p>SEMANTICS.md sections 3 to 5: chain by min, Z absorbs, a Z condition
 * spans both branches, branches are lazy under a known condition.
 *
 * <p><strong>G1 — evaluation is total.</strong> Every method here returns a
 * well-formed particle. Nothing throws. The exhaustive switch over the sealed
 * {@link Ast} makes the "every node is handled" half of that a compile-time
 * check; the "no exception escapes" half is why arithmetic, list indexing and
 * recursion each carry an explicit refusal rather than relying on the JVM to
 * raise. A StackOverflowError is caught at the boundary and returned as a Z,
 * because a runtime that dies is not total no matter what the rules say.
 *
 * <p><strong>Depth.</strong> This evaluator has no anchor mechanism, so it
 * cannot grant earned depth — that rule lives in layer 2's {@code Lambda},
 * and the Python AST evaluator has the same seam and says so. What is here is
 * a checked halt (G8): past the limit, a call returns
 * {@code Z(unbounded)} rather than recursing.
 */
public final class Eval {

    /** A user definition, as the evaluator needs it. */
    public record Fn(String name, List<String> params, Ast body) { }

    private final Map<String, Fn> fns;
    private final int limit;
    private final Trust trust;
    private final StringBuilder shown = new StringBuilder();

    /**
     * The function whose call last hit the depth ceiling, or null.
     *
     * <p>A Particle carries no identity — deliberately, since the value
     * domain is shared with the C atom and adding a field there would
     * ripple everywhere. But a refusal that cannot say *which* function ran
     * out of depth cannot say how to buy more, so the name is recorded
     * here, where only the runner reads it. Nothing in the evaluator
     * branches on it and no Particle changes shape, so the two runtimes
     * still agree byte for byte on the refusal itself.
     */
    private String ceilingName = null;

    /** @see #ceilingName */
    public String ceilingName() { return ceilingName; }

    public Eval(Map<String, Fn> fns, int limit) {
        this(fns, limit, Trust.none());
    }

    /** With evidence: what each definition has earned, and what it may cash. */
    public Eval(Map<String, Fn> fns, int limit, Trust trust) {
        this.fns   = fns;
        this.limit = limit;
        this.trust = trust;
    }

    /** Anything {@code show} printed, in order. */
    public String shownOutput() { return shown.toString(); }

    /** Collect the definitions out of a parsed program. */
    public static Map<String, Fn> definitions(Ast ast) {
        Map<String, Fn> out = new LinkedHashMap<>();
        if (ast instanceof Ast.Prog p) {
            for (Ast.Def d : p.defs()) {
                out.put(d.name(), new Fn(d.name(), d.params(), d.body()));
            }
        }
        return out;
    }

    /** Evaluate, catching even a stack overflow so that G1 holds. */
    public Particle run(Ast node) {
        try {
            return eval(node, new HashMap<>(), 0);
        } catch (StackOverflowError so) {
            return Particle.z(Defect.UNBOUNDED,
                "recursion exhausted the runtime stack before the depth limit");
        }
    }

    /* ── the rules ──────────────────────────────────────────────────── */

    private Particle eval(Ast node, Map<String, Particle> env, int depth) {
        return switch (node) {

            // 3.1 [LIT]. A program constant enters at CERTAIN: the author
            // wrote it, so there is no uncertainty about what it says. An
            // earlier draft entered literals at INTAKE and floored every
            // computation in the language below the execute floor forever.
            case Ast.Num  n -> Particle.certain(n.value());
            case Ast.Str  n -> Particle.certain(n.value());
            case Ast.Bool n -> Particle.certain(n.value());

            // 3.2 [VAR] / [VAR-Z]
            case Ast.Var v -> {
                Particle p = env.get(v.name());
                yield p != null ? p
                    : Particle.z(Defect.UNBOUND, v.name() + " was never bound");
            }

            case Ast.Bin b   -> binary(b, env, depth);
            case Ast.If  f   -> conditional(f, env, depth);
            case Ast.Call c  -> call(c, env, depth);
            case Ast.Lst l   -> list(l, env, depth);
            case Ast.Let l   -> let(l, env, depth);

            case Ast.Def d   -> Particle.of(d.name(), Particle.INTAKE);
            case Ast.Prog p  -> p.expr() != null ? eval(p.expr(), env, depth)
                                                 : Particle.z(Defect.UNBOUND,
                                       "a program of definitions has no value "
                                       + "of its own; call one of them");
        };
    }

    /* ── 3.3 arithmetic and comparison ──────────────────────────────── */

    private Particle binary(Ast.Bin b, Map<String, Particle> env, int depth) {
        Particle a = eval(b.left(), env, depth);
        if (a.isZ()) return a;                       // [OP-Z], and left-first
        Particle c = eval(b.right(), env, depth);
        if (c.isZ()) return c;

        int conf = Laws.chain(a.confidence, c.confidence);   // [OP], [CHAIN]
        Object x = a.value, y = c.value;

        if (Ast.isCompare(b.op())) return compare(b.op(), x, y, conf);

        // '+' over two texts is concatenation; everything else needs numbers
        if (b.op().equals("+") && x instanceof String && y instanceof String) {
            return Particle.of((String) x + (String) y, conf);
        }
        if (!(x instanceof Double) || !(y instanceof Double)) {   // [OP-tau]
            return Particle.z(Defect.MISBOUND,
                "cannot " + b.op() + " " + typeName(x) + " with " + typeName(y));
        }
        double l = (Double) x, r = (Double) y;
        return switch (b.op()) {
            case "+" -> Particle.of(l + r, conf);
            case "-" -> Particle.of(l - r, conf);
            case "*" -> Particle.of(l * r, conf);
            case "/" -> r == 0.0
                        ? Particle.z(Defect.MISBOUND, "division by zero")
                        : Particle.of(l / r, conf);
            default  -> Particle.z(Defect.MISBOUND, "unknown operator " + b.op());
        };
    }

    private Particle compare(String op, Object x, Object y, int conf) {
        if (x instanceof Double && y instanceof Double) {
            double l = (Double) x, r = (Double) y;
            return Particle.of(switch (op) {
                case "<"  -> l <  r;  case ">"  -> l >  r;
                case "<=" -> l <= r;  case ">=" -> l >= r;
                case "==" -> l == r;  default   -> l != r;
            }, conf);
        }
        // equality is defined on any two values of the same kind; ordering
        // is not, so a '<' between texts is a refusal rather than a guess
        if (op.equals("==") || op.equals("!=")) {
            boolean same = (x == null) ? y == null : x.equals(y);
            return Particle.of(op.equals("==") == same, conf);
        }
        if (x instanceof String && y instanceof String) {
            int cmp = ((String) x).compareTo((String) y);
            return Particle.of(switch (op) {
                case "<"  -> cmp <  0;  case ">"  -> cmp >  0;
                case "<=" -> cmp <= 0;  default   -> cmp >= 0;
            }, conf);
        }
        return Particle.z(Defect.MISBOUND,
            "cannot order " + typeName(x) + " against " + typeName(y));
    }

    /* ── 5. conditionals ────────────────────────────────────────────── */

    private Particle conditional(Ast.If f, Map<String, Particle> env, int depth) {
        Particle cond = eval(f.cond(), env, depth);

        if (!cond.isZ()) {
            // 5.1 [IF-T] / [IF-F] — lazy. The untaken arm is NOT evaluated.
            // This is required, not an optimisation: evaluating both arms
            // eagerly makes every recursive function non-terminating,
            // because the recursive arm runs even when the base case won.
            Ast taken = truthy(cond.value) ? f.then() : f.otherwise();
            Particle r = eval(taken, env, depth);
            if (r.isZ()) return r;
            return r.at(Laws.chain(cond.confidence, r.confidence));
        }

        // 5.2 [IF-Z] — unknown condition: eager, and it spans. "It is one of
        // these two" is real information; discarding it would be a lie in
        // the other direction.
        Particle a = eval(f.then(), env, depth);
        Particle c = eval(f.otherwise(), env, depth);
        if (a.isZ() || c.isZ()) {
            return Particle.z(Defect.UNBOUND, "condition unknown and a branch is Z");
        }
        int conf = Laws.chain(a.confidence, c.confidence);

        // [IF-AGREE] — both arms agree, so the ignorance is moot
        if (a.value == null ? c.value == null : a.value.equals(c.value)) {
            return a.at(conf);
        }
        if (!(a.value instanceof Double) || !(c.value instanceof Double)) {
            return Particle.z(Defect.UNBOUNDED, "branches are not spannable"); // [IF-BOT]
        }
        long l = (long) (double) (Double) a.value;
        long r = (long) (double) (Double) c.value;
        long lo = Math.min(l, r), hi = Math.max(l, r);
        if (hi - lo > Particle.PI_WARN) {           // pi judges the width
            return Particle.z(Defect.UNBOUNDED,
                "branches span " + (hi - lo) + ", past the pi threshold");
        }
        return Particle.equivalence(lo, hi, conf);
    }

    /** Only false and Z are false. Everything else is a truth value of yes. */
    private static boolean truthy(Object v) {
        if (v == null)            return false;
        if (v instanceof Boolean) return (Boolean) v;
        if (v instanceof Double)  return (Double) v != 0.0;
        if (v instanceof String)  return !((String) v).isEmpty();
        if (v instanceof List)    return !((List<?>) v).isEmpty();
        return true;
    }

    /* ── 4.3 application ────────────────────────────────────────────── */

    private Particle call(Ast.Call c, Map<String, Particle> env, int depth) {
        Fn fn = fns.get(c.name());

        if (fn == null) {                            // a builtin, or nothing
            List<Particle> args = new ArrayList<>();
            for (Ast a : c.args()) {
                Particle p = eval(a, env, depth);
                if (p.isZ()) return p;               // Z absorbs
                args.add(p);
            }
            Particle built = builtin(c.name(), args);
            if (built != null) return built;
            return Particle.z(Defect.UNBOUND, c.name() + " was never defined");
        }

        // G8 — a checked halt, not a hang, and checked before recursing.
        // [ANCHOR-REC] lifts the ceiling for an anchored function with a
        // proven measure, and for nothing else: depth is earned.
        int ceiling = trust.limitFor(c.name(), limit);
        if (depth > ceiling) {
            ceilingName = c.name();
            return Particle.z(Defect.UNBOUNDED, "depth ceiling " + ceiling + " exceeded");
        }
        List<Particle> args = new ArrayList<>();
        for (Ast a : c.args()) {
            Particle p = eval(a, env, depth);
            if (p.isZ()) return p;
            args.add(p);
        }
        if (args.size() != fn.params().size()) {
            return Particle.z(Defect.MISBOUND, "expected " + fn.params().size()
                              + " argument(s), got " + args.size());
        }
        Map<String, Particle> local = new HashMap<>();
        for (int i = 0; i < args.size(); i++) local.put(fn.params().get(i), args.get(i));

        Particle r = eval(fn.body(), local, depth + 1);
        if (r.isZ()) return r;

        // [APP]: min(c_f, c_args, c_result). The c_f term is the one that
        // was missing — a result is only as trustworthy as the function that
        // produced it, which is the whole point of the language.
        int conf = Math.min(r.confidence, trust.of(c.name()));
        for (Particle a : args) conf = Math.min(conf, a.confidence);
        return r.at(conf);
    }

    /* ── builtins ───────────────────────────────────────────────────── */

    private Particle builtin(String name, List<Particle> args) {
        if (!Semantic.BUILTINS.contains(name)) return null;

        if (name.equals("show")) {
            if (args.size() != 1) {
                return Particle.z(Defect.MISBOUND, "show takes 1 argument");
            }
            Particle a = args.get(0);
            String line = a.render() + "  @ " + a.confidence + "/256";
            System.out.println(line);
            shown.append(line).append('\n');
            return a;                                // identity, so it composes
        }
        if (args.size() != 1) {
            return Particle.z(Defect.MISBOUND, name + " takes 1 argument");
        }
        Particle a = args.get(0);
        if (!(a.value instanceof List)) {
            return Particle.z(Defect.MISBOUND,
                name + " needs a list, got " + typeName(a.value));
        }
        List<?> xs = (List<?>) a.value;
        if (name.equals("len")) return Particle.of((double) xs.size(), a.confidence);

        // An empty list has no head and no tail. That is a refusal, not an
        // exception and not a silent empty answer.
        if (xs.isEmpty()) {
            return Particle.z(Defect.UNBOUND, name + " of an empty list");
        }
        if (name.equals("head")) return Particle.of(xs.get(0), a.confidence);
        return Particle.of(new ArrayList<>(xs.subList(1, xs.size())), a.confidence);
    }

    /* ── lists and let ──────────────────────────────────────────────── */

    private Particle list(Ast.Lst l, Map<String, Particle> env, int depth) {
        List<Object> vals = new ArrayList<>();
        int conf = Particle.CERTAIN;                 // an empty list is certain
        for (Ast it : l.items()) {
            Particle r = eval(it, env, depth);
            if (r.isZ()) return r;                   // T1, Z absorbs
            vals.add(r.value);
            conf = Math.min(conf, r.confidence);     // the chain rule, over elements
        }
        return Particle.of(vals, conf);
    }

    private Particle let(Ast.Let l, Map<String, Particle> env, int depth) {
        Particle bound = eval(l.value(), env, depth);
        if (bound.isZ()) return bound;
        Map<String, Particle> inner = new HashMap<>(env);
        inner.put(l.name(), bound);
        return eval(l.body(), inner, depth);
    }

    /* ── names for the refusal messages ─────────────────────────────── */

    static String typeName(Object v) {
        if (v == null)             return "nothing";
        if (v instanceof Double)   return "a number";
        if (v instanceof String)   return "text";
        if (v instanceof Boolean)  return "a bool";
        if (v instanceof List)     return "a list";
        if (v instanceof double[]) return "a span";
        return v.getClass().getSimpleName();
    }
}
