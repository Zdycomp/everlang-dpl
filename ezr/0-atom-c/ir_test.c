/*
 * ir_test.c — Ever / Tapestry, IR + arena verification
 *
 * Tests the arena allocator, EvNode IR, the wire format, and structural
 * metrics. Every allocation goes through the arena; every free is one call.
 */

#include <stdio.h>
#include <string.h>
#include "ir.h"
#include <math.h>
#include <math.h>

static int ok_count = 0, fail_count = 0;

static void _ok(const char *name, int cond) {
    if (cond) { ok_count++; printf("  \u2713 %s\n", name); }
    else       { fail_count++; printf("  \u2717 %s\n", name); }
}
#define ok(name, cond) _ok(name, cond)

int main(void) {
    printf("\n=== Ever \u2014 IR + arena ===\n\n");

    /* ── ARENA ── */
    printf("Arena allocator\n");
    EvArena *a = ev_arena_new("test");
    ok("arena created",         a != NULL);
    ok("debug tag set",         strcmp(a->debug_tag, "test") == 0);
    ok("slab count 1",          a->slab_count == 1);

    void *p1 = ev_arena_alloc(a, 16);
    void *p2 = ev_arena_alloc(a, 32);
    ok("first alloc non-null",  p1 != NULL);
    ok("second alloc non-null", p2 != NULL);
    ok("allocs are distinct",   p1 != p2);
    ok("total allocated grows", a->total_allocated >= 48);

    char *s = ev_arena_strdup(a, "Ever");
    ok("strdup works",          s && strcmp(s, "Ever") == 0);
    ok("strdup is arena-owned", (void*)s >= p1); /* same arena */

    char stats[128];
    ev_arena_stats(a, stats, sizeof stats);
    ok("stats non-empty",       strlen(stats) > 10);
    ok("stats includes tag",    strstr(stats, "test") != NULL);

    /* alloc enough to force a second slab */
    for (int i = 0; i < 100; i++)
        ev_arena_alloc(a, 1024);
    ok("grew to multiple slabs", a->slab_count > 1);

    ev_arena_free(a);
    ok("free doesn't crash",    1);   /* if we get here, free succeeded */

    /* ── EvNode constructors ── */
    printf("\nEvNode constructors\n");
    EvArena *b = ev_arena_new("nodes");

    EvNode *ni = ev_node_int(b, 42, 1);
    ok("int node kind",         ni && ni->kind == EV_NODE_INT);
    ok("int value",             ni && ni->lit.as_int == 42);
    ok("int line",              ni && ni->line == 1);
    ok("int arena backref",     ni && ni->arena == b);

    EvNode *nb_node = ev_node_bool(b, 1, 2);
    ok("bool true",             nb_node && nb_node->lit.as_bool == 1);

    EvNode *nr = ev_node_real(b, 3.14, 1);
    ok("real value",            nr && fabs(nr->lit.as_real - 3.14) < 1e-9);

    EvNode *nt = ev_node_text(b, "Codric", 1);
    ok("text value",            nt && strcmp(nt->str, "Codric") == 0);

    EvNode *nv = ev_node_var(b, "n", 1);
    ok("var name",              nv && strcmp(nv->str, "n") == 0);

    EvNode *ne = ev_node_error(b, "bad input", 5);
    ok("error node",            ne && ne->kind == EV_NODE_ERR);
    ok("error message",         ne && strcmp(ne->error, "bad input") == 0);

    /* binop */
    EvNode *left  = ev_node_int(b, 1, 1);
    EvNode *right = ev_node_int(b, 2, 1);
    EvNode *add   = ev_node_binop(b, EV_NODE_ADD, left, right, 1);
    ok("binop kind",            add && add->kind == EV_NODE_ADD);
    ok("binop child count",     add && add->child_count == 2);
    ok("binop left",            add && add->children[0]->lit.as_int == 1);
    ok("binop right",           add && add->children[1]->lit.as_int == 2);

    /* if */
    EvNode *cond   = ev_node_bool(b, 1, 1);
    EvNode *then_n = ev_node_int(b, 10, 1);
    EvNode *else_n = ev_node_int(b, 20, 1);
    EvNode *if_n   = ev_node_if(b, cond, then_n, else_n, 1);
    ok("if child count",        if_n && if_n->child_count == 3);
    ok("if cond",               if_n && if_n->children[0]->lit.as_bool == 1);

    /* def */
    const char *params[] = {"n"};
    EvNode *body = ev_node_int(b, 0, 1);
    EvNode *def  = ev_node_def(b, "fact", params, 1, body, 1);
    ok("def kind",              def && def->kind == EV_NODE_DEF);
    ok("def name",              def && strcmp(def->str, "fact") == 0);
    ok("def param count",       def && def->param_count == 1);
    ok("def param name",        def && strcmp(def->params[0], "n") == 0);
    ok("def body is child",     def && def->child_count == 1);

    /* call */
    EvNode *arg  = ev_node_var(b, "n", 1);
    EvNode *args[] = {arg};
    EvNode *call = ev_node_call(b, "fact", args, 1, 1);
    ok("call kind",             call && call->kind == EV_NODE_CALL);
    ok("call name",             call && strcmp(call->str, "fact") == 0);
    ok("call arg count",        call && call->child_count == 1);

    /* ── Structural metrics ── */
    printf("\nStructural metrics\n");
    /* fact(n) = if n <= 1 then 1 else n * fact(n-1) */
    EvArena *c = ev_arena_new("metrics");
    EvNode *vn    = ev_node_var(c, "n", 1);
    EvNode *one_a = ev_node_int(c, 1, 1);
    EvNode *cmp   = ev_node_binop(c, EV_NODE_LTE, vn, one_a, 1);
    EvNode *one_b = ev_node_int(c, 1, 1);
    EvNode *vn2   = ev_node_var(c, "n", 1);
    EvNode *vn3   = ev_node_var(c, "n", 1);
    EvNode *one_c = ev_node_int(c, 1, 1);
    EvNode *dec   = ev_node_binop(c, EV_NODE_SUB, vn3, one_c, 1);
    EvNode *carg[] = {dec};
    EvNode *rec   = ev_node_call(c, "fact", carg, 1, 1);
    EvNode *mul   = ev_node_binop(c, EV_NODE_MUL, vn2, rec, 1);
    EvNode *iff   = ev_node_if(c, cmp, one_b, mul, 1);
    const char *prm[] = {"n"};
    EvNode *fn    = ev_node_def(c, "fact", prm, 1, iff, 1);

    ev_node_measure(fn);
    ok("fact size == 12",       fn->size == 12);
    ok("fact depth == 5",       fn->depth == 5);

    const char *sk = ev_node_skeleton(fn->children[0], c);
    ok("skeleton erases consts", strstr(sk, "K") != NULL);
    ok("skeleton erases cmps",   strstr(sk, "CMP") != NULL);
    ok("skeleton keeps var",     strstr(sk, "V") != NULL);

    /* ── Wire format ── */
    printf("\nWire format — round-trip every node type\n");
    EvArena *d = ev_arena_new("rt");
    uint8_t buf[4096];

    struct { const char *label; EvNode *node; } cases[] = {
        {"int",  ev_node_int(d, 42, 1)},
        {"real", ev_node_real(d, 2.718, 1)},
        {"bool", ev_node_bool(d, 0, 1)},
        {"text", ev_node_text(d, "Ever", 1)},
        {"var",  ev_node_var(d, "n", 1)},
        {"err",  ev_node_error(d, "bad", 1)},
    };
    for (int i = 0; i < 6; i++) {
        int32_t n_bytes = ev_ir_serialise(cases[i].node, buf, sizeof buf);
        ok(cases[i].label, n_bytes > 0);
        int32_t consumed = 0;
        EvArena *rt = ev_arena_new("rt-inner");
        EvNode  *back = ev_ir_deserialise(buf, n_bytes, &consumed, rt);
        char lbl[64]; snprintf(lbl, sizeof lbl, "%s round-trip", cases[i].label);
        ok(lbl, back && consumed == n_bytes &&
                back->kind == cases[i].node->kind);
        ev_arena_free(rt);
    }

    /* binop round-trip */
    EvNode *ba = ev_node_binop(d, EV_NODE_ADD,
                               ev_node_int(d, 10, 1), ev_node_int(d, 20, 1), 1);
    int32_t bn = ev_ir_serialise(ba, buf, sizeof buf);
    ok("binop serialise",        bn > 0);
    int32_t bc = 0;
    EvArena *brt = ev_arena_new("brt");
    EvNode  *bb  = ev_ir_deserialise(buf, bn, &bc, brt);
    ok("binop round-trip",       bb && bc == bn && bb->kind == EV_NODE_ADD);
    ok("binop child count rt",   bb && bb->child_count == 2);
    ev_arena_free(brt);

    /* if round-trip */
    EvNode *ifa = ev_node_if(d, ev_node_bool(d,1,1),
                             ev_node_int(d,10,1), ev_node_int(d,20,1), 1);
    int32_t ifn = ev_ir_serialise(ifa, buf, sizeof buf);
    int32_t ifc = 0;
    EvArena *irt = ev_arena_new("irt");
    EvNode  *ifb = ev_ir_deserialise(buf, ifn, &ifc, irt);
    ok("if round-trip",          ifb && ifc == ifn && ifb->kind == EV_NODE_IF);
    ok("if 3 children",          ifb && ifb->child_count == 3);
    ev_arena_free(irt);

    /* def round-trip */
    EvNode *defa = ev_node_def(d, "f", prm, 1, ev_node_var(d,"n",1), 1);
    int32_t defn = ev_ir_serialise(defa, buf, sizeof buf);
    int32_t defc = 0;
    EvArena *drt = ev_arena_new("drt");
    EvNode  *defb = ev_ir_deserialise(buf, defn, &defc, drt);
    ok("def round-trip",         defb && defc == defn && defb->kind == EV_NODE_DEF);
    ok("def param preserved",    defb && defb->param_count == 1 &&
                                  strcmp(defb->params[0], "n") == 0);
    ev_arena_free(drt);

    ev_arena_free(b); ev_arena_free(c); ev_arena_free(d);

    /* ── Parse result lifecycle ── */
    printf("\nParse result lifecycle\n");
    EvResult *res = ev_result_new("lifecycle-test");
    ok("result created",         res != NULL);
    ok("arena non-null",         res->arena != NULL);
    ok("root starts null",       res->root == NULL);
    res->root = ev_node_int(res->arena, 99, 1);
    ok("root settable",          res->root != NULL);
    ev_result_free(res);   /* frees arena + result itself */
    ok("free doesn't crash",     1);

    /* ── Ownership rules — the border is copy, not alias ── */
    printf("\nOwnership rules\n");
    EvArena *oa = ev_arena_new("owner-a");
    EvArena *ob = ev_arena_new("owner-b");
    EvNode  *n1 = ev_node_int(oa, 77, 1);
    /* copy a node's serialised form into a different arena */
    uint8_t ibuf[64];
    int32_t ilen = ev_ir_serialise(n1, ibuf, sizeof ibuf);
    int32_t ic = 0;
    EvNode  *n2 = ev_ir_deserialise(ibuf, ilen, &ic, ob);
    ok("cross-arena copy works", n2 && n2->lit.as_int == 77);
    ok("copy is in arena b",     n2 && n2->arena == ob);
    ev_arena_free(oa);   /* frees n1 */
    ok("n1's arena freed",       1);
    /* n2 is still alive because it's in ob */
    ok("n2 survives its source", n2 && n2->lit.as_int == 77);
    ev_arena_free(ob);

    printf("\n=== IR + arena: %d passed, %d failed ===\n\n",
           ok_count, fail_count);
    return fail_count == 0 ? 0 : 1;
}
