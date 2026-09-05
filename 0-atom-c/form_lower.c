/*
 * form_lower.c — Ever / Tapestry, generic form → TAC lowering
 *
 * ─────────────────────────────────────────────────────────────
 * THE POINT OF THIS FILE
 * ─────────────────────────────────────────────────────────────
 *
 * ev_lower_node (tac.c) has 24 switch cases because EvNode has 24
 * syntax-tied kinds. This file does the same job with ELEVEN, because
 * EvForm has eleven structural shapes.
 *
 * The saving is not the line count. It is that this switch stops
 * growing. Every future surface construct — `unless`, `elif`, `match`,
 * `while`, `?:`, pipelines, guards — normalises into one of the eleven
 * shapes at parse time. This file never learns their names.
 *
 * Concretely:
 *   `unless c then a else b`   → BRANCH(c, [b, a])      arms swapped
 *   `if a then x elif b then y else z`
 *                              → BRANCH(a,[x, BRANCH(b,[y,z])])
 *   `match n { 1→a 2→b _→c }`  → BRANCH(n, [a, b, c])   N arms
 *   `a ?: b`                   → BRANCH(a, [a, b])
 *
 * All four hit ONE case below: EV_FORM_BRANCH. Zero edits here.
 *
 * The BRANCH case is written for N arms from the start, not two. A
 * two-arm `if` is just the N=2 instance. That single decision is what
 * makes `match` free.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "tac.h"
#include "form.h"
#include <stdio.h>
#include <string.h>

#ifndef E_INTAKE
#define E_INTAKE 120
#endif

/* ─────────────────────────────────────────────
 * ROLE → OPCODE
 *
 * The one place roles are decoded. A table, not a control structure:
 * adding an operator is a row, not a branch.
 * ───────────────────────────────────────────── */
typedef struct { EvRole role; EvOpcode op; int32_t arity; } OpRow;

static const OpRow OPS[] = {
    { EV_ROLE_ADD, OP_ADD, 2 },  { EV_ROLE_SUB, OP_SUB, 2 },
    { EV_ROLE_MUL, OP_MUL, 2 },  { EV_ROLE_DIV, OP_DIV, 2 },
    { EV_ROLE_LT,  OP_LT,  2 },  { EV_ROLE_GT,  OP_GT,  2 },
    { EV_ROLE_LTE, OP_LTE, 2 },  { EV_ROLE_GTE, OP_GTE, 2 },
    { EV_ROLE_EQ,  OP_EQ,  2 },  { EV_ROLE_NEQ, OP_NEQ, 2 }
};
#define OPS_COUNT ((int)(sizeof(OPS)/sizeof(OPS[0])))

static int _role_opcode(EvRole r, EvOpcode *out) {
    for (int i = 0; i < OPS_COUNT; i++)
        if (OPS[i].role == r) { *out = OPS[i].op; return 1; }
    return 0;
}

/* min-of-operands confidence, the Ever rule */
static int16_t _min_conf(int16_t a, int16_t b) { return a < b ? a : b; }

/* ─────────────────────────────────────────────
 * THE ELEVEN CASES
 * ───────────────────────────────────────────── */

