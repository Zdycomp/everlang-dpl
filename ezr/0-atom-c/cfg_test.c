/*
 * cfg_test.c — Ever / Tapestry, CFG and definite-assignment tests
 *
 * Every test proves one of two things:
 *   SAFE  — a program that is correct should produce 0 errors
 *   CATCH — a program with a bug should produce >= 1 errors at the
 *            exact kind of error we expect
 *
 * This is the test that catches null-pointer / undefined-variable
 * crashes before the program runs.
 */

#include <stdio.h>
#include <string.h>
#include "cfg.h"

static int ok_count = 0, fail_count = 0;

static void _ok(const char *name, int cond) {
    if (cond) { ok_count++; printf("  \u2713 %s\n", name); }
    else       { fail_count++; printf("  \u2717 %s\n", name); }
}
#define ok(n, c) _ok(n, c)

/* Build a CFG for a function, run analysis, return error count */
static int analyse_fn(EvNode *fn, EvArena *arena) {
    Cfg *cfg = cfg_build(fn, arena);
    if (!cfg) return -1;
    cfg_analyse(cfg);
    cfg_liveness(cfg);
    cfg_insert_phis(cfg);
    cfg_check_definite_assignment(cfg);
    return cfg->error_count;
}

int main(void) {
    printf("\n=== Ever \u2014 CFG + definite assignment ===\n\n");

    /* ── Name table ── */
    printf("Name table\n");
    {
        NameTable t; memset(&t, 0, sizeof t);
        NameId n1 = name_intern(&t, "foo");
        NameId n2 = name_intern(&t, "bar");
        NameId n3 = name_intern(&t, "foo");   /* already interned */
        ok("first intern",        n1 == 0);
        ok("second intern",       n2 == 1);
        ok("re-intern same name", n3 == n1);
        ok("find existing",       name_find(&t, "foo") == n1);
        ok("find missing",        name_find(&t, "xyz") == -1);
        ok("name_str round-trip", strcmp(name_str(&t, n1), "foo") == 0);
    }

    /* ── DefinedSet ── */
    printf("\nDefinedSet\n");
    {
        DefinedSet s;
        defset_clear(&s);
        ok("empty set has nothing",    !defset_has(&s, 0));
        defset_add(&s, 0);
        ok("add 0, has 0",             defset_has(&s, 0));
        ok("add 0, not 1",             !defset_has(&s, 1));
        defset_add(&s, 127);
        ok("add 127 works",            defset_has(&s, 127));
        defset_remove(&s, 0);
        ok("remove 0",                 !defset_has(&s, 0));
        ok("127 still there",          defset_has(&s, 127));

        DefinedSet a, b;
        defset_clear(&a); defset_clear(&b);
        defset_add(&a, 1); defset_add(&a, 2);
        defset_add(&b, 2); defset_add(&b, 3);
        DefinedSet c = a;
        defset_intersect(&c, &b);
        ok("intersect has 2",          defset_has(&c, 2));
        ok("intersect no 1",           !defset_has(&c, 1));
        ok("intersect no 3",           !defset_has(&c, 3));
        defset_union(&c, &a);
        ok("union has 1",              defset_has(&c, 1));
        ok("union has 2",              defset_has(&c, 2));
        ok("union no 3",               !defset_has(&c, 3));

        DefinedSet full; defset_fill(&full);
        ok("filled: has 0",            defset_has(&full, 0));
        ok("filled: has 255",          defset_has(&full, 255));
        ok("equal reflexive",          defset_equal(&a, &a));
        ok("not equal",                !defset_equal(&a, &b));
        ok("subset",                   defset_subset(&c, &full));
    }

    /* ── CFG construction ── */
    printf("\nCFG construction\n");
    {
        EvArena *arena = ev_arena_new("cfg-test");

        /* Simple function: def id(x) = x */
        EvNode *body  = ev_node_var(arena, "x", 1);
        const char *p[] = {"x"};
        EvNode *fn    = ev_node_def(arena, "id", p, 1, body, 1);

        Cfg *cfg = cfg_build(fn, arena);
        ok("cfg created",              cfg != NULL);
        ok("has entry block",          cfg->block_count >= 1);
        ok("fn name preserved",        strcmp(cfg->fn_name, "id") == 0);
        ok("has name 'x'",             name_find(&cfg->names, "x") >= 0);
        ok("has name 'id'",            name_find(&cfg->names, "id") >= 0);

        /* entry block should have x in def_gen (it's a param) */
        CfgBlock *entry = cfg->blocks[cfg->entry_id];
        NameId xid = name_find(&cfg->names, "x");
        ok("x in entry def_gen",       defset_has(&entry->def_gen, xid));

        ev_arena_free(arena);
    }

    /* ── CFG for an if/then/else ── */
    printf("\nCFG structure for if/then/else\n");
    {
        EvArena *a = ev_arena_new("cfg-if");
        /* def f(n) = if n <= 1 then 1 else 0 */
        EvNode *vn   = ev_node_var(a, "n", 1);
        EvNode *one  = ev_node_int(a, 1, 1);
        EvNode *cmp  = ev_node_binop(a, EV_NODE_LTE, vn, one, 1);
        EvNode *then = ev_node_int(a, 1, 1);
        EvNode *els  = ev_node_int(a, 0, 1);
        EvNode *iff  = ev_node_if(a, cmp, then, els, 1);
        const char *ps[] = {"n"};
        EvNode *fn   = ev_node_def(a, "f", ps, 1, iff, 1);

        Cfg *cfg = cfg_build(fn, a);
        ok("if produces >=4 blocks",   cfg->block_count >= 4);

        /* entry, then, else, join */
        int has_branch = 0;
        int join_count = 0;
        for (int i = 0; i < cfg->block_count; i++) {
            CfgBlock *b = cfg->blocks[i];
            if (b->term == CFG_TERM_BRANCH) has_branch = 1;
            if (b->pred_count == 2) join_count++;
        }
        ok("has a branch block",       has_branch);
        ok("has a join block",         join_count > 0);
        ev_arena_free(a);
    }

    /* ── DEFINITE ASSIGNMENT ANALYSIS ── */
    printf("\nDefinite assignment: SAFE programs\n");

    /* SAFE 1: def id(x) = x — param always defined */
    {
        EvArena *a = ev_arena_new("safe1");
        EvNode *body = ev_node_var(a, "x", 1);
        const char *ps[] = {"x"};
        EvNode *fn = ev_node_def(a, "id", ps, 1, body, 1);
        int errs = analyse_fn(fn, a);
        ok("id(x)=x: 0 errors",        errs == 0);
        ev_arena_free(a);
    }

    /* SAFE 2: def f(n) = n + 1 — param used in arithmetic */
    {
        EvArena *a = ev_arena_new("safe2");
        EvNode *vn  = ev_node_var(a, "n", 1);
        EvNode *one = ev_node_int(a, 1, 1);
        EvNode *add = ev_node_binop(a, EV_NODE_ADD, vn, one, 1);
        const char *ps[] = {"n"};
        EvNode *fn = ev_node_def(a, "f", ps, 1, add, 1);
        int errs = analyse_fn(fn, a);
        ok("f(n)=n+1: 0 errors",       errs == 0);
        ev_arena_free(a);
    }

    /* SAFE 3: if/else — both branches define the result, join is fine */
    {
        EvArena *a = ev_arena_new("safe3");
        /* def f(n) = if n <= 0 then 0 else n */
        EvNode *vn   = ev_node_var(a, "n", 1);
        EvNode *zero = ev_node_int(a, 0, 1);
        EvNode *cmp  = ev_node_binop(a, EV_NODE_LTE, vn, zero, 1);
        EvNode *then = ev_node_int(a, 0, 1);
        EvNode *vn2  = ev_node_var(a, "n", 1);
        EvNode *iff  = ev_node_if(a, cmp, then, vn2, 1);
        const char *ps[] = {"n"};
        EvNode *fn = ev_node_def(a, "f", ps, 1, iff, 1);
        int errs = analyse_fn(fn, a);
        ok("if n<=0 then 0 else n: 0 errors", errs == 0);
        ev_arena_free(a);
    }

    /* SAFE 4: two params, both used */
    {
        EvArena *a = ev_arena_new("safe4");
        /* def add(x, y) = x + y */
        EvNode *vx  = ev_node_var(a, "x", 1);
        EvNode *vy  = ev_node_var(a, "y", 1);
        EvNode *add = ev_node_binop(a, EV_NODE_ADD, vx, vy, 1);
        const char *ps[] = {"x", "y"};
        EvNode *fn = ev_node_def(a, "add", ps, 2, add, 1);
        int errs = analyse_fn(fn, a);
        ok("add(x,y)=x+y: 0 errors",   errs == 0);
        ev_arena_free(a);
    }

    /* SAFE 5: recursive — fact(n) = if n<=1 then 1 else n*fact(n-1) */
    {
        EvArena *a = ev_arena_new("safe5");
        EvNode *vn   = ev_node_var(a, "n", 1);
        EvNode *one  = ev_node_int(a, 1, 1);
        EvNode *cmp  = ev_node_binop(a, EV_NODE_LTE, vn, one, 1);
        EvNode *base = ev_node_int(a, 1, 1);
        EvNode *vn2  = ev_node_var(a, "n", 1);
        EvNode *one2 = ev_node_int(a, 1, 1);
        EvNode *dec  = ev_node_binop(a, EV_NODE_SUB, ev_node_var(a,"n",1), one2, 1);
        EvNode *rec_args[] = {dec};
        EvNode *rec  = ev_node_call(a, "fact", rec_args, 1, 1);
        EvNode *mul  = ev_node_binop(a, EV_NODE_MUL, vn2, rec, 1);
        EvNode *iff  = ev_node_if(a, cmp, base, mul, 1);
        const char *ps[] = {"n"};
        EvNode *fn = ev_node_def(a, "fact", ps, 1, iff, 1);
        int errs = analyse_fn(fn, a);
        ok("fact recursive: 0 errors", errs == 0);
        ev_arena_free(a);
    }

    printf("\nDefinite assignment: UNSAFE programs are CAUGHT\n");

    /* CATCH 1: def f(x) = y — y is never defined */
    {
        EvArena *a = ev_arena_new("catch1");
        EvNode *vy = ev_node_var(a, "y", 1);   /* y is NOT a param */
        const char *ps[] = {"x"};
        EvNode *fn = ev_node_def(a, "f", ps, 1, vy, 1);
        int errs = analyse_fn(fn, a);
        ok("f(x)=y: caught (y undefined)", errs > 0);
        ev_arena_free(a);
    }

    /* CATCH 2: partial definition — use after if where one branch skips */
    {
        EvArena *a = ev_arena_new("catch2");
        /*
         * Simulates:
         *   if n > 0 then  x = n   else  skip
         *   x + 1              ← x may be undefined (false branch skips)
         *
         * We model this directly in the CFG:
         *   - then block defines 'x'
         *   - else block does NOT define 'x'
         *   - join block uses 'x'
         */
        Cfg *cfg = cfg_new(a, "partial");
        NameId n_id = name_intern(&cfg->names, "n");
        NameId x_id = name_intern(&cfg->names, "x");

        CfgBlock *entry = cfg_block_new(cfg, "entry");
        defset_add(&entry->def_gen, n_id);   /* n is a param */

        CfgBlock *then_b = cfg_block_new(cfg, "then");
        defset_add(&then_b->def_gen, x_id);  /* x defined in then */

        CfgBlock *else_b = cfg_block_new(cfg, "else");
        /* x NOT defined in else */

        CfgBlock *join_b = cfg_block_new(cfg, "join");
        defset_add(&join_b->use, x_id);      /* x USED after join */
        defset_add(&join_b->live_out, x_id); /* x live after join */

        entry->term = CFG_TERM_BRANCH;
        then_b->term = CFG_TERM_JUMP;
        else_b->term = CFG_TERM_JUMP;
        join_b->term = CFG_TERM_RETURN;

        cfg_connect(cfg, entry->id, then_b->id);
        cfg_connect(cfg, entry->id, else_b->id);
        cfg_connect(cfg, then_b->id, join_b->id);
        cfg_connect(cfg, else_b->id, join_b->id);

        cfg_analyse(cfg);
        cfg_liveness(cfg);
        cfg_insert_phis(cfg);
        int errs = cfg_check_definite_assignment(cfg);

        ok("partial x: caught",            errs > 0);
        ok("partial x: partial-def kind",
           cfg->error_count > 0 &&
           cfg->errors[0].kind == CFG_ERR_PARTIAL_DEF);
        ok("partial x: names 'x'",
           cfg->error_count > 0 &&
           strcmp(cfg->names.names[cfg->errors[0].name], "x") == 0);

        ev_arena_free(a);
    }

    /* CATCH 3: use of free variable in recursive function */
    {
        EvArena *a = ev_arena_new("catch3");
        /* def f(n) = n + k   — k is free, never defined */
        EvNode *vn = ev_node_var(a, "n", 1);
        EvNode *vk = ev_node_var(a, "k", 1);   /* k not a param */
        EvNode *add = ev_node_binop(a, EV_NODE_ADD, vn, vk, 1);
        const char *ps[] = {"n"};
        EvNode *fn = ev_node_def(a, "f", ps, 1, add, 1);
        int errs = analyse_fn(fn, a);
        ok("f(n)=n+k: caught (k undefined)", errs > 0);
        ev_arena_free(a);
    }

    /* ── Phi node insertion ── */
    printf("\nPhi node insertion\n");
    {
        EvArena *a = ev_arena_new("phi-test");
        /* if cond then x=1 else skip; use x */
        Cfg *cfg = cfg_new(a, "phi-fn");
        NameId n_id = name_intern(&cfg->names, "n");
        NameId x_id = name_intern(&cfg->names, "x");

        CfgBlock *entry   = cfg_block_new(cfg, "entry");
        CfgBlock *then_b  = cfg_block_new(cfg, "then");
        CfgBlock *else_b  = cfg_block_new(cfg, "else");
        CfgBlock *join_b  = cfg_block_new(cfg, "join");

        defset_add(&entry->def_gen, n_id);   /* n defined at entry */
        defset_add(&then_b->def_gen, x_id);  /* x defined in then */
        defset_add(&join_b->use, x_id);      /* x used at join */
        defset_add(&join_b->live_out, x_id); /* x live after */

        entry->term = CFG_TERM_BRANCH;
        then_b->term = else_b->term = CFG_TERM_JUMP;
        join_b->term = CFG_TERM_RETURN;

        cfg_connect(cfg, entry->id, then_b->id);
        cfg_connect(cfg, entry->id, else_b->id);
        cfg_connect(cfg, then_b->id, join_b->id);
        cfg_connect(cfg, else_b->id, join_b->id);

        cfg_analyse(cfg);
        cfg_liveness(cfg);
        cfg_insert_phis(cfg);

        /* x should have a phi at join because it's in then but not else */
        ok("phi inserted at join", join_b->phi_count > 0);
        ok("phi names x",
           join_b->phi_count > 0 &&
           join_b->phis[0].name == x_id);
        ok("phi has 2 sources",
           join_b->phi_count > 0 &&
           join_b->phis[0].src_block[0] >= 0 &&
           join_b->phis[0].src_block[1] >= 0);

        ev_arena_free(a);
    }

    /* ── Dominator summary ── */
    printf("\nCFG correctness\n");
    {
        /* n defined in entry must dominate all uses — verify via def_in */
        EvArena *a = ev_arena_new("dom");
        /* def f(n) = if n > 0 then n else 0 */
        EvNode *vn  = ev_node_var(a, "n", 1);
        EvNode *z   = ev_node_int(a, 0, 1);
        EvNode *cmp = ev_node_binop(a, EV_NODE_GT, vn, z, 1);
        EvNode *vn2 = ev_node_var(a, "n", 1);
        EvNode *ze2 = ev_node_int(a, 0, 1);
        EvNode *iff = ev_node_if(a, cmp, vn2, ze2, 1);
        const char *ps[] = {"n"};
        EvNode *fn = ev_node_def(a, "f", ps, 1, iff, 1);
        Cfg *cfg = cfg_build(fn, a);
        cfg_analyse(cfg);
        NameId nid = name_find(&cfg->names, "n");
        /* n must be in def_in of every block except the entry itself */
        int n_in_all = 1;
        for (int i = 1; i < cfg->block_count; i++) {
            if (!defset_has(&cfg->blocks[i]->def_in, nid)) {
                n_in_all = 0; break;
            }
        }
        ok("n dominates all blocks",   n_in_all);
        ok("0 errors for safe fn",     analyse_fn(fn, a) == 0);
        ev_arena_free(a);
    }

    printf("\n=== CFG: %d passed, %d failed ===\n\n", ok_count, fail_count);
    return fail_count == 0 ? 0 : 1;
}
