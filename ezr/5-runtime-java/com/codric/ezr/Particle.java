package com.codric.ezr;

import java.util.List;

/**
 * The only kind of value EZR has.
 *
 * <p>SEMANTICS.md section 1 calls this a <em>thread</em>. This class is not
 * called Thread, because a type named {@code Thread} in this package would
 * shadow {@code java.lang.Thread} for every file in it — the kind of
 * cross-language trap this layer exists to find rather than create. It takes
 * the name the C atom gives the same struct: {@code e_particle}.
 *
 * <p>Immutable. G9 (no mutation) is a guarantee of the language, so it is a
 * property of this class: every field is final and every operation derives a
 * new particle rather than writing to an old one.
 */
public final class Particle {

    /* ── the scale, from SEMANTICS.md 1.1. Load-bearing. ────────────── */

    public static final int ZERO             = 0;
    public static final int CERTAIN          = 256;   // 4^4
    public static final int EXECUTE_FLOOR    = 128;   // 256 / 2
    public static final int PI_WARN          = 81;    // floor(256 / pi)
    public static final int PI_ENUMERATE     = 25;    // floor(256 / pi^2)
    public static final int DEPTH_CEILING    = 3;     // floor(pi)
    public static final int ASCEND_POINTS    = 3;     // floor(pi)
    public static final int INTAKE           = 120;   // external data, pre-evidence

    /** Binding modes. Mirrors e_state in the C atom, same ordinals. */
    public enum State {
        Z, CONFIDENT, CERTAIN_S, EQUIVALENCE, EXPRESSION,
        EMULATING, EVOLVED, ANCHORED, ABSENT, EERROR
    }

    /** The five ways a binding fails. Mirrors e_defect, same ordinals. */
    public enum Defect {
        NONE, UNBOUND, MISBOUND, UNBOUNDED, OVERBOUND, ORPHANED;

        @Override public String toString() {
            return name().toLowerCase();
        }
    }

    /** Source language. Mirrors e_lang; JAVA is 5, which is this layer. */
    public enum Lang {
        C, CPP, PYTHON, RUBY, SQL, JAVA, HTML, RUST, GO, TS, SWIFT, EZR
    }

    /* ── the thread, SEMANTICS.md section 1 ─────────────────────────── */

    public final Object  value;      // v   Long | Double | String | Boolean | List | Closure | null
    public final State   state;      // sigma
    public final int     confidence; // c   0..256
    public final int     lo, hi;     // bounds; lo == hi == c unless EQUIVALENCE
    public final Lang    lang;       // l
    public final int     anchor;     // alpha, 0 = unanchored
    public final Defect  defect;     // delta
    public final int     generation; // g
    public final String  reason;     // rho, preserved always

    private Particle(Object value, State state, int confidence, int lo, int hi,
                     Lang lang, int anchor, Defect defect, int generation,
                     String reason) {
        this.value      = value;
        this.state      = state;
        this.confidence = confidence;
        this.lo         = lo;
        this.hi         = hi;
        this.lang       = lang;
        this.anchor     = anchor;
        this.defect     = defect;
        this.generation = generation;
        this.reason     = reason;
    }

    /* ── constructors ───────────────────────────────────────────────── */

    /**
     * A program constant. SEMANTICS.md 1.2: the author wrote {@code 1}; it is
     * {@code 1}. Literals carry no uncertainty about their own value, so they
     * enter at CERTAIN. Treating them as external input floors every
     * computation in the language at INTAKE forever.
     */
    public static Particle certain(Object v) {
        return new Particle(v, State.CERTAIN_S, CERTAIN, CERTAIN, CERTAIN,
                            Lang.JAVA, 0, Defect.NONE, 0, "program constant");
    }

    /** A value at a stated confidence. */
    public static Particle of(Object v, int c) {
        int k = clamp(c);
        State s = (k == CERTAIN) ? State.CERTAIN_S : State.CONFIDENT;
        return new Particle(v, s, k, k, k, Lang.JAVA, 0, Defect.NONE, 0, "");
    }

    /** External data, lifted from outside. SEMANTICS.md 1.2. */
    public static Particle intake(Object v, Lang from) {
        return new Particle(v, State.CONFIDENT, INTAKE, INTAKE, INTAKE,
                            from, 0, Defect.NONE, 0, "external, pre-evidence");
    }

    /** Maximum uncertainty. Absorbing under corroboration (T1). */
    public static Particle z(Defect d, String why) {
        return new Particle(null, State.Z, ZERO, ZERO, ZERO,
                            Lang.JAVA, 0, d, 0, why);
    }

    /** A span: "it is one of these two", SEMANTICS.md 5.2. */
    public static Particle equivalence(double lo, double hi, int c) {
        int k = clamp(c);
        return new Particle(new double[] { lo, hi }, State.EQUIVALENCE, k,
                            (int) Math.round(lo), (int) Math.round(hi),
                            Lang.JAVA, 0, Defect.NONE, 0, "spanned by an unknown condition");
    }

    /* ── derivations. Every one returns a new particle. ─────────────── */

    /** Same thread at a different confidence, reason preserved. */
    public Particle at(int c) {
        int k = clamp(c);
        State s = (state == State.ANCHORED) ? State.ANCHORED
                : (k == CERTAIN)            ? State.CERTAIN_S
                                            : State.CONFIDENT;
        return new Particle(value, s, k, k, k, lang, anchor, defect, generation, reason);
    }

