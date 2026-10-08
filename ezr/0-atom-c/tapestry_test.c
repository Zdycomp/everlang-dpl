/*
 * tapestry_test.c — Ever / Tapestry verification
 * Proves the atom carries T, and that the six A-operators hold.
 */

#include "tapestry.h"
#include <stdio.h>
#include <string.h>

static int passed = 0, failed = 0;

static void ok(const char *name, int cond) {
    if (cond) { passed++; printf("  \u2713 %s\n", name); }
    else      { failed++; printf("  \u2717 %s\n", name); }
}

static e_particle halve(const e_particle *p) {
    e_particle q = *p;
    q.confidence = p->confidence / 2;
    q.lo = q.hi = q.confidence;
    return q;
}

int main(void) {
    printf("\n=== Ever / Tapestry — the atom carries T ===\n\n");

    printf("Scale unchanged from v1\n");
    ok("Certain is 256",            E_CERTAIN == 256);
    ok("execute floor is 128",      E_EXECUTE_FLOOR == 128);
    ok("pi warn is 81",             E_PI_WIDTH_WARN == 81);
    ok("pi squared is 25",          E_PI_WIDTH_ENUMERATE == 25);
    ok("emulate ceiling is 3",      E_EMULATE_CEILING == 3);
    ok("ascend points is 3",        E_ASCEND_POINTS == 3);

    printf("\nThe payload — what v1 dropped\n");
    e_particle n = e_int("count", 42, 180, E_LANG_PYTHON);
    ok("int holds its value",       n.value.as_int == 42);
    ok("int knows its type",        n.type == E_TYPE_INT);
    ok("int carries confidence",    n.confidence == 180);
    ok("int has a value",           e_has_value(&n));

    e_particle t = e_text("name", "Codric", 200, E_LANG_RUBY);
    ok("text holds its value",      !strcmp(t.text, "Codric"));
    ok("text knows its type",       t.type == E_TYPE_TEXT);

    e_particle r = e_real("ratio", 1.618, 190, E_LANG_C);
    ok("real holds its value",      r.value.as_real > 1.6 && r.value.as_real < 1.7);

    e_particle b = e_bool("flag", 1, 150, E_LANG_JAVA);
    ok("bool holds its value",      b.value.as_bool == 1);

    e_particle z = e_z("missing", "never assigned");
    ok("Z holds no value",          !e_has_value(&z));
    ok("Z records the defect",      z.defect == E_DEFECT_UNBOUND);

    e_particle expr = e_expression("pending", E_TYPE_INT, E_LANG_EVER);
    ok("Expression has shape",      expr.type == E_TYPE_INT);
    ok("Expression has no value",   !e_has_value(&expr));

    printf("\nThe five binding defects\n");
    ok("unbound named",   !strcmp(e_defect_name(E_DEFECT_UNBOUND),   "unbound"));
    ok("misbound named",  !strcmp(e_defect_name(E_DEFECT_MISBOUND),  "misbound"));
    ok("unbounded named", !strcmp(e_defect_name(E_DEFECT_UNBOUNDED), "unbounded"));
    ok("overbound named", !strcmp(e_defect_name(E_DEFECT_OVERBOUND), "overbound"));
    ok("orphaned named",  !strcmp(e_defect_name(E_DEFECT_ORPHANED),  "orphaned"));

    printf("\nA1 — ANY: lift any language's binding\n");
    e_particle a_i = a_any("x", "42", E_LANG_PYTHON);
    ok("lifts an integer",          a_i.type == E_TYPE_INT && a_i.value.as_int == 42);
    e_particle a_r = a_any("y", "3.14", E_LANG_RUST);
    ok("lifts a real",              a_r.type == E_TYPE_REAL);
    e_particle a_s = a_any("s", "\"hello\"", E_LANG_GO);
    ok("lifts a string",            a_s.type == E_TYPE_TEXT && !strcmp(a_s.text, "hello"));
    e_particle a_b = a_any("f", "true", E_LANG_TS);
    ok("lifts a bool",              a_b.type == E_TYPE_BOOL && a_b.value.as_bool == 1);

    e_particle a_null = a_any("n", "null", E_LANG_JAVA);
    ok("null lifts to Z",           e_is_z(&a_null));
    e_particle a_nil  = a_any("n", "nil",  E_LANG_RUBY);
    e_particle a_none = a_any("n", "None", E_LANG_PYTHON);
    e_particle a_undef= a_any("n", "undefined", E_LANG_TS);
    ok("nil lifts to Z",            e_is_z(&a_nil));
    ok("None lifts to Z",           e_is_z(&a_none));
    ok("undefined lifts to Z",      e_is_z(&a_undef));
    ok("nothing is an unbound defect", a_none.defect == E_DEFECT_UNBOUND);

    e_particle a_bad = a_any("s", "\"unterminated", E_LANG_C);
    ok("unterminated string is unbounded", a_bad.defect == E_DEFECT_UNBOUNDED);

    ok("intake sits below execute floor", a_i.confidence < E_EXECUTE_FLOOR);

    printf("\nA2 — ASSIMILATE: cross languages without losing the thing\n");
    e_particle py = e_int("total", 99, 200, E_LANG_PYTHON);
    e_particle rs = a_assimilate(&py, E_LANG_RUST);
    ok("payload survives crossing", rs.value.as_int == 99);
    ok("type survives crossing",    rs.type == E_TYPE_INT);
    ok("language changed",          rs.lang == E_LANG_RUST);
    ok("unanchored pays 1",         rs.confidence == 199);

    e_particle zz = e_z("unknown", "not set");
    e_particle zx = a_assimilate(&zz, E_LANG_GO);
    ok("Z does not translate",      e_is_z(&zx));

    e_particle same = a_assimilate(&py, E_LANG_PYTHON);
    ok("same language is identity", same.confidence == 200);

    printf("\nA3 — ANCHOR: identity that survives translation\n");
    e_particle anc = a_anchor(&py, 7001);
    ok("anchor is set",             e_is_anchored(&anc));
    ok("anchor state recorded",     anc.state == E_STATE_ANCHORED);
    ok("payload preserved",         anc.value.as_int == 99);

    e_particle hop1 = a_assimilate(&anc,  E_LANG_RUST);
    e_particle hop2 = a_assimilate(&hop1, E_LANG_SWIFT);
    e_particle hop3 = a_assimilate(&hop2, E_LANG_JAVA);
    ok("anchored survives 3 hops with no loss", hop3.confidence == 200);
    ok("anchor id held across hops",  hop3.anchor_id == 7001);
    ok("payload held across hops",    hop3.value.as_int == 99);
    ok("landed in the target language", hop3.lang == E_LANG_JAVA);

    e_particle drift1 = a_assimilate(&py,     E_LANG_RUST);
    e_particle drift2 = a_assimilate(&drift1, E_LANG_SWIFT);
    e_particle drift3 = a_assimilate(&drift2, E_LANG_JAVA);
    ok("unanchored drifts visibly",   drift3.confidence == 197);
    ok("anchoring is the difference", hop3.confidence > drift3.confidence);

    e_particle bad_anchor = a_anchor(&zz, 9000);
    ok("cannot anchor a Z",           e_is_z(&bad_anchor));
    e_particle zero_anchor = a_anchor(&py, 0);
    ok("anchor id zero refused",      e_is_z(&zero_anchor));

    printf("\nA4 — ASCEND: the only path upward\n");
    e_particle base = e_int("parse", 150, 150, E_LANG_C);
    e_particle ev   = e_int("parse", 150, 160, E_LANG_C);

    e_particle s1 = a_ascend(&base, &ev);
    ok("one point does not lift",   s1.confidence == 150);
    ok("one point counted",         s1.ascend_points == 1);
    e_particle s2 = a_ascend(&s1, &ev);
    ok("two points do not lift",    s2.confidence == 150);
    e_particle s3 = a_ascend(&s2, &ev);
    ok("three points lift",         s3.confidence > 150);
    ok("generation advanced",       s3.generation == 1);
    ok("points reset after rise",   s3.ascend_points == 0);
    ok("rise matches excel",        s3.confidence == e_excel_formula(150, 160));

    e_particle far = e_int("other", 0, 40, E_LANG_C);
    e_particle reset = a_ascend(&s1, &far);
    ok("disagreeing evidence resets", reset.ascend_points == 0);
    ok("disagreement does not lower", reset.confidence == 150);

    e_particle z_asc = a_ascend(&zz, &ev);
    ok("Z cannot ascend",           e_is_z(&z_asc));

    e_particle no_ev = a_ascend(&base, &zz);
    ok("uncleared evidence ignored", no_ev.ascend_points == 0);

    printf("\nA5 — APPLY2ALL: broadcast, halting on Z\n");
    e_particle set[4] = {
        e_int("a", 1, 200, E_LANG_EVER),
        e_int("b", 2, 180, E_LANG_EVER),
        e_int("c", 3, 160, E_LANG_EVER),
        e_int("d", 4, 140, E_LANG_EVER)
    };
    int halted = -1;
    int done = a_apply2all(set, 4, halve, &halted);
    ok("all four transformed",      done == 4);
    ok("nothing halted",            halted == -1);
    ok("transform applied",         set[0].confidence == 100);

    e_particle set2[4] = {
        e_int("a", 1, 200, E_LANG_EVER),
        e_int("b", 2, 180, E_LANG_EVER),
        e_z("c", "unresolved"),
        e_int("d", 4, 140, E_LANG_EVER)
    };
    done = a_apply2all(set2, 4, halve, &halted);
    ok("broadcast halts at Z",      done == 2);
    ok("halt position reported",    halted == 2);
    ok("particle past the halt untouched", set2[3].confidence == 140);

    printf("\nA6 — AUTO-DIDACT: derive a rule from history\n");
    e_particle hist[4] = {
        e_int("obs", 1, 170, E_LANG_EVER),
        e_int("obs", 2, 175, E_LANG_EVER),
        e_int("obs", 3, 180, E_LANG_EVER),
        e_int("obs", 4, 178, E_LANG_EVER)
    };
    e_particle rule = a_autodidact(hist, 4, "parse_confidence");
    ok("rule derived from history", e_is_cleared(&rule));
    ok("rule holds the mean",       rule.value.as_int == 175);
    ok("rule records the spread",   rule.lo == 170 && rule.hi == 180);

    e_particle two[2] = { hist[0], hist[1] };
    e_particle no_rule = a_autodidact(two, 2, "too_short");
    ok("under three observations refuses", e_is_z(&no_rule));

    e_particle scattered[4] = {
        e_int("o", 1, 20,  E_LANG_EVER),
        e_int("o", 2, 240, E_LANG_EVER),
        e_int("o", 3, 60,  E_LANG_EVER),
        e_int("o", 4, 200, E_LANG_EVER)
    };
    e_particle no_rule2 = a_autodidact(scattered, 4, "scattered");
    ok("scattered history refuses", e_is_z(&no_rule2));

    e_particle defects[4] = {
        e_z_defect("d", "null deref",   E_DEFECT_UNBOUND),
        e_z_defect("d", "nil deref",    E_DEFECT_UNBOUND),
        e_z_defect("d", "None deref",   E_DEFECT_UNBOUND),
        e_int("d", 1, 180, E_LANG_EVER)
    };
    e_particle drule = a_autodidact(defects, 4, "recurring");
    ok("recurring defect becomes a rule", e_is_cleared(&drule));
    ok("rule names the defect",     !strcmp(drule.text, "unbound"));

    printf("\nOperators compose — closed over E\n");
    e_particle chain = a_any("total", "500", E_LANG_PYTHON);
    chain = a_anchor(&chain, 42);
    chain = a_assimilate(&chain, E_LANG_RUST);
    chain = a_assimilate(&chain, E_LANG_GO);
    ok("any->anchor->assimilate->assimilate holds value",
       chain.value.as_int == 500);
    ok("chain kept its anchor",     chain.anchor_id == 42);
    ok("chain lost no confidence",  chain.confidence == 120);
    ok("chain landed in Go",        chain.lang == E_LANG_GO);

    printf("\nZ contagion still absolute\n");
    e_particle from_z = e_carry(&zz, "downstream");
    ok("Z carried forward stays Z", e_is_z(&from_z));
    ok("defect carried forward",    from_z.defect == E_DEFECT_UNBOUND);

    printf("\nSerialization round trip with payload\n");
    char buf[640];
    e_serialize(&anc, buf, sizeof buf);
    e_particle back;
    ok("deserialize succeeds",      e_deserialize(buf, &back) == 1);
    ok("payload survives",          back.value.as_int == 99);
    ok("anchor survives",           back.anchor_id == 7001);
    ok("type survives",             back.type == E_TYPE_INT);
    ok("confidence survives",       back.confidence == 200);
    ok("ident survives",            !strcmp(back.ident, "total"));

    e_serialize(&t, buf, sizeof buf);
    e_deserialize(buf, &back);
    ok("text payload survives",     !strcmp(back.text, "Codric"));

    printf("\n=== Tapestry atom: %d passed, %d failed ===\n\n", passed, failed);
    return failed == 0 ? 0 : 1;
}
