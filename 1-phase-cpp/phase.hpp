/*
 * phase.hpp — Ever / Tapestry, Layer 1 (C++)
 * The phase engine. What happens when two threads meet in the weave.
 *
 * v1 could only compare confidence, because particles held no value.
 * v2 holds T, which makes a distinction v1 could not make:
 *
 *   two threads agreeing on a value  = corroboration  -> Excel
 *   two threads disagreeing          = conflict       -> Expel or Repel
 *
 * That is the difference between "both of these are 80% trusted" and
 * "both of these say 500 and are 80% trusted." Only the second is
 * evidence.
 *
 * Check order, as implemented:
 *   Z-contagion and archived error -> type conflict -> Excel ->
 *   Expel -> Repel
 *
 * Excel is checked BEFORE the conflict paths, and deliberately: two
 * independent threads agreeing on a value is the strongest thing that
 * can happen in the weave, so it outranks dominance. This header used
 * to state the v1 order and call it "not negotiable" while phase.cpp
 * implemented this one -- a stale comment reading as a rule.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef TAPESTRY_PHASE_HPP
#define TAPESTRY_PHASE_HPP

extern "C" {
#include "../0-atom-c/tapestry.h"
}

#include <string>
#include <vector>

namespace ever {

enum class Outcome {
    Excel,    /* corroboration: same value, confidence rises   */
    Expel,    /* dominance: one displaces the other            */
    Repel,    /* opposition: both stand as boundary markers    */
    Conflict, /* same name, incompatible types                 */
    Blocked   /* Z present; nothing processes through Z        */
};

const char* outcomeName(Outcome o);

struct PhaseResult {
    Outcome     outcome;
    e_particle  a, b;
    e_particle  survivor;   /* Expel  */
    e_particle  expelled;   /* Expel  */
    e_particle  combined;   /* Excel  */
    int         lowEdge, highEdge;   /* Repel */
    std::string note;

    bool cleared() const;
};

class PhaseEngine {
public:
    /* Proximity: confidence gap narrower than the pi warn threshold.
     *
     * This is a TOLERANCE relation — reflexive and symmetric, but NOT
     * transitive: 0~1 and 1~81, while 0!~81. It answers "are these two
     * near each other", which is a fair question, and it must never be
     * mistaken for the Zeroth Law. For comparison, use equilibrium(). */
    static bool sameSpectrum(const e_particle& a, const e_particle& b);

    /* The Zeroth Law: same band, and therefore transitive by
     * construction. Delegates to the atom so the layers cannot drift. */
    static bool equilibrium(const e_particle& a, const e_particle& b);

    /* Pauli: identical confidence, necessarily in the same band */
    static bool pauliCollision(const e_particle& a, const e_particle& b);

    /* do two threads hold the same thing? corroboration requires it. */
    static bool sameValue(const e_particle& a, const e_particle& b);

    /* do two threads hold compatible kinds of thing? */
    static bool sameType(const e_particle& a, const e_particle& b);

    static bool equidistant(const e_particle& a, const e_particle& b, int mid);

    static PhaseResult combine(const e_particle& a, const e_particle& b);

    struct EqualizeResult {
        std::vector<e_particle> balanced;
        std::vector<e_particle> flagged;
    };
    static EqualizeResult phiEqualize(const std::vector<e_particle>& set);

    /* Weave a whole set: fold pairwise, corroborating where possible.
     * Returns the resulting thread, or Z if the set cannot be woven. */
    static e_particle weave(const std::vector<e_particle>& set,
                            const char* ident);

private:
    static bool isExpel(const e_particle& a, const e_particle& b);
    static bool isRepel(const e_particle& a, const e_particle& b);
};

} /* namespace ever */

#endif /* TAPESTRY_PHASE_HPP */
