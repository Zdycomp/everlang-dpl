/*
 * native_test.c — Ever / Tapestry, native C test suite (ev_test.h)
 *
 * This file demonstrates the native harness pattern.
 * Every test uses ASSERT_EQ_INT / ASSERT_EQ_REAL / ASSERT_EQ_STR
 * so failures print EXPECTED vs GOT, not just a name and a bool.
 *
 * Suites are tagged so the harness can filter:
 *   ./native_test --tag atom
 *   ./native_test --tag tac
 *   ./native_test -v          (verbose: print passing assertions too)
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "ev_test.h"
#include "tapestry.h"
#include "evalue.h"
#include "ir.h"
#include "scope.h"
#include "tac.h"
#include <math.h>

/* ─────────────────────────────────────────────
 * TAG: atom — e_particle, confidence arithmetic, state machine
 * ───────────────────────────────────────────── */

EV_SUITE_TAGGED(atom_layout, "atom", "layout") {
    /* ABI contract: sizes and offsets must match tapestry.h assertions */
    ASSERT_EQ_INT(440, sizeof(e_particle));
    ASSERT_EQ_INT(0,   offsetof(e_particle, type));
    ASSERT_EQ_INT(8,   offsetof(e_particle, value));
    ASSERT_EQ_INT(16,  offsetof(e_particle, text));
    ASSERT_EQ_INT(208, offsetof(e_particle, state));
    ASSERT_EQ_INT(216, offsetof(e_particle, confidence));
    ASSERT_EQ_INT(224, offsetof(e_particle, lang));
    ASSERT_EQ_INT(232, offsetof(e_particle, anchor_id));
    ASSERT_EQ_INT(240, offsetof(e_particle, born_ms));
    ASSERT_EQ_INT(248, offsetof(e_particle, ident));
    ASSERT_EQ_INT(312, offsetof(e_particle, reason));
}

EV_SUITE_TAGGED(atom_constructors, "atom") {
    e_particle pi = e_int("x", 42, E_CERTAIN, E_LANG_EVER);
    ASSERT_EQ_INT(42,       pi.value.as_int);
    ASSERT_EQ_INT(E_CERTAIN,pi.confidence);
    ASSERT_EQ_INT(E_LANG_EVER, pi.lang);
    ASSERT_EQ_STR("x",      pi.ident);

    e_particle pr = e_real("pi", 3.14159, E_CERTAIN, E_LANG_EVER);
    ASSERT_EQ_REAL(3.14159, pr.value.as_real, 1e-5);

    e_particle pt = e_text("s", "hello", E_CERTAIN, E_LANG_EVER);
    ASSERT_EQ_STR("hello", pt.text);

    e_particle pb = e_bool("flag", 1, E_CERTAIN, E_LANG_EVER);
    ASSERT_EQ_INT(1, pb.value.as_bool);

    e_particle pz = e_z("unknown", "not measured");
    ASSERT_EQ_INT(0, pz.confidence);
    ASSERT_EQ_INT(1, e_is_z(&pz));
    ASSERT_EQ_INT(0, e_is_z(&pi));
}

EV_SUITE_TAGGED(atom_excel, "atom", "confidence") {
    /* Excel (corroboration) formula: u_result = u_a * u_b */
    /* Certain + Certain = Certain */
    ASSERT_EQ_INT(E_CERTAIN, e_excel_formula(E_CERTAIN, E_CERTAIN));
    /* Zero is contagious through state, not formula */
    e_particle z = e_z("z", "");
    ASSERT_EQ_INT(1, e_is_z(&z));
    ASSERT_EQ_INT(0, z.confidence);
    /* Certain + anything < Certain → still < Certain */
    int16_t mid = e_excel_formula(200, 200);
    ASSERT(mid < E_CERTAIN);
    ASSERT(mid > 0);
}

EV_SUITE_TAGGED(atom_params, "atom") {
    /* Parameterised: integer construction round-trips */
    struct { int64_t v; int16_t c; } cases[] = {
        {0,      E_CERTAIN},
        {42,     E_CERTAIN},
        {-99,    200},
        {999999, E_CERTAIN},
    };
    EV_PARAMS(cases, tc) {
        e_particle p = e_int("t", tc.v, tc.c, E_LANG_EVER);
        ASSERT_EQ_INT(tc.v, p.value.as_int);
        ASSERT_EQ_INT(tc.c, p.confidence);
    }
}

