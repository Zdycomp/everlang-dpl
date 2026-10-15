package com.codric.ever;

/**
 * EParticle.java — Ever Language, Layer 5 (Java)
 *
 * The runtime particle. Same shape as the C struct in Layer 0, same
 * serialization line, same constants.
 *
 * Java owns this layer because the runtime has to be portable, has to
 * carry guardrails into other people's build pipelines, and has to be
 * immutable under concurrency. Java is where Ever runs inside somebody
 * else's system without asking permission.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 * Theory of Relative E:  E = MC²
 */
public final class EParticle {

    /* ── constants, identical to 0-core-c/ever.h ── */
    public static final int ZERO               = 0;
    public static final int CERTAIN            = 256;
    public static final int PI_WIDTH_WARN      = 81;   // int(256 / pi)
    public static final int PI_WIDTH_ENUMERATE = 25;   // int(256 / pi^2)
    public static final int EMULATE_CEILING    = 3;    // int(pi)
    public static final int EXECUTE_FLOOR      = 128;  // 256 / 2
    public static final double PHI             = 1.6180339887;

    public enum State {
        Z, CONFIDENT, CERTAIN_S, EQUIVALENCE, EXPRESSION,
        EMULATING, EVOLVED, ABSENT, EERROR
    }

    public enum Lang { C, CPP, PYTHON, RUBY, SQL, JAVA, HTML, EVER }

    public enum PiStatus { ACCEPTABLE, ENUMERATE, APPROACHING_Z }

    /* ── the particle is immutable. every operation returns a new one. ── */
    private final State  state;
    private final Lang   lang;
    private final int    confidence;
    private final int    lo;
    private final int    hi;
    private final int    errorDistance;
    private final int    generation;
    private final long   bornMs;
    private final String ident;
    private final String reason;

    private EParticle(State state, Lang lang, int confidence, int lo, int hi,
                      int errorDistance, int generation, long bornMs,
                      String ident, String reason) {
        this.state         = state;
        this.lang          = lang;
        this.confidence    = confidence;
        this.lo            = lo;
        this.hi            = hi;
        this.errorDistance = errorDistance;
        this.generation    = generation;
        this.bornMs        = bornMs;
        this.ident         = ident == null ? "" : ident;
        this.reason        = reason == null ? "" : reason;
    }

    /* ── constructors ── */

    public static EParticle z(String ident, String reason) {
        return new EParticle(State.Z, Lang.EVER, ZERO, ZERO, ZERO, 0, 0,
                System.currentTimeMillis(), ident,
                reason == null ? "unverified" : reason);
    }

    public static EParticle certain(String ident, Lang lang) {
        return new EParticle(State.CERTAIN_S, lang, CERTAIN, CERTAIN, CERTAIN,
                0, 0, System.currentTimeMillis(), ident, "");
    }

    public static EParticle confident(String ident, int degree, Lang lang) {
        if (degree <= ZERO)    return z(ident, "confidence collapsed to zero");
        if (degree >= CERTAIN) return certain(ident, lang);
        return new EParticle(State.CONFIDENT, lang, degree, degree, degree,
                0, 0, System.currentTimeMillis(), ident, "");
    }

    public static EParticle equivalence(String ident, int lo, int hi, Lang lang) {
        if (lo > hi) { int t = lo; lo = hi; hi = t; }
        return new EParticle(State.EQUIVALENCE, lang, (lo + hi) / 2, lo, hi,
                0, 0, System.currentTimeMillis(), ident, "");
    }

    public static EParticle expression(String ident, Lang lang) {
        return new EParticle(State.EXPRESSION, lang, ZERO, ZERO, ZERO, 0, 0,
                System.currentTimeMillis(), ident,
                "shape known, value pending");
    }

    public static EParticle eerror(String ident, String reason, int at) {
        return new EParticle(State.EERROR, Lang.EVER, ZERO, at, at, 0, 0,
                System.currentTimeMillis(), ident, reason);
    }

    /* ── accessors ── */

    public State  state()         { return state; }
    public Lang   lang()          { return lang; }
    public int    confidence()    { return confidence; }
    public int    lo()            { return lo; }
    public int    hi()            { return hi; }
    public int    errorDistance() { return errorDistance; }
    public int    generation()    { return generation; }
    public long   bornMs()        { return bornMs; }
    public String ident()         { return ident; }
    public String reason()        { return reason; }

    /* ── predicates ── */

    public boolean isZ() { return state == State.Z; }

    public boolean isCleared() {
        if (state == State.Z || state == State.EERROR || state == State.ABSENT)
            return false;
        return confidence > ZERO;
    }

