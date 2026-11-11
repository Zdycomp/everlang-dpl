/*
 * cfg.c — Ever / Tapestry, Control Flow Graph implementation
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "cfg.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>

/* ─────────────────────────────────────────────
 * NameTable
 * ───────────────────────────────────────────── */

NameId name_intern(NameTable *t, const char *name) {
    if (!name) return -1;
    for (int i = 0; i < t->count; i++)
        if (strcmp(t->names[i], name) == 0) return (NameId)i;
    if (t->count >= CFG_MAX_NAMES) return -1;
    NameId id = (NameId)t->count++;
    strncpy(t->names[id], name, 63); t->names[id][63] = '\0';
    return id;
}

NameId name_find(const NameTable *t, const char *name) {
    if (!name) return -1;
    for (int i = 0; i < t->count; i++)
        if (strcmp(t->names[i], name) == 0) return (NameId)i;
    return -1;
}

const char *name_str(const NameTable *t, NameId id) {
    if (id < 0 || id >= t->count) return "?";
    return t->names[id];
}

/* ─────────────────────────────────────────────
 * DefinedSet — 256-bit bitset
 * ───────────────────────────────────────────── */

void defset_clear(DefinedSet *s) { memset(s->bits, 0, sizeof s->bits); }
void defset_fill (DefinedSet *s) { memset(s->bits, 0xFF, sizeof s->bits); }

void defset_add(DefinedSet *s, NameId id) {
    if (id < 0 || id >= 256) return;
    s->bits[id >> 6] |= (uint64_t)1 << (id & 63);
}

void defset_remove(DefinedSet *s, NameId id) {
    if (id < 0 || id >= 256) return;
    s->bits[id >> 6] &= ~((uint64_t)1 << (id & 63));
}

int defset_has(const DefinedSet *s, NameId id) {
    if (id < 0 || id >= 256) return 0;
    return (s->bits[id >> 6] >> (id & 63)) & 1;
}

void defset_intersect(DefinedSet *dst, const DefinedSet *src) {
    for (int i = 0; i < DEFSET_WORDS; i++) dst->bits[i] &= src->bits[i];
}

void defset_union(DefinedSet *dst, const DefinedSet *src) {
    for (int i = 0; i < DEFSET_WORDS; i++) dst->bits[i] |= src->bits[i];
}

int defset_equal(const DefinedSet *a, const DefinedSet *b) {
    for (int i = 0; i < DEFSET_WORDS; i++)
        if (a->bits[i] != b->bits[i]) return 0;
    return 1;
}

int defset_subset(const DefinedSet *sub, const DefinedSet *super) {
    for (int i = 0; i < DEFSET_WORDS; i++)
        if ((sub->bits[i] & super->bits[i]) != sub->bits[i]) return 0;
    return 1;
}

/* ─────────────────────────────────────────────
 * Cfg and CfgBlock allocation
 * ───────────────────────────────────────────── */

Cfg *cfg_new(EvArena *arena, const char *fn_name) {
    Cfg *g = (Cfg*)ev_arena_alloc(arena, sizeof *g);
    if (!g) return NULL;
    g->arena       = arena;
    g->block_count = 0;
    g->entry_id    = 0;
    g->exit_id     = -1;
    g->phi_count   = 0;
    g->error_count = 0;
    g->fn_name     = fn_name ? fn_name : "?";
    g->param_count = 0;
    memset(&g->names, 0, sizeof g->names);
    return g;
}

CfgBlock *cfg_block_new(Cfg *cfg, const char *label) {
    if (!cfg || cfg->block_count >= CFG_MAX_BLOCKS) return NULL;
    CfgBlock *b = (CfgBlock*)ev_arena_alloc(cfg->arena, sizeof *b);
    if (!b) return NULL;
    b->id          = cfg->block_count;
    b->label       = label ? label : "block";
    b->node_count  = 0;
    b->term        = CFG_TERM_JUMP;
    b->cond_node   = NULL;
    b->ret_node    = NULL;
    b->succ_count  = 0;
    b->pred_count  = 0;
    b->phi_count   = 0;
    defset_clear(&b->def_gen);
    defset_clear(&b->def_kill);
    defset_clear(&b->def_in);
    defset_fill (&b->def_out);   /* initialise to ALL for intersection */
    defset_clear(&b->use);
    defset_clear(&b->live_in);
    defset_clear(&b->live_out);
    cfg->blocks[cfg->block_count++] = b;
    return b;
}

