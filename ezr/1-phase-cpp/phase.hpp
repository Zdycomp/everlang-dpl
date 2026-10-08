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
 * Check order, unchanged and not negotiable:
 *   Z-contagion -> type conflict -> Expel -> Repel -> Excel
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
    /* same spectrum: confidence gap narrower than the pi warn threshold */
    static bool sameSpectrum(const e_particle& a, const e_particle& b);

    /* Pauli: identical confidence in the same spectrum */
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