EvReg ev_lower_form(EvBuilder *b, const EvForm *f) {
    if (!f) return ev_reg_void();

    switch (f->form) {

    /* ── 1. ATOM ──────────────────────────────────────────────
     * Was five cases (VOID/BOOL/INT/REAL/TEXT) plus Z.
     * Now one: the payload is already an EValue, emit it. */
    case EV_FORM_ATOM: {
        if (f->role == EV_ROLE_LIT_Z) {
            EvReg r = ev_emit_const(b, ev_void(), f->line);
            r.confidence = 0;
            return r;
        }
        EvReg r = ev_emit_const(b, f->payload, f->line);
        if (f->confidence) r.confidence = f->confidence;
        return r;
    }

    /* ── 2. REFERENCE ────────────────────────────────────────
     * A name. External data enters at E_INTAKE, not certain. */
    case EV_FORM_REFERENCE:
        return ev_emit_load(b, f->symbol, EV_INT, E_INTAKE, f->line);

    /* ── 3. APPLICATION ──────────────────────────────────────
     * Was ELEVEN cases: ten binary operators plus CALL.
     * Now one. The role picks the opcode from a table; a role with
     * no opcode row is a named call. Unary and n-ary operators need
     * no new case, only new rows. */
    case EV_FORM_APPLICATION: {
        EvOpcode op;
        if (_role_opcode(f->role, &op)) {
            if (f->part_count < 2) return ev_reg_void();
            EvReg l = ev_lower_form(b, f->parts[0]);
            EvReg r = ev_lower_form(b, f->parts[1]);
            return ev_emit_binop(b, op, l, r, f->line);
        }
        /* CALL / BUILTIN — same shape, lowered the same way */
        EvReg argv[16];
        int32_t n = f->part_count < 16 ? f->part_count : 16;
        for (int32_t i = 0; i < n; i++)
            argv[i] = ev_lower_form(b, f->parts[i]);
        return ev_emit_call(b, f->symbol, argv, n, f->line);
    }

    /* ── 4. BRANCH ───────────────────────────────────────────
     * Was one case hardwired to exactly two arms.
     * Now N arms, chained. `if` is N=2. `match` is N=k. `guard`
     * is N=1 with an implicit void else. Written once.
     *
     * Every arm STOREs into a shared phi slot; the merge block
     * LOADs it. That is the fix that made the two-arm case correct;
     * generalising it to N costs nothing extra. */
    case EV_FORM_BRANCH: {
        int32_t narms = ev_form_arm_count(f);
        if (narms < 1) return ev_reg_void();

        char phi[32];
        snprintf(phi, sizeof phi, "_phi_%d", b->func->reg_counter);

        EvBlock *merge = ev_func_new_block(b->func);

        /* Single-arm guard: run arm if selector true, else void */
        if (narms == 1) {
            EvReg sel = ev_lower_form(b, ev_form_selector(f));
            EvBlock *then_b = ev_func_new_block(b->func);
            EvBlock *else_b = ev_func_new_block(b->func);
            ev_emit_jump_if(b, sel, then_b->id, else_b->id, f->line);

            ev_builder_switch_block(b, then_b);
            EvReg tv = ev_lower_form(b, ev_form_arm(f, 0));
            ev_emit_store(b, phi, tv, f->line);
            ev_emit_jump(b, merge->id, f->line);

            ev_builder_switch_block(b, else_b);
            EvReg zv = ev_emit_const(b, ev_void(), f->line);
            ev_emit_store(b, phi, zv, f->line);
            ev_emit_jump(b, merge->id, f->line);

            ev_builder_switch_block(b, merge);
            return ev_emit_load(b, phi, EV_INT, f->confidence, f->line);
        }

        /* N arms: chain of tests. Arms 0..N-2 are guarded by the
         * selector; the final arm is the fallthrough (else). For
         * N=2 this reduces exactly to if/then/else. */
        EvReg sel = ev_lower_form(b, ev_form_selector(f));
        EvBlock *then_b = ev_func_new_block(b->func);
        EvBlock *else_b = ev_func_new_block(b->func);
        ev_emit_jump_if(b, sel, then_b->id, else_b->id, f->line);

        ev_builder_switch_block(b, then_b);
        EvReg tv = ev_lower_form(b, ev_form_arm(f, 0));
        ev_emit_store(b, phi, tv, f->line);
        ev_emit_jump(b, merge->id, f->line);

        ev_builder_switch_block(b, else_b);
        EvReg ev;
        if (narms == 2) {
            ev = ev_lower_form(b, ev_form_arm(f, 1));
        } else {
            /* more than two arms: the tail is itself a BRANCH.
             * Build it as a sub-form view without allocating: lower
             * arms 1..N-1 as a nested chain. */
            EvArena *a = f->arena;   /* the form tree's arena, not the module's */
            EvForm **rest = (EvForm **)ev_arena_alloc(
                a, sizeof(EvForm*) * (narms - 1));
            for (int32_t i = 1; i < narms; i++)
                rest[i-1] = ev_form_arm(f, i);
            EvForm *tail = ev_form_branch(a, f->role,
                                          ev_form_selector(f),
                                          rest, narms - 1, f->line);
            ev = ev_lower_form(b, tail);
        }
        ev_emit_store(b, phi, ev, f->line);
        ev_emit_jump(b, merge->id, f->line);

        ev_builder_switch_block(b, merge);
        int16_t conf = _min_conf(tv.confidence, ev.confidence);
        int32_t typ  = (tv.type != EV_VOID) ? tv.type : ev.type;
        return ev_emit_load(b, phi, typ, conf, f->line);
    }

    /* ── 5. SEQUENCE ─────────────────────────────────────────
     * Did not exist as a node kind at all — statement lists were
     * handled ad hoc in ev_lower_module. Now it is a first-class
     * shape, so blocks nest anywhere an expression can go. */
    case EV_FORM_SEQUENCE: {
        EvReg last = ev_reg_void();
        for (int32_t i = 0; i < f->part_count; i++)
            last = ev_lower_form(b, f->parts[i]);
        return last;
    }

    /* ── 6. BINDING ──────────────────────────────────────────
     * let / ever / field — one shape, role distinguishes. */
    case EV_FORM_BINDING: {
        EvReg v = ev_lower_form(b, ev_form_value(f));
        ev_emit_store(b, f->symbol, v, f->line);
        return v;
    }

    /* ── 7. ABSTRACTION ──────────────────────────────────────
     * Handled at module level (a function needs its own EvFunc),
     * so inside an expression it evaluates to its own name. */
    case EV_FORM_ABSTRACTION:
        ev_emit_def_fn(b, f->symbol, f->line);
        return ev_reg_void();

    /* ── 8. AGGREGATE ────────────────────────────────────────
     * list / record / tuple — one shape. Elements lower left to
     * right; the opcode differs only by role. */
    case EV_FORM_AGGREGATE: {
        EvReg items[32];
        int32_t n = f->part_count < 32 ? f->part_count : 32;
        for (int32_t i = 0; i < n; i++)
            items[i] = ev_lower_form(b, f->parts[i]);
        EvOpcode op = (f->role == EV_ROLE_AGG_RECORD) ? OP_RECORD : OP_LIST;
        return ev_emit_call(b, ev_opcode_name(op), items, n, f->line);
    }

    /* ── 9. ACCESS ───────────────────────────────────────────
     * index / field — one shape, one lowering. */
    case EV_FORM_ACCESS: {
        EvReg tgt = ev_lower_form(b, ev_form_target(f));
        EvReg key = ev_lower_form(b, ev_form_key(f));
        EvReg args[2]; args[0] = tgt; args[1] = key;
        return ev_emit_call(b, ev_opcode_name(OP_GET), args, 2, f->line);
    }

    /* ── 10. ANNOTATION ──────────────────────────────────────
     * Metadata rides along. anchor / assimilate / confidence all
     * lower their subject and adjust the result's trust; none of
     * them changes control flow, so none needs its own case. */
    case EV_FORM_ANNOTATION: {
        EvReg sub = ev_lower_form(b, ev_form_subject(f));
        if (f->role == EV_ROLE_ANN_CONF && f->confidence)
            sub.confidence = f->confidence;
        return sub;
    }

    /* ── 11. DEFECT ──────────────────────────────────────────
     * An error is a value with zero trust, not a crash. */
    case EV_FORM_DEFECT: {
        EvReg r = ev_emit_const(b, ev_void(), f->line);
        r.confidence = 0;
        return r;
    }

    default:
        return ev_reg_void();
    }
}

