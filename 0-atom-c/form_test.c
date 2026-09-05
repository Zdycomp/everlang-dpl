/*
 * form_test.c — Ever / Tapestry, generic structural IR test suite
 *
 * The suites here fall into three groups:
 *
 *   1. STRUCTURE   — contracts, roles, validation, metrics, wire
 *   2. EQUIVALENCE — the form path and the legacy node path must
 *                    produce byte-identical results on every program
 *   3. EXTENSION   — the architectural claim, made falsifiable:
 *                    four surface constructs that DO NOT EXIST in
 *                    ir.h, tac.c, or form_lower.c are built out of
 *                    the existing eleven forms and executed. If the
 *                    IR were still a syntax schema, each would need
 *                    a new node kind and a new lowering case.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "ev_test.h"
#include "tac.h"
#include "form.h"

/* ═════════════════════════════════════════════
 * GROUP 1 — STRUCTURE
 * ═════════════════════════════════════════════ */

EV_SUITE_TAGGED(form_contracts, "form", "structure") {
    /* Every form kind has exactly one contract row */
    for (int k = 0; k < EV_FORM_KIND_COUNT; k++) {
        const EvFormContract *c = ev_form_contract((EvFormKind)k);
        ASSERT_NOT_NULL(c);
        ASSERT_EQ_INT(k, c->form);          /* table is index-aligned */
        ASSERT_NOT_NULL(c->name);
        ASSERT_NOT_NULL(c->shape_desc);
    }
    ASSERT_EQ_STR("ATOM",        ev_form_name(EV_FORM_ATOM));
    ASSERT_EQ_STR("APPLICATION", ev_form_name(EV_FORM_APPLICATION));
    ASSERT_EQ_STR("BRANCH",      ev_form_name(EV_FORM_BRANCH));
    ASSERT_EQ_STR("SEQUENCE",    ev_form_name(EV_FORM_SEQUENCE));

    /* Contract arities encode the shape rules */
    ASSERT_EQ_INT(0,  ev_form_contract(EV_FORM_ATOM)->max_parts);
    ASSERT_EQ_INT(2,  ev_form_contract(EV_FORM_BRANCH)->min_parts);
    ASSERT_EQ_INT(-1, ev_form_contract(EV_FORM_BRANCH)->max_parts); /* N arms */
    ASSERT_EQ_INT(1,  ev_form_contract(EV_FORM_BINDING)->max_parts);
    ASSERT_EQ_INT(2,  ev_form_contract(EV_FORM_ACCESS)->min_parts);
    ASSERT_EQ_INT(1,  ev_form_contract(EV_FORM_REFERENCE)->needs_symbol);
}

EV_SUITE_TAGGED(form_role_ownership, "form", "structure") {
    /* Each role belongs to exactly one form — this is what lets a
       pass trust f->form without cross-checking f->role */
    ASSERT_EQ_INT(EV_FORM_ATOM,        ev_role_form(EV_ROLE_LIT_INT));
    ASSERT_EQ_INT(EV_FORM_ATOM,        ev_role_form(EV_ROLE_LIT_Z));
    ASSERT_EQ_INT(EV_FORM_REFERENCE,   ev_role_form(EV_ROLE_REF_VAR));
    ASSERT_EQ_INT(EV_FORM_APPLICATION, ev_role_form(EV_ROLE_ADD));
    ASSERT_EQ_INT(EV_FORM_APPLICATION, ev_role_form(EV_ROLE_LTE));
    ASSERT_EQ_INT(EV_FORM_APPLICATION, ev_role_form(EV_ROLE_CALL));
    ASSERT_EQ_INT(EV_FORM_BRANCH,      ev_role_form(EV_ROLE_IF));
    ASSERT_EQ_INT(EV_FORM_BRANCH,      ev_role_form(EV_ROLE_MATCH));
    ASSERT_EQ_INT(EV_FORM_ABSTRACTION, ev_role_form(EV_ROLE_FN_DEF));
    ASSERT_EQ_INT(EV_FORM_AGGREGATE,   ev_role_form(EV_ROLE_AGG_RECORD));

    /* ADD, LTE and CALL — three very different surface constructs —
       all live under one form. That collapse IS the architecture. */
    ASSERT_EQ_INT(ev_role_form(EV_ROLE_ADD), ev_role_form(EV_ROLE_CALL));
    ASSERT_EQ_INT(ev_role_form(EV_ROLE_IF),  ev_role_form(EV_ROLE_MATCH));

    ASSERT_EQ_STR("ADD",  ev_role_name(EV_ROLE_ADD));
    ASSERT_EQ_STR("CALL", ev_role_name(EV_ROLE_CALL));
    ASSERT_EQ_STR("IF",   ev_role_name(EV_ROLE_IF));
}

