/*
 * kitchen_sink.c — Ever / Tapestry, the exhaustive single-file test
 *
 * ═══════════════════════════════════════════════════════════════
 * WHAT THIS IS
 * ═══════════════════════════════════════════════════════════════
 *
 * One file that touches every feature the language has, at every
 * boundary it has, in one run. Not a demo — a net. The targeted
 * suites (native_test, form_test, profiler_test) each check one
 * layer well; this one checks the SEAMS BETWEEN layers, which is
 * where the two bugs that produced this file were hiding:
 *
 *   1. The interpreter had no call frames, so a recursive call bound
 *      its parameters over the caller's registers. fact(n) returned
 *      2^(n-1). Every layer passed its own tests. Nothing composed
 *      recursion with parameter binding until this file did.
 *
 *   2. Z did not travel through arithmetic. An INT times a VOID read
 *      the void's body as a double and produced a confident, wrong,
 *      entirely plausible REAL — the exact failure the whole
 *      confidence system exists to prevent.
 *
 * Both were silent. Neither crashed. That is the argument for a
 * kitchen sink: the dangerous failures in a language runtime are not
 * segfaults, they are believable numbers.
 *
 * ═══════════════════════════════════════════════════════════════
 * SECTIONS
 * ═══════════════════════════════════════════════════════════════
 *
 *   1  DATA TYPES        every tag, every boundary value
 *   2  TEXT BOUNDARIES   empty, one byte, exact fit, overflow
 *   3  NUMERIC EDGES     INT64 limits, inf, NaN, -0.0, div by zero
 *   4  CONFIDENCE        the 0..256 scale at its ends
 *   5  Z SEMANTICS       zero-absolute as a state, and contagion
 *   6  CONTROL FLOW      thirty-plus branch circumstances
 *   7  RECURSION         base cases, the depth ceiling, either side
 *   8  SCOPING           chains, shadowing, deletion, restoration
 *   9  ARGUMENT PASSING  by value vs by reference, proven both ways
 *  10  IR + FORMS        every node kind, every form, round trips
 *  11  WIRE              serialise/deserialise across arenas
 *  12  FULL PIPELINE     source semantics end to end, both backends
 *
 * Run:  ./kitchen_sink            all sections
 *       ./kitchen_sink --tag ks_scoping
 *       ./kitchen_sink -v         show passing assertions too
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "ev_test.h"
#include "tapestry.h"
#include "evalue.h"
#include "ir.h"
#include "scope.h"
#include "tac.h"
#include "form.h"

#include <math.h>
#include <float.h>
#include <string.h>
#include <stdint.h>

#ifndef E_INTAKE
#define E_INTAKE 120
#endif
/* Ever's depth ceiling is floor(pi) = 3. It lives in ever.py and ir.py
   on the Python side and in tac.c on the C side; tapestry.h does not
   export it, so the guard mirrors the same value here. */
#ifndef E_DEPTH_CEILING
#define E_DEPTH_CEILING 3
#endif

/* ═══════════════════════════════════════════════════════════════
 * SECTION 1 — DATA TYPES: every tag the language can hold
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_types_all_eight, "ks", "ks_types") {
    ev_pool pool; ev_pool_init(&pool);

    /* All eight EValue tags constructed and identified. If a ninth
       is ever added, this count is the first thing that fails. */
    EValue v_void = ev_void();
    EValue v_bool = ev_bool(1);
    EValue v_int  = ev_int(42);
    EValue v_real = ev_real(3.14159);
    EValue v_text = ev_text("Codric");
    uint8_t raw[4] = { 0xDE, 0xAD, 0xBE, 0xEF };
    EValue v_blob = ev_blob_new(raw, 4, &pool);
    EValue v_list = ev_list_new(&pool);
    EValue v_rec  = ev_record_new(&pool);

    ASSERT_EQ_INT(EV_VOID,   v_void.tag);
    ASSERT_EQ_INT(EV_BOOL,   v_bool.tag);
    ASSERT_EQ_INT(EV_INT,    v_int.tag);
    ASSERT_EQ_INT(EV_REAL,   v_real.tag);
    ASSERT_EQ_INT(EV_TEXT,   v_text.tag);
    ASSERT_EQ_INT(EV_BLOB,   v_blob.tag);
    ASSERT_EQ_INT(EV_LIST,   v_list.tag);
    ASSERT_EQ_INT(EV_RECORD, v_rec.tag);

    /* Tag numbering is part of the wire contract — it must not drift */
    ASSERT_EQ_INT(0, EV_VOID);
    ASSERT_EQ_INT(5, EV_BLOB);
    ASSERT_EQ_INT(6, EV_LIST);
    ASSERT_EQ_INT(7, EV_RECORD);

    /* The 208-byte envelope holds all eight identically */
    ASSERT_EQ_INT(208, (int)sizeof(EValue));
    ASSERT_EQ_INT(208, (int)sizeof(v_blob));
    ASSERT_EQ_INT(208, (int)sizeof(v_void));

    ev_pool_clear(&pool);
}