void cfg_connect(Cfg *cfg, int32_t from_id, int32_t to_id) {
    if (!cfg) return;
    CfgBlock *from = cfg->blocks[from_id];
    CfgBlock *to   = cfg->blocks[to_id];
    if (!from || !to) return;
    if (from->succ_count < CFG_BLOCK_SUCCS_MAX)
        from->succ[from->succ_count++] = to_id;
    if (to->pred_count < CFG_BLOCK_PREDS_MAX)
        to->pred[to->pred_count++] = from_id;
}

/* ─────────────────────────────────────────────
 * CFG Builder — walks EvNode tree, emits blocks
 *
 * For an expression language like Ever, every expression produces a
 * value. The "program" of a function body is:
 *
 *   ENTRY → eval body expression → RETURN value
 *
 * If the body contains an if/then/else, it splits into:
 *
 *   COND-EVAL → TRUE-BRANCH → JOIN
 *            ↘ FALSE-BRANCH ↗
 *
 * The BUILD functions return the block ID that holds the expression's
 * result. For simple expressions this is the current block; for
 * if/then/else it is the JOIN block.
 * ───────────────────────────────────────────── */

typedef struct {
    Cfg     *cfg;
    EvArena *arena;
    int32_t  block_serial;  /* for unique block labels */
} Builder;

static char *blabel(Builder *b, const char *prefix, EvArena *a) {
    char buf[64];
    snprintf(buf, sizeof buf, "%s_%d", prefix, b->block_serial++);
    return ev_arena_strdup(a, buf);
}

/* Forward declaration */
static int32_t build_expr(Builder *b, EvNode *n, int32_t cur_block_id);

/* Scan an expression for variable definitions (assignments).
   In Ever, params are the only definitions — the language is pure.
   But we also track let-bindings added by the interpreter layer.
   For now: a DEF node defines its name; a VAR node uses a name. */
static void scan_defs(Builder *b, EvNode *n, int32_t block_id) __attribute__((unused));
static void scan_defs(Builder *b, EvNode *n, int32_t block_id) {
    if (!n) return;
    CfgBlock *blk = b->cfg->blocks[block_id];
    if (n->kind == EV_NODE_DEF) {
        /* function definition: record params as defined in entry */
        for (int i = 0; i < n->param_count; i++) {
            NameId id = name_intern(&b->cfg->names, n->params[i]);
            defset_add(&blk->def_gen, id);
            defset_add(&blk->use, id);
        }
    }
}

static void record_use(Builder *b, EvNode *n, int32_t block_id) {
    if (!n || n->kind != EV_NODE_VAR) return;
    if (!n->str) return;
    CfgBlock *blk = b->cfg->blocks[block_id];
    NameId id = name_intern(&b->cfg->names, n->str);
    /* a use is live-in if not already defined in this block */
    if (!defset_has(&blk->def_gen, id))
        defset_add(&blk->use, id);
}

static void record_def(Builder *b, const char *name, int32_t block_id) {
    if (!name) return;
    CfgBlock *blk = b->cfg->blocks[block_id];
    NameId id = name_intern(&b->cfg->names, name);
    defset_add(&blk->def_gen, id);
}

/* Build a node, possibly creating new blocks.
   Returns the block id that is "current" after building. */
