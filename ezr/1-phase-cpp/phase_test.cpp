/*
 * phase_test.cpp — Ever / Tapestry Layer 1 verification
 */

#include "phase.hpp"
#include <cstdio>
#include <cstring>
#include <vector>

using namespace ever;

static int passed = 0, failed = 0;

static void ok(const char* name, bool cond) {
    if (cond) { passed++; std::printf("  \u2713 %s\n", name); }
    else      { failed++; std::printf("  \u2717 %s\n", name); }
}

int main() {
    std::printf("\n=== Tapestry Layer 1 (C++) — the phase engine ===\n\n");

    std::printf("Spectrum\n");
    ok("gap 70 same spectrum",
       PhaseEngine::sameSpectrum(e_int("a",1,100,E_LANG_CPP),
                                 e_int("b",1,170,E_LANG_CPP)));
    ok("gap 190 not same spectrum",
       !PhaseEngine::sameSpectrum(e_int("a",1,10,E_LANG_CPP),
                                  e_int("b",1,200,E_LANG_CPP)));

    std::printf("\nValue comparison — impossible in v1\n");
    e_particle v1 = e_int("a", 500, 180, E_LANG_CPP);
    e_particle v2 = e_int("b", 500, 160, E_LANG_CPP);
    e_particle v3 = e_int("c", 700, 160, E_LANG_CPP);
    ok("same value detected",       PhaseEngine::sameValue(v1, v2));
    ok("different value detected",  !PhaseEngine::sameValue(v1, v3));
    ok("text compared by content",
       PhaseEngine::sameValue(e_text("a","Codric",180,E_LANG_CPP),
                              e_text("b","Codric",150,E_LANG_CPP)));
    ok("different text detected",
       !PhaseEngine::sameValue(e_text("a","Codric",180,E_LANG_CPP),
                               e_text("b","Other",150,E_LANG_CPP)));
    ok("int and real interoperate",
       PhaseEngine::sameType(e_int("a",1,150,E_LANG_CPP),
                             e_real("b",1.0,150,E_LANG_CPP)));
    ok("int and text do not",
       !PhaseEngine::sameType(e_int("a",1,150,E_LANG_CPP),
                              e_text("b","x",150,E_LANG_CPP)));

    std::printf("\nZ contagion\n");
    e_particle z = e_z("unknown", "not verified");
    PhaseResult blocked = PhaseEngine::combine(z, v1);
    ok("Z blocks interaction",      blocked.outcome == Outcome::Blocked);
    ok("blocked is not cleared",    !blocked.cleared());
    ok("defect carried",            blocked.survivor.defect == E_DEFECT_UNBOUND);

    std::printf("\nType conflict — new in v2\n");
    PhaseResult conf = PhaseEngine::combine(
        e_int("n", 5, 180, E_LANG_CPP), e_text("s", "five", 180, E_LANG_CPP));
    ok("mismatched types conflict", conf.outcome == Outcome::Conflict);
    ok("conflict is misbound",
       conf.survivor.defect == E_DEFECT_MISBOUND);
    ok("conflict is not cleared",   !conf.cleared());

    std::printf("\nExcel — corroboration requires agreement\n");
    PhaseResult ex = PhaseEngine::combine(v1, v2);
    ok("agreeing threads Excel",    ex.outcome == Outcome::Excel);
    ok("confidence rises",          ex.combined.confidence > 180);
    ok("matches excel formula",
       ex.combined.confidence == e_excel_formula(180, 160));
    ok("value preserved",           ex.combined.value.as_int == 500);
    ok("combination cannot reach Certain", e_excel_formula(250,250) == 255);
    ok("two verified inputs stay Certain", e_excel_formula(256,256) == 256);

    std::printf("\nCorroboration outranks collision\n");
    /* identical confidence AND identical value: v1 would have expelled on
     * the Pauli collision. v2 recognises it as two witnesses agreeing. */
    PhaseResult agree = PhaseEngine::combine(
        e_int("a", 500, 128, E_LANG_CPP), e_int("b", 500, 128, E_LANG_CPP));
    ok("same value same confidence corroborates",
       agree.outcome == Outcome::Excel);
    PhaseResult clash = PhaseEngine::combine(
        e_int("a", 500, 128, E_LANG_CPP), e_int("b", 700, 128, E_LANG_CPP));
    ok("different value same confidence expels",
       clash.outcome == Outcome::Expel);
    ok("expelled marked overbound",
       clash.expelled.defect == E_DEFECT_OVERBOUND);

    std::printf("\nAnchors survive corroboration\n");
    e_particle anc = a_anchor(&v1, 5150);
    PhaseResult ax = PhaseEngine::combine(anc, v2);
    ok("anchor carried into result", ax.combined.anchor_id == 5150);

    std::printf("\nExpel\n");
    PhaseResult xp = PhaseEngine::combine(
        e_int("dom", 1, 240, E_LANG_CPP), e_int("weak", 2, 30, E_LANG_CPP));
    ok("dominance expels",          xp.outcome == Outcome::Expel);
    ok("stronger survives",         xp.survivor.confidence == 240);
    ok("expelled archived",         xp.expelled.state == E_STATE_ERROR);
    ok("expelled keeps position",   xp.expelled.lo == 30);

    std::printf("\nRepel\n");
    PhaseResult rp = PhaseEngine::combine(
        e_int("lo", 1, 63, E_LANG_CPP), e_int("hi", 2, 200, E_LANG_CPP));
    ok("opposite zones repel",      rp.outcome == Outcome::Repel);
    ok("low edge recorded",         rp.lowEdge == 63);
    ok("high edge recorded",        rp.highEdge == 200);

    std::printf("\nCheck order preserved\n");
    PhaseResult order = PhaseEngine::combine(
        e_int("vlo", 1, 20, E_LANG_CPP), e_int("vhi", 2, 250, E_LANG_CPP));
    ok("Expel checked before Repel", order.outcome == Outcome::Expel);
    PhaseResult zfirst = PhaseEngine::combine(z, e_text("t","x",180,E_LANG_CPP));
    ok("Z checked before type conflict", zfirst.outcome == Outcome::Blocked);

    std::printf("\nEquidistance\n");
    ok("100 and 156 equidistant from 128",
       PhaseEngine::equidistant(e_int("a",1,100,E_LANG_CPP),
                                e_int("b",1,156,E_LANG_CPP), 128));
    ok("100 and 200 are not",
       !PhaseEngine::equidistant(e_int("a",1,100,E_LANG_CPP),
                                 e_int("b",1,200,E_LANG_CPP), 128));

    std::printf("\nPhi equalizer\n");
    std::vector<e_particle> bal = {
        e_int("a",1,180,E_LANG_CPP), e_int("b",1,160,E_LANG_CPP),
        e_int("c",1,150,E_LANG_CPP) };
    ok("balanced flags nothing",    PhaseEngine::phiEqualize(bal).flagged.empty());
    std::vector<e_particle> skew = {
        e_int("a",1,250,E_LANG_CPP), e_int("b",1,10,E_LANG_CPP) };
    ok("skewed flags outliers",     !PhaseEngine::phiEqualize(skew).flagged.empty());
    std::vector<e_particle> none;
    ok("empty equalizes cleanly",   PhaseEngine::phiEqualize(none).balanced.empty());

    std::printf("\nWeave — folding a whole set\n");
    std::vector<e_particle> witnesses = {
        e_int("w1", 500, 150, E_LANG_C),
        e_int("w2", 500, 160, E_LANG_PYTHON),
        e_int("w3", 500, 155, E_LANG_RUST) };
    e_particle woven = PhaseEngine::weave(witnesses, "total");
    ok("three agreeing witnesses weave", e_is_cleared(&woven));
    ok("woven value preserved",     woven.value.as_int == 500);
    ok("woven confidence rises above all",
       woven.confidence > 160);
    ok("woven takes the given name", !std::strcmp(woven.ident, "total"));

    std::vector<e_particle> withZ = {
        e_int("w1", 500, 150, E_LANG_C),
        e_z("w2", "never measured"),
        e_int("w3", 500, 155, E_LANG_RUST) };
    ok("a Z in the set halts the weave",
       e_is_z(&(woven = PhaseEngine::weave(withZ, "total"))));

    std::vector<e_particle> mixed = {
        e_int("w1", 500, 150, E_LANG_C),
        e_text("w2", "five hundred", 150, E_LANG_C) };
    e_particle badweave = PhaseEngine::weave(mixed, "total");
    ok("type conflict halts the weave", e_is_z(&badweave));
    ok("halt is misbound",          badweave.defect == E_DEFECT_MISBOUND);

    std::vector<e_particle> empty;
    ok("empty weave is Z",
       e_is_z(&(badweave = PhaseEngine::weave(empty, "nothing"))));

    std::printf("\nSix risk categories (ReVision scenario)\n");
    std::vector<e_particle> risks = {
        e_int("deceptive_language", 1, 180, E_LANG_CPP),
        e_int("tone_manipulation",  1, 160, E_LANG_CPP),
        e_int("scare_tactics",      1, 170, E_LANG_CPP),
        e_int("artificial_urgency", 1, 150, E_LANG_CPP),
        e_int("hidden_terms",       1, 155, E_LANG_CPP),
        e_int("contract_traps",     1, 165, E_LANG_CPP) };
    auto rr = PhaseEngine::phiEqualize(risks);
    ok("six accounted for",  rr.balanced.size() + rr.flagged.size() == 6);
    ok("tight cluster flags nothing", rr.flagged.empty());
    e_particle verdict = PhaseEngine::weave(risks, "risk_verdict");
    ok("six agreeing risks weave to one verdict", e_is_cleared(&verdict));
    ok("verdict can execute",       e_can_execute(&verdict));

    std::printf("\n=== Layer 1: %d passed, %d failed ===\n\n", passed, failed);
    return failed == 0 ? 0 : 1;
}