EV_SUITE_TAGGED(ks_types_composites, "ks", "ks_types") {
    ev_pool pool; ev_pool_init(&pool);

    /* LIST holding one of every scalar type at once — a list is not
       typed, so this is legal and must round-trip element by element */
    EValue mixed = ev_list_new(&pool);
    ev_list_push(&mixed, ev_void(),        &pool);
    ev_list_push(&mixed, ev_bool(0),       &pool);
    ev_list_push(&mixed, ev_int(-7),       &pool);
    ev_list_push(&mixed, ev_real(2.5),     &pool);
    ev_list_push(&mixed, ev_text("mixed"), &pool);
    ASSERT_EQ_INT(5, ev_list_len(&mixed, &pool));
    ASSERT_EQ_INT(EV_VOID, ev_list_get(&mixed, 0, &pool).tag);
    ASSERT_EQ_INT(0,       ev_list_get(&mixed, 1, &pool).body.as_bool);
    ASSERT_EQ_INT(-7,      ev_list_get(&mixed, 2, &pool).body.as_int);
    ASSERT_EQ_REAL(2.5,    ev_list_get(&mixed, 3, &pool).body.as_real, 1e-12);
    ASSERT_EQ_STR("mixed", ev_list_get(&mixed, 4, &pool).text);

    /* Out-of-range index yields VOID rather than reading past the end */
    ASSERT_EQ_INT(EV_VOID, ev_list_get(&mixed,  99, &pool).tag);
    ASSERT_EQ_INT(EV_VOID, ev_list_get(&mixed,  -1, &pool).tag);

    /* Empty list is a legal value, not an error */
    EValue empty = ev_list_new(&pool);
    ASSERT_EQ_INT(0,       ev_list_len(&empty, &pool));
    ASSERT_EQ_INT(EV_LIST, empty.tag);

    /* RECORD: the structure that makes an SQL row and an HTML element
       the same shape. Absent key is VOID, present key is the value. */
    EValue rec = ev_record_new(&pool);
    ev_record_set(&rec, "id",     ev_int(7),         E_CERTAIN, &pool);
    ev_record_set(&rec, "name",   ev_text("Alice"),  E_CERTAIN, &pool);
    ev_record_set(&rec, "score",  ev_real(99.5),     200,       &pool);
    ev_record_set(&rec, "active", ev_bool(1),        E_CERTAIN, &pool);
    ev_record_set(&rec, "note",   ev_void(),         0,         &pool);

    ASSERT_EQ_INT(7,        ev_record_get(&rec, "id",    &pool).body.as_int);
    ASSERT_EQ_STR("Alice",  ev_record_get(&rec, "name",  &pool).text);
    ASSERT_EQ_REAL(99.5,    ev_record_get(&rec, "score", &pool).body.as_real, 1e-9);
    ASSERT_EQ_INT(1,        ev_record_get(&rec, "active",&pool).body.as_bool);
    ASSERT_EQ_INT(EV_VOID,  ev_record_get(&rec, "note",  &pool).tag);
    ASSERT_EQ_INT(EV_VOID,  ev_record_get(&rec, "absent",&pool).tag);
    ASSERT_EQ_INT(1, ev_record_has(&rec, "id",     &pool));
    ASSERT_EQ_INT(0, ev_record_has(&rec, "absent", &pool));

    /* Overwriting a key replaces rather than duplicates */
    ev_record_set(&rec, "id", ev_int(8), E_CERTAIN, &pool);
    ASSERT_EQ_INT(8, ev_record_get(&rec, "id", &pool).body.as_int);

    /* Nesting: a list inside a record inside a list */
    EValue inner = ev_list_new(&pool);
    ev_list_push(&inner, ev_int(1), &pool);
    ev_list_push(&inner, ev_int(2), &pool);
    EValue holder = ev_record_new(&pool);
    ev_record_set(&holder, "items", inner, E_CERTAIN, &pool);
    EValue outer = ev_list_new(&pool);
    ev_list_push(&outer, holder, &pool);
    EValue got_rec  = ev_list_get(&outer, 0, &pool);
    EValue got_list = ev_record_get(&got_rec, "items", &pool);
    ASSERT_EQ_INT(EV_RECORD, got_rec.tag);
    ASSERT_EQ_INT(EV_LIST,   got_list.tag);
    ASSERT_EQ_INT(2,         ev_list_len(&got_list, &pool));
    ASSERT_EQ_INT(2,         ev_list_get(&got_list, 1, &pool).body.as_int);

    ev_pool_clear(&pool);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 2 — TEXT BOUNDARIES
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_text_boundaries, "ks", "ks_bounds") {
    /* EV_INLINE_MAX is 192 bytes of storage, so the longest string
       that fits with its terminator is 191 characters. */
    ASSERT_EQ_INT(192, EV_INLINE_MAX);

    /* empty string is a value, distinct from void */
    EValue e = ev_text("");
    ASSERT_EQ_INT(EV_TEXT, e.tag);
    ASSERT_EQ_INT(0, (int)strlen(e.text));

    /* one byte */
    EValue one = ev_text("x");
    ASSERT_EQ_INT(1, (int)strlen(one.text));
    ASSERT_EQ_STR("x", one.text);

    /* exact fit: 191 characters survives whole */
    char fit[192];
    memset(fit, 'a', 191); fit[191] = '\0';
    EValue vfit = ev_text(fit);
    ASSERT_EQ_INT(191, (int)strlen(vfit.text));

    /* overflow: 400 characters truncates to 191, does not corrupt */
    char over[400];
    memset(over, 'x', sizeof over - 1); over[sizeof over - 1] = '\0';
    EValue vover = ev_text(over);
    ASSERT_EQ_INT(191,     (int)strlen(vover.text));
    ASSERT_EQ_INT(EV_TEXT, vover.tag);
    ASSERT_EQ_INT('\0',    vover.text[191]);   /* terminator intact */

    /* embedded specials survive */
    EValue tabs  = ev_text("a\tb\nc");
    ASSERT_EQ_STR("a\tb\nc", tabs.text);
    EValue quote = ev_text("say \"hi\"");
    ASSERT_EQ_STR("say \"hi\"", quote.text);

    /* NULL is tolerated, not dereferenced */
    EValue vnull = ev_text(NULL);
    ASSERT_EQ_INT(EV_TEXT, vnull.tag);
    ASSERT_EQ_INT(0, (int)strlen(vnull.text));
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 3 — NUMERIC EDGES
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_numeric_edges, "ks", "ks_bounds") {
    /* INT64 at both extremes, exactly */
    EValue imin = ev_int(INT64_MIN);
    EValue imax = ev_int(INT64_MAX);
    ASSERT(imin.body.as_int == INT64_MIN);
    ASSERT(imax.body.as_int == INT64_MAX);
    ASSERT_EQ_INT(0,  ev_int(0).body.as_int);
    ASSERT_EQ_INT(-1, ev_int(-1).body.as_int);

    /* REAL specials are preserved rather than normalised away */
    EValue vinf  = ev_real(INFINITY);
    EValue vninf = ev_real(-INFINITY);
    EValue vnan  = ev_real(NAN);
    EValue vnzero= ev_real(-0.0);
    /* C99 only promises isinf() is non-zero; glibc encodes the sign,
       so -inf gives -1. Test the contract, not one libc's spelling. */
    ASSERT(isinf(vinf.body.as_real)  != 0);
    ASSERT(isinf(vninf.body.as_real) != 0);
    ASSERT(vinf.body.as_real  > 0);
    ASSERT(vninf.body.as_real < 0);
    ASSERT_EQ_INT(1, isnan(vnan.body.as_real));
    ASSERT_EQ_INT(1, signbit(vnzero.body.as_real));   /* -0.0 ≠ 0.0 */

    /* smallest and largest finite doubles */
    ASSERT_EQ_REAL(DBL_MAX, ev_real(DBL_MAX).body.as_real, 0.0);
    ASSERT_EQ_REAL(DBL_MIN, ev_real(DBL_MIN).body.as_real, 0.0);

    /* BOOL normalises any non-zero to exactly 1 — the tag promises a
       two-valued type, so 2 must not survive as 2 */
    ASSERT_EQ_INT(1, ev_bool(1).body.as_bool);
    ASSERT_EQ_INT(1, ev_bool(2).body.as_bool);
    ASSERT_EQ_INT(1, ev_bool(-99).body.as_bool);
    ASSERT_EQ_INT(0, ev_bool(0).body.as_bool);

    /* INT and REAL compare across representations */
    ev_pool pool; ev_pool_init(&pool);
    EValue i3 = ev_int(3), r3 = ev_real(3.0), r31 = ev_real(3.1);
    ASSERT_EQ_INT(1, ev_equal(&i3, &r3,  &pool));
    ASSERT_EQ_INT(0, ev_equal(&i3, &r31, &pool));
    ev_pool_clear(&pool);
}

EV_SUITE_TAGGED(ks_arithmetic_edges, "ks", "ks_bounds") {
    /* Arithmetic through the real pipeline, at edges */
    struct { const char *label; int64_t a, b; EvNodeKind op; int64_t want; }
    cases[] = {
        { "0+0",         0,  0, EV_NODE_ADD,  0 },
        { "0*99",        0, 99, EV_NODE_MUL,  0 },
        { "neg+pos",   -50, 92, EV_NODE_ADD, 42 },
        { "neg*neg",    -6, -7, EV_NODE_MUL, 42 },
        { "big-big", 1000000, 999958, EV_NODE_SUB, 42 },
        { "identity",   42,  1, EV_NODE_MUL, 42 },
    };
    EV_PARAMS(cases, tc) {
        EvArena *a = ev_arena_new(tc.label);
        EvNode  *n = ev_node_binop(a, tc.op,
                        ev_node_int(a, tc.a, 1),
                        ev_node_int(a, tc.b, 1), 1);
        EvModule *m = ev_lower_module(tc.label, n, a);
        ev_optimise(m->global_body);
        EvInterp *ip = ev_interp_new(m);
        EValue r = ev_interp_run(ip);
        ASSERT_EQ_INT(tc.want, r.body.as_int);
        ev_interp_free(ip); ev_module_free(m);
        ev_arena_free(a);
    }
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 4 — CONFIDENCE: the 0..256 scale at its ends
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_confidence_scale, "ks", "ks_conf") {
    /* The constants that define the scale */
    ASSERT_EQ_INT(256, E_CERTAIN);
    ASSERT_EQ_INT(0,   E_ZERO);
    ASSERT_EQ_INT(128, E_EXECUTE_FLOOR);
    ASSERT_EQ_INT(120, E_INTAKE);

    /* External data enters below the execute floor by design: nothing
       from outside is trusted enough to act on without corroboration */
    ASSERT(E_INTAKE < E_EXECUTE_FLOOR);

    /* Corroboration is multiplicative: u_result = u_a × u_b */
    ASSERT_EQ_INT(256, e_excel_formula(E_CERTAIN, E_CERTAIN));

    /* Two certains stay certain; anything less never reaches certain */
    ASSERT(e_excel_formula(255, 255) < E_CERTAIN);
    ASSERT(e_excel_formula(200, 200) < E_CERTAIN);
    ASSERT(e_excel_formula(128, 128) < E_CERTAIN);

    /* Corroboration RAISES trust — two independent 128s beat one */
    ASSERT(e_excel_formula(128, 128) > 128);

    /* Monotonic: more trust in equals more trust out */
    ASSERT(e_excel_formula(200, 200) > e_excel_formula(100, 100));
    ASSERT(e_excel_formula(255, 255) > e_excel_formula(200, 200));

    /* Certain is unreachable by combining the merely confident */
    for (int16_t c = 1; c < 256; c++)
        if (e_excel_formula(c, c) >= E_CERTAIN) {
            ASSERT_EQ_INT(256, c);   /* only 256 may produce 256 */
        }
}