/* ─────────────────────────────────────────────
 * TAG: evalue — unified variant type
 * ───────────────────────────────────────────── */

EV_SUITE_TAGGED(evalue_layout, "evalue", "layout") {
    ASSERT_EQ_INT(208, sizeof(EValue));
    ASSERT_EQ_INT(0,   offsetof(EValue, tag));
    ASSERT_EQ_INT(8,   offsetof(EValue, body));
    ASSERT_EQ_INT(16,  offsetof(EValue, text));
}

EV_SUITE_TAGGED(evalue_scalars, "evalue") {
    ev_pool pool; ev_pool_init(&pool);

    EValue vi = ev_int(42);
    ASSERT_EQ_INT(EV_INT, vi.tag);
    ASSERT_EQ_INT(42,     vi.body.as_int);

    EValue vr = ev_real(3.14);
    ASSERT_EQ_INT(EV_REAL, vr.tag);
    ASSERT_EQ_REAL(3.14, vr.body.as_real, 1e-9);

    EValue vb = ev_bool(1);
    ASSERT_EQ_INT(EV_BOOL, vb.tag);
    ASSERT_EQ_INT(1,       vb.body.as_bool);

    EValue vt = ev_text("Codric");
    ASSERT_EQ_INT(EV_TEXT, vt.tag);
    ASSERT_EQ_STR("Codric", vt.text);

    EValue vv = ev_void();
    ASSERT_EQ_INT(EV_VOID, vv.tag);

    /* INT/REAL interoperability */
    { EValue _i3=ev_int(3),_r30=ev_real(3.0),_r31=ev_real(3.1);
    ASSERT_EQ_INT(1, ev_equal(&_i3,&_r30,&pool));
    ASSERT_EQ_INT(0, ev_equal(&_i3,&_r31,&pool)); }
}

EV_SUITE_TAGGED(evalue_composites, "evalue") {
    ev_pool pool; ev_pool_init(&pool);

    /* LIST */
    EValue lst = ev_list_new(&pool);
    ASSERT_EQ_INT(EV_LIST, lst.tag);
    ASSERT_EQ_INT(0, ev_list_len(&lst, &pool));

    ev_list_push(&lst, ev_int(10), &pool);
    ev_list_push(&lst, ev_int(20), &pool);
    ev_list_push(&lst, ev_text("hi"), &pool);
    ASSERT_EQ_INT(3, ev_list_len(&lst, &pool));
    ASSERT_EQ_INT(10, ev_list_get(&lst, 0, &pool).body.as_int);
    ASSERT_EQ_INT(20, ev_list_get(&lst, 1, &pool).body.as_int);
    ASSERT_EQ_STR("hi", ev_list_get(&lst, 2, &pool).text);

    /* RECORD */
    EValue rec = ev_record_new(&pool);
    ev_record_set(&rec, "id",   ev_int(7),       E_CERTAIN, &pool);
    ev_record_set(&rec, "name", ev_text("Alice"), E_CERTAIN, &pool);
    ASSERT_EQ_INT(7,       ev_record_get(&rec, "id",   &pool).body.as_int);
    ASSERT_EQ_STR("Alice", ev_record_get(&rec, "name", &pool).text);
    ASSERT_EQ_INT(EV_VOID, ev_record_get(&rec, "zzz",  &pool).tag);
    ASSERT_EQ_INT(1, ev_record_has(&rec, "id",  &pool));
    ASSERT_EQ_INT(0, ev_record_has(&rec, "zzz", &pool));

    /* Bulk pool teardown — one call releases every composite minted
       here, including nested ones no local ref names. */
    ev_pool_clear(&pool);
}

EV_SUITE_TAGGED(evalue_wire, "evalue", "wire") {
    ev_pool pool; ev_pool_init(&pool);
    uint8_t buf[4096];

    /* Parameterised wire round-trips */
    EValue cases[] = {
        ev_void(),
        ev_bool(1), ev_bool(0),
        ev_int(42), ev_int(-1), ev_int(0),
        ev_real(3.14159),
        ev_text("Codric"),
    };
    const char *labels[] = {
        "void","bool:T","bool:F","int:42","int:-1","int:0","real","text"
    };
    for (int i = 0; i < 8; i++) {
        int32_t n = ev_serialise(&cases[i], buf, sizeof buf, &pool);
        ASSERT(n > 0);
        int32_t cons = 0;
        EValue back = ev_deserialise(buf, n, &cons, &pool);
        ASSERT_EQ_INT(n, cons);
        ASSERT_EQ_INT(1, ev_equal(&cases[i], &back, &pool));
        (void)labels[i];
    }
}

