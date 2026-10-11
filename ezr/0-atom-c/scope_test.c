/*
 * scope_test.c — Ever / Tapestry, universal map verification
 *
 * Tests the hash function, insert/lookup/delete, resize, scope chain,
 * all five entry kinds, and the wire round-trip through EValue(RECORD).
 */

#include <stdio.h>
#include <string.h>
#include <math.h>
#include "scope.h"

static int ok_n = 0, fail_n = 0;
static void _ok(const char *name, int cond) {
    if (cond) { ok_n++;   printf("  \u2713 %s\n", name); }
    else       { fail_n++; printf("  \u2717 %s\n", name); }
}
#define ok(n, c) _ok(n, c)

int main(void) {
    ev_pool  pool;    ev_pool_init(&pool);
    EvArena *arena = ev_arena_new("scope-test");

    printf("\n=== Ever \u2014 universal map (EvScope) ===\n\n");

    /* ── FNV-1a hash ── */
    printf("FNV-1a hash\n");
    ok("hash non-zero",         ev_fnv1a("x") != 0);
    ok("hash deterministic",    ev_fnv1a("hello") == ev_fnv1a("hello"));
    ok("hash distinct a/b",     ev_fnv1a("abc") != ev_fnv1a("def"));
    ok("hash empty string",     ev_fnv1a("") != 0);   /* FNV offset basis */
    ok("hash long name",        ev_fnv1a("my_very_long_module_name") != 0);

    /* ── Lifecycle ── */
    printf("\nLifecycle\n");
    EvScope *global = ev_scope_new(arena, NULL, "global");
    ok("global created",        global != NULL);
    ok("global depth 0",        global->depth == 0);
    ok("global cap 64",         global->cap == EV_SCOPE_INIT_CAP);
    ok("global used 0",         global->used == 0);
    ok("global parent null",    global->parent == NULL);
    ok("global name set",       strcmp(global->name, "global") == 0);

    /* ── Insert and lookup — VAR ── */
    printf("\nInsert and lookup — VAR\n");
    ok("set x=42",       ev_scope_set_var(global, "x", ev_int(42),
                                           E_CERTAIN, E_LANG_EVER));
    ok("set y=3.14",     ev_scope_set_var(global, "y", ev_real(3.14),
                                           E_CERTAIN, E_LANG_PYTHON));
    ok("set flag=true",  ev_scope_set_var(global, "flag", ev_bool(1),
                                           E_CERTAIN, E_LANG_EVER));
    ok("set name=Codric",ev_scope_set_var(global, "name", ev_text("Codric"),
                                           E_CERTAIN, E_LANG_EVER));

    EvScopeEntry *ex = ev_scope_get(global, "x");
    ok("get x != NULL",        ex != NULL);
    ok("x value = 42",         ex && ex->value.body.as_int == 42);
    ok("x kind = VAR",         ex && ex->kind == EV_SK_VAR);
    ok("x confidence = 256",   ex && ex->confidence == E_CERTAIN);
    ok("x lang = EVER",        ex && ex->lang == E_LANG_EVER);

    EvScopeEntry *ey = ev_scope_get(global, "y");
    ok("get y != NULL",        ey != NULL);
    ok("y value ≈ 3.14",       ey && fabs(ey->value.body.as_real - 3.14) < 1e-9);
    ok("y lang = PYTHON",      ey && ey->lang == E_LANG_PYTHON);

    ok("get missing = NULL",   ev_scope_get(global, "zzz") == NULL);
    ok("lookup missing = NULL", ev_scope_lookup(global, "zzz") == NULL);
    ok("used = 4",             global->used == 4);

    /* ── Update existing ── */
    printf("\nUpdate existing binding\n");
    ok("update x=99",    ev_scope_set_var(global, "x", ev_int(99),
                                           200, E_LANG_EVER));
    EvScopeEntry *ex2 = ev_scope_get(global, "x");
    ok("x updated to 99",      ex2 && ex2->value.body.as_int == 99);
    ok("used still 4",         global->used == 4);  /* update, not insert */

    /* ── Function entries ── */
    printf("\nFunction entries — EV_SK_FN\n");
    EvArena *fa = ev_arena_new("fn-arena");
    EvNode *body = ev_node_binop(fa, EV_NODE_MUL,
                                 ev_node_var(fa,"n",1),
                                 ev_node_var(fa,"n",1), 1);
    const char *prms[] = {"n"};
    ok("set_fn square",  ev_scope_set_fn(global, "square", body,
                                          prms, 1, E_CERTAIN, E_LANG_EVER));

    EvScopeEntry *efn = ev_scope_get(global, "square");
    ok("get square",           efn != NULL);
    ok("square kind = FN",     efn && efn->kind == EV_SK_FN);
    ok("square node set",      efn && efn->node == body);
    ok("square param_count=1", efn && efn->param_count == 1);
    ok("square param name",    efn && strcmp(efn->params[0], "n") == 0);

    EvNode *got_fn = ev_scope_get_fn(global, "square");
    ok("get_fn returns body",  got_fn == body);
    ok("get_fn missing=NULL",  ev_scope_get_fn(global, "nope") == NULL);
    ev_arena_free(fa);

    /* ── Module entries ── */
    printf("\nModule entries — EV_SK_MODULE\n");
    EvArena *ma = ev_arena_new("math-arena");
    EvScope *math_mod = ev_scope_new(ma, global, "Math");
    ev_scope_set_var(math_mod, "PI", ev_real(3.14159265358979),
                     E_CERTAIN, E_LANG_EVER);
    ev_scope_set_module(global, "Math", math_mod, E_LANG_EVER);

    EvScopeEntry *em = ev_scope_get(global, "Math");
    ok("get Math module",      em != NULL);
    ok("Math kind = MODULE",   em && em->kind == EV_SK_MODULE);

    EvScope *got_mod = ev_scope_get_module(global, "Math");
    ok("get_module returns scope", got_mod == math_mod);
    ok("module PI = π",
       fabs(ev_scope_get_value(got_mod,"PI").body.as_real - 3.14159265) < 1e-7);
    ev_arena_free(ma);

    /* ── Scope chain — local inherits from global ── */
    printf("\nScope chain — local inherits global\n");
    EvArena *la = ev_arena_new("local-arena");
    EvScope *local = ev_scope_new(la, global, "fn:add");
    ok("local depth = 1",      local->depth == 1);
    ok("local parent = global",local->parent == global);

    ev_scope_set_var(local, "a", ev_int(10), E_CERTAIN, E_LANG_EVER);
    ev_scope_set_var(local, "b", ev_int(32), E_CERTAIN, E_LANG_EVER);

    /* local binding found in local */
    EvScopeEntry *ea = ev_scope_lookup(local, "a");
    ok("lookup 'a' in local",  ea && ea->value.body.as_int == 10);

    /* global binding found by walking chain */
    EvScopeEntry *ex3 = ev_scope_lookup(local, "x");
    ok("lookup 'x' via chain", ex3 && ex3->value.body.as_int == 99);

    /* shadow: local 'x' shadows global 'x' */
    ev_scope_set_var(local, "x", ev_int(0), E_CERTAIN, E_LANG_EVER);
    EvScopeEntry *shadow = ev_scope_lookup(local, "x");
    ok("shadow x = 0 (local)",  shadow && shadow->value.body.as_int == 0);

    /* global x unchanged */
    EvScopeEntry *global_x = ev_scope_get(global, "x");
    ok("global x still = 99",  global_x && global_x->value.body.as_int == 99);

    /* get_value walks chain */
    EValue bval = ev_scope_get_value(local, "b");
    ok("get_value 'b'",         bval.body.as_int == 32);
    EValue missing = ev_scope_get_value(local, "zzz");
    ok("get_value missing=void", missing.tag == EV_VOID);
    ev_arena_free(la);

    /* ── Deletion / tombstones ── */
    printf("\nDeletion (tombstones)\n");
    EvArena *da = ev_arena_new("del-arena");
    EvScope *ds = ev_scope_new(da, NULL, "del-test");
    ev_scope_set_var(ds, "a", ev_int(1), E_CERTAIN, E_LANG_EVER);
    ev_scope_set_var(ds, "b", ev_int(2), E_CERTAIN, E_LANG_EVER);
    ev_scope_set_var(ds, "c", ev_int(3), E_CERTAIN, E_LANG_EVER);

    ok("delete 'b'",            ev_scope_delete(ds, "b"));
    ok("get 'b' = NULL",        ev_scope_get(ds, "b") == NULL);
    ok("get 'a' still live",    ev_scope_get(ds, "a") != NULL);
    ok("get 'c' still live",    ev_scope_get(ds, "c") != NULL);
    ok("delete missing = 0",    !ev_scope_delete(ds, "zzz"));
    ok("used decremented",      ds->used == 2);

    /* re-insert after deletion */
    ev_scope_set_var(ds, "b", ev_int(99), E_CERTAIN, E_LANG_EVER);
    ok("re-insert 'b'=99",      ev_scope_get(ds,"b") != NULL);
    ok("re-inserted value",
       ev_scope_get(ds,"b")->value.body.as_int == 99);
    ev_scope_free(ds); ev_arena_free(da);

    /* ── Resize — force growth past 75 % ── */
    printf("\nResize — force growth past 75%%\n");
    EvArena *ra = ev_arena_new("resize-arena");
    EvScope *rs = ev_scope_new(ra, NULL, "resize");
    char key[16];
    /* insert 50 items — exceeds 64 * 0.75 = 48 threshold */
    for (int i = 0; i < 50; i++) {
        snprintf(key, sizeof key, "var_%d", i);
        ev_scope_set_var(rs, key, ev_int(i), E_CERTAIN, E_LANG_EVER);
    }
    ok("50 items inserted",     rs->used == 50);
    ok("cap grew past 64",      rs->cap > EV_SCOPE_INIT_CAP);

    /* all 50 items still retrievable after resize */
    int all_ok = 1;
    for (int i = 0; i < 50; i++) {
        snprintf(key, sizeof key, "var_%d", i);
        EvScopeEntry *e = ev_scope_get(rs, key);
        if (!e || e->value.body.as_int != i) { all_ok = 0; break; }
    }
    ok("all 50 items survive resize", all_ok);
    ev_scope_free(rs); ev_arena_free(ra);

    /* ── Wire format — scope ↔ EValue(RECORD) ── */
    printf("\nWire format — scope \u2194 EValue(RECORD)\n");
    EvArena *wa = ev_arena_new("wire-arena");
    EvScope *ws = ev_scope_new(wa, NULL, "wire");
    ev_scope_set_var(ws, "id",    ev_int(7),         E_CERTAIN, E_LANG_SQL);
    ev_scope_set_var(ws, "name",  ev_text("Alice"),   E_CERTAIN, E_LANG_SQL);
    ev_scope_set_var(ws, "score", ev_real(98.6),      E_CERTAIN, E_LANG_SQL);

    EValue rec = ev_scope_to_record(ws, &pool);
    ok("to_record tag = RECORD",  rec.tag == EV_RECORD);

    EvScope *ws2 = ev_scope_new(wa, NULL, "wire2");
    ok("from_record",             ev_scope_from_record(ws2, &rec, &pool,
                                                        E_LANG_SQL));
    ok("id round-trips",
       ev_scope_get_value(ws2,"id").body.as_int == 7);
    ok("name round-trips",
       strcmp(ev_scope_get_value(ws2,"name").text, "Alice") == 0);
    ok("score round-trips",
       fabs(ev_scope_get_value(ws2,"score").body.as_real - 98.6) < 1e-9);

    /* serialise the RECORD further through EValue wire format */
    uint8_t buf[2048];
    int32_t n = ev_serialise(&rec, buf, sizeof buf, &pool);
    ok("EValue serialise succeeds", n > 0);
    int32_t consumed = 0;
    EValue rec2 = ev_deserialise(buf, n, &consumed, &pool);
    ok("EValue round-trip",       rec2.tag == EV_RECORD && consumed == n);

    EvScope *ws3 = ev_scope_new(wa, NULL, "wire3");
    ev_scope_from_record(ws3, &rec2, &pool, E_LANG_PYTHON);
    ok("C→wire→Python→C id",
       ev_scope_get_value(ws3,"id").body.as_int == 7);
    ev_scope_free(ws);  ev_scope_free(ws2);  ev_scope_free(ws3);
    ev_arena_free(wa);

    /* ── Stats and dump ── */
    printf("\nDiagnostics\n");
    char stats[128];
    ev_scope_stats(global, stats, sizeof stats);
    ok("stats non-empty",       strlen(stats) > 10);
    ok("stats has scope name",  strstr(stats, "global") != NULL);
    printf("  %s\n", stats);

    /* ── Cleanup ── */
    ev_scope_free(global);
    ev_arena_free(arena);

    printf("\n=== EvScope: %d passed, %d failed ===\n\n", ok_n, fail_n);
    return fail_n == 0 ? 0 : 1;
}