EV_SUITE_TAGGED(ks_confidence_propagation, "ks", "ks_conf") {
    /* A result is only as trustworthy as its least trustworthy input.
       Constants are certain; loaded values enter at intake. */
    EvArena *a = ev_arena_new("conf");
    EvModule *m = ev_module_new("conf", a);
    EvFunc  *f  = ev_module_add_func(m, "f", NULL, 0);
    EvBlock *b  = ev_func_new_block(f);
    EvBuilder bld = ev_builder(m, f, b);

    EvReg certain = ev_emit_const(&bld, ev_int(42), 1);
    EvReg intake  = ev_emit_load(&bld, "external", EV_INT, E_INTAKE, 1);
    EvReg sum     = ev_emit_binop(&bld, OP_ADD, certain, intake, 1);

    ASSERT_EQ_INT(E_CERTAIN, certain.confidence);
    ASSERT_EQ_INT(E_INTAKE,  intake.confidence);

    ev_pass_conf_prop(f);

    int16_t got = E_CERTAIN;
    for (int32_t i = 0; i < b->len; i++)
        if (b->instrs[i].dest.id == sum.id)
            got = b->instrs[i].dest.confidence;

    /* min-of-operands: certain + intake = intake, never certain */
    ASSERT_EQ_INT(E_INTAKE, got);
    ASSERT(got < E_CERTAIN);

    /* ARENA OWNERSHIP, the asymmetry that has caused two double-frees
       in this codebase and is worth stating exactly where it bites:
         ev_module_new(name, arena)     TAKES the arena; ev_module_free
                                        frees it. Never free it again.
         ev_lower_module(name, root, a) MINTS its own arena; `a` still
                                        owns the tree and stays yours.
         ev_lower_form_module(...)      same as ev_lower_module.
       This suite built its module the first way, so `a` goes with it
       and there is deliberately no ev_arena_free here. */
    ev_module_free(m);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 5 — Z: zero-absolute as a state, and its contagion
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_z_semantics, "ks", "ks_z") {
    /* Z is not the number zero. It is the absence of a measurement. */
    e_particle z    = e_z("unmeasured", "sensor offline");
    e_particle zero = e_int("zero", 0, E_CERTAIN, E_LANG_EVER);

    ASSERT_EQ_INT(1, e_is_z(&z));
    ASSERT_EQ_INT(0, e_is_z(&zero));      /* 0 is a known value */
    ASSERT_EQ_INT(0, z.confidence);
    ASSERT_EQ_INT(E_CERTAIN, zero.confidence);
    ASSERT_EQ_INT(0, zero.value.as_int);

    /* Z carries its reason — an unknown that cannot say why it is
       unknown is not much better than a crash */
    ASSERT_NOT_NULL(z.reason);
    ASSERT(strlen(z.reason) > 0);
}