static int32_t build_expr(Builder *b, EvNode *n, int32_t cur) {
    if (!n) return cur;
    CfgBlock *blk = b->cfg->blocks[cur];
    if (!blk) return cur;

    switch ((EvNodeKind)n->kind) {

    case EV_NODE_INT:
    case EV_NODE_REAL:
    case EV_NODE_BOOL:
    case EV_NODE_TEXT:
    case EV_NODE_VOID:
        /* literals: no side effects, no uses */
        if (blk->node_count < CFG_BLOCK_NODES_MAX)
            blk->nodes[blk->node_count++] = n;
        return cur;

    case EV_NODE_VAR:
        record_use(b, n, cur);
        if (blk->node_count < CFG_BLOCK_NODES_MAX)
            blk->nodes[blk->node_count++] = n;
        return cur;

    case EV_NODE_ADD: case EV_NODE_SUB: case EV_NODE_MUL: case EV_NODE_DIV:
    case EV_NODE_LT:  case EV_NODE_GT:  case EV_NODE_LTE: case EV_NODE_GTE:
    case EV_NODE_EQ:  case EV_NODE_NEQ:
        /* binary op: evaluate both children in current block */
        cur = build_expr(b, n->child_count > 0 ? n->children[0] : NULL, cur);
        cur = build_expr(b, n->child_count > 1 ? n->children[1] : NULL, cur);
        if (blk->node_count < CFG_BLOCK_NODES_MAX)
            blk->nodes[blk->node_count++] = n;
        return cur;

    case EV_NODE_CALL:
        /* evaluate args, then call */
        for (int i = 0; i < n->child_count; i++)
            cur = build_expr(b, n->children[i], cur);
        /* the function name is a use */
        if (n->str) {
            NameId id = name_intern(&b->cfg->names, n->str);
            CfgBlock *cb = b->cfg->blocks[cur];
            if (cb && !defset_has(&cb->def_gen, id))
                defset_add(&cb->use, id);
        }
        if (blk->node_count < CFG_BLOCK_NODES_MAX)
            blk->nodes[blk->node_count++] = n;
        return cur;

    case EV_NODE_IF: {
        /*
         * if-then-else splits into four blocks:
         *
         *   [cond_block]     ← evaluates the condition
         *       ↙         ↘
         * [then_block]  [else_block]
         *       ↘         ↙
         *     [join_block]
         *
         * The DefinedSet at join = intersection of then-out and else-out.
         * Any name defined in only one branch is NOT in join.defined.
         */
        if (n->child_count < 3) return cur;   /* malformed */

        EvNode *cond_n = n->children[0];
        EvNode *then_n = n->children[1];
        EvNode *else_n = n->children[2];

        /* evaluate condition in current block */
        cur = build_expr(b, cond_n, cur);
        CfgBlock *cond_blk = b->cfg->blocks[cur];
        cond_blk->term     = CFG_TERM_BRANCH;
        cond_blk->cond_node = cond_n;

        /* then block */
        CfgBlock *then_blk = cfg_block_new(b->cfg, blabel(b, "then", b->arena));
        int32_t then_id = then_blk->id;
        cfg_connect(b->cfg, cur, then_id);

        /* else block */
        CfgBlock *else_blk = cfg_block_new(b->cfg, blabel(b, "else", b->arena));
        int32_t else_id = else_blk->id;
        cfg_connect(b->cfg, cur, else_id);

        /* build both branches */
        int32_t then_end = build_expr(b, then_n, then_id);
        int32_t else_end = build_expr(b, else_n, else_id);

        /* join block */
        CfgBlock *join_blk = cfg_block_new(b->cfg, blabel(b, "join", b->arena));
        int32_t join_id = join_blk->id;

        /* set terminators */
        CfgBlock *te = b->cfg->blocks[then_end];
        CfgBlock *ee = b->cfg->blocks[else_end];
        te->term = CFG_TERM_JUMP;
        ee->term = CFG_TERM_JUMP;
        cfg_connect(b->cfg, then_end, join_id);
        cfg_connect(b->cfg, else_end, join_id);

        /* the IF node itself lives at the join */
        join_blk->nodes[join_blk->node_count++] = n;
        return join_id;
    }

    case EV_NODE_DEF: {
        /* function definition: params are defined at entry */
        for (int i = 0; i < n->param_count; i++)
            record_def(b, n->params[i], cur);
        /* also record the function name itself as defined */
        record_def(b, n->str, cur);
        /* build the body */
        if (n->child_count > 0) {
            cur = build_expr(b, n->children[0], cur);
        }
        CfgBlock *rb = b->cfg->blocks[cur];
        rb->term = CFG_TERM_RETURN;
        rb->ret_node = n->child_count > 0 ? n->children[0] : NULL;
        b->cfg->exit_id = cur;
        return cur;
    }

    default:
        if (blk->node_count < CFG_BLOCK_NODES_MAX)
            blk->nodes[blk->node_count++] = n;
        return cur;
    }
}