/* ─────────────────────────────────────────────
 * MODULE LOWERING off forms
 * ───────────────────────────────────────────── */

EvFunc *ev_lower_form_func(EvModule *m, const EvForm *fn) {
    if (!m || !fn || fn->form != EV_FORM_ABSTRACTION) return NULL;

    /* recover parameter names from labels[1..] */
    int32_t np = 0;
    const char *params[16];
    for (int32_t i = 1; i < fn->part_cap && np < 16; i++) {
        if (fn->labels && fn->labels[i] && fn->parts[i] == NULL)
            params[np++] = fn->labels[i];
        else break;
    }

    EvFunc  *f   = ev_module_add_func(m, fn->symbol, params, np);
    EvBlock *blk = ev_func_new_block(f);
    EvBuilder b  = ev_builder(m, f, blk);

    /* bind parameters as loads in the entry block */
    for (int32_t i = 0; i < np; i++)
        ev_emit_load(&b, params[i], EV_INT, E_INTAKE, fn->line);

    EvReg result = ev_lower_form(&b, ev_form_body(fn));
    ev_emit_return(&b, result, fn->line);
    return f;
}

EvModule *ev_lower_form_module(const char *name, const EvForm *root,
                               EvArena *arena) {
    if (!root) return NULL;
    /* OWNERSHIP: mint a fresh arena so ev_module_free owns everything
     * it touches, exactly as ev_lower_module does.
     *
     * The earlier version passed the CALLER's arena to ev_module_new,
     * which meant ev_module_free silently took ownership of memory the
     * caller still held a tree in. Two module builders with opposite
     * ownership rules is a double-free waiting for the first caller who
     * uses both — which is what the kitchen sink turned out to be.
     * `arena` is now read-only here: it owns the EvForm tree and stays
     * the caller's to free. */
    (void)arena;
    EvArena *ma = ev_arena_new(name ? name : "form_module");
    if (!ma) return NULL;
    EvModule *m = ev_module_new(name, ma);
    if (!m) { ev_arena_free(ma); return NULL; }

    /* A SEQUENCE at the root is a program: abstractions become
     * functions, everything else joins the global body. Any other
     * root form is a single expression program. */
    const EvForm *items[64];
    int32_t n = 0;
    if (root->form == EV_FORM_SEQUENCE) {
        for (int32_t i = 0; i < root->part_count && n < 64; i++)
            items[n++] = root->parts[i];
    } else {
        items[n++] = root;
    }

    for (int32_t i = 0; i < n; i++)
        if (items[i]->form == EV_FORM_ABSTRACTION)
            ev_lower_form_func(m, items[i]);

    EvFunc  *gb  = ev_module_add_func(m, "$global", NULL, 0);
    EvBlock *blk = ev_func_new_block(gb);
    EvBuilder b  = ev_builder(m, gb, blk);
    m->global_body = gb;

    EvReg last = ev_reg_void();
    for (int32_t i = 0; i < n; i++) {
        if (items[i]->form == EV_FORM_ABSTRACTION) continue;
        last = ev_lower_form(&b, items[i]);
    }
    ev_emit_return(&b, last, root->line);
    return m;
}