EV_SUITE_TAGGED(form_constructors, "form") {
    EvArena *a = ev_arena_new("ctor");

    EvForm *i = ev_form_int(a, 42, 1);
    ASSERT_EQ_INT(EV_FORM_ATOM,    i->form);
    ASSERT_EQ_INT(EV_ROLE_LIT_INT, i->role);
    ASSERT_EQ_INT(42,              i->payload.body.as_int);
    ASSERT_EQ_INT(0,               i->part_count);

    EvForm *t = ev_form_text(a, "Ever", 1);
    ASSERT_EQ_INT(EV_ROLE_LIT_TEXT, t->role);
    ASSERT_EQ_STR("Ever",           t->payload.text);

    EvForm *z = ev_form_z(a, 1);
    ASSERT_EQ_INT(EV_ROLE_LIT_Z, z->role);
    ASSERT_EQ_INT(0,             z->confidence);   /* z is zero trust */

    EvForm *v = ev_form_ref(a, "n", 1);
    ASSERT_EQ_INT(EV_FORM_REFERENCE, v->form);
    ASSERT_EQ_STR("n",               v->symbol);

    EvForm *add = ev_form_apply2(a, EV_ROLE_ADD,
                                 ev_form_int(a,6,1), ev_form_int(a,36,1), 1);
    ASSERT_EQ_INT(EV_FORM_APPLICATION, add->form);
    ASSERT_EQ_INT(2,                   add->part_count);

    EvForm *arms[2] = { ev_form_int(a,1,1), ev_form_int(a,0,1) };
    EvForm *br = ev_form_branch(a, EV_ROLE_IF, add, arms, 2, 1);
    ASSERT_EQ_INT(EV_FORM_BRANCH, br->form);
    ASSERT_EQ_INT(3,              br->part_count);  /* selector + 2 arms */
    ASSERT_EQ_INT(2,              ev_form_arm_count(br));
    ASSERT_NOT_NULL(ev_form_selector(br));
    ASSERT_EQ_INT(EV_FORM_APPLICATION, ev_form_selector(br)->form);

    ev_arena_free(a);
}

EV_SUITE_TAGGED(form_validate, "form", "structure") {
    EvArena *a = ev_arena_new("valid");
    char err[256];

    /* well-formed tree passes */
    EvForm *ok = ev_form_apply2(a, EV_ROLE_ADD,
                                ev_form_int(a,1,1), ev_form_int(a,2,1), 1);
    ASSERT_EQ_INT(1, ev_form_validate(ok, err, sizeof err));

    /* BRANCH with no arms violates min_parts=2 */
    EvForm *bad = ev_form_new(a, EV_FORM_BRANCH, EV_ROLE_IF, 7);
    ev_form_add_part(bad, ev_form_bool(a,1,7), "selector");
    ASSERT_EQ_INT(0, ev_form_validate(bad, err, sizeof err));
    ASSERT(strstr(err, "BRANCH")   != NULL);
    ASSERT(strstr(err, "at least") != NULL);
    ASSERT(strstr(err, "line 7")   != NULL);   /* precise location */

    /* REFERENCE with no symbol violates needs_symbol */
    EvForm *nosym = ev_form_new(a, EV_FORM_REFERENCE, EV_ROLE_REF_VAR, 9);
    ASSERT_EQ_INT(0, ev_form_validate(nosym, err, sizeof err));
    ASSERT(strstr(err, "requires a symbol") != NULL);

    /* role belonging to the wrong form is caught */
    EvForm *wrong = ev_form_new(a, EV_FORM_ATOM, EV_ROLE_IF, 11);
    ASSERT_EQ_INT(0, ev_form_validate(wrong, err, sizeof err));
    ASSERT(strstr(err, "does not belong") != NULL);

    /* BINDING allows exactly one value — two is a violation */
    EvForm *bind2 = ev_form_binding(a, EV_ROLE_BIND_LET, "x",
                                    ev_form_int(a,1,1), 13);
    ev_form_add_part(bind2, ev_form_int(a,2,1), NULL);
    ASSERT_EQ_INT(0, ev_form_validate(bind2, err, sizeof err));
    ASSERT(strstr(err, "at most") != NULL);

    ev_arena_free(a);
}

