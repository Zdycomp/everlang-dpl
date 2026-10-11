/*
 * phase.cpp — Ever / Tapestry, Layer 1 (C++)
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "phase.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <algorithm>

namespace ever {

static const double PHI    = 1.6180339887;
static const double PHI_X2 = PHI * 2.0;   /* 3.236… */

const char* outcomeName(Outcome o) {
    switch (o) {
        case Outcome::Excel:    return "Excel";
        case Outcome::Expel:    return "Expel";
        case Outcome::Repel:    return "Repel";
        case Outcome::Conflict: return "Conflict";
        case Outcome::Blocked:  return "Blocked";
    }
    return "Unknown";
}

bool PhaseResult::cleared() const {
    return outcome != Outcome::Blocked && outcome != Outcome::Conflict;
}

/* ─────────────────────────────────────────────
 * spectrum, type and value
 * ───────────────────────────────────────────── */

bool PhaseEngine::sameSpectrum(const e_particle& a, const e_particle& b) {
    return std::abs((int)a.confidence - (int)b.confidence) < E_PI_WIDTH_WARN;
}

bool PhaseEngine::pauliCollision(const e_particle& a, const e_particle& b) {
    return a.confidence == b.confidence && sameSpectrum(a, b);
}

bool PhaseEngine::sameType(const e_particle& a, const e_particle& b) {
    if (a.type == b.type) return true;
    /* int and real interoperate; nothing else does silently */
    bool an = (a.type == E_TYPE_INT || a.type == E_TYPE_REAL);
    bool bn = (b.type == E_TYPE_INT || b.type == E_TYPE_REAL);
    return an && bn;
}

bool PhaseEngine::sameValue(const e_particle& a, const e_particle& b) {
    if (!sameType(a, b)) return false;
    switch (a.type) {
        case E_TYPE_INT:
            if (b.type == E_TYPE_REAL)
                return std::fabs((double)a.value.as_int - b.value.as_real) < 1e-9;
            return a.value.as_int == b.value.as_int;
        case E_TYPE_REAL:
            if (b.type == E_TYPE_INT)
                return std::fabs(a.value.as_real - (double)b.value.as_int) < 1e-9;
            return std::fabs(a.value.as_real - b.value.as_real) < 1e-9;
        case E_TYPE_BOOL:
            return a.value.as_bool == b.value.as_bool;
        case E_TYPE_TEXT:
        case E_TYPE_FOREIGN:
            return std::strcmp(a.text, b.text) == 0;
        case E_TYPE_VOID:
            return true;
        default:
            return false;
    }
}

bool PhaseEngine::equidistant(const e_particle& a, const e_particle& b, int mid) {
    int da = std::abs((int)a.confidence - mid);
    int db = std::abs((int)b.confidence - mid);
    return da == db && da > 0;
}

/* ─────────────────────────────────────────────
 * Expel and Repel
 * ───────────────────────────────────────────── */

bool PhaseEngine::isExpel(const e_particle& a, const e_particle& b) {
    if (pauliCollision(a, b)) return true;
    int lo = std::min((int)a.confidence, (int)b.confidence);
    int hi = std::max((int)a.confidence, (int)b.confidence);
    if (lo <= 0) return false;
    return ((double)hi / lo) > PHI_X2;
}

bool PhaseEngine::isRepel(const e_particle& a, const e_particle& b) {
    int lo = std::min((int)a.confidence, (int)b.confidence);
    int hi = std::max((int)a.confidence, (int)b.confidence);
    if (!(lo < 64 && hi > 192)) return false;
    if (lo <= 0) return false;
    return ((double)hi / lo) <= PHI_X2;
}

/* ─────────────────────────────────────────────
 * combine
 * ───────────────────────────────────────────── */

