package com.codric.ezr;

/**
 * The two composition laws, and the crossing rule.
 *
 * <p>SEMANTICS.md section 2 is emphatic that EZR has <em>two</em> operators
 * drawn from <em>two</em> formalisms answering <em>two</em> questions, and
 * that silently mixing them would be an error. They are kept in one file so
 * that the distinction is visible rather than scattered.
 */
public final class Laws {

    private Laws() { }

    /* ── 2.1 Chain — min. "What is the floor?" ──────────────────────── */

    /**
     * [CHAIN] — the possibilistic rule (Zadeh). A result is no more trusted
     * than its weakest participant.
     *
     * <p>This is a <strong>bound, not a probability</strong>, and must never
     * be reported as one. Chosen over the probabilistic rule because chains
     * compose without collapsing; the cost is that min does not track
     * accumulated independent error, and EZR accepts that cost openly.
     */
    public static int chain(int... confidences) {
        int m = Particle.CERTAIN;
        for (int c : confidences) if (c < m) m = c;
        return m;
    }

    /* ── 2.2 Corroborate — multiplicative uncertainty ───────────────── */

    /**
     * [EXCEL] — u(a + b) = u(a) * u(b), for independent witnesses that agree
     * on the value. Equivalently c = a + b - floor(ab/256).
     *
     * <p>Capped one short of CERTAIN by T3: a product of non-zero ignorances
     * is never zero, so combination approaches Certain without attaining it.
     * The integer scale used to round the last fraction away and hand back
     * 256, which manufactured Certain out of accumulated evidence.
     *
     * <p>Byte-identical to {@code e_excel_formula} in the C atom and
     * {@code excel} in the Python interpreter, which agree across the full
     * 1089-cell grid.
     */
    public static int corroborate(int a, int b) {
        if (a >= Particle.CERTAIN && b >= Particle.CERTAIN) return Particle.CERTAIN;
        int v = a + b - (a * b / Particle.CERTAIN);
        if (v > Particle.CERTAIN - 1) v = Particle.CERTAIN - 1;
        if (v < Particle.ZERO)        v = Particle.ZERO;
        return v;
    }

    /**
     * [EXAMPLE] — how a function earns confidence, SEMANTICS.md 4.2.
     *
     * <p>u_f = ((256-120)/256)^p, then c_f = floor(256 * (1-u_f) * p/t),
     * capped at 255. Each passing Example is an independent witness at intake
     * strength, so Examples corroborate rather than chain. One Example no
     * more verifies a function than one observation lets a binding Ascend.
     *
     * @param passing how many Examples passed. A depth-exceeded Example
     *                counts as a failure, or the ceiling would be free.
     * @param total   how many Examples were offered.
     */
    /**
     * [EXAMPLE], solved for the missing evidence instead of the score.
     *
     * <p>{@link #fromExamples} runs the rule forwards: given p of t
     * witnesses, here is what you are worth. This runs it backwards: you
     * are worth 120 and need 128, so how many more passing witnesses is
     * that? The answer is 1, and that is a sentence somebody can act on —
     * unlike "below the execute floor", which is the same fact with the
     * actionable half deleted.
     *
     * <p>Nothing is inverted analytically because nothing needs to be: the
     * forward rule is monotone in k and saturates one short of CERTAIN, so
     * walking k up from 0 finds the least sufficient k or establishes there
     * is none. A failure already recorded cannot be withdrawn, so the
     * answer accounts for it — 1 of 9 needs eight more, not one.
     *
     * @return the least k, or -1 when the target is out of reach within cap
     */
    public static int witnessesNeeded(int passing, int total, int target, int cap) {
        for (int k = 0; k <= cap; k++) {
            if (fromExamples(passing + k, total + k) >= target) return k;
        }
        return -1;
    }

    /** {@link #witnessesNeeded} at the execute floor, within 64 witnesses. */
    public static int witnessesNeeded(int passing, int total) {
        return witnessesNeeded(passing, total, Particle.EXECUTE_FLOOR, 64);
    }

    public static int fromExamples(int passing, int total) {
        if (total <= 0) return Particle.ZERO;
        double unit = (Particle.CERTAIN - Particle.INTAKE) / (double) Particle.CERTAIN;
        double u    = Math.pow(unit, passing);
        int    c    = (int) Math.floor(Particle.CERTAIN * (1.0 - u) * (passing / (double) total));
        if (c > Particle.CERTAIN - 1) c = Particle.CERTAIN - 1;
        if (c < Particle.ZERO)        c = Particle.ZERO;
        return c;
    }

    /* ── the three theorems, as checkable predicates ────────────────── */

    /** T1 — Z is absorbing. u(Z) = 1 and 1 * x = 1. */
    public static boolean zIsAbsorbing(int other) {
        return corroborate(Particle.ZERO, other) == other
            && Particle.z(Particle.Defect.UNBOUND, "t1").uncertainty() == 1.0;
    }

    /** T2 — corroboration creates nothing it was not given. */
    public static boolean corroborationCreatesNothing(int a, int b) {
        double ua = (Particle.CERTAIN - a) / (double) Particle.CERTAIN;
        double ub = (Particle.CERTAIN - b) / (double) Particle.CERTAIN;
        double uc = (Particle.CERTAIN - corroborate(a, b)) / (double) Particle.CERTAIN;
        return uc <= ua + 1e-9 && uc <= ub + 1e-9;   // never more ignorant than either
    }

    /** T3 — Certain is unreachable by combination. */
    public static boolean certainUnreachable(int a, int b) {
        if (a >= Particle.CERTAIN && b >= Particle.CERTAIN) return true;  // entered, not combined
        return corroborate(a, b) < Particle.CERTAIN;
    }

    /* ── crossing a language boundary: G6 and G7 ────────────────────── */

    /**
     * Assimilate — move a particle into another language.
     *
     * <ul>
     *   <li><strong>G6</strong>: an anchored thread crosses losslessly.</li>
     *   <li><strong>G7</strong>: an unanchored one loses exactly 1 per hop.</li>
     * </ul>
     *
     * <p>Z does not translate: it stays Z, carrying its defect. Mirrors
     * {@code a_assimilate} in the C atom.
     */
    public static Particle assimilate(Particle p, Particle.Lang to) {
        if (p.isZ()) return Particle.z(p.defect, "Z does not translate");
        if (p.state == Particle.State.EERROR) {
            return Particle.z(Particle.Defect.MISBOUND,
                              "misbound particle does not translate");
        }
        if (p.lang == to) return p;

        if (p.isAnchored()) {                                   // G6
            return p.inLang(to, "assimilated " + p.lang + " to " + to
                                + ", anchor " + p.anchor + " held");
        }
        int c = p.confidence > 1 ? p.confidence - 1 : p.confidence;   // G7
        return p.at(c).inLang(to, "assimilated " + p.lang + " to " + to
                                  + ", unanchored, -1 confidence");
    }
}