    public boolean canExecute() {
        return isCleared() && confidence >= EXECUTE_FLOOR;
    }

    public int width() { return hi - lo; }

    public PiStatus piStatus() {
        int w = width();
        if (w > PI_WIDTH_WARN)      return PiStatus.APPROACHING_Z;
        if (w > PI_WIDTH_ENUMERATE) return PiStatus.ENUMERATE;
        return PiStatus.ACCEPTABLE;
    }

    /* ── propagation: Z is contagious ── */

    public EParticle carry(String newIdent) {
        if (state == State.Z)      return z(newIdent, reason);
        if (state == State.EERROR) return z(newIdent, "upstream error");
        if (state == State.ABSENT) return z(newIdent, "upstream absent");
        return new EParticle(state, lang, confidence, lo, hi, errorDistance,
                generation, System.currentTimeMillis(), newIdent, reason);
    }

    public EParticle cap(int ceiling) {
        if (ceiling <= ZERO)        return z(ident, "capped to zero");
        if (confidence <= ceiling)  return this;
        State demoted = (state == State.CERTAIN_S) ? State.CONFIDENT : state;
        return new EParticle(demoted, lang, ceiling,
                Math.min(lo, ceiling), Math.min(hi, ceiling),
                errorDistance, generation, bornMs, ident, reason);
    }

    public EParticle assimilate(Lang to) {
        if (state == State.Z || state == State.EERROR)
            return z(ident, "uncleared particle does not translate");
        return new EParticle(state, to, confidence, lo, hi, errorDistance,
                generation, System.currentTimeMillis(), ident,
                "assimilated " + lang + " to " + to);
    }

    public boolean equilibriumWith(EParticle other) {
        return EverRuntime.equilibrium(this, other);
    }


    public static int excelFormula(int a, int b) {
        if (a >= CERTAIN && b >= CERTAIN) return CERTAIN;
        long v = (long) a + b - ((long) a * b / CERTAIN);
        if (v > CERTAIN - 1) v = CERTAIN - 1;
        if (v < ZERO)        v = ZERO;
        return (int) v;
    }

    /* ── Emulate ── */

    public static EParticle emulate(EParticle broken, EParticle working,
                                    int errorDistance) {
        if (errorDistance > EMULATE_CEILING)
            return z(broken.ident, "error distance " + errorDistance
                    + " exceeds emulate ceiling " + EMULATE_CEILING);
        if (!working.isCleared())
            return z(broken.ident, "no cleared neighbour to emulate");

        int borrowed = Math.max(1, working.confidence - (30 * errorDistance));
        return new EParticle(State.EMULATING, broken.lang, borrowed,
                borrowed, borrowed, errorDistance, broken.generation,
                System.currentTimeMillis(), broken.ident,
                "emulating " + working.ident + " at distance " + errorDistance);
    }

    public EParticle evolved(int newConfidence, String why) {
        return new EParticle(State.EVOLVED, lang, newConfidence,
                newConfidence, newConfidence, errorDistance, generation + 1,
                System.currentTimeMillis(), ident, why);
    }

    /* ── serialization: the Layer 0 line format ── */

    public String serialize() {
        return state.ordinal() + "|0|" + lang.ordinal() + "|" + confidence
             + "|" + lo + "|" + hi + "|" + errorDistance + "|" + generation
             + "|-1|" + bornMs + "|" + ident + "|" + reason;
    }

    public static EParticle deserialize(String line) {
        String[] f = line.split("\\|", 12);
        if (f.length < 12) return z("malformed", "malformed particle line");
        return new EParticle(
                State.values()[Integer.parseInt(f[0])],
                Lang.values()[Integer.parseInt(f[2])],
                Integer.parseInt(f[3]), Integer.parseInt(f[4]),
                Integer.parseInt(f[5]), Integer.parseInt(f[6]),
                Integer.parseInt(f[7]), Long.parseLong(f[9]),
                f[10], f[11]);
    }

    @Override public String toString() {
        return "E<" + state + ">(" + ident + " @ " + confidence + "/256 · "
             + lang + ")";
    }

    @Override public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof EParticle)) return false;
        EParticle p = (EParticle) o;
        return state == p.state && lang == p.lang
            && confidence == p.confidence && lo == p.lo && hi == p.hi
            && ident.equals(p.ident);
    }

    @Override public int hashCode() {
        int h = state.hashCode();
        h = 31 * h + lang.hashCode();
        h = 31 * h + confidence;
        h = 31 * h + lo;
        h = 31 * h + hi;
        h = 31 * h + ident.hashCode();
        return h;
    }
}
