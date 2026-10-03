package com.codric.ever;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * EverRuntime.java — Ever Language, Layer 5 (Java)
 *
 * The runtime. Guardrails, phase interaction, force loops, and the
 * Examine → Evaluate → Execute pipeline.
 *
 * This is the layer that goes into somebody else's build. It must never
 * let an unverified value through, and it must be able to say exactly
 * why it stopped.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */
public final class EverRuntime {

    /* ═════════════════════════════════════════
     * Expect — the gate
     * ═════════════════════════════════════════ */

    public static final class ExpectFailure extends RuntimeException {
        public ExpectFailure(String m) { super(m); }
    }

    public static final class Gate {
        private final EParticle p;
        private final List<String> failures = new ArrayList<>();

        private Gate(EParticle p) { this.p = p; }

        public static Gate on(EParticle p) { return new Gate(p); }

        public Gate notZ() {
            if (p.isZ()) failures.add("is Z: " + p.reason());
            return this;
        }

        public Gate cleared() {
            if (!p.isCleared()) failures.add("not cleared");
            return this;
        }

        public Gate minConfidence(int min) {
            if (p.confidence() < min)
                failures.add("confidence " + p.confidence() + " below " + min);
            return this;
        }

        public Gate piAcceptable() {
            if (p.piStatus() != EParticle.PiStatus.ACCEPTABLE)
                failures.add("range " + p.piStatus() + " (width "
                        + p.width() + ")");
            return this;
        }

        public boolean passes() { return failures.isEmpty(); }

        public List<String> failures() { return new ArrayList<>(failures); }

        public EParticle orZ() {
            return passes() ? p : EParticle.z(p.ident(), joined());
        }

        public EParticle orThrow() {
            if (!passes())
                throw new ExpectFailure(p.ident() + ": " + joined());
            return p;
        }

        public EParticle orArchive(List<EParticle> archive) {
            if (!passes()) {
                archive.add(EParticle.eerror(p.ident(), joined(),
                        p.confidence()));
                return EParticle.z(p.ident(), joined());
            }
            return p;
        }

        private String joined() { return String.join("; ", failures); }
    }

    /* ═════════════════════════════════════════
     * Phase — mirrors Layer 1 exactly.
     * Check order: Z-contagion → Expel → Repel → Excel
     * ═════════════════════════════════════════ */

    public enum Outcome { REPEL, EXPEL, EXCEL, BLOCKED }

    public static final class PhaseResult {
        public final Outcome   outcome;
        public final EParticle survivor;
        public final EParticle expelled;
        public final EParticle combined;
        public final int       lowEdge;
        public final int       highEdge;
        public final String    note;

        PhaseResult(Outcome o, EParticle s, EParticle e, EParticle c,
                    int lo, int hi, String note) {
            this.outcome  = o;   this.survivor = s;   this.expelled = e;
            this.combined = c;   this.lowEdge  = lo;  this.highEdge = hi;
            this.note     = note;
        }

        public boolean cleared() { return outcome != Outcome.BLOCKED; }
    }

    private static final double PHI_X2 = EParticle.PHI * 2.0;  // 3.236…

    /**
     * Proximity: are these two near each other on the scale?
     *
     * <p>A TOLERANCE relation — reflexive and symmetric, but <b>not</b>
     * transitive: 0~1 and 1~81, while 0!~81. A fair question, and not
     * the one the Zeroth Law answers. For comparison use
     * {@link #equilibrium}.
     */
    public static boolean sameSpectrum(EParticle a, EParticle b) {
        return Math.abs(a.confidence() - b.confidence())
                < EParticle.PI_WIDTH_WARN;
    }

    /**
     * The Zeroth Law. If two threads are each in equilibrium with a
     * third, they are in equilibrium with each other.
     *
     * <p>Prior to the First Law: the First says what happens when
     * evidence combines, the Zeroth says confidence is a comparable
     * quantity at all. Implemented as equality of band, which is the
     * kernel of a total function and therefore transitive by
     * construction rather than by luck.
     *
     * <p>Bands and boundaries mirror {@code e_band} in
     * {@code 0-atom-c/tapestry.c} exactly. The runtime travels into
     * other people's pipelines, so it must not hold a private opinion
     * about where the boundaries are.
     */
    public enum Band {
        Z,            // 0        unknown, carrying its reason
        VESTIGIAL,    // 1..24    below int(256 / pi^2)
        APPROACHING,  // 25..80   below int(256 / pi)
        SUBFLOOR,     // 81..127  below 256 / 2
        EXECUTABLE,   // 128..255 cleared, not verified
        CERTAIN       // 256      earned
    }