    /** Same confidence, different value. Used by the builtins. */
    public Particle withValue(Object v) {
        return new Particle(v, state, confidence, lo, hi, lang, anchor,
                            defect, generation, reason);
    }

    /** Same thread, now attributed to another language. See Laws.assimilate. */
    public Particle inLang(Lang to, String why) {
        return new Particle(value, state, confidence, lo, hi, to, anchor,
                            defect, generation, why);
    }

    /**
     * [ANCHOR-FN] / [ANCHOR-REC]. The caller is responsible for the measure
     * check; this only pins the identity.
     */
    public Particle anchored(int id) {
        return new Particle(value, State.ANCHORED, confidence, lo, hi, lang,
                            id, defect, generation, "anchor " + id);
    }

    /* ── predicates ─────────────────────────────────────────────────── */

    public boolean isZ()        { return state == State.Z; }
    public boolean isAnchored() { return state == State.ANCHORED && anchor != 0; }
    public boolean canExecute() { return !isZ() && confidence >= EXECUTE_FLOOR; }
    public boolean isCleared()  { return !isZ() && confidence >= EXECUTE_FLOOR; }
    public int     width()      { return hi - lo; }

    /** Uncertainty, the quantity the laws are stated over. u = (256-c)/256. */
    public double uncertainty() { return (CERTAIN - confidence) / (double) CERTAIN; }

    /* ── pi's verdict on a span, SEMANTICS.md 5.2 ───────────────────── */

    public enum PiVerdict { ACCEPTABLE, ENUMERATE, COLLAPSE }

    public static PiVerdict piCheck(int width) {
        if (width <= PI_ENUMERATE) return PiVerdict.ACCEPTABLE;
        if (width <= PI_WARN)      return PiVerdict.ENUMERATE;
        return PiVerdict.COLLAPSE;
    }

    /* ── rendering, byte-compatible with ezrun.py ───────────────────── */

    /** How the value prints. Must match the Python runner exactly. */
    public String render() {
        return renderValue(value);
    }

    static String renderValue(Object v) {
        if (v == null)            return "None";
        if (v instanceof Boolean) return ((Boolean) v) ? "True" : "False";
        if (v instanceof Double) {
            // A whole number renders without a decimal point. The reference
            // interpreter normalises float to int whenever the value is
            // whole, so 4 / 2 is "2" and not "2.0"; rendering it Java's way
            // would diverge from Python on almost every arithmetic result.
            double d = (Double) v;
            if (d == Math.floor(d) && !Double.isInfinite(d)) {
                // Every magnitude, not just the ones that fit in a long.
                // The reference interpreter converts a whole float with
                // Python's int(), which is arbitrary precision and never
                // falls back to scientific notation — 1e25 prints as
                // 10000000000000000905969664, the double's exact value.
                // A `long` cast gives up at 2^63 and String.valueOf gives
                // up at 1e7, so both diverge on any deep result. This only
                // became reachable once anchoring bought the depth to
                // compute numbers that big.
                return new java.math.BigDecimal(d).toBigInteger().toString();
            }
            return String.valueOf(d);
        }
        if (v instanceof double[]) {
            double[] span = (double[]) v;
            return "[" + renderValue(span[0]) + " .. " + renderValue(span[1]) + "]";
        }
        if (v instanceof List) {
            StringBuilder sb = new StringBuilder("[");
            List<?> xs = (List<?>) v;
            for (int i = 0; i < xs.size(); i++) {
                if (i > 0) sb.append(", ");
                Object e = xs.get(i);
                sb.append(e instanceof Particle ? ((Particle) e).render()
                                                : renderNested(e));
            }
            return sb.append("]").toString();
        }
        return String.valueOf(v);
    }

    /**
     * How a value renders <em>inside a list</em>, which is not how it renders
     * on its own.
     *
     * <p><strong>This is an open question, not a decision.</strong> EZR
     * prints a bare string unquoted — {@code "hello"} runs to {@code hello} —
     * but prints it quoted inside a list, {@code ['a', 'b']}. The same value
     * renders two ways depending on nesting, which came from the reference
     * interpreter formatting lists through CPython's {@code repr}: it was
     * inherited, not chosen.
     *
     * <p>The Java runtime reproduces it rather than quietly fixing it.
     * Arbitration withholds here — no document specifies rendering, no law
     * settles it, and two implementations is below the floor(pi) = 3 that
     * consensus needs — and when arbitration withholds, the incumbent
     * stands and the disagreement gets written down. See FINDINGS.md.
     */
    static String renderNested(Object v) {
        if (v instanceof String s) {
            // CPython's rule: single quotes, unless the text contains a
            // single quote and no double quote.
            boolean useDouble = s.indexOf('\'') >= 0 && s.indexOf('"') < 0;
            char q = useDouble ? '"' : '\'';
            return q + s + q;
        }
        return renderValue(v);
    }

    @Override public String toString() {
        if (isZ()) return "Z(" + defect + ") " + reason;
        return render() + "  @ " + confidence + "/" + CERTAIN;
    }

    static int clamp(int c) {
        return c < ZERO ? ZERO : (c > CERTAIN ? CERTAIN : c);
    }
}