EV_SUITE_TAGGED(form_metrics, "form") {
    EvArena *a = ev_arena_new("metrics");
    /* if (n <= 1) then 1 else n * fact(n-1) */
    EvForm *cmp = ev_form_apply2(a, EV_ROLE_LTE,
                    ev_form_ref(a,"n",1), ev_form_int(a,1,1), 1);
    EvForm *sub = ev_form_apply2(a, EV_ROLE_SUB,
                    ev_form_ref(a,"n",1), ev_form_int(a,1,1), 1);
    EvForm *args[1] = { sub };
    EvForm *rec = ev_form_apply(a, EV_ROLE_CALL, "fact", args, 1, 1);
    EvForm *mul = ev_form_apply2(a, EV_ROLE_MUL, ev_form_ref(a,"n",1), rec, 1);
    EvForm *arms[2] = { ev_form_int(a,1,1), mul };
    EvForm *iff = ev_form_branch(a, EV_ROLE_IF, cmp, arms, 2, 1);

    ev_form_measure(iff);
    ASSERT_EQ_INT(11, iff->size);
    ASSERT_EQ_INT(5,  iff->depth);

    /* counting by shape and by role — the two questions a pass asks */
    ASSERT_EQ_INT(1, ev_form_count_kind(iff, EV_FORM_BRANCH));
    ASSERT_EQ_INT(4, ev_form_count_kind(iff, EV_FORM_APPLICATION));
    ASSERT_EQ_INT(3, ev_form_count_kind(iff, EV_FORM_REFERENCE));
    ASSERT_EQ_INT(1, ev_form_count_role(iff, EV_ROLE_CALL));
    ASSERT_EQ_INT(1, ev_form_count_role(iff, EV_ROLE_MUL));

    /* skeleton erases values and operators, keeps pure shape */
    const char *sk = ev_form_skeleton(iff, a);
    ASSERT_NOT_NULL(sk);
    ASSERT(strstr(sk, "BR") != NULL);
    ASSERT(strstr(sk, "AP") != NULL);
    ASSERT(strstr(sk, "V")  != NULL);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(form_wire, "form", "wire") {
    EvArena *a = ev_arena_new("wire");
    uint8_t buf[8192];

    EvForm *cases[6];
    cases[0] = ev_form_int(a, 42, 1);
    cases[1] = ev_form_text(a, "Codric", 2);
    cases[2] = ev_form_ref(a, "count", 3);
    cases[3] = ev_form_apply2(a, EV_ROLE_MUL,
                 ev_form_int(a,7,4), ev_form_int(a,6,4), 4);
    {
        EvForm *arms[2] = { ev_form_int(a,1,5), ev_form_int(a,0,5) };
        cases[4] = ev_form_branch(a, EV_ROLE_IF,
                     ev_form_bool(a,1,5), arms, 2, 5);
    }
    cases[5] = ev_form_binding(a, EV_ROLE_BIND_EVER, "total",
                 ev_form_int(a,100,6), 6);

    for (int i = 0; i < 6; i++) {
        int32_t n = ev_form_serialise(cases[i], buf, sizeof buf);
        ASSERT(n > 0);
        int32_t cons = 0;
        EvArena *b = ev_arena_new("rt");
        EvForm *back = ev_form_deserialise(buf, n, &cons, b);
        ASSERT_NOT_NULL(back);
        ASSERT_EQ_INT(n, cons);
        ASSERT_EQ_INT(cases[i]->form,       back->form);
        ASSERT_EQ_INT(cases[i]->role,       back->role);
        ASSERT_EQ_INT(cases[i]->line,       back->line);
        ASSERT_EQ_INT(cases[i]->part_count, back->part_count);
        ev_arena_free(b);
    }
    ev_arena_free(a);
}

/* ═════════════════════════════════════════════
 * GROUP 2 — NORMALISATION AND EQUIVALENCE
 * ═════════════════════════════════════════════ */

EV_SUITE_TAGGED(form_normalise_map, "form", "normalise") {
    EvArena *a = ev_arena_new("norm");

    /* every literal node kind collapses onto ATOM */
    struct { EvNode *n; EvFormKind want_form; EvRole want_role; } cases[] = {
        { ev_node_int (a, 42,   1), EV_FORM_ATOM,      EV_ROLE_LIT_INT  },
        { ev_node_real(a, 3.14, 1), EV_FORM_ATOM,      EV_ROLE_LIT_REAL },
        { ev_node_bool(a, 1,    1), EV_FORM_ATOM,      EV_ROLE_LIT_BOOL },
        { ev_node_text(a, "hi", 1), EV_FORM_ATOM,      EV_ROLE_LIT_TEXT },
        { ev_node_var (a, "n",  1), EV_FORM_REFERENCE, EV_ROLE_REF_VAR  },
    };
    EV_PARAMS(cases, tc) {
        EvForm *f = ev_form_from_node(tc.n, a);
        ASSERT_NOT_NULL(f);
        ASSERT_EQ_INT(tc.want_form, f->form);
        ASSERT_EQ_INT(tc.want_role, f->role);
    }

    /* all ten binary operators collapse onto APPLICATION */
    EvNodeKind binops[] = {
        EV_NODE_ADD, EV_NODE_SUB, EV_NODE_MUL, EV_NODE_DIV,
        EV_NODE_LT,  EV_NODE_GT,  EV_NODE_LTE, EV_NODE_GTE,
        EV_NODE_EQ,  EV_NODE_NEQ
    };
    for (int i = 0; i < 10; i++) {
        EvNode *n = ev_node_binop(a, binops[i],
                       ev_node_int(a,1,1), ev_node_int(a,2,1), 1);
        EvForm *f = ev_form_from_node(n, a);
        ASSERT_EQ_INT(EV_FORM_APPLICATION, f->form);
        ASSERT_EQ_INT(2, f->part_count);
    }

    /* CALL is the same form as ADD, differing only by role */
    EvNode *cargs[1] = { ev_node_int(a,3,1) };
    EvNode *call = ev_node_call(a, "square", cargs, 1, 1);
    EvForm *cf   = ev_form_from_node(call, a);
    ASSERT_EQ_INT(EV_FORM_APPLICATION, cf->form);
    ASSERT_EQ_INT(EV_ROLE_CALL,        cf->role);
    ASSERT_EQ_STR("square",            cf->symbol);

    /* IF becomes a two-arm BRANCH */
    EvNode *iff = ev_node_if(a, ev_node_bool(a,1,1),
                    ev_node_int(a,1,1), ev_node_int(a,0,1), 1);
    EvForm *bf = ev_form_from_node(iff, a);
    ASSERT_EQ_INT(EV_FORM_BRANCH, bf->form);
    ASSERT_EQ_INT(2, ev_form_arm_count(bf));

    /* DEF becomes ABSTRACTION and keeps its parameter names */
    const char *ps[] = { "n" };
    EvNode *def = ev_node_def(a, "square", ps, 1,
                    ev_node_binop(a,EV_NODE_MUL,
                      ev_node_var(a,"n",1), ev_node_var(a,"n",1), 1), 1);
    EvForm *df = ev_form_from_node(def, a);
    ASSERT_EQ_INT(EV_FORM_ABSTRACTION, df->form);
    ASSERT_EQ_STR("square", df->symbol);
    ASSERT_NOT_NULL(ev_form_body(df));

    ev_arena_free(a);
}

EV_SUITE_TAGGED(form_roundtrip, "form", "normalise") {
    /* node → form → node must preserve structure */
    EvArena *a = ev_arena_new("rt");
    EvNode *orig = ev_node_if(a,
        ev_node_binop(a,EV_NODE_GT, ev_node_var(a,"x",1), ev_node_int(a,5,1),1),
        ev_node_binop(a,EV_NODE_ADD,ev_node_int(a,6,1), ev_node_int(a,36,1),1),
        ev_node_int(a,0,1), 1);

    EvForm *f    = ev_form_from_node(orig, a);
    EvNode *back = ev_node_from_form(f, a);
    ASSERT_NOT_NULL(back);
    ASSERT_EQ_INT(orig->kind,        back->kind);
    ASSERT_EQ_INT(orig->child_count, back->child_count);
    ASSERT_EQ_INT(orig->children[0]->kind, back->children[0]->kind);
    ASSERT_EQ_INT(orig->children[1]->kind, back->children[1]->kind);

    ev_node_measure(orig); ev_node_measure(back);
    ASSERT_EQ_INT(orig->size,  back->size);
    ASSERT_EQ_INT(orig->depth, back->depth);
    ev_arena_free(a);
}

/* Helper: run one EvNode program through BOTH lowering paths */
static void _both_paths(EvNode *prog, EValue *node_out, EValue *form_out) {
    EvArena *na = ev_arena_new("nodepath");
    EvNode  *cp = prog;
    EvModule *mn = ev_lower_module("N", cp, na);
    ev_optimise(mn->global_body);
    EvInterp *in = ev_interp_new(mn);
    *node_out = ev_interp_run(in);
    ev_interp_free(in);
    ev_module_free(mn);

    EvArena *fa = ev_arena_new("formpath");
    EvForm  *f  = ev_form_from_node(prog, fa);
    EvModule *mf = ev_lower_form_module("F", f, fa);
    ev_optimise(mf->global_body);
    EvInterp *ifp = ev_interp_new(mf);
    *form_out = ev_interp_run(ifp);
    ev_interp_free(ifp);
    ev_module_free(mf);
    ev_arena_free(na);
    ev_arena_free(fa);
}

EV_SUITE_TAGGED(form_equivalence, "form", "equivalence") {
    /* The load-bearing suite. If the generic IR is a faithful
       refactor, these must agree on every program. */
    EvArena *a = ev_arena_new("equiv");

    struct { const char *label; EvNode *prog; int64_t want; } cases[] = {
        { "6+36",        ev_node_binop(a,EV_NODE_ADD,
                           ev_node_int(a,6,1),  ev_node_int(a,36,1),1), 42 },
        { "10-3",        ev_node_binop(a,EV_NODE_SUB,
                           ev_node_int(a,10,1), ev_node_int(a,3,1),1),   7 },
        { "7*6",         ev_node_binop(a,EV_NODE_MUL,
                           ev_node_int(a,7,1),  ev_node_int(a,6,1),1),  42 },
        { "nested",      ev_node_binop(a,EV_NODE_ADD,
                           ev_node_binop(a,EV_NODE_MUL,
                             ev_node_int(a,6,1), ev_node_int(a,6,1),1),
                           ev_node_int(a,6,1),1),                       42 },
        { "if-true",     ev_node_if(a,
                           ev_node_binop(a,EV_NODE_GT,
                             ev_node_int(a,10,1), ev_node_int(a,5,1),1),
                           ev_node_int(a,42,1), ev_node_int(a,0,1),1),  42 },
        { "if-false",    ev_node_if(a,
                           ev_node_binop(a,EV_NODE_GT,
                             ev_node_int(a,1,1), ev_node_int(a,10,1),1),
                           ev_node_int(a,42,1), ev_node_int(a,-1,1),1), -1 },
        { "if-nested",   ev_node_if(a,
                           ev_node_bool(a,1,1),
                           ev_node_if(a, ev_node_bool(a,0,1),
                             ev_node_int(a,1,1), ev_node_int(a,42,1),1),
                           ev_node_int(a,0,1),1),                       42 },
    };

    EV_PARAMS(cases, tc) {
        EValue nv, fv;
        _both_paths(tc.prog, &nv, &fv);
        /* both paths correct */
        ASSERT_EQ_INT(tc.want, nv.body.as_int);
        ASSERT_EQ_INT(tc.want, fv.body.as_int);
        /* and identical to each other */
        ASSERT_EQ_INT(nv.tag,          fv.tag);
        ASSERT_EQ_INT(nv.body.as_int,  fv.body.as_int);
    }
    ev_arena_free(a);
}

EV_SUITE_TAGGED(form_equivalence_functions, "form", "equivalence") {
    EvArena *a = ev_arena_new("equivfn");
    const char *ps[] = { "n" };
    EvNode *body = ev_node_binop(a, EV_NODE_MUL,
                     ev_node_var(a,"n",1), ev_node_var(a,"n",1), 1);
    EvNode *def  = ev_node_def(a, "square", ps, 1, body, 1);

    /* node path */
    EvArena *na = ev_arena_new("n");
    EvModule *mn = ev_lower_module("N", def, na);
    ev_optimise(mn->funcs[0]);
    EvInterp *in = ev_interp_new(mn);
    EValue arg = ev_int(7);
    EValue rn  = ev_interp_call(in, "square", &arg, 1);

    /* form path */
    EvArena *fa = ev_arena_new("f");
    EvForm  *ff = ev_form_from_node(def, fa);
    EvModule *mf = ev_lower_form_module("F", ff, fa);
    ev_optimise(mf->funcs[0]);
    EvInterp *ifp = ev_interp_new(mf);
    EValue arg2 = ev_int(7);
    EValue rf   = ev_interp_call(ifp, "square", &arg2, 1);

    ASSERT_EQ_INT(49,     rn.body.as_int);
    ASSERT_EQ_INT(49,     rf.body.as_int);
    ASSERT_EQ_INT(rn.tag, rf.tag);
    ASSERT_EQ_INT(rn.body.as_int, rf.body.as_int);

    ev_interp_free(in);  ev_module_free(mn);
    ev_interp_free(ifp); ev_module_free(mf);
    ev_arena_free(a);


    /* ev_lower_form_module mints its own arena, so these are
       ours to release. */
    ev_arena_free(na);
    ev_arena_free(fa);
}

/* ═════════════════════════════════════════════
 * GROUP 3 — EXTENSION WITHOUT IR CHANGES
 *
 * Each construct below is absent from ir.h, tac.c and form_lower.c.
 * None required a new node kind, opcode, or lowering case. They are
 * built entirely from the eleven forms already in the table.
 * ═════════════════════════════════════════════ */

EV_SUITE_TAGGED(form_ext_unless, "form", "extension") {
    /* `unless c then a else b` — inverted conditional.
       Under a syntax-schema IR this needs EV_NODE_UNLESS plus a
       lowering case. Here it is BRANCH with the arms swapped. */
    EvArena *a = ev_arena_new("unless");

    /* Desugaring rule:  unless C then A else B   ≡   if C then B else A
     *
     * Source:   unless (1 > 10) then 99 else 42
     * Condition 1 > 10 is FALSE, so `unless` runs its then-text: 99.
     * Desugared: BRANCH(1>10, [42, 99]) — arms swapped — also 99. */
    EvForm *cond = ev_form_apply2(a, EV_ROLE_GT,
                     ev_form_int(a,1,1), ev_form_int(a,10,1), 1);
    EvForm *arms[2] = { ev_form_int(a,42,1),   /* arm0 ← the else-text B */
                        ev_form_int(a,99,1) }; /* arm1 ← the then-text A */
    EvForm *unless = ev_form_branch(a, EV_ROLE_IF, cond, arms, 2, 1);

    char err[256];
    ASSERT_EQ_INT(1, ev_form_validate(unless, err, sizeof err));

    EvModule *m = ev_lower_form_module("unless", unless, a);
    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    ASSERT_EQ_INT(EV_INT, r.tag);
    ASSERT_EQ_INT(99,     r.body.as_int);   /* then-text, condition false */
    ev_interp_free(ip); ev_module_free(m);

    /* And the mirror case: condition TRUE means `unless` runs its
     * else-text, proving the swap is not an accident of one input. */
    EvArena *a2 = ev_arena_new("unless2");
    EvForm *cond2 = ev_form_apply2(a2, EV_ROLE_GT,
                      ev_form_int(a2,10,1), ev_form_int(a2,1,1), 1);
    EvForm *arms2[2] = { ev_form_int(a2,42,1), ev_form_int(a2,99,1) };
    EvForm *unless2 = ev_form_branch(a2, EV_ROLE_IF, cond2, arms2, 2, 1);
    EvModule *m2 = ev_lower_form_module("unless2", unless2, a2);
    ev_optimise(m2->global_body);
    EvInterp *ip2 = ev_interp_new(m2);
    EValue r2 = ev_interp_run(ip2);
    ASSERT_EQ_INT(42, r2.body.as_int);      /* else-text, condition true */
    ev_interp_free(ip2); ev_module_free(m2);


    /* ev_lower_form_module mints its own arena, so these are
       ours to release. */
    ev_arena_free(a);
    ev_arena_free(a2);
}

EV_SUITE_TAGGED(form_ext_ternary, "form", "extension") {
    /* `c ? a : b` — C-style ternary. Same BRANCH, different spelling. */
    EvArena *a = ev_arena_new("ternary");
    EvForm *cond = ev_form_apply2(a, EV_ROLE_LT,
                     ev_form_int(a,3,1), ev_form_int(a,9,1), 1);
    EvForm *arms[2] = { ev_form_int(a,42,1), ev_form_int(a,0,1) };
    EvForm *tern = ev_form_branch(a, EV_ROLE_IF, cond, arms, 2, 1);

    EvModule *m = ev_lower_form_module("tern", tern, a);
    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    ASSERT_EQ_INT(42, r.body.as_int);
    ev_interp_free(ip); ev_module_free(m);


    /* ev_lower_form_module mints its own arena, so these are
       ours to release. */
    ev_arena_free(a);
}

EV_SUITE_TAGGED(form_ext_guard, "form", "extension") {
    /* `guard c then a` — one arm, no else. The contract allows
       BRANCH with a single arm, and form_lower handles N=1 without
       a special case. */
    EvArena *a = ev_arena_new("guard");
    EvForm *arms[1] = { ev_form_int(a,42,1) };
    EvForm *g = ev_form_branch(a, EV_ROLE_GUARD,
                  ev_form_bool(a,1,1), arms, 1, 1);

    char err[256];
    ASSERT_EQ_INT(1, ev_form_validate(g, err, sizeof err));
    ASSERT_EQ_INT(1, ev_form_arm_count(g));

    EvModule *m = ev_lower_form_module("guard", g, a);
    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    ASSERT_EQ_INT(42, r.body.as_int);
    ev_interp_free(ip); ev_module_free(m);


    /* ev_lower_form_module mints its own arena, so these are
       ours to release. */
    ev_arena_free(a);
}

EV_SUITE_TAGGED(form_ext_sequence, "form", "extension") {
    /* `{ a; b; c }` — a block expression yielding its last value.
       EvNode has no block kind at all; statement lists were handled
       ad hoc inside ev_lower_module. SEQUENCE makes blocks a normal
       form that nests anywhere. */
    EvArena *a = ev_arena_new("seq");
    EvForm *items[3] = {
        ev_form_int(a, 1, 1),
        ev_form_int(a, 2, 2),
        ev_form_apply2(a, EV_ROLE_ADD,
          ev_form_int(a,6,3), ev_form_int(a,36,3), 3)
    };
    EvForm *blk = ev_form_sequence(a, EV_ROLE_BLOCK, items, 3, 1);

    char err[256];
    ASSERT_EQ_INT(1, ev_form_validate(blk, err, sizeof err));
    ev_form_measure(blk);
    ASSERT_EQ_INT(6, blk->size);

    EvModule *m = ev_lower_form_module("seq", blk, a);
    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    ASSERT_EQ_INT(42, r.body.as_int);   /* value of the last item */
    ev_interp_free(ip); ev_module_free(m);


    /* ev_lower_form_module mints its own arena, so these are
       ours to release. */
    ev_arena_free(a);
}

EV_SUITE_TAGGED(form_ext_binding_in_block, "form", "extension") {
    /* `{ let x = 6; let y = 36; x + y }` — bindings inside a block.
       Two forms composed: SEQUENCE of BINDING, then an APPLICATION
       over REFERENCEs. No new IR. */
    EvArena *a = ev_arena_new("bindblk");
    EvForm *items[3] = {
        ev_form_binding(a, EV_ROLE_BIND_LET,  "x", ev_form_int(a,6,1),  1),
        ev_form_binding(a, EV_ROLE_BIND_EVER, "y", ev_form_int(a,36,2), 2),
        ev_form_apply2(a, EV_ROLE_ADD,
          ev_form_ref(a,"x",3), ev_form_ref(a,"y",3), 3)
    };
    EvForm *blk = ev_form_sequence(a, EV_ROLE_BLOCK, items, 3, 1);

    char err[256];
    ASSERT_EQ_INT(1, ev_form_validate(blk, err, sizeof err));

    EvModule *m = ev_lower_form_module("bindblk", blk, a);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    ASSERT_EQ_INT(EV_INT, r.tag);
    ASSERT_EQ_INT(42,     r.body.as_int);
    ev_interp_free(ip); ev_module_free(m);


    /* ev_lower_form_module mints its own arena, so these are
       ours to release. */
    ev_arena_free(a);
}

EV_MAIN