    /** Total on 0..256. Off-scale reports Z — the safe direction. */
    public static Band band(int confidence) {
        if (confidence <= EParticle.ZERO)               return Band.Z;
        if (confidence >  EParticle.CERTAIN)            return Band.Z;
        if (confidence >= EParticle.CERTAIN)            return Band.CERTAIN;
        if (confidence >= EParticle.EXECUTE_FLOOR)      return Band.EXECUTABLE;
        if (confidence >= EParticle.PI_WIDTH_WARN)      return Band.SUBFLOOR;
        if (confidence >= EParticle.PI_WIDTH_ENUMERATE) return Band.APPROACHING;
        return Band.VESTIGIAL;
    }

    /** The Zeroth Law relation. Z is in equilibrium only with Z. */
    public static boolean equilibrium(EParticle a, EParticle b) {
        return band(a.confidence()) == band(b.confidence());
    }

    /*
     * Equal confidences fall in the same band trivially, so the second
     * clause cannot change the answer. It is here to say which relation
     * a Pauli collision is a collision IN. It used to read sameSpectrum,
     * which was equally inert and named the wrong relation.
     */
    public static boolean pauliCollision(EParticle a, EParticle b) {
        return a.confidence() == b.confidence() && equilibrium(a, b);
    }

    private static boolean isExpel(EParticle a, EParticle b) {
        if (pauliCollision(a, b)) return true;
        int lo = Math.min(a.confidence(), b.confidence());
        int hi = Math.max(a.confidence(), b.confidence());
        if (lo <= 0) return false;
        return ((double) hi / lo) > PHI_X2;
    }

    private static boolean isRepel(EParticle a, EParticle b) {
        int lo = Math.min(a.confidence(), b.confidence());
        int hi = Math.max(a.confidence(), b.confidence());
        if (!(lo < 64 && hi > 192)) return false;
        if (lo <= 0) return false;
        return ((double) hi / lo) <= PHI_X2;
    }

    public static PhaseResult combine(EParticle a, EParticle b) {
        // 1. Z-contagion. Nothing processes through Z.
        if (a.isZ() || b.isZ()) {
            return new PhaseResult(Outcome.BLOCKED,
                    EParticle.z("blocked", "Z present in phase interaction"),
                    null, null, 0, 0, "Z-contagion: interaction blocked");
        }

        // 2. Expel — before Repel, because it is the more specific claim.
        if (isExpel(a, b)) {
            EParticle survivor = a.confidence() >= b.confidence() ? a : b;
            EParticle loser    = a.confidence() >= b.confidence() ? b : a;
            EParticle expelled = EParticle.eerror(loser.ident(),
                    "expelled in phase collision", loser.confidence());
            return new PhaseResult(Outcome.EXPEL, survivor, expelled, null,
                    0, 0, "Expel: " + survivor.ident() + " survives at "
                    + survivor.confidence());
        }

        // 3. Repel — opposite zones, moderate ratio.
        if (isRepel(a, b)) {
            int lo = Math.min(a.confidence(), b.confidence());
            int hi = Math.max(a.confidence(), b.confidence());
            return new PhaseResult(Outcome.REPEL, null, null, null, lo, hi,
                    "Repel: boundary defined between " + lo + " and " + hi);
        }

        // 4. Excel — constructive interference.
        int c = EParticle.excelFormula(a.confidence(), b.confidence());
        EParticle combined = EParticle.confident(
                a.ident() + "+" + b.ident(), c, a.lang());
        return new PhaseResult(Outcome.EXCEL, null, null, combined, 0, 0,
                "Excel: " + a.confidence() + " and " + b.confidence()
                + " combine to " + c);
    }

    /* ═════════════════════════════════════════
     * phi equalizer
     * ═════════════════════════════════════════ */

    public static final class Equalized {
        public final List<EParticle> balanced = new ArrayList<>();
        public final List<EParticle> flagged  = new ArrayList<>();
    }

    public static Equalized phiEqualize(List<EParticle> set) {
        Equalized out = new Equalized();
        if (set.isEmpty()) return out;

        long sum = 0;
        for (EParticle p : set) sum += p.confidence();
        int mean = (int) (sum / set.size());
        int hi = (int) (mean * EParticle.PHI);
        int lo = (int) (mean / EParticle.PHI);

        for (EParticle p : set) {
            if (p.confidence() > hi || p.confidence() < lo) out.flagged.add(p);
            else out.balanced.add(p);
        }
        return out;
    }

    /* ═════════════════════════════════════════
     * Evolve — the three-point force loop
     *
     * Action = Reaction / Force. Three aligned applications and the
     * construct has earned the right to advance its own state.
     * Downward evolution is legitimate: learning you were overconfident
     * is learning.
     * ═════════════════════════════════════════ */

    public static final class ForceLoop {
        private final String ident;
        private final List<EParticle> points = new ArrayList<>();

        public ForceLoop(String ident) { this.ident = ident; }