Cfg *cfg_build(EvNode *fn_def, EvArena *arena) {
    if (!fn_def || !arena) return NULL;
    const char *fn_name = fn_def->str ? fn_def->str : "?";
    Cfg *g = cfg_new(arena, fn_name);
    if (!g) return NULL;

    /* entry block */
    CfgBlock *entry = cfg_block_new(g, "entry");
    g->entry_id = entry->id;

    Builder b = { .cfg = g, .arena = arena, .block_serial = 0 };
    build_expr(&b, fn_def, entry->id);
    g->param_count = fn_def->param_count;
    return g;
}

/* ─────────────────────────────────────────────
 * DATAFLOW: MUST-definition analysis (forward, intersection)
 *
 * Classic iterative dataflow for definite assignment:
 *
 *   def_out[B] = def_gen[B] ∪ (def_in[B] − def_kill[B])
 *   def_in[B]  = ⋂ { def_out[P] : P is a predecessor of B }
 *
 * The entry block's def_in is the parameter set.
 * All other blocks start with def_in = ALL (so intersection can begin).
 * ───────────────────────────────────────────── */

void cfg_analyse(Cfg *cfg) {
    if (!cfg || cfg->block_count == 0) return;

    /* initialise: entry def_in = params; others = ALL */
    for (int i = 0; i < cfg->block_count; i++) {
        CfgBlock *b = cfg->blocks[i];
        defset_fill(&b->def_out);   /* start high for intersection */
        defset_clear(&b->def_in);
    }
    /* entry: def_in is just what was in def_gen (params) */
    /* already set by build_expr via record_def */

    /* iterate until stable */
    int changed = 1;
    int iters = 0;
    while (changed && iters++ < CFG_MAX_BLOCKS) {
        changed = 0;
        for (int i = 0; i < cfg->block_count; i++) {
            CfgBlock *b = cfg->blocks[i];

            /* def_in[B] = ⋂ { def_out[P] } */
            DefinedSet new_in;
            if (b->pred_count == 0) {
                /* entry: def_in is the param defs */
                new_in = b->def_gen;
            } else {
                defset_fill(&new_in);
                for (int p = 0; p < b->pred_count; p++) {
                    CfgBlock *pred = cfg->blocks[b->pred[p]];
                    defset_intersect(&new_in, &pred->def_out);
                }
            }

            /* def_out[B] = def_gen[B] ∪ def_in[B] */
            DefinedSet new_out = new_in;
            defset_union(&new_out, &b->def_gen);

            if (!defset_equal(&b->def_in, &new_in) ||
                !defset_equal(&b->def_out, &new_out)) {
                b->def_in  = new_in;
                b->def_out = new_out;
                changed = 1;
            }
        }
    }
}

/* ─────────────────────────────────────────────
 * LIVENESS ANALYSIS (backward, union)
 *
 *   live_in[B]  = use[B] ∪ (live_out[B] − def_gen[B])
 *   live_out[B] = ⋃ { live_in[S] : S is a successor of B }
 * ───────────────────────────────────────────── */

void cfg_liveness(Cfg *cfg) {
    if (!cfg) return;
    int changed = 1, iters = 0;
    while (changed && iters++ < CFG_MAX_BLOCKS) {
        changed = 0;
        /* iterate backward */
        for (int i = cfg->block_count - 1; i >= 0; i--) {
            CfgBlock *b = cfg->blocks[i];

            /* live_out = union of successors' live_in */
            DefinedSet new_out; defset_clear(&new_out);
            for (int s = 0; s < b->succ_count; s++) {
                CfgBlock *succ = cfg->blocks[b->succ[s]];
                defset_union(&new_out, &succ->live_in);
            }

            /* live_in = use ∪ (live_out − def_gen) */
            DefinedSet new_in = new_out;
            for (int n = 0; n < cfg->names.count; n++) {
                if (defset_has(&b->def_gen, (NameId)n))
                    defset_remove(&new_in, (NameId)n);
            }
            defset_union(&new_in, &b->use);

            if (!defset_equal(&b->live_in, &new_in) ||
                !defset_equal(&b->live_out, &new_out)) {
                b->live_in  = new_in;
                b->live_out = new_out;
                changed = 1;
            }
        }
    }
}