PhaseResult PhaseEngine::combine(const e_particle& a, const e_particle& b) {
    PhaseResult r;
    r.a = a; r.b = b;
    r.lowEdge = r.highEdge = 0;

    /* 1. Z-contagion */
    if (e_is_z(&a) || e_is_z(&b)) {
        r.outcome  = Outcome::Blocked;
        r.survivor = e_z_defect("blocked", "Z present in phase interaction",
                                e_is_z(&a) ? (e_defect)a.defect : (e_defect)b.defect);
        r.note     = "Z-contagion: interaction blocked";
        return r;
    }

    /* 2. type conflict — new in v2, only possible because threads hold T */
    if (!sameType(a, b)) {
        r.outcome  = Outcome::Conflict;
        r.survivor = e_error(a.ident, "incompatible types in phase",
                             E_DEFECT_MISBOUND, a.confidence);
        char buf[192];
        std::snprintf(buf, sizeof buf,
            "Conflict: %s holds %s, %s holds %s",
            a.ident, e_type_name((e_type)a.type), b.ident, e_type_name((e_type)b.type));
        r.note = buf;
        return r;
    }

    /* 3. corroboration — same value is evidence, and outranks dominance.
     *    Two independent threads agreeing is the strongest thing that can
     *    happen in the weave, so it is checked before the conflict paths. */
    if (sameValue(a, b)) {
        r.outcome = Outcome::Excel;
        int16_t c = e_excel_formula(a.confidence, b.confidence);
        char ident[E_IDENT_MAX];
        std::snprintf(ident, sizeof ident, "%s+%s", a.ident, b.ident);

        r.combined = a;
        std::snprintf(r.combined.ident, E_IDENT_MAX, "%s", ident);
        r.combined.confidence = c;
        r.combined.lo = r.combined.hi = c;
        r.combined.state = (c >= E_CERTAIN) ? E_STATE_CERTAIN : E_STATE_CONFIDENT;
        /* an anchor survives corroboration if either side carried one */
        if (a.anchor_id) r.combined.anchor_id = a.anchor_id;
        else if (b.anchor_id) r.combined.anchor_id = b.anchor_id;

        char buf[192];
        std::snprintf(buf, sizeof buf,
            "Excel: corroborated, %d and %d rise to %d",
            (int)a.confidence, (int)b.confidence, (int)c);
        r.note = buf;
        return r;
    }

    /* 4. Expel — before Repel, being the more specific claim */
    if (isExpel(a, b)) {
        r.outcome = Outcome::Expel;
        const e_particle& win  = (a.confidence >= b.confidence) ? a : b;
        const e_particle& lose = (a.confidence >= b.confidence) ? b : a;
        r.survivor = win;
        r.expelled = e_error(lose.ident, "expelled: disagreed and was weaker",
                             E_DEFECT_OVERBOUND, lose.confidence);
        char buf[192];
        std::snprintf(buf, sizeof buf,
            "Expel: %s survives at %d, %s archived at %d",
            win.ident, (int)win.confidence,
            lose.ident, (int)lose.confidence);
        r.note = buf;
        return r;
    }

    /* 5. Repel */
    if (isRepel(a, b)) {
        r.outcome  = Outcome::Repel;
        r.lowEdge  = std::min((int)a.confidence, (int)b.confidence);
        r.highEdge = std::max((int)a.confidence, (int)b.confidence);
        char buf[192];
        std::snprintf(buf, sizeof buf,
            "Repel: disagreement bounded between %d and %d, both archived",
            r.lowEdge, r.highEdge);
        r.note = buf;
        return r;
    }

    /* 6. disagreement without dominance or opposition becomes a range.
     *    Two threads that disagree are not corroboration; the honest
     *    result is an Equivalence spanning both, and pi will judge it. */
    r.outcome = Outcome::Repel;
    r.lowEdge  = std::min((int)a.confidence, (int)b.confidence);
    r.highEdge = std::max((int)a.confidence, (int)b.confidence);
    char buf[192];
    std::snprintf(buf, sizeof buf,
        "Repel: values differ, range %d..%d held open",
        r.lowEdge, r.highEdge);
    r.note = buf;
    return r;
}

/* ─────────────────────────────────────────────
 * phi equalizer
 * ───────────────────────────────────────────── */

PhaseEngine::EqualizeResult
PhaseEngine::phiEqualize(const std::vector<e_particle>& set) {
    EqualizeResult out;
    if (set.empty()) return out;

    long sum = 0;
    for (const auto& p : set) sum += p.confidence;
    int mean = (int)(sum / (long)set.size());
    int hiB = (int)((double)mean * PHI);
    int loB = (int)((double)mean / PHI);

    for (const auto& p : set) {
        if (p.confidence > hiB || p.confidence < loB) out.flagged.push_back(p);
        else out.balanced.push_back(p);
    }
    return out;
}

/* ─────────────────────────────────────────────
 * weave — fold a whole set
 * ───────────────────────────────────────────── */

e_particle PhaseEngine::weave(const std::vector<e_particle>& set,
                              const char* ident) {
    if (set.empty())
        return e_z_defect(ident, "nothing to weave", E_DEFECT_UNBOUND);

    e_particle acc = set[0];
    for (size_t i = 1; i < set.size(); i++) {
        PhaseResult r = combine(acc, set[i]);
        switch (r.outcome) {
            case Outcome::Excel:
                acc = r.combined;
                break;
            case Outcome::Expel:
                acc = r.survivor;
                break;
            case Outcome::Blocked:
                return e_z_defect(ident, "Z encountered while weaving",
                                  E_DEFECT_UNBOUND);
            case Outcome::Conflict:
                return e_z_defect(ident, "type conflict while weaving",
                                  E_DEFECT_MISBOUND);
            case Outcome::Repel: {
                /* unresolved disagreement becomes an open range */
                e_particle eq = e_equivalence(ident, (int16_t)r.lowEdge,
                                              (int16_t)r.highEdge, (e_lang)acc.lang);
                std::snprintf(eq.reason, E_REASON_MAX,
                    "wove to a range: threads disagreed at step %zu", i);
                return eq;
            }
        }
    }
    std::snprintf(acc.ident, E_IDENT_MAX, "%s", ident);
    return acc;
}

} /* namespace ever */