/* ─────────────────────────────────────────────
 * TAG: arena — EvArena allocator
 * ───────────────────────────────────────────── */

EV_SUITE_TAGGED(arena_basic, "arena") {
    EvArena *a = ev_arena_new("test");
    ASSERT_NOT_NULL(a);
    ASSERT_EQ_INT(1, a->slab_count);

    void *p1 = ev_arena_alloc(a, 16);
    void *p2 = ev_arena_alloc(a, 32);
    ASSERT_NOT_NULL(p1);
    ASSERT_NOT_NULL(p2);
    ASSERT(p1 != p2);

    char *s = ev_arena_strdup(a, "Ever");
    ASSERT_EQ_STR("Ever", s);

    ev_arena_free(a);
    ASSERT(1); /* no crash = pass */
}

EV_SUITE_TAGGED(arena_growth, "arena") {
    EvArena *a = ev_arena_new("growth");
    /* Force multiple slabs */
    for (int i = 0; i < 100; i++)
        ev_arena_alloc(a, 1024);
    ASSERT(a->slab_count > 1);
    ASSERT(a->total_allocated >= 100 * 1024);

    char stats[128];
    ev_arena_stats(a, stats, sizeof stats);
    ASSERT(strlen(stats) > 0);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(arena_ownership, "arena", "ownership") {
    /* Rule 3: cross-arena copy, never alias */
    EvArena *a = ev_arena_new("src");
    EvArena *b = ev_arena_new("dst");

    EvNode *n1 = ev_node_int(a, 77, 1);
    uint8_t buf[256];
    int32_t len = ev_ir_serialise(n1, buf, sizeof buf);
    ASSERT(len > 0);

    int32_t cons = 0;
    EvNode *n2 = ev_ir_deserialise(buf, len, &cons, b);
    ASSERT_NOT_NULL(n2);
    ASSERT_EQ_INT(77, n2->lit.as_int);
    ASSERT(n2->arena == b);   /* copy is in dst arena */

    ev_arena_free(a);         /* n1 freed */
    ASSERT_EQ_INT(77, n2->lit.as_int); /* n2 survives */
    ev_arena_free(b);
}

/* ─────────────────────────────────────────────
 * TAG: ir — EvNode tree, serialisation
 * ───────────────────────────────────────────── */

EV_SUITE_TAGGED(ir_constructors, "ir") {
    EvArena *a = ev_arena_new("ir");

    EvNode *ni = ev_node_int(a, 42, 3);
    ASSERT_EQ_INT(EV_NODE_INT, ni->kind);
    ASSERT_EQ_INT(42,          ni->lit.as_int);
    ASSERT_EQ_INT(3,           ni->line);

    EvNode *nr = ev_node_real(a, 3.14, 1);
    ASSERT_EQ_REAL(3.14, nr->lit.as_real, 1e-9);

    EvNode *nt = ev_node_text(a, "Ever", 1);
    ASSERT_EQ_STR("Ever", nt->str);

    EvNode *nv = ev_node_var(a, "n", 1);
    ASSERT_EQ_INT(EV_NODE_VAR, nv->kind);
    ASSERT_EQ_STR("n", nv->str);

    EvNode *left  = ev_node_int(a, 6,  1);
    EvNode *right = ev_node_int(a, 36, 1);
    EvNode *add   = ev_node_binop(a, EV_NODE_ADD, left, right, 1);
    ASSERT_EQ_INT(EV_NODE_ADD, add->kind);
    ASSERT_EQ_INT(2, add->child_count);
    ASSERT_EQ_INT(6,  add->children[0]->lit.as_int);
    ASSERT_EQ_INT(36, add->children[1]->lit.as_int);

    ev_arena_free(a);
}

EV_SUITE_TAGGED(ir_metrics, "ir") {
    EvArena *a = ev_arena_new("metrics");

    /* fact body: if n <= 1 then 1 else n * fact(n-1) */
    EvNode *vn   = ev_node_var(a,"n",1);
    EvNode *one  = ev_node_int(a,1,1);
    EvNode *cmp  = ev_node_binop(a,EV_NODE_LTE,vn,one,1);
    EvNode *base = ev_node_int(a,1,1);
    EvNode *vn2  = ev_node_var(a,"n",1);
    EvNode *vn3  = ev_node_var(a,"n",1);
    EvNode *sub  = ev_node_binop(a,EV_NODE_SUB,vn3,ev_node_int(a,1,1),1);
    EvNode *carg[]={sub};
    EvNode *rec  = ev_node_call(a,"fact",carg,1,1);
    EvNode *mul  = ev_node_binop(a,EV_NODE_MUL,vn2,rec,1);
    EvNode *iff  = ev_node_if(a,cmp,base,mul,1);

    ev_node_measure(iff);
    ASSERT_EQ_INT(11, iff->size);   /* 11 nodes in body */
    ASSERT_EQ_INT(4,  iff->depth);  /* max depth */

    const char *sk = ev_node_skeleton(iff, a);
    ASSERT_NOT_NULL(sk);
    ASSERT(strstr(sk, "CMP") != NULL);   /* comparisons erased to CMP */
    ASSERT(strstr(sk, "K")   != NULL);   /* constants erased to K     */
    ASSERT(strstr(sk, "V")   != NULL);   /* variables kept as V       */

    ev_arena_free(a);
}

EV_SUITE_TAGGED(ir_wire, "ir", "wire") {
    EvArena *a = ev_arena_new("wire");
    uint8_t buf[4096];

    /* Round-trip every node kind */
    EvNode *nodes[] = {
        ev_node_int(a, 42, 1),
        ev_node_real(a, 3.14, 1),
        ev_node_bool(a, 1, 1),
        ev_node_text(a, "Ever", 1),
        ev_node_var(a, "n", 1),
        ev_node_error(a, "oops", 1),
        ev_node_binop(a, EV_NODE_ADD,
                      ev_node_int(a,1,1), ev_node_int(a,2,1), 1),
    };
    const char *names[] = {
        "int","real","bool","text","var","err","binop"
    };
    for (int i = 0; i < 7; i++) {
        int32_t n = ev_ir_serialise(nodes[i], buf, sizeof buf);
        ASSERT(n > 0);
        int32_t cons = 0;
        EvArena *b = ev_arena_new("rt");
        EvNode *back = ev_ir_deserialise(buf, n, &cons, b);
        ASSERT_NOT_NULL(back);
        ASSERT_EQ_INT(n, cons);
        ASSERT_EQ_INT(nodes[i]->kind, back->kind);
        ev_arena_free(b);
        (void)names[i];
    }

    ev_arena_free(a);
}

/* ─────────────────────────────────────────────
 * TAG: scope — universal map
 * ───────────────────────────────────────────── */

EV_SUITE_TAGGED(scope_hash, "scope") {
    ASSERT(ev_fnv1a("x") != 0);
    ASSERT_EQ_INT(ev_fnv1a("hello"), ev_fnv1a("hello"));
    ASSERT(ev_fnv1a("abc") != ev_fnv1a("def"));
}

EV_SUITE_TAGGED(scope_basic, "scope") {
    EvArena *a = ev_arena_new("scope");
    EvScope *g = ev_scope_new(a, NULL, "global");
    ASSERT_NOT_NULL(g);
    ASSERT_EQ_INT(0, g->depth);
    ASSERT_EQ_INT(0, g->used);

    ev_scope_set_var(g, "x", ev_int(42), E_CERTAIN, E_LANG_EVER);
    ev_scope_set_var(g, "y", ev_real(3.14), E_CERTAIN, E_LANG_EVER);
    ASSERT_EQ_INT(2, g->used);

    EvScopeEntry *ex = ev_scope_get(g, "x");
    ASSERT_NOT_NULL(ex);
    ASSERT_EQ_INT(42, ex->value.body.as_int);
    ASSERT_EQ_INT(EV_SK_VAR, ex->kind);

    ASSERT_NULL(ev_scope_get(g, "zzz"));
    ev_scope_free(g);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(scope_chain, "scope") {
    EvArena *a = ev_arena_new("chain");
    EvScope *global = ev_scope_new(a, NULL, "global");
    ev_scope_set_var(global, "x", ev_int(99), E_CERTAIN, E_LANG_EVER);

    EvScope *local = ev_scope_new(a, global, "local");
    ASSERT_EQ_INT(1, local->depth);
    ev_scope_set_var(local, "y", ev_int(10), E_CERTAIN, E_LANG_EVER);

    /* y found in local */
    EvScopeEntry *ey = ev_scope_lookup(local, "y");
    ASSERT_NOT_NULL(ey);
    ASSERT_EQ_INT(10, ey->value.body.as_int);

    /* x found by walking chain */
    EvScopeEntry *ex = ev_scope_lookup(local, "x");
    ASSERT_NOT_NULL(ex);
    ASSERT_EQ_INT(99, ex->value.body.as_int);

    /* shadow x in local */
    ev_scope_set_var(local, "x", ev_int(0), E_CERTAIN, E_LANG_EVER);
    ASSERT_EQ_INT(0, ev_scope_lookup(local, "x")->value.body.as_int);
    ASSERT_EQ_INT(99, ev_scope_get(global, "x")->value.body.as_int);

    ev_scope_free(local);
    ev_scope_free(global);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(scope_resize, "scope") {
    EvArena *a = ev_arena_new("resize");
    EvScope *s = ev_scope_new(a, NULL, "bulk");
    char key[32];
    /* insert 50 entries — forces growth past 64*0.75=48 threshold */
    for (int i = 0; i < 50; i++) {
        snprintf(key, sizeof key, "var_%d", i);
        ev_scope_set_var(s, key, ev_int(i), E_CERTAIN, E_LANG_EVER);
    }
    ASSERT_EQ_INT(50, s->used);
    ASSERT(s->cap > 64);  /* must have grown */
    /* all 50 still retrievable */
    for (int i = 0; i < 50; i++) {
        snprintf(key, sizeof key, "var_%d", i);
        EvScopeEntry *e = ev_scope_get(s, key);
        ASSERT_NOT_NULL(e);
        ASSERT_EQ_INT(i, e->value.body.as_int);
    }
    ev_scope_free(s);
    ev_arena_free(a);
}

/* ─────────────────────────────────────────────
 * TAG: tac — Three-Address IR
 * ───────────────────────────────────────────── */

EV_SUITE_TAGGED(tac_opcodes, "tac") {
    ASSERT_EQ_STR("CONST",   ev_opcode_name(OP_CONST));
    ASSERT_EQ_STR("ADD",     ev_opcode_name(OP_ADD));
    ASSERT_EQ_STR("JUMP_IF", ev_opcode_name(OP_JUMP_IF));
    ASSERT_EQ_STR("RETURN",  ev_opcode_name(OP_RETURN));
    ASSERT_EQ_INT(1, ev_opcode_is_binary(OP_MUL));
    ASSERT_EQ_INT(1, ev_opcode_is_cmp(OP_LTE));
    ASSERT_EQ_INT(1, ev_opcode_is_branch(OP_JUMP));
    ASSERT_EQ_INT(0, ev_opcode_is_binary(OP_CONST));
}

EV_SUITE_TAGGED(tac_lower_arith, "tac", "lower") {
    EvArena *a = ev_arena_new("lower");
    EvNode *n6   = ev_node_int(a,6,1);
    EvNode *n36  = ev_node_int(a,36,1);
    EvNode *add  = ev_node_binop(a,EV_NODE_ADD,n6,n36,1);
    EvModule *m  = ev_lower_module("arith", add, a);
    ASSERT_NOT_NULL(m);
    ASSERT_NOT_NULL(m->global_body);
    ASSERT(m->global_body->nblocks > 0);

    EvBlock *gb = m->global_body->blocks[0];
    /* Should have: CONST 6, CONST 36, ADD, RETURN */
    ASSERT_EQ_INT(OP_CONST, gb->instrs[0].op);
    ASSERT_EQ_INT(6,        gb->instrs[0].literal.body.as_int);
    ASSERT_EQ_INT(OP_CONST, gb->instrs[1].op);
    ASSERT_EQ_INT(36,       gb->instrs[1].literal.body.as_int);
    ASSERT_EQ_INT(OP_ADD,   gb->instrs[2].op);

    ev_module_free(m);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(tac_const_fold, "tac", "optimise") {
    EvArena *a = ev_arena_new("fold");
    /* 3 - 1 should fold to CONST 2 */
    EvNode *n3 = ev_node_int(a,3,1);
    EvNode *n1 = ev_node_int(a,1,1);
    EvNode *sub = ev_node_binop(a,EV_NODE_SUB,n3,n1,1);
    EvModule *m = ev_lower_module("fold", sub, a);
    int changes = ev_pass_const_fold(m->global_body);
    ASSERT(changes > 0);
    /* The SUB instruction should now be CONST */
    EvBlock *gb = m->global_body->blocks[0];
    int found_const_2 = 0;
    for (int i=0;i<gb->len;i++) {
        if (gb->instrs[i].op == OP_CONST &&
            gb->instrs[i].literal.body.as_int == 2)
            found_const_2 = 1;
    }
    ASSERT_EQ_INT(1, found_const_2);
    ev_module_free(m);
    ev_arena_free(a);
}

EV_SUITE_TAGGED(tac_conf_propagation, "tac", "confidence") {
    EvArena *a = ev_arena_new("conf");
    const char *pn[] = {};
    EvModule *m = ev_module_new("conf", a);
    EvFunc *f = ev_module_add_func(m,"f",pn,0);
    EvBlock *b = ev_func_new_block(f);
    EvBuilder bld = ev_builder(m,f,b);

    /* CONST = certain, LOAD = intake (120) */
    EvReg rc  = ev_emit_const(&bld, ev_int(42), 1);
    EvReg rld = ev_emit_load(&bld, "x", EV_INT, 120, 1);
    EvReg radd = ev_emit_binop(&bld, OP_ADD, rc, rld, 1);

    ASSERT_EQ_INT(E_CERTAIN, rc.confidence);

    ev_pass_conf_prop(f);

    /* after propagation, ADD dest = min(256, 120) = 120 */
    int add_conf = 256;
    for (int i=0;i<b->len;i++) {
        if (b->instrs[i].dest.id == radd.id)
            add_conf = b->instrs[i].dest.confidence;
    }
    ASSERT(add_conf <= 120);
    /* ev_module_free owns the arena when created via ev_module_new(name, arena).
     * Do NOT call ev_arena_free separately — that would double-free. */
    ev_module_free(m);
}

EV_SUITE_TAGGED(tac_interpret, "tac", "interp") {
    /* Parameterised interpreter tests */
    struct {
        const char *label;
        int64_t expected;
        int64_t a, b;
        EvOpcode op;
    } cases[] = {
        {"6+36=42",  42,  6,  36, OP_ADD},
        {"10-3=7",    7, 10,   3, OP_SUB},
        {"7*6=42",   42,  7,   6, OP_MUL},
        {"0+0=0",     0,  0,   0, OP_ADD},
        {"99+1=100", 100, 99,  1, OP_ADD},
    };

    EV_PARAMS(cases, tc) {
        EvArena *aa = ev_arena_new(tc.label);
        EvNode *na = ev_node_int(aa, tc.a, 1);
        EvNode *nb = ev_node_int(aa, tc.b, 1);
        EvNode *op = ev_node_binop(aa,
            (tc.op==OP_ADD ? EV_NODE_ADD :
             tc.op==OP_SUB ? EV_NODE_SUB : EV_NODE_MUL),
            na, nb, 1);
        EvModule *mm = ev_lower_module(tc.label, op, aa);
        ev_optimise(mm->global_body);
        EvInterp *ip = ev_interp_new(mm);
        EValue r = ev_interp_run(ip);
        ASSERT_EQ_INT(EV_INT,    r.tag);
        ASSERT_EQ_INT(tc.expected, r.body.as_int);
        ev_interp_free(ip);
        ev_module_free(mm);
        ev_arena_free(aa);
    }
}

EV_SUITE_TAGGED(tac_if_branch, "tac", "interp") {
    /* if 10 > 5 then 42 else 0 */
    EvArena *a = ev_arena_new("if");
    EvNode *n10 = ev_node_int(a,10,1);
    EvNode *n5  = ev_node_int(a,5,1);
    EvNode *cmp = ev_node_binop(a,EV_NODE_GT,n10,n5,1);
    EvNode *n42 = ev_node_int(a,42,1);
    EvNode *n0  = ev_node_int(a,0,1);
    EvNode *iff = ev_node_if(a,cmp,n42,n0,1);
    EvModule *m = ev_lower_module("if",iff,a);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    ASSERT_EQ_INT(EV_INT, r.tag);
    ASSERT_EQ_INT(42, r.body.as_int);
    ev_interp_free(ip);
    ev_module_free(m);
    ev_arena_free(a);

    /* if 1 > 10 then 42 else -1  (false branch) */
    EvArena *a2 = ev_arena_new("if2");
    EvModule *m2 = ev_lower_module("if2",
        ev_node_if(a2,
            ev_node_binop(a2,EV_NODE_GT,ev_node_int(a2,1,1),ev_node_int(a2,10,1),1),
            ev_node_int(a2,42,1),
            ev_node_int(a2,-1,1),1), a2);
    EvInterp *ip2 = ev_interp_new(m2);
    EValue r2 = ev_interp_run(ip2);
    ASSERT_EQ_INT(EV_INT, r2.tag);
    ASSERT_EQ_INT(-1, r2.body.as_int);
    ev_interp_free(ip2);
    ev_module_free(m2);
    ev_arena_free(a2);
}

EV_SUITE_TAGGED(tac_function_call, "tac", "interp") {
    /* def square(n) = n * n; square(7) = 49 */
    EvArena *a = ev_arena_new("sq");
    const char *pn[] = {"n"};
    EvNode *sqn  = ev_node_var(a,"n",1);
    EvNode *sqn2 = ev_node_var(a,"n",1);
    EvNode *sqmul = ev_node_binop(a,EV_NODE_MUL,sqn,sqn2,1);
    EvNode *sqfn  = ev_node_def(a,"square",pn,1,sqmul,1);
    EvModule *m = ev_lower_module("sq", sqfn, a);
    ev_optimise(m->funcs[0]);
    EvInterp *ip = ev_interp_new(m);
    EValue arg = ev_int(7);
    EValue r = ev_interp_call(ip, "square", &arg, 1);
    ASSERT_EQ_INT(EV_INT, r.tag);
    ASSERT_EQ_INT(49, r.body.as_int);
    ev_interp_free(ip);
    ev_module_free(m);
    ev_arena_free(a);
}

/* ─────────────────────────────────────────────
 * TAG: bridge — end-to-end: 6 + 36 = 42
 * ───────────────────────────────────────────── */

EV_SUITE_TAGGED(bridge_e2e, "bridge") {
    /* Stage 0: C atom */
    e_particle pa = e_int("six",      6, E_CERTAIN, E_LANG_C);
    e_particle pb = e_int("thirtysix",36, E_CERTAIN, E_LANG_C);
    ASSERT_EQ_INT(6,        pa.value.as_int);
    ASSERT_EQ_INT(36,       pb.value.as_int);
    ASSERT_EQ_INT(E_CERTAIN,pa.confidence);

    /* Stage 1: ABI wire */
    uint8_t abi_buf[sizeof(e_particle)];
    memcpy(abi_buf, &pa, sizeof pa);
    e_particle pa2;
    memcpy(&pa2, abi_buf, sizeof pa2);
    ASSERT_EQ_INT(6,        pa2.value.as_int);
    ASSERT_EQ_INT(E_CERTAIN,pa2.confidence);
    ASSERT_EQ_STR("six",    pa2.ident);

    /* Stage 2: IR tree */
    EvArena *a = ev_arena_new("bridge");
    EvNode *n6   = ev_node_int(a, 6,  1);
    EvNode *n36  = ev_node_int(a, 36, 1);
    EvNode *add  = ev_node_binop(a, EV_NODE_ADD, n6, n36, 1);

    uint8_t ir_buf[256];
    int32_t ir_len = ev_ir_serialise(add, ir_buf, sizeof ir_buf);
    ASSERT(ir_len > 0);
    ASSERT(ir_len < 64);

    EvArena *b = ev_arena_new("recv");
    int32_t cons = 0;
    EvNode *add2 = ev_ir_deserialise(ir_buf, ir_len, &cons, b);
    ASSERT_NOT_NULL(add2);
    ASSERT_EQ_INT(ir_len, cons);
    ASSERT_EQ_INT(EV_NODE_ADD, add2->kind);

    /* Stage 3: TAC interpreter evaluates the deserialized tree */
    EvModule *m = ev_lower_module("bridge", add2, b);
    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue result = ev_interp_run(ip);
    ASSERT_EQ_INT(EV_INT, result.tag);
    ASSERT_EQ_INT(42, result.body.as_int);

    ev_interp_free(ip);
    ev_module_free(m);
    ev_arena_free(b);
    ev_arena_free(a);
}

/* ─────────────────────────────────────────────
 * Entry point
 * ───────────────────────────────────────────── */

EV_MAIN
