package com.codric.ezr;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * How far each definition is believed, and which have earned depth.
 *
 * <p>Runtime state, deliberately not a field on {@code Eval.Fn}: what a
 * function <em>says</em> is syntax, and how much it is <em>believed</em> is
 * evidence. Evidence accumulates outside the parse tree.
 *
 * <p>A name absent from the map sits at {@link Particle#INTAKE}.
 * SEMANTICS.md 4.1 <strong>[DEF]</strong>: a definition enters below the
 * execute floor because it is a claim, not a verification — exactly as a
 * literal enters at CERTAIN because the author wrote it and there is nothing
 * left to verify.
 *
 * <p>This existing at all is a correction. Both evaluators computed
 * <strong>[APP]</strong> as {@code min(c_args, c_result)} and dropped the
 * {@code c_f} term, so every answer came back at 256/256 however unverified
 * the code behind it. {@code abstract.py}'s Lambda had it right the whole
 * time and nothing compared the two.
 */
public final class Trust {

    private final Map<String, Integer> confidence = new HashMap<>();
    private final Set<String> anchored = new HashSet<>();

    /** Nothing verified: every definition sits at INTAKE. */
    public static Trust none() { return new Trust(); }

    /** Record what a function has earned. */
    public Trust believe(String name, int c) {
        confidence.put(name, Particle.clamp(c));
        return this;
    }

    /**
     * Grant earned depth. The caller must have checked the bar first —
     * cleared, and a decreasing measure if recursive. This only records it.
     */
    public Trust anchor(String name) {
        anchored.add(name);
        return this;
    }

    /** What {@code name} is believed to be worth. */
    public int of(String name) {
        return confidence.getOrDefault(name, Particle.INTAKE);
    }

    public boolean isAnchored(String name) { return anchored.contains(name); }

    /**
     * Depth is earned. An anchored function with a measure recurses to the
     * hard ceiling; everything else keeps the caller's limit.
     */
    public int limitFor(String name, int fallback) {
        return anchored.contains(name) ? HARD_DEPTH : fallback;
    }

    /**
     * The hard stop, mirroring {@code abstract.py}. "Unbounded" means not
     * bounded by the pi ceiling — never "will not be stopped".
     */
    public static final int HARD_DEPTH = 4000;

    /**
     * <strong>[EXAMPLE]</strong>, SEMANTICS.md 4.2 — identical to
     * {@link Laws#fromExamples}, which the runtime already had. Kept as one
     * call so the runner and the laws cannot drift apart.
     *
     * <p>1/1 is 120 and still below the floor, 2/2 clears at 183, 3/3 is
     * 217, and 2 of 3 is 122 because a failure costs.
     */
    public static int fromExamples(int passing, int total) {
        return Laws.fromExamples(passing, total);
    }
}