EV_SUITE_TAGGED(ks_z_contagion, "ks", "ks_z") {
    /* Z must TRAVEL through arithmetic. This is the regression guard
       for the second bug this file found: an INT times a VOID used to
       read the void's body as a double and return a plausible REAL. */
    EvArena *a = ev_arena_new("zc");
    const char *pn[] = { "n" };

    /* A function that recurses past the ceiling returns z, so
       n * f(n-1) gives us an INT times a z at the boundary. */
    EvNode *body = ev_node_if(a,
        ev_node_binop(a, EV_NODE_LTE,
            ev_node_var(a,"n",1), ev_node_int(a,1,1), 1),
        ev_node_int(a,1,1),
        ev_node_binop(a, EV_NODE_MUL,
            ev_node_var(a,"n",1),
            ev_node_call(a, "deep",
                (EvNode*[]){ ev_node_binop(a, EV_NODE_SUB,
                    ev_node_var(a,"n",1), ev_node_int(a,1,1), 1) }, 1, 1), 1), 1);
    EvNode *def = ev_node_def(a, "deep", pn, 1, body, 1);
    EvModule *m = ev_lower_module("zc", def, a);
    ev_optimise(m->funcs[0]);
    EvInterp *ip = ev_interp_new(m);

    /* past the ceiling the whole expression is z, NOT a stray REAL */
    EValue arg = ev_int(6);
    EValue r = ev_interp_call(ip, "deep", &arg, 1);
    ASSERT_EQ_INT(EV_VOID, r.tag);
    ASSERT(r.tag != EV_REAL);   /* the exact bug, named */

    ev_interp_free(ip); ev_module_free(m);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(a);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 6 — CONTROL FLOW: many branch circumstances
 * ═══════════════════════════════════════════════════════════════ */

/* helper: build `if (a OP b) then t else e` and run it */
static int64_t _branch(EvNodeKind op, int64_t a_, int64_t b_,
                       int64_t t_, int64_t e_) {
    EvArena *a = ev_arena_new("br");
    EvNode *n = ev_node_if(a,
        ev_node_binop(a, op, ev_node_int(a,a_,1), ev_node_int(a,b_,1), 1),
        ev_node_int(a, t_, 1), ev_node_int(a, e_, 1), 1);
    EvModule *m = ev_lower_module("br", n, a);
    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    int64_t out = (r.tag == EV_INT) ? r.body.as_int : -12345;
    ev_interp_free(ip); ev_module_free(m); ev_arena_free(a);
    return out;
}

EV_SUITE_TAGGED(ks_branch_all_operators, "ks", "ks_flow") {
    /* Every comparison operator, true side and false side, plus the
       equality boundary where < and <= disagree. Thirty circumstances. */
    struct { const char *label; EvNodeKind op;
             int64_t a, b; int64_t want; } cases[] = {
        /* LT */
        { "3<9 true",     EV_NODE_LT,   3,  9,  1 },
        { "9<3 false",    EV_NODE_LT,   9,  3,  0 },
        { "3<3 boundary", EV_NODE_LT,   3,  3,  0 },
        /* GT */
        { "9>3 true",     EV_NODE_GT,   9,  3,  1 },
        { "3>9 false",    EV_NODE_GT,   3,  9,  0 },
        { "3>3 boundary", EV_NODE_GT,   3,  3,  0 },
        /* LTE — differs from LT exactly at equality */
        { "3<=9 true",    EV_NODE_LTE,  3,  9,  1 },
        { "9<=3 false",   EV_NODE_LTE,  9,  3,  0 },
        { "3<=3 boundary",EV_NODE_LTE,  3,  3,  1 },
        /* GTE */
        { "9>=3 true",    EV_NODE_GTE,  9,  3,  1 },
        { "3>=9 false",   EV_NODE_GTE,  3,  9,  0 },
        { "3>=3 boundary",EV_NODE_GTE,  3,  3,  1 },
        /* EQ */
        { "3==3 true",    EV_NODE_EQ,   3,  3,  1 },
        { "3==9 false",   EV_NODE_EQ,   3,  9,  0 },
        { "0==0 zero",    EV_NODE_EQ,   0,  0,  1 },
        { "-1==-1 neg",   EV_NODE_EQ,  -1, -1,  1 },
        /* NEQ */
        { "3!=9 true",    EV_NODE_NEQ,  3,  9,  1 },
        { "3!=3 false",   EV_NODE_NEQ,  3,  3,  0 },
        { "0!=-0 zero",   EV_NODE_NEQ,  0,  0,  0 },
    };
    EV_PARAMS(cases, tc) {
        ASSERT_EQ_INT(tc.want, _branch(tc.op, tc.a, tc.b, 1, 0));
    }
}

EV_SUITE_TAGGED(ks_branch_shapes, "ks", "ks_flow") {
    EvArena *a = ev_arena_new("shapes");

    /* 1. condition is a bare literal, not a comparison */
    {
        EvNode *n = ev_node_if(a, ev_node_bool(a,1,1),
                        ev_node_int(a,42,1), ev_node_int(a,0,1), 1);
        EvModule *m = ev_lower_module("lit", n, a);
        EvInterp *ip = ev_interp_new(m);
        ASSERT_EQ_INT(42, ev_interp_run(ip).body.as_int);
        ev_interp_free(ip); ev_module_free(m);
    }
    /* 2. condition false literal takes the else arm */
    {
        EvArena *b = ev_arena_new("s2");
        EvNode *n = ev_node_if(b, ev_node_bool(b,0,1),
                        ev_node_int(b,42,1), ev_node_int(b,7,1), 1);
        EvModule *m = ev_lower_module("lit0", n, b);
        EvInterp *ip = ev_interp_new(m);
        ASSERT_EQ_INT(7, ev_interp_run(ip).body.as_int);
        ev_interp_free(ip); ev_module_free(m); ev_arena_free(b);
    }
    /* 3. arms are expressions, not literals */
    {
        EvArena *b = ev_arena_new("s3");
        EvNode *n = ev_node_if(b,
            ev_node_binop(b,EV_NODE_GT,ev_node_int(b,10,1),ev_node_int(b,5,1),1),
            ev_node_binop(b,EV_NODE_ADD,ev_node_int(b,6,1),ev_node_int(b,36,1),1),
            ev_node_binop(b,EV_NODE_MUL,ev_node_int(b,0,1),ev_node_int(b,9,1),1),1);
        EvModule *m = ev_lower_module("expr", n, b);
        ev_optimise(m->global_body);
        EvInterp *ip = ev_interp_new(m);
        ASSERT_EQ_INT(42, ev_interp_run(ip).body.as_int);
        ev_interp_free(ip); ev_module_free(m); ev_arena_free(b);
    }
    /* 4. the CONDITION is itself a branch */
    {
        EvArena *b = ev_arena_new("s4");
        EvNode *inner = ev_node_if(b, ev_node_bool(b,1,1),
                            ev_node_bool(b,1,1), ev_node_bool(b,0,1), 1);
        EvNode *n = ev_node_if(b, inner,
                        ev_node_int(b,42,1), ev_node_int(b,0,1), 1);
        EvModule *m = ev_lower_module("condbr", n, b);
        EvInterp *ip = ev_interp_new(m);
        ASSERT_EQ_INT(42, ev_interp_run(ip).body.as_int);
        ev_interp_free(ip); ev_module_free(m); ev_arena_free(b);
    }
    /* 5. branch nested three deep in the THEN arm */
    {
        EvArena *b = ev_arena_new("s5");
        EvNode *l3 = ev_node_if(b, ev_node_bool(b,1,1),
                        ev_node_int(b,42,1), ev_node_int(b,-3,1), 1);
        EvNode *l2 = ev_node_if(b, ev_node_bool(b,1,1), l3,
                        ev_node_int(b,-2,1), 1);
        EvNode *l1 = ev_node_if(b, ev_node_bool(b,1,1), l2,
                        ev_node_int(b,-1,1), 1);
        EvModule *m = ev_lower_module("deep", l1, b);
        EvInterp *ip = ev_interp_new(m);
        ASSERT_EQ_INT(42, ev_interp_run(ip).body.as_int);
        ev_interp_free(ip); ev_module_free(m); ev_arena_free(b);
    }
    /* 6. branch nested three deep in the ELSE arm — the path the
          original merge-block bug got wrong */
    {
        EvArena *b = ev_arena_new("s6");
        EvNode *l3 = ev_node_if(b, ev_node_bool(b,0,1),
                        ev_node_int(b,-3,1), ev_node_int(b,42,1), 1);
        EvNode *l2 = ev_node_if(b, ev_node_bool(b,0,1),
                        ev_node_int(b,-2,1), l3, 1);
        EvNode *l1 = ev_node_if(b, ev_node_bool(b,0,1),
                        ev_node_int(b,-1,1), l2, 1);
        EvModule *m = ev_lower_module("deepelse", l1, b);
        EvInterp *ip = ev_interp_new(m);
        ASSERT_EQ_INT(42, ev_interp_run(ip).body.as_int);
        ev_interp_free(ip); ev_module_free(m); ev_arena_free(b);
    }
    /* 7. both arms nested — every leaf reachable, only one taken */
    {
        EvArena *b = ev_arena_new("s7");
        EvNode *tarm = ev_node_if(b, ev_node_bool(b,0,1),
                        ev_node_int(b,-1,1), ev_node_int(b,42,1), 1);
        EvNode *earm = ev_node_if(b, ev_node_bool(b,1,1),
                        ev_node_int(b,-2,1), ev_node_int(b,-3,1), 1);
        EvNode *n = ev_node_if(b, ev_node_bool(b,1,1), tarm, earm, 1);
        EvModule *m = ev_lower_module("both", n, b);
        EvInterp *ip = ev_interp_new(m);
        ASSERT_EQ_INT(42, ev_interp_run(ip).body.as_int);
        ev_interp_free(ip); ev_module_free(m); ev_arena_free(b);
    }
    /* 8. arms return DIFFERENT types — the merge slot must not assume */
    {
        EvArena *b = ev_arena_new("s8");
        EvNode *n = ev_node_if(b, ev_node_bool(b,0,1),
                        ev_node_int(b,1,1), ev_node_text(b,"else",1), 1);
        EvModule *m = ev_lower_module("mixed", n, b);
        EvInterp *ip = ev_interp_new(m);
        EValue r = ev_interp_run(ip);
        ASSERT_EQ_INT(EV_TEXT, r.tag);
        ASSERT_EQ_STR("else",  r.text);
        ev_interp_free(ip); ev_module_free(m); ev_arena_free(b);
    }
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_branch_generic_forms, "ks", "ks_flow") {
    /* The same control flow through the generic BRANCH form, including
       shapes the legacy EvNode cannot express at all. */
    EvArena *a = ev_arena_new("gbr");

    /* guard: one arm, no else — false selector yields void */
    EvForm *garms[1] = { ev_form_int(a,42,1) };
    EvForm *g_false = ev_form_branch(a, EV_ROLE_GUARD,
                        ev_form_bool(a,0,1), garms, 1, 1);
    EvModule *mg = ev_lower_form_module("g0", g_false, a);
    EvInterp *ig = ev_interp_new(mg);
    ASSERT_EQ_INT(EV_VOID, ev_interp_run(ig).tag);
    ev_interp_free(ig); ev_module_free(mg);

    /* guard with a true selector yields the arm */
    EvArena *b = ev_arena_new("g1");
    EvForm *garms2[1] = { ev_form_int(b,42,1) };
    EvForm *g_true = ev_form_branch(b, EV_ROLE_GUARD,
                        ev_form_bool(b,1,1), garms2, 1, 1);
    EvModule *mg2 = ev_lower_form_module("g1", g_true, b);
    EvInterp *ig2 = ev_interp_new(mg2);
    ASSERT_EQ_INT(42, ev_interp_run(ig2).body.as_int);
    ev_interp_free(ig2); ev_module_free(mg2);

    /* sequence: a block of statements yielding its last value */
    EvArena *c = ev_arena_new("sq");
    EvForm *items[4] = {
        ev_form_binding(c, EV_ROLE_BIND_LET,  "a", ev_form_int(c,6,1),  1),
        ev_form_binding(c, EV_ROLE_BIND_EVER, "b", ev_form_int(c,36,2), 2),
        ev_form_int(c, 999, 3),                      /* discarded */
        ev_form_apply2(c, EV_ROLE_ADD,
            ev_form_ref(c,"a",4), ev_form_ref(c,"b",4), 4)
    };
    EvForm *blk = ev_form_sequence(c, EV_ROLE_BLOCK, items, 4, 1);
    char err[256];
    ASSERT_EQ_INT(1, ev_form_validate(blk, err, sizeof err));
    EvModule *mc = ev_lower_form_module("sq", blk, c);
    EvInterp *ic = ev_interp_new(mc);
    ASSERT_EQ_INT(42, ev_interp_run(ic).body.as_int);
    ev_interp_free(ic); ev_module_free(mc);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(a);
    ev_arena_free(b);
    ev_arena_free(c);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 7 — RECURSION and the depth ceiling
 * ═══════════════════════════════════════════════════════════════ */

/* Build `def NAME(n) = if n <= BASE then BASEVAL else n OP NAME(n-1)` */
static EvModule *_recursive_fn(EvArena *a, const char *name,
                               EvNodeKind combine,
                               int64_t base_n, int64_t base_v) {
    const char *pn[] = { "n" };
    EvNode *rec_arg = ev_node_binop(a, EV_NODE_SUB,
                        ev_node_var(a,"n",1), ev_node_int(a,1,1), 1);
    EvNode *args[1] = { rec_arg };
    EvNode *body = ev_node_if(a,
        ev_node_binop(a, EV_NODE_LTE,
            ev_node_var(a,"n",1), ev_node_int(a, base_n, 1), 1),
        ev_node_int(a, base_v, 1),
        ev_node_binop(a, combine,
            ev_node_var(a,"n",1),
            ev_node_call(a, name, args, 1, 1), 1), 1);
    EvNode *def = ev_node_def(a, name, pn, 1, body, 1);
    EvModule *m = ev_lower_module(name, def, a);
    ev_optimise(m->funcs[0]);
    return m;
}

EV_SUITE_TAGGED(ks_recursion_factorial, "ks", "ks_recursion") {
    /* THE REGRESSION GUARD for the call-frame bug.
       Before frames existed this returned 1, 2, 4, 8 — 2^(n-1) —
       because the recursive call rebound n over the caller's copy. */
    EvArena *a = ev_arena_new("fact");
    EvModule *m = _recursive_fn(a, "fact", EV_NODE_MUL, 1, 1);
    EvInterp *ip = ev_interp_new(m);

    EValue a1 = ev_int(1), a2 = ev_int(2), a3 = ev_int(3);
    EValue r1 = ev_interp_call(ip, "fact", &a1, 1);
    EValue r2 = ev_interp_call(ip, "fact", &a2, 1);
    EValue r3 = ev_interp_call(ip, "fact", &a3, 1);

    ASSERT_EQ_INT(1, r1.body.as_int);   /* base case, no recursion   */
    ASSERT_EQ_INT(2, r2.body.as_int);   /* one level                 */
    ASSERT_EQ_INT(6, r3.body.as_int);   /* two levels — was 4        */

    /* the wrong answers the bug produced, named so they cannot return */
    ASSERT(r3.body.as_int != 4);        /* 2^(3-1)                   */
    ev_interp_free(ip); ev_module_free(m);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_recursion_ceiling, "ks", "ks_recursion") {
    /* Unanchored recursion may use at most floor(pi) = 3 call levels.
       This is a language rule, not a stack limit: past the ceiling the
       answer is z, because the system will not assert what it has not
       earned the right to compute. */
    ASSERT_EQ_INT(3, E_DEPTH_CEILING);

    EvArena *a = ev_arena_new("ceil");
    EvModule *m = _recursive_fn(a, "fact", EV_NODE_MUL, 1, 1);
    EvInterp *ip = ev_interp_new(m);

    /* fact(3) needs exactly 3 frames — the last legal case */
    EValue a3 = ev_int(3);
    EValue r3 = ev_interp_call(ip, "fact", &a3, 1);
    ASSERT_EQ_INT(EV_INT, r3.tag);
    ASSERT_EQ_INT(6,      r3.body.as_int);

    /* fact(4) needs 4 — one past the ceiling, so z */
    EValue a4 = ev_int(4);
    EValue r4 = ev_interp_call(ip, "fact", &a4, 1);
    ASSERT_EQ_INT(EV_VOID, r4.tag);

    /* and it stays z further out, rather than wrapping or drifting */
    EValue a9 = ev_int(9);
    EValue r9 = ev_interp_call(ip, "fact", &a9, 1);
    ASSERT_EQ_INT(EV_VOID, r9.tag);

    ev_interp_free(ip); ev_module_free(m);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_recursion_shapes, "ks", "ks_recursion") {
    /* A different combining operator down the same recursive shape,
       to show the frame fix is not specific to multiplication. */
    EvArena *a = ev_arena_new("tri");
    EvModule *m = _recursive_fn(a, "tri", EV_NODE_ADD, 1, 1);
    EvInterp *ip = ev_interp_new(m);

    EValue a1 = ev_int(1), a2 = ev_int(2), a3 = ev_int(3);
    ASSERT_EQ_INT(1, ev_interp_call(ip, "tri", &a1, 1).body.as_int);
    ASSERT_EQ_INT(3, ev_interp_call(ip, "tri", &a2, 1).body.as_int); /* 2+1 */
    ASSERT_EQ_INT(6, ev_interp_call(ip, "tri", &a3, 1).body.as_int); /* 3+2+1 */
    ev_interp_free(ip); ev_module_free(m);

    /* Repeated calls must be independent: calling fact twice with the
       same argument must give the same answer, and interleaving
       arguments must not leak state between calls. */
    EvArena *b = ev_arena_new("indep");
    EvModule *m2 = _recursive_fn(b, "fact", EV_NODE_MUL, 1, 1);
    EvInterp *ip2 = ev_interp_new(m2);
    EValue x3 = ev_int(3), x2 = ev_int(2);
    int64_t first  = ev_interp_call(ip2, "fact", &x3, 1).body.as_int;
    int64_t middle = ev_interp_call(ip2, "fact", &x2, 1).body.as_int;
    int64_t again  = ev_interp_call(ip2, "fact", &x3, 1).body.as_int;
    ASSERT_EQ_INT(6, first);
    ASSERT_EQ_INT(2, middle);
    ASSERT_EQ_INT(first, again);      /* no residue from the call between */
    ev_interp_free(ip2); ev_module_free(m2);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(a);
    ev_arena_free(b);
}

EV_SUITE_TAGGED(ks_recursion_detection, "ks", "ks_recursion") {
    /* Recursion is visible to static analysis before anything runs */
    EvArena *a = ev_arena_new("detect");
    const char *pn[] = { "n" };
    EvNode *args[1] = { ev_node_var(a,"n",1) };
    EvNode *self = ev_node_call(a, "loops", args, 1, 1);
    EvNode *def  = ev_node_def(a, "loops", pn, 1, self, 1);
    ev_node_measure(def);
    ASSERT(def->size > 1);
    ASSERT_EQ_STR("loops", def->str);
    ASSERT_EQ_INT(EV_NODE_CALL, def->children[0]->kind);
    ASSERT_EQ_STR("loops", def->children[0]->str);  /* calls itself */
    ev_arena_free(a);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 8 — SCOPING and SHADOWING
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_scope_chain, "ks", "ks_scoping") {
    EvArena *a = ev_arena_new("chain");

    EvScope *global = ev_scope_new(a, NULL, "global");
    EvScope *outer  = ev_scope_new(a, global, "outer");
    EvScope *inner  = ev_scope_new(a, outer,  "inner");

    ASSERT_EQ_INT(0, global->depth);
    ASSERT_EQ_INT(1, outer->depth);
    ASSERT_EQ_INT(2, inner->depth);

    ev_scope_set_var(global, "g", ev_int(1), E_CERTAIN, E_LANG_EVER);
    ev_scope_set_var(outer,  "o", ev_int(2), E_CERTAIN, E_LANG_EVER);
    ev_scope_set_var(inner,  "i", ev_int(3), E_CERTAIN, E_LANG_EVER);

    /* lookup walks up the chain; get does not */
    ASSERT_EQ_INT(1, ev_scope_lookup(inner, "g")->value.body.as_int);
    ASSERT_EQ_INT(2, ev_scope_lookup(inner, "o")->value.body.as_int);
    ASSERT_EQ_INT(3, ev_scope_lookup(inner, "i")->value.body.as_int);
    ASSERT_NULL(ev_scope_get(inner, "g"));       /* not local          */
    ASSERT_NOT_NULL(ev_scope_get(inner, "i"));   /* local              */

    /* inner names are invisible from outside — scope has a direction */
    ASSERT_NULL(ev_scope_lookup(global, "i"));
    ASSERT_NULL(ev_scope_lookup(outer,  "i"));
    ASSERT_NULL(ev_scope_lookup(global, "o"));

    /* a name bound nowhere is NULL, not a zero */
    ASSERT_NULL(ev_scope_lookup(inner, "nowhere"));

    ev_scope_free(inner); ev_scope_free(outer); ev_scope_free(global);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_scope_shadowing, "ks", "ks_scoping") {
    EvArena *a = ev_arena_new("shadow");
    EvScope *global = ev_scope_new(a, NULL, "global");
    EvScope *mid    = ev_scope_new(a, global, "mid");
    EvScope *inner  = ev_scope_new(a, mid,    "inner");

    /* the same name bound at all three levels, with different values
       AND different confidences, to prove the whole entry shadows */
    ev_scope_set_var(global, "x", ev_int(100), E_CERTAIN, E_LANG_EVER);
    ev_scope_set_var(mid,    "x", ev_int(200), 200,       E_LANG_EVER);
    ev_scope_set_var(inner,  "x", ev_int(300), 120,       E_LANG_EVER);

    /* each level sees its own binding */
    ASSERT_EQ_INT(300, ev_scope_lookup(inner,  "x")->value.body.as_int);
    ASSERT_EQ_INT(200, ev_scope_lookup(mid,    "x")->value.body.as_int);
    ASSERT_EQ_INT(100, ev_scope_lookup(global, "x")->value.body.as_int);

    /* confidence shadows too — the inner binding is less trusted and
       that must not silently inherit the outer certainty */
    ASSERT_EQ_INT(120,       ev_scope_lookup(inner,  "x")->confidence);
    ASSERT_EQ_INT(200,       ev_scope_lookup(mid,    "x")->confidence);
    ASSERT_EQ_INT(E_CERTAIN, ev_scope_lookup(global, "x")->confidence);

    /* shadowing does not MUTATE the outer binding */
    ASSERT_EQ_INT(100, ev_scope_get(global, "x")->value.body.as_int);
    ASSERT_EQ_INT(200, ev_scope_get(mid,    "x")->value.body.as_int);

    /* removing the inner shadow reveals the next one up, unchanged —
       shadowing hides, it does not overwrite */
    ASSERT_EQ_INT(1, ev_scope_delete(inner, "x"));
    ASSERT_NULL(ev_scope_get(inner, "x"));
    ASSERT_EQ_INT(200, ev_scope_lookup(inner, "x")->value.body.as_int);

    /* remove the middle one too and the global surfaces */
    ASSERT_EQ_INT(1, ev_scope_delete(mid, "x"));
    ASSERT_EQ_INT(100, ev_scope_lookup(inner, "x")->value.body.as_int);
    ASSERT_EQ_INT(E_CERTAIN, ev_scope_lookup(inner, "x")->confidence);

    /* deleting something absent reports it rather than pretending */
    ASSERT_EQ_INT(0, ev_scope_delete(inner, "never_bound"));

    ev_scope_free(inner); ev_scope_free(mid); ev_scope_free(global);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_scope_shadow_types, "ks", "ks_scoping") {
    /* A shadow may change the TYPE, not just the value. Nothing about
       the outer binding constrains the inner one. */
    EvArena *a = ev_arena_new("stypes");
    EvScope *g = ev_scope_new(a, NULL, "g");
    EvScope *c = ev_scope_new(a, g, "c");

    ev_scope_set_var(g, "v", ev_int(42),          E_CERTAIN, E_LANG_EVER);
    ev_scope_set_var(c, "v", ev_text("shadowed"), E_CERTAIN, E_LANG_EVER);

    ASSERT_EQ_INT(EV_INT,  ev_scope_lookup(g, "v")->value.tag);
    ASSERT_EQ_INT(EV_TEXT, ev_scope_lookup(c, "v")->value.tag);
    ASSERT_EQ_STR("shadowed", ev_scope_lookup(c, "v")->value.text);
    ASSERT_EQ_INT(42, ev_scope_lookup(g, "v")->value.body.as_int);

    /* shadow with z: the inner name is explicitly unknown while the
       outer remains perfectly well known */
    EvScope *c2 = ev_scope_new(a, g, "c2");
    ev_scope_set_var(c2, "v", ev_void(), 0, E_LANG_EVER);
    ASSERT_EQ_INT(EV_VOID, ev_scope_lookup(c2, "v")->value.tag);
    ASSERT_EQ_INT(0,       ev_scope_lookup(c2, "v")->confidence);
    ASSERT_EQ_INT(42,      ev_scope_lookup(g,  "v")->value.body.as_int);

    ev_scope_free(c2); ev_scope_free(c); ev_scope_free(g);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_scope_capacity, "ks", "ks_scoping") {
    /* Shadowing must survive a rehash. The map grows at 75% load, and
       a resize that lost tombstones would resurrect deleted names. */
    EvArena *a = ev_arena_new("cap");
    EvScope *g = ev_scope_new(a, NULL, "g");
    EvScope *c = ev_scope_new(a, g, "c");

    char key[32];
    for (int i = 0; i < 100; i++) {
        snprintf(key, sizeof key, "k%d", i);
        ev_scope_set_var(g, key, ev_int(i), E_CERTAIN, E_LANG_EVER);
    }
    /* shadow every tenth one in the child */
    for (int i = 0; i < 100; i += 10) {
        snprintf(key, sizeof key, "k%d", i);
        ev_scope_set_var(c, key, ev_int(i * 1000), E_CERTAIN, E_LANG_EVER);
    }
    ASSERT_EQ_INT(100, g->used);
    ASSERT_EQ_INT(10,  c->used);
    ASSERT(g->cap > 64);          /* it grew */

    /* every lookup resolves to the right level after the rehash */
    for (int i = 0; i < 100; i++) {
        snprintf(key, sizeof key, "k%d", i);
        int64_t want = (i % 10 == 0) ? (int64_t)i * 1000 : (int64_t)i;
        ASSERT_EQ_INT(want, ev_scope_lookup(c, key)->value.body.as_int);
        ASSERT_EQ_INT(i,    ev_scope_get(g, key)->value.body.as_int);
    }

    /* delete a shadow after the rehash and the parent still surfaces */
    ASSERT_EQ_INT(1, ev_scope_delete(c, "k50"));
    ASSERT_EQ_INT(50, ev_scope_lookup(c, "k50")->value.body.as_int);

    /* a tombstoned slot must not be reported as present */
    ASSERT_NULL(ev_scope_get(c, "k50"));

    /* reusing a tombstoned key works */
    ev_scope_set_var(c, "k50", ev_int(-1), E_CERTAIN, E_LANG_EVER);
    ASSERT_EQ_INT(-1, ev_scope_lookup(c, "k50")->value.body.as_int);
    ASSERT_EQ_INT(50, ev_scope_get(g, "k50")->value.body.as_int);

    ev_scope_free(c); ev_scope_free(g);
    ev_arena_free(a);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 9 — ARGUMENT PASSING: by value vs by reference
 *
 * This distinction is REAL in Ever, not academic, and it is decided
 * by where a value lives:
 *
 *   INT, REAL, BOOL, TEXT, VOID  live INLINE in the 208-byte EValue.
 *                                Copying the struct copies the data.
 *                                → BY VALUE.
 *
 *   BLOB, LIST, RECORD           live in the pool; the EValue holds
 *                                only body.pool_ref, an index.
 *                                Copying the struct copies the index.
 *                                → BY REFERENCE.
 *
 * Anyone writing Ever needs to know which side of that line a value
 * sits on, so the line gets tested from both directions.
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_pass_by_value_scalars, "ks", "ks_passing") {
    /* Scalars are copied. Mutating a copy cannot reach the original. */
    EValue a = ev_int(10);
    EValue b = a;                       /* struct assignment */
    b.body.as_int = 99;
    ASSERT_EQ_INT(10, a.body.as_int);   /* untouched */
    ASSERT_EQ_INT(99, b.body.as_int);

    EValue r1 = ev_real(1.5);
    EValue r2 = r1;
    r2.body.as_real = 9.5;
    ASSERT_EQ_REAL(1.5, r1.body.as_real, 1e-12);
    ASSERT_EQ_REAL(9.5, r2.body.as_real, 1e-12);

    /* TEXT is inline too, so it is by value despite being variable
       length — this is the surprising one and the reason for the
       191-byte cap */
    EValue t1 = ev_text("original");
    EValue t2 = t1;
    strcpy(t2.text, "changed");
    ASSERT_EQ_STR("original", t1.text);
    ASSERT_EQ_STR("changed",  t2.text);

    EValue bo1 = ev_bool(1);
    EValue bo2 = bo1;
    bo2.body.as_bool = 0;
    ASSERT_EQ_INT(1, bo1.body.as_bool);
    ASSERT_EQ_INT(0, bo2.body.as_bool);
}

EV_SUITE_TAGGED(ks_pass_by_reference_composites, "ks", "ks_passing") {
    ev_pool pool; ev_pool_init(&pool);

    /* Composites carry a pool_ref, so two EValues copied from each
       other name the SAME backing store. */
    EValue l1 = ev_list_new(&pool);
    ev_list_push(&l1, ev_int(1), &pool);

    EValue l2 = l1;                          /* struct copy */
    ASSERT_EQ_INT(l1.body.pool_ref, l2.body.pool_ref);   /* same handle */

    ev_list_push(&l2, ev_int(2), &pool);     /* mutate through the copy */

    /* the change is visible through BOTH names — by reference */
    ASSERT_EQ_INT(2, ev_list_len(&l1, &pool));
    ASSERT_EQ_INT(2, ev_list_len(&l2, &pool));
    ASSERT_EQ_INT(2, ev_list_get(&l1, 1, &pool).body.as_int);

    /* records behave the same way */
    EValue r1 = ev_record_new(&pool);
    ev_record_set(&r1, "k", ev_int(1), E_CERTAIN, &pool);
    EValue r2 = r1;
    ev_record_set(&r2, "k", ev_int(2), E_CERTAIN, &pool);
    ASSERT_EQ_INT(r1.body.pool_ref, r2.body.pool_ref);
    ASSERT_EQ_INT(2, ev_record_get(&r1, "k", &pool).body.as_int);

    /* two SEPARATELY constructed composites do not alias */
    EValue i1 = ev_list_new(&pool);
    EValue i2 = ev_list_new(&pool);
    ASSERT(i1.body.pool_ref != i2.body.pool_ref);
    ev_list_push(&i1, ev_int(7), &pool);
    ASSERT_EQ_INT(1, ev_list_len(&i1, &pool));
    ASSERT_EQ_INT(0, ev_list_len(&i2, &pool));   /* independent */

    /* Bulk teardown: one call releases every composite this suite
       minted, including the nested ones it never held a ref to. */
    ev_pool_clear(&pool);
}

EV_SUITE_TAGGED(ks_pass_function_arguments, "ks", "ks_passing") {
    /* Function arguments are evaluated in the caller and arrive as
       EValue copies, so a callee rebinding its parameter cannot reach
       back into the caller's binding. The frame fix is what makes
       this true across a recursive call as well as a flat one. */
    EvArena *a = ev_arena_new("args");
    const char *pn[] = { "n" };

    /* def double(n) = n + n */
    EvNode *body = ev_node_binop(a, EV_NODE_ADD,
                     ev_node_var(a,"n",1), ev_node_var(a,"n",1), 1);
    EvNode *def  = ev_node_def(a, "double", pn, 1, body, 1);
    EvModule *m = ev_lower_module("args", def, a);
    ev_optimise(m->funcs[0]);
    EvInterp *ip = ev_interp_new(m);

    /* the same EValue passed repeatedly is unchanged by the callee */
    EValue arg = ev_int(21);
    EValue r1 = ev_interp_call(ip, "double", &arg, 1);
    ASSERT_EQ_INT(42, r1.body.as_int);
    ASSERT_EQ_INT(21, arg.body.as_int);       /* caller's copy intact */

    EValue r2 = ev_interp_call(ip, "double", &arg, 1);
    ASSERT_EQ_INT(42, r2.body.as_int);        /* repeatable */
    ASSERT_EQ_INT(21, arg.body.as_int);

    ev_interp_free(ip); ev_module_free(m);

    /* Multi-parameter: arguments bind positionally and do not swap */
    EvArena *b = ev_arena_new("two");
    const char *pn2[] = { "a", "b" };
    EvNode *sub = ev_node_binop(b, EV_NODE_SUB,
                    ev_node_var(b,"a",1), ev_node_var(b,"b",1), 1);
    EvNode *d2  = ev_node_def(b, "diff", pn2, 2, sub, 1);
    EvModule *m2 = ev_lower_module("two", d2, b);
    ev_optimise(m2->funcs[0]);
    EvInterp *ip2 = ev_interp_new(m2);

    EValue args2[2]; args2[0] = ev_int(50); args2[1] = ev_int(8);
    EValue rd = ev_interp_call(ip2, "diff", args2, 2);
    ASSERT_EQ_INT(42, rd.body.as_int);        /* 50-8, not 8-50 */

    /* reversed inputs give the negated result, proving order matters
       and is respected */
    EValue args3[2]; args3[0] = ev_int(8); args3[1] = ev_int(50);
    EValue rd2 = ev_interp_call(ip2, "diff", args3, 2);
    ASSERT_EQ_INT(-42, rd2.body.as_int);
    ev_interp_free(ip2); ev_module_free(m2);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(a);
    ev_arena_free(b);
}

EV_SUITE_TAGGED(ks_pass_cross_arena, "ks", "ks_passing") {
    /* Ownership rule 3: a value crossing an arena boundary is COPIED,
       never aliased. Freeing the source must not disturb the copy. */
    EvArena *src = ev_arena_new("src");
    EvArena *dst = ev_arena_new("dst");

    EvNode *tree = ev_node_binop(src, EV_NODE_ADD,
                     ev_node_int(src, 6, 1),
                     ev_node_int(src, 36, 1), 1);
    uint8_t buf[512];
    int32_t len = ev_ir_serialise(tree, buf, sizeof buf);
    ASSERT(len > 0);

    int32_t consumed = 0;
    EvNode *copy = ev_ir_deserialise(buf, len, &consumed, dst);
    ASSERT_NOT_NULL(copy);
    ASSERT_EQ_INT(len, consumed);
    ASSERT(copy->arena == dst);              /* lives in dst */
    ASSERT(copy != tree);                    /* not the same object */

    ev_arena_free(src);                      /* source is gone */

    /* the copy is still whole and still evaluates */
    ASSERT_EQ_INT(EV_NODE_ADD, copy->kind);
    ASSERT_EQ_INT(6,  copy->children[0]->lit.as_int);
    ASSERT_EQ_INT(36, copy->children[1]->lit.as_int);

    EvModule *m = ev_lower_module("copy", copy, dst);
    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    ASSERT_EQ_INT(42, ev_interp_run(ip).body.as_int);
    ev_interp_free(ip); ev_module_free(m);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(dst);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 10 — IR and FORMS: every kind, both directions
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_forms_every_kind, "ks", "ks_forms") {
    EvArena *a = ev_arena_new("everyform");
    char err[256];

    /* One well-formed instance of all eleven structural shapes. If a
       twelfth is ever added this suite is where it must appear. */
    EvForm *forms[EV_FORM_KIND_COUNT];
    forms[EV_FORM_ATOM]        = ev_form_int(a, 42, 1);
    forms[EV_FORM_REFERENCE]   = ev_form_ref(a, "n", 1);
    forms[EV_FORM_APPLICATION] = ev_form_apply2(a, EV_ROLE_ADD,
                                    ev_form_int(a,1,1), ev_form_int(a,2,1), 1);
    {
        EvForm *arms[2] = { ev_form_int(a,1,1), ev_form_int(a,0,1) };
        forms[EV_FORM_BRANCH]  = ev_form_branch(a, EV_ROLE_IF,
                                    ev_form_bool(a,1,1), arms, 2, 1);
    }
    {
        EvForm *items[2] = { ev_form_int(a,1,1), ev_form_int(a,2,1) };
        forms[EV_FORM_SEQUENCE] = ev_form_sequence(a, EV_ROLE_BLOCK,
                                     items, 2, 1);
    }
    forms[EV_FORM_BINDING]     = ev_form_binding(a, EV_ROLE_BIND_LET,
                                    "x", ev_form_int(a,1,1), 1);
    {
        const char *ps[] = { "n" };
        forms[EV_FORM_ABSTRACTION] = ev_form_abstraction(a, EV_ROLE_FN_DEF,
                                        "f", ps, 1, ev_form_ref(a,"n",1), 1);
    }
    {
        EvForm *items[2] = { ev_form_int(a,1,1), ev_form_int(a,2,1) };
        forms[EV_FORM_AGGREGATE] = ev_form_aggregate(a, EV_ROLE_AGG_LIST,
                                      items, NULL, 2, 1);
    }
    forms[EV_FORM_ACCESS]      = ev_form_access(a, EV_ROLE_ACC_INDEX,
                                    ev_form_ref(a,"xs",1),
                                    ev_form_int(a,0,1), 1);
    forms[EV_FORM_ANNOTATION]  = ev_form_annotate(a, EV_ROLE_ANN_ANCHOR,
                                    "measure", ev_form_ref(a,"n",1), 1);
    forms[EV_FORM_DEFECT]      = ev_form_defect(a, EV_ROLE_DEF_PARSE,
                                    "unexpected token", 1);

    for (int k = 0; k < EV_FORM_KIND_COUNT; k++) {
        ASSERT_NOT_NULL(forms[k]);
        ASSERT_EQ_INT(k, forms[k]->form);
        ASSERT_EQ_INT(1, ev_form_validate(forms[k], err, sizeof err));
        /* every form's role belongs to that form */
        ASSERT_EQ_INT(forms[k]->form, ev_role_form(forms[k]->role));
        /* every form measures without walking off the end */
        ev_form_measure(forms[k]);
        ASSERT(forms[k]->size  >= 1);
        ASSERT(forms[k]->depth >= 1);
    }
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_ir_every_node_kind, "ks", "ks_forms") {
    /* Every legacy EvNode kind normalises into a form, and the whole
       mapping is total: nothing falls through to DEFECT by accident. */
    EvArena *a = ev_arena_new("everynode");

    EvNode *nodes[] = {
        ev_node_new(a, EV_NODE_VOID, 1),
        ev_node_bool(a, 1, 1),
        ev_node_int(a, 42, 1),
        ev_node_real(a, 3.14, 1),
        ev_node_text(a, "t", 1),
        ev_node_var(a, "v", 1),
        ev_node_new(a, EV_NODE_Z, 1),
        ev_node_binop(a, EV_NODE_ADD, ev_node_int(a,1,1), ev_node_int(a,2,1), 1),
        ev_node_if(a, ev_node_bool(a,1,1),
                      ev_node_int(a,1,1), ev_node_int(a,0,1), 1),
        ev_node_error(a, "bad", 1),
    };
    EvFormKind want[] = {
        EV_FORM_ATOM, EV_FORM_ATOM, EV_FORM_ATOM, EV_FORM_ATOM,
        EV_FORM_ATOM, EV_FORM_REFERENCE, EV_FORM_ATOM,
        EV_FORM_APPLICATION, EV_FORM_BRANCH, EV_FORM_DEFECT
    };
    for (int i = 0; i < 10; i++) {
        EvForm *f = ev_form_from_node(nodes[i], a);
        ASSERT_NOT_NULL(f);
        ASSERT_EQ_INT(want[i], f->form);
    }

    /* CALL and DEF need their own construction */
    EvNode *cargs[1] = { ev_node_int(a,3,1) };
    EvForm *cf = ev_form_from_node(ev_node_call(a,"sq",cargs,1,1), a);
    ASSERT_EQ_INT(EV_FORM_APPLICATION, cf->form);
    ASSERT_EQ_INT(EV_ROLE_CALL,        cf->role);

    const char *ps[] = { "n" };
    EvForm *df = ev_form_from_node(
        ev_node_def(a,"sq",ps,1,ev_node_var(a,"n",1),1), a);
    ASSERT_EQ_INT(EV_FORM_ABSTRACTION, df->form);
    ev_arena_free(a);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 11 — WIRE: every value crosses the boundary intact
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_wire_all_values, "ks", "ks_wire") {
    ev_pool pool; ev_pool_init(&pool);
    uint8_t buf[8192];

    /* Every scalar tag, including the awkward ones */
    char maxstr[192];
    memset(maxstr, 'z', 191); maxstr[191] = '\0';

    EValue vals[] = {
        ev_void(), ev_bool(0), ev_bool(1),
        ev_int(0), ev_int(-1), ev_int(INT64_MAX), ev_int(INT64_MIN),
        ev_real(0.0), ev_real(-0.5), ev_real(3.14159265358979),
        ev_text(""), ev_text("x"), ev_text(maxstr),
    };
    for (int i = 0; i < 13; i++) {
        int32_t n = ev_serialise(&vals[i], buf, sizeof buf, &pool);
        ASSERT(n > 0);
        int32_t consumed = 0;
        EValue back = ev_deserialise(buf, n, &consumed, &pool);
        ASSERT_EQ_INT(n, consumed);
        ASSERT_EQ_INT(vals[i].tag, back.tag);
        ASSERT_EQ_INT(1, ev_equal(&vals[i], &back, &pool));
    }
    ev_pool_clear(&pool);
}

EV_SUITE_TAGGED(ks_wire_forms_deep, "ks", "ks_wire") {
    /* A deep nested tree survives the round trip whole */
    EvArena *a = ev_arena_new("deepwire");
    EvForm *f = ev_form_int(a, 1, 1);
    for (int i = 0; i < 12; i++)
        f = ev_form_apply2(a, EV_ROLE_ADD, f, ev_form_int(a, i, 1), 1);
    ev_form_measure(f);
    int32_t orig_size = f->size, orig_depth = f->depth;
    ASSERT_EQ_INT(13, orig_depth);

    uint8_t buf[16384];
    int32_t n = ev_form_serialise(f, buf, sizeof buf);
    ASSERT(n > 0);

    EvArena *b = ev_arena_new("recv");
    int32_t consumed = 0;
    EvForm *back = ev_form_deserialise(buf, n, &consumed, b);
    ASSERT_NOT_NULL(back);
    ASSERT_EQ_INT(n, consumed);
    ev_form_measure(back);
    ASSERT_EQ_INT(orig_size,  back->size);
    ASSERT_EQ_INT(orig_depth, back->depth);

    /* and it still computes the same answer after the crossing */
    EvModule *m1 = ev_lower_form_module("a", f,    a);
    EvModule *m2 = ev_lower_form_module("b", back, b);
    ev_optimise(m1->global_body); ev_optimise(m2->global_body);
    EvInterp *i1 = ev_interp_new(m1), *i2 = ev_interp_new(m2);
    EValue r1 = ev_interp_run(i1), r2 = ev_interp_run(i2);
    ASSERT_EQ_INT(r1.tag,         r2.tag);
    ASSERT_EQ_INT(r1.body.as_int, r2.body.as_int);
    ev_interp_free(i1); ev_interp_free(i2);
    ev_module_free(m1); ev_module_free(m2);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(a);
    ev_arena_free(b);
}

/* ═══════════════════════════════════════════════════════════════
 * SECTION 12 — FULL PIPELINE, both lowering paths agreeing
 * ═══════════════════════════════════════════════════════════════ */

EV_SUITE_TAGGED(ks_pipeline_both_paths, "ks", "ks_pipeline") {
    /* Programs of increasing complexity, each run through the legacy
       node path AND the generic form path. Divergence between them is
       a defect regardless of which one is right. */
    EvArena *a = ev_arena_new("pipe");

    struct { const char *label; EvNode *prog; int64_t want; } cases[] = {
        { "const",  ev_node_int(a,42,1), 42 },
        { "add",    ev_node_binop(a,EV_NODE_ADD,
                      ev_node_int(a,6,1), ev_node_int(a,36,1),1), 42 },
        { "chain",  ev_node_binop(a,EV_NODE_SUB,
                      ev_node_binop(a,EV_NODE_MUL,
                        ev_node_int(a,7,1), ev_node_int(a,7,1),1),
                      ev_node_int(a,7,1),1), 42 },
        { "branch", ev_node_if(a,
                      ev_node_binop(a,EV_NODE_GTE,
                        ev_node_int(a,5,1), ev_node_int(a,5,1),1),
                      ev_node_int(a,42,1), ev_node_int(a,-1,1),1), 42 },
        { "nested", ev_node_if(a, ev_node_bool(a,0,1),
                      ev_node_int(a,-1,1),
                      ev_node_if(a, ev_node_bool(a,1,1),
                        ev_node_binop(a,EV_NODE_ADD,
                          ev_node_int(a,40,1), ev_node_int(a,2,1),1),
                        ev_node_int(a,-2,1),1),1), 42 },
    };

    EV_PARAMS(cases, tc) {
        /* node path */
        EvArena *na = ev_arena_new("n");
        EvModule *mn = ev_lower_module("N", tc.prog, na);
        ev_optimise(mn->global_body);
        EvInterp *in = ev_interp_new(mn);
        EValue rn = ev_interp_run(in);

        /* form path */
        EvArena *fa = ev_arena_new("f");
        EvForm *ff = ev_form_from_node(tc.prog, fa);
        char err[256];
        ASSERT_EQ_INT(1, ev_form_validate(ff, err, sizeof err));
        EvModule *mf = ev_lower_form_module("F", ff, fa);
        ev_optimise(mf->global_body);
        EvInterp *ifp = ev_interp_new(mf);
        EValue rf = ev_interp_run(ifp);

        ASSERT_EQ_INT(tc.want, rn.body.as_int);
        ASSERT_EQ_INT(tc.want, rf.body.as_int);
        ASSERT_EQ_INT(rn.tag,  rf.tag);        /* paths agree */

        ev_interp_free(in);  ev_module_free(mn);
        ev_interp_free(ifp); ev_module_free(mf);
        /* ev_module_free releases the arena ev_lower_module minted for
           itself. na/fa are the CALLER's arenas holding the EvNode and
           EvForm trees, and stay ours to free. */
        ev_arena_free(na); ev_arena_free(fa);
    }
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_pipeline_optimiser_safety, "ks", "ks_pipeline") {
    /* Optimisation must not change an answer. Each program is run
       with and without the passes and the results compared. */
    EvArena *a = ev_arena_new("opt");

    struct { const char *label; EvNode *prog; } cases[] = {
        { "fold",   ev_node_binop(a,EV_NODE_ADD,
                      ev_node_int(a,6,1), ev_node_int(a,36,1),1) },
        { "branch", ev_node_if(a,
                      ev_node_binop(a,EV_NODE_LT,
                        ev_node_int(a,1,1), ev_node_int(a,2,1),1),
                      ev_node_int(a,42,1), ev_node_int(a,0,1),1) },
        { "deep",   ev_node_binop(a,EV_NODE_MUL,
                      ev_node_binop(a,EV_NODE_ADD,
                        ev_node_int(a,3,1), ev_node_int(a,4,1),1),
                      ev_node_int(a,6,1),1) },
    };

    EV_PARAMS(cases, tc) {
        EvArena *u = ev_arena_new("u");
        EvModule *mu = ev_lower_module("U", tc.prog, u);
        EvInterp *iu = ev_interp_new(mu);
        EValue ru = ev_interp_run(iu);          /* unoptimised */

        EvArena *o = ev_arena_new("o");
        EvModule *mo = ev_lower_module("O", tc.prog, o);
        ev_optimise(mo->global_body);
        EvInterp *io = ev_interp_new(mo);
        EValue ro = ev_interp_run(io);          /* optimised */

        ASSERT_EQ_INT(ru.tag,         ro.tag);
        ASSERT_EQ_INT(ru.body.as_int, ro.body.as_int);

        ev_interp_free(iu); ev_module_free(mu);
        ev_interp_free(io); ev_module_free(mo);
        ev_arena_free(u); ev_arena_free(o);
    }
    ev_arena_free(a);
}

EV_SUITE_TAGGED(ks_pipeline_end_to_end, "ks", "ks_pipeline") {
    /* The whole stack in one path: C atom → ABI bytes → IR tree →
       wire → other arena → forms → TAC → optimiser → interpreter. */

    /* stage 0: the atom layer holds the operands */
    e_particle p6  = e_int("six",       6, E_CERTAIN, E_LANG_C);
    e_particle p36 = e_int("thirtysix",36, E_CERTAIN, E_LANG_C);
    ASSERT_EQ_INT(6,  p6.value.as_int);
    ASSERT_EQ_INT(36, p36.value.as_int);

    /* stage 1: across the ABI as raw bytes */
    uint8_t abi[sizeof(e_particle)];
    memcpy(abi, &p6, sizeof p6);
    e_particle back6;
    memcpy(&back6, abi, sizeof back6);
    ASSERT_EQ_INT(6, back6.value.as_int);
    ASSERT_EQ_STR("six", back6.ident);
    ASSERT_EQ_INT(E_CERTAIN, back6.confidence);

    /* stage 2: as an IR tree */
    EvArena *a = ev_arena_new("e2e");
    EvNode *tree = ev_node_binop(a, EV_NODE_ADD,
                     ev_node_int(a, back6.value.as_int, 1),
                     ev_node_int(a, p36.value.as_int,  1), 1);
    ev_node_measure(tree);
    ASSERT_EQ_INT(3, tree->size);
    /* DEPTH CONVENTION, pinned here because it differs by layer and
       silently produces off-by-one bugs at the seam:
         EvNode  (ir.c)     0-based — a bare literal has depth 0
         EvForm  (form.c)   1-based — a bare literal has depth 1
         Semantic(syntax.py)1-based — matches EvForm
       Both are correct for their layer. `6 + 36` is therefore depth 1
       as a node and depth 2 as a form, and the next two assertions
       hold that difference still. */
    ASSERT_EQ_INT(1, tree->depth);

    /* stage 3: over the wire into a different arena */
    uint8_t wire[512];
    int32_t n = ev_ir_serialise(tree, wire, sizeof wire);
    ASSERT(n > 0);
    EvArena *b = ev_arena_new("recv");
    int32_t consumed = 0;
    EvNode *recv = ev_ir_deserialise(wire, n, &consumed, b);
    ASSERT_EQ_INT(n, consumed);

    /* stage 4: normalise to the generic IR and validate the shape */
    EvForm *form = ev_form_from_node(recv, b);
    char err[256];
    ASSERT_EQ_INT(1, ev_form_validate(form, err, sizeof err));
    ASSERT_EQ_INT(EV_FORM_APPLICATION, form->form);
    ASSERT_EQ_INT(EV_ROLE_ADD,         form->role);
    ev_form_measure(form);
    ASSERT_EQ_INT(3, form->size);      /* same node count as the tree */
    ASSERT_EQ_INT(2, form->depth);     /* 1-based: node depth 1 + 1   */

    /* stage 5: lower, optimise, execute */
    EvModule *m = ev_lower_form_module("e2e", form, b);
    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue result = ev_interp_run(ip);

    ASSERT_EQ_INT(EV_INT, result.tag);
    ASSERT_EQ_INT(42,     result.body.as_int);

    ev_interp_free(ip); ev_module_free(m);
    ev_arena_free(a);


    /* Arena teardown. ev_module_free owns only the arena the
       lowerer minted for itself; these hold our trees. */
    ev_arena_free(b);
}

EV_MAIN