        public ForceLoop add(EParticle p) {
            points.add(p);
            while (points.size() > 3) points.remove(0);
            return this;
        }

        public boolean closed() { return points.size() == 3; }

        public int spread() {
            if (points.isEmpty()) return 0;
            int lo = Integer.MAX_VALUE, hi = Integer.MIN_VALUE;
            for (EParticle p : points) {
                lo = Math.min(lo, p.confidence());
                hi = Math.max(hi, p.confidence());
            }
            return hi - lo;
        }

        public String direction() {
            if (!closed()) return "flat";
            int first = points.get(0).confidence();
            int last  = points.get(2).confidence();
            if (last > first) return "up";
            if (last < first) return "down";
            return "flat";
        }

        /** Returns null if the loop has not closed or the points disagree. */
        public EParticle evolve() {
            if (!closed()) return null;
            if (spread() > EParticle.PI_WIDTH_ENUMERATE) return null;

            int sum = 0;
            for (EParticle p : points) sum += p.confidence();
            int mean = sum / 3;

            return points.get(2).evolved(mean,
                    "evolved from 3 aligned points, spread " + spread()
                    + ", direction " + direction());
        }
    }

    /* ═════════════════════════════════════════
     * The pipeline: Examine → Evaluate → Execute
     * ═════════════════════════════════════════ */

    private final String name;
    private final Map<String, EParticle> particles = new LinkedHashMap<>();
    private final List<EParticle> archive = new ArrayList<>();
    private final Map<String, ForceLoop> loops = new LinkedHashMap<>();

    public EverRuntime(String name) { this.name = name; }

    public EverRuntime declare(EParticle p) {
        particles.put(p.ident(), p);
        return this;
    }

    public EParticle get(String ident) {
        EParticle p = particles.get(ident);
        return p != null ? p : EParticle.z(ident, "never declared");
    }

    public EverRuntime expect(String ident, int minConfidence,
                              boolean piAcceptable) {
        EParticle p = get(ident);
        Gate g = Gate.on(p).notZ().minConfidence(minConfidence);
        if (piAcceptable) g.piAcceptable();
        particles.put(ident, g.orArchive(archive));
        return this;
    }

    public EverRuntime emulate(String ident, String from, int distance) {
        particles.put(ident,
                EParticle.emulate(get(ident), get(from), distance));
        return this;
    }

    public EParticle evolve(String ident) {
        ForceLoop loop = loops.computeIfAbsent(ident, ForceLoop::new);
        loop.add(get(ident));
        EParticle evolved = loop.evolve();
        if (evolved != null) particles.put(ident, evolved);
        return evolved;
    }

    public EverRuntime assimilate(String ident, EParticle.Lang to) {
        particles.put(ident, get(ident).assimilate(to));
        return this;
    }

    public List<EParticle> particles() {
        return new ArrayList<>(particles.values());
    }


    public Result execute() {
        List<EParticle> cleared = new ArrayList<>();
        List<EParticle> blocked = new ArrayList<>();
        for (EParticle p : particles.values()) {
            if (p.isCleared()) cleared.add(p);
            else {
                blocked.add(p);
                if (p.state() != EParticle.State.EXPRESSION) archive.add(p);
            }
        }
        return new Result(name, cleared, blocked, phiEqualize(cleared),
                archive);
    }

    public static final class Result {
        public final String name;
        public final List<EParticle> cleared;
        public final List<EParticle> blocked;
        public final Equalized equalized;
        public final List<EParticle> archive;

        Result(String name, List<EParticle> cleared, List<EParticle> blocked,
               Equalized equalized, List<EParticle> archive) {
            this.name = name; this.cleared = cleared; this.blocked = blocked;
            this.equalized = equalized; this.archive = archive;
        }

        public boolean executable() {
            if (!blocked.isEmpty()) return false;
            for (EParticle p : cleared) if (!p.canExecute()) return false;
            return true;
        }

        public String report() {
            StringBuilder b = new StringBuilder();
            b.append("\nExamination: ").append(name).append('\n');
            for (int i = 0; i < 52; i++) b.append('-');
            b.append("\n  cleared : ").append(cleared.size()).append('\n');
            for (EParticle p : cleared)
                b.append("      ").append(p).append('\n');
            b.append("  blocked : ").append(blocked.size()).append('\n');
            for (EParticle p : blocked)
                b.append("      ").append(p).append("  <- ")
                 .append(p.reason()).append('\n');
            b.append("  flagged by phi : ")
             .append(equalized.flagged.size()).append('\n');
            for (EParticle p : equalized.flagged)
                b.append("      ").append(p).append('\n');
            b.append("  archived : ").append(archive.size()).append('\n');
            b.append('\n').append(executable()
                    ? "  CLEARED FOR EXECUTION" : "  BLOCKED").append('\n');
            return b.toString();
        }
    }
}