/* ─────────────────────────────────────────────
 * PHI INSERTION
 *
 * At every join point (pred_count == 2): for each name that is defined
 * differently on the two incoming paths (i.e. it is in one def_out but
 * not both), insert a phi node so the join block can unify them.
 * ───────────────────────────────────────────── */

void cfg_insert_phis(Cfg *cfg) {
    if (!cfg) return;
    for (int i = 0; i < cfg->block_count; i++) {
        CfgBlock *b = cfg->blocks[i];
        if (b->pred_count < 2) continue;   /* only join points need phis */

        CfgBlock *p0 = cfg->blocks[b->pred[0]];
        CfgBlock *p1 = cfg->blocks[b->pred[1]];

        for (int n = 0; n < cfg->names.count; n++) {
            int in_p0 = defset_has(&p0->def_out, (NameId)n);
            int in_p1 = defset_has(&p1->def_out, (NameId)n);

            /* only need a phi if definition differs on paths */
            if (in_p0 == in_p1) continue;

            if (b->phi_count >= CFG_BLOCK_PHIS_MAX) break;
            if (cfg->phi_count >= CFG_MAX_PHIS) break;

            PhiNode *phi = (PhiNode*)ev_arena_alloc(
                cfg->arena, sizeof *phi);
            phi->name         = (NameId)n;
            phi->src_block[0] = b->pred[0];
            phi->src_block[1] = b->pred[1];
            phi->dest_block   = b->id;

            b->phis[b->phi_count++] = *phi;
            cfg->phis[cfg->phi_count++] = phi;

            /* a phi makes the name defined at the join point
               regardless of which path — if both paths define it */
            if (in_p0 && in_p1)
                defset_add(&b->def_gen, (NameId)n);
        }
    }
}

/* ─────────────────────────────────────────────
 * DEFINITE ASSIGNMENT CHECK
 *
 * After cfg_analyse(), every block has def_in: the set of names
 * guaranteed to be defined before any instruction in that block runs.
 *
 * For each USE of a name in a block:
 *   if the name is NOT in def_in AND NOT in def_gen of a preceding
 *   instruction in this block, it is an error.
 * ───────────────────────────────────────────── */

static void add_error(Cfg *cfg, CfgErrKind kind, NameId name,
                      int32_t block_id, int32_t line, const char *fmt, ...) {
    if (cfg->error_count >= CFG_MAX_ERRORS) return;
    DefError *e = &cfg->errors[cfg->error_count++];
    e->kind     = kind;
    e->name     = name;
    e->block_id = block_id;
    e->line     = line;
    if (fmt) {
        va_list ap; va_start(ap, fmt);
        vsnprintf(e->message, sizeof e->message, fmt, ap);
        va_end(ap);
    }
}


/* check a single expression node for undefined uses */
static void check_node_uses(Cfg *cfg, EvNode *n,
                             DefinedSet *available, int32_t block_id) {
    if (!n) return;
    if (n->kind == EV_NODE_VAR && n->str) {
        NameId id = name_find(&cfg->names, n->str);
        if (id >= 0 && !defset_has(available, id)) {
            add_error(cfg, CFG_ERR_USE_BEFORE_DEF, id, block_id,
                      n->line,
                      "name '%s' used before it is defined on all paths",
                      n->str);
        }
        return;
    }
    for (int i = 0; i < n->child_count; i++)
        check_node_uses(cfg, n->children[i], available, block_id);
}

int cfg_check_definite_assignment(Cfg *cfg) {
    if (!cfg) return 0;
    cfg->error_count = 0;

    for (int i = 0; i < cfg->block_count; i++) {
        CfgBlock *b = cfg->blocks[i];

        /* the available set starts as def_in and grows as we encounter defs */
        DefinedSet avail = b->def_in;

        /* phis at the head of this block add definitions */
        for (int p = 0; p < b->phi_count; p++)
            defset_add(&avail, b->phis[p].name);

        /* check each instruction */
        for (int n = 0; n < b->node_count; n++) {
            EvNode *node = b->nodes[n];
            check_node_uses(cfg, node, &avail, b->id);
        }

        /* check the branch condition if any */
        if (b->term == CFG_TERM_BRANCH && b->cond_node)
            check_node_uses(cfg, b->cond_node, &avail, b->id);
    }

    /* Additional check: names partially defined (phi exists, but
       not in all join predecessors). Already caught by check_node_uses
       because def_in at the join block won't include them.
       But we also report it explicitly for clarity. */
    for (int i = 0; i < cfg->block_count; i++) {
        CfgBlock *b = cfg->blocks[i];
        if (b->pred_count < 2) continue;
        CfgBlock *p0 = cfg->blocks[b->pred[0]];
        CfgBlock *p1 = cfg->blocks[b->pred[1]];
        for (int n = 0; n < cfg->names.count; n++) {
            int in0 = defset_has(&p0->def_out, (NameId)n);
            int in1 = defset_has(&p1->def_out, (NameId)n);
            if (in0 == in1) continue;
            /* defined on one path only — check if it is live after the join */
            if (defset_has(&b->live_out, (NameId)n)) {
                add_error(cfg, CFG_ERR_PARTIAL_DEF, (NameId)n, i,
                          0,
                          "name '%s' defined on only one branch "
                          "but used after the join — use after if "
                          "requires definition in both branches",
                          cfg->names.names[n]);
            }
        }
    }

    return cfg->error_count;
}

/* ─────────────────────────────────────────────
 * Diagnostics
 * ───────────────────────────────────────────── */

static void print_defset(const DefinedSet *s, const NameTable *t) {
    int first = 1;
    for (int i = 0; i < t->count; i++) {
        if (defset_has(s, (NameId)i)) {
            if (!first) printf(", ");
            printf("%s", t->names[i]);
            first = 0;
        }
    }
    if (first) printf("∅");
}

void cfg_dump(const Cfg *cfg, const char *title) {
    if (!cfg) return;
    printf("\n══ CFG: %s (%s) ══\n", title ? title : "", cfg->fn_name);
    for (int i = 0; i < cfg->block_count; i++) {
        CfgBlock *b = cfg->blocks[i];
        printf("  [%d:%s]\n", b->id, b->label);
        printf("    def_in:  "); print_defset(&b->def_in,  &cfg->names); printf("\n");
        printf("    def_gen: "); print_defset(&b->def_gen, &cfg->names); printf("\n");
        printf("    def_out: "); print_defset(&b->def_out, &cfg->names); printf("\n");
        printf("    live_in: "); print_defset(&b->live_in, &cfg->names); printf("\n");
        if (b->phi_count > 0) {
            printf("    phis:    ");
            for (int p = 0; p < b->phi_count; p++) {
                printf("φ(%s from [%d],[%d])  ",
                       cfg->names.names[b->phis[p].name],
                       b->phis[p].src_block[0],
                       b->phis[p].src_block[1]);
            }
            printf("\n");
        }
        if (b->node_count > 0) {
            printf("    nodes:   ");
            for (int n = 0; n < b->node_count; n++)
                printf("%s ", ev_node_kind_name((EvNodeKind)b->nodes[n]->kind));
            printf("\n");
        }
        printf("    term:    ");
        switch (b->term) {
            case CFG_TERM_JUMP:   printf("jump → [%d]", b->succ_count>0?b->succ[0]:-1); break;
            case CFG_TERM_BRANCH: printf("branch true→[%d] false→[%d]",
                                         b->succ_count>0?b->succ[0]:-1,
                                         b->succ_count>1?b->succ[1]:-1); break;
            case CFG_TERM_RETURN: printf("return"); break;
        }
        printf("\n");
    }
    printf("\n");
}

void cfg_print_errors(const Cfg *cfg) {
    if (!cfg) return;
    if (cfg->error_count == 0) {
        printf("  ✓ %s: no definite-assignment errors\n", cfg->fn_name);
        return;
    }
    printf("  ✗ %s: %d error(s)\n", cfg->fn_name, cfg->error_count);
    for (int i = 0; i < cfg->error_count; i++) {
        const DefError *e = &cfg->errors[i];
        const char *kind_str =
            e->kind == CFG_ERR_USE_BEFORE_DEF   ? "use-before-def"   :
            e->kind == CFG_ERR_PARTIAL_DEF       ? "partial-def"      :
            e->kind == CFG_ERR_UNDEF_AFTER_JOIN  ? "undef-after-join" :
            "error";
        printf("    [%s] line %d block %d: %s\n",
               kind_str, e->line, e->block_id, e->message);
    }
}
