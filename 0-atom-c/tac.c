/*
 * tac.c — Ever / Tapestry, Three-Address IR implementation
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "tac.h"
#include "repair.h"
#ifndef E_INTAKE
#define E_INTAKE 120  /* external data enters at 120/256 */
#endif
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

EvRepairRegistry *g_repair_registry = NULL;

/* ─────────────────────────────────────────────
 * OPCODE METADATA
 * ───────────────────────────────────────────── */

const char *ev_opcode_name(EvOpcode op) {
    switch (op) {
        case OP_CONST:   return "CONST";
        case OP_COPY:    return "COPY";
        case OP_ADD:     return "ADD";
        case OP_SUB:     return "SUB";
        case OP_MUL:     return "MUL";
        case OP_DIV:     return "DIV";
        case OP_NEG:     return "NEG";
        case OP_LT:      return "LT";
        case OP_GT:      return "GT";
        case OP_LTE:     return "LTE";
        case OP_GTE:     return "GTE";
        case OP_EQ:      return "EQ";
        case OP_NEQ:     return "NEQ";
        case OP_LABEL:   return "LABEL";
        case OP_JUMP:    return "JUMP";
        case OP_JUMP_IF: return "JUMP_IF";
        case OP_RETURN:  return "RETURN";
        case OP_CALL:    return "CALL";
        case OP_ARG:     return "ARG";
        case OP_CONF:    return "CONF";
        case OP_TRUST:   return "TRUST";
        case OP_LOAD:    return "LOAD";
        case OP_STORE:   return "STORE";
        case OP_DEF_FN:  return "DEF_FN";
        case OP_LIST:    return "LIST";
        case OP_RECORD:  return "RECORD";
        case OP_GET:     return "GET";
        case OP_SET:     return "SET";
        case OP_NOP:     return "NOP";
        case OP_HEAL:    return "HEAL";
        case OP_RECOVERY:   return "RECOVERY";
        case OP_REPAIR_STATE: return "REPAIR_STATE";
        case OP_CAUSE_OPEN:  return "CAUSE_OPEN";
        case OP_CAUSE_CLOSE: return "CAUSE_CLOSE";
        case OP_NOTE:        return "NOTE";
        case OP_SETTLE:      return "SETTLE";
        case OP_ERR:     return "ERR";
        default:         return "?";
    }
}

int ev_opcode_is_binary(EvOpcode op) {
    return op >= OP_ADD && op <= OP_DIV;
}
int ev_opcode_is_cmp(EvOpcode op) {
    return op >= OP_LT && op <= OP_NEQ;
}
int ev_opcode_is_branch(EvOpcode op) {
    return op == OP_JUMP || op == OP_JUMP_IF || op == OP_RETURN;
}

/* ─────────────────────────────────────────────
 * VIRTUAL REGISTERS
 * ───────────────────────────────────────────── */

EvReg ev_reg_void(void) {
    EvReg r = {0}; r.id = EV_REG_VOID; r.type = EV_VOID;
    r.confidence = 0; return r;
}
EvReg ev_reg_temp(int32_t id, int32_t type, int16_t conf) {
    EvReg r = {0}; r.id = id; r.type = type;
    r.confidence = conf; return r;
}
EvReg ev_reg_named(int32_t id, const char *name,
                   int32_t type, int16_t conf, EvArena *a) {
    EvReg r = ev_reg_temp(id, type, conf);
    r.name = ev_arena_strdup(a, name);
    return r;
}
int ev_reg_is_void(EvReg r) { return r.id == EV_REG_VOID; }

/* ─────────────────────────────────────────────
 * BLOCK
 * ───────────────────────────────────────────── */

static EvBlock *block_new(EvArena *arena, int32_t id) {
    EvBlock *b = (EvBlock*)ev_arena_alloc(arena, sizeof *b);
    if (!b) return NULL;
    b->id     = id;
    b->cap    = 8;
    b->len    = 0;
    b->nsucc  = 0;
    b->succ[0] = b->succ[1] = -1;
    b->instrs = (EvInstr*)ev_arena_alloc(arena, b->cap * sizeof(EvInstr));
    if (!b->instrs) return NULL;
    return b;
}

static EvInstr *block_append(EvBlock *blk, EvArena *arena) {
    if (!blk) return NULL;
    if (blk->len >= blk->cap) {
        int32_t newcap = blk->cap * 2;
        EvInstr *nb = (EvInstr*)ev_arena_alloc(arena,
                                               newcap * sizeof(EvInstr));
        if (!nb) return NULL;
        memcpy(nb, blk->instrs, blk->len * sizeof(EvInstr));
        blk->instrs = nb;
        blk->cap    = newcap;
    }
    EvInstr *ins = &blk->instrs[blk->len++];
    memset(ins, 0, sizeof *ins);
    ins->src0 = ev_reg_void();
    ins->src1 = ev_reg_void();
    ins->dest = ev_reg_void();
    ins->true_label    = -1;
    ins->false_label   = -1;
    ins->unknown_label = -1;
    return ins;
}

/* ─────────────────────────────────────────────
 * FUNCTION + MODULE LIFECYCLE
 * ───────────────────────────────────────────── */

static EvFunc *func_new(EvArena *arena, const char *name,
                        const char **params, int32_t np) {
    EvFunc *f = (EvFunc*)ev_arena_alloc(arena, sizeof *f);
    if (!f) return NULL;
    f->name        = ev_arena_strdup(arena, name);
    f->nparam      = np;
    f->reg_counter = EV_REG_FIRST;
    f->confidence  = E_CERTAIN;
    f->arena       = arena;
    f->block_cap   = 8;
    f->nblocks     = 0;
    f->blocks      = (EvBlock**)ev_arena_alloc(arena,
                                               f->block_cap * sizeof(EvBlock*));
    if (np > 0) {
        f->params = (const char**)ev_arena_alloc(arena, np * sizeof(char*));
        for (int32_t i = 0; i < np; i++)
            f->params[i] = ev_arena_strdup(arena, params[i]);
    }
    return f;
}

EvModule *ev_module_new(const char *name, EvArena *arena) {
    EvModule *m = (EvModule*)ev_arena_alloc(arena, sizeof *m);
    if (!m) return NULL;
    m->name       = ev_arena_strdup(arena, name);
    m->arena      = arena;
    m->func_cap   = 16;
    m->nfuncs     = 0;
    m->funcs      = (EvFunc**)ev_arena_alloc(arena,
                                             m->func_cap * sizeof(EvFunc*));
    m->global_body = func_new(arena, "$global", NULL, 0);
    return m;
}

void ev_module_free(EvModule *m) {
    if (m) ev_arena_free(m->arena);
}

EvFunc *ev_module_add_func(EvModule *m, const char *name,
                            const char **params, int32_t np) {
    if (!m) return NULL;
    if (m->nfuncs >= m->func_cap) {
        int32_t nc = m->func_cap * 2;
        EvFunc **nf = (EvFunc**)ev_arena_alloc(m->arena, nc * sizeof(EvFunc*));
        if (!nf) return NULL;
        memcpy(nf, m->funcs, m->nfuncs * sizeof(EvFunc*));
        m->funcs    = nf;
        m->func_cap = nc;
    }
    EvFunc *f = func_new(m->arena, name, params, np);
    if (!f) return NULL;
    m->funcs[m->nfuncs++] = f;
    return f;
}

EvBlock *ev_func_new_block(EvFunc *f) {
    if (!f) return NULL;
    if (f->nblocks >= f->block_cap) {
        int32_t nc = f->block_cap * 2;
        EvBlock **nb = (EvBlock**)ev_arena_alloc(f->arena,
                                                 nc * sizeof(EvBlock*));
        if (!nb) return NULL;
        memcpy(nb, f->blocks, f->nblocks * sizeof(EvBlock*));
        f->blocks    = nb;
        f->block_cap = nc;
    }
    EvBlock *b = block_new(f->arena, f->nblocks);
    if (!b) return NULL;
    f->blocks[f->nblocks++] = b;
    return b;
}

/* ─────────────────────────────────────────────
 * BUILDER
 * ───────────────────────────────────────────── */

EvBuilder ev_builder(EvModule *m, EvFunc *f, EvBlock *b) {
    EvBuilder bld = {0};
    bld.module = m; bld.func = f; bld.block = b;
    return bld;
}

void ev_builder_switch_block(EvBuilder *b, EvBlock *blk) {
    b->block = blk;
}

EvReg ev_next_reg(EvBuilder *b, int32_t type, int16_t conf) {
    return ev_reg_temp(b->func->reg_counter++, type, conf);
}

/* ── emit helpers ── */

void ev_lower_fail(EvBuilder *b, const char *msg) {
    if (b && b->module && !b->module->lower_error)
        b->module->lower_error = msg;
}

static EvInstr *_emit(EvBuilder *b, EvOpcode op, int32_t line) {
    EvInstr *ins = block_append(b->block, b->func->arena);
    if (!ins) {
        ev_lower_fail(b, "out of arena memory while lowering");
        return NULL;
    }
    ins->op   = op;
    ins->line = line;
    return ins;
}

EvReg ev_emit_const(EvBuilder *b, EValue lit, int32_t line) {
    int32_t typ = lit.tag;
    int16_t conf = E_CERTAIN;   /* program constants are certain */
    EvReg dest = ev_next_reg(b, typ, conf);
    EvInstr *ins = _emit(b, OP_CONST, line);
    if (!ins) return ev_reg_void();
    ins->dest    = dest;
    ins->literal = lit;
    return dest;
}

EvReg ev_emit_copy(EvBuilder *b, EvReg src, int32_t line) {
    EvReg dest = ev_next_reg(b, src.type, src.confidence);
    EvInstr *ins = _emit(b, OP_COPY, line);
    if (!ins) return ev_reg_void();
    ins->dest = dest; ins->src0 = src;
    return dest;
}

/* Confidence propagation rule for binary ops: MIN of operands */
static int16_t _binconf(EvReg a, EvReg b) {
    return a.confidence < b.confidence ? a.confidence : b.confidence;
}

/* Result type for binary op */
static int32_t _bintype(EvOpcode op, EvReg a, EvReg b) {
    if (op >= OP_LT && op <= OP_NEQ) return EV_BOOL;
    if (a.type == EV_REAL || b.type == EV_REAL) return EV_REAL;
    if (a.type == EV_INT  && b.type == EV_INT)  return EV_INT;
    if (op == OP_ADD && a.type == EV_TEXT)       return EV_TEXT;
    return EV_VOID;
}

EvReg ev_emit_binop(EvBuilder *b, EvOpcode op,
                    EvReg src0, EvReg src1, int32_t line) {
    int16_t conf = _binconf(src0, src1);
    int32_t typ  = _bintype(op, src0, src1);
    EvReg dest = ev_next_reg(b, typ, conf);
    EvInstr *ins = _emit(b, op, line);
    if (!ins) return ev_reg_void();
    ins->dest = dest; ins->src0 = src0; ins->src1 = src1;
    return dest;
}

EvReg ev_emit_recovery(EvBuilder *b, EvReg primary, EvReg strategy,
                       EvReg reason, int32_t line) {
    EvReg dest = ev_next_reg(b, EV_VOID, primary.confidence);
    EvInstr *ins = _emit(b, OP_RECOVERY, line);
    if (!ins) return ev_reg_void();
    ins->dest = dest; ins->src0 = primary; ins->src1 = strategy; ins->src2 = reason;
    return dest;
}

/* The outcome of the last repair, as an int (EV_HEAL_*). The lowered branch
   tests this, never the repaired value's truthiness. */
EvReg ev_emit_repair_state(EvBuilder *b, int32_t line) {
    EvReg dest = ev_next_reg(b, EV_INT, E_INTAKE);
    EvInstr *ins = _emit(b, OP_REPAIR_STATE, line);
    if (!ins) return ev_reg_void();
    ins->dest = dest;
    return dest;
}

/* Cause frames. A heal names its primary's failure by the first failure noted
   while the primary runs, as the Python reference does. These emitters have
   no value of their own except the reason, so their destinations are void
   where they are only side effects, and the dead-register pass keeps them. */
void ev_emit_cause_open(EvBuilder *b, int32_t line) {
    _emit(b, OP_CAUSE_OPEN, line);
}

EvReg ev_emit_cause_close(EvBuilder *b, EvReg primary, int32_t line) {
    EvReg dest = ev_next_reg(b, EV_TEXT, E_CERTAIN);
    EvInstr *ins = _emit(b, OP_CAUSE_CLOSE, line);
    if (!ins) return ev_reg_void();
    ins->dest = dest; ins->src0 = primary;
    return dest;
}

void ev_emit_cause_drop(EvBuilder *b, int32_t line) {
    _emit(b, OP_CAUSE_CLOSE, line);   /* dest and src0 void: pop, yield nothing */
}

void ev_emit_note(EvBuilder *b, const char *reason, int32_t line) {
    EvInstr *ins = _emit(b, OP_NOTE, line);
    if (!ins) return;
    ins->name = ev_arena_strdup(b->func->arena, reason);
}

void ev_emit_settle(EvBuilder *b, EvReg result, EvReg reason, int32_t line) {
    EvInstr *ins = _emit(b, OP_SETTLE, line);
    if (!ins) return;
    ins->src0 = result; ins->src1 = reason;
}

EvReg ev_emit_call(EvBuilder *b, const char *name,
                   EvReg *args, int32_t nargs, int32_t line) {
    /* confidence of a call = min over all args (and fn itself unknown here) */
    int16_t conf = E_CERTAIN;
    for (int32_t i = 0; i < nargs; i++)
        if (args[i].confidence < conf) conf = args[i].confidence;

    EvReg dest = ev_next_reg(b, EV_VOID, conf);  /* type resolved at runtime */
    EvInstr *ins = _emit(b, OP_CALL, line);
    if (!ins) return ev_reg_void();
    ins->dest  = dest;
    ins->name  = ev_arena_strdup(b->func->arena, name);
    ins->nargs = nargs;
    if (nargs > 0) {
        ins->args = (EvReg*)ev_arena_alloc(b->func->arena,
                                            nargs * sizeof(EvReg));
        memcpy(ins->args, args, nargs * sizeof(EvReg));
    }
    return dest;
}

void ev_emit_return(EvBuilder *b, EvReg src, int32_t line) {
    EvInstr *ins = _emit(b, OP_RETURN, line);
    if (!ins) return;
    ins->src0 = src;
    b->block->nsucc = 0;   /* RETURN has no successors */
}

void ev_emit_jump(EvBuilder *b, int32_t label_id, int32_t line) {
    EvInstr *ins = _emit(b, OP_JUMP, line);
    if (!ins) return;
    ins->true_label = label_id;
    b->block->succ[0]  = label_id;
    b->block->nsucc    = 1;
}

void ev_emit_jump_if(EvBuilder *b, EvReg cond, int32_t true_lbl,
                     int32_t false_lbl, int32_t unknown_lbl, int32_t line) {
    EvInstr *ins = _emit(b, OP_JUMP_IF, line);
    if (!ins) return;
    ins->src0          = cond;
    ins->true_label    = true_lbl;
    ins->false_label   = false_lbl;
    ins->unknown_label = unknown_lbl;
    b->block->succ[0] = true_lbl;
    b->block->succ[1] = false_lbl;
    b->block->nsucc   = 2;
}

void ev_emit_heal(EvBuilder *b, EvReg primary, int32_t trusted_lbl,
                  int32_t repair_lbl, int32_t line) {
    EvInstr *ins = _emit(b, OP_HEAL, line);
    if (!ins) return;
    ins->src0        = primary;
    ins->true_label  = trusted_lbl;
    ins->false_label = repair_lbl;
    b->block->succ[0] = trusted_lbl;
    b->block->succ[1] = repair_lbl;
    b->block->nsucc   = 2;
}

EvReg ev_emit_load(EvBuilder *b, const char *name,
                   int32_t type, int16_t conf, int32_t line) {
    EvReg dest = ev_reg_named(b->func->reg_counter++, name,
                               type, conf, b->func->arena);
    EvInstr *ins = _emit(b, OP_LOAD, line);
    if (!ins) return ev_reg_void();
    ins->dest = dest;
    ins->name = ev_arena_strdup(b->func->arena, name);
    return dest;
}

void ev_emit_store(EvBuilder *b, const char *name,
                   EvReg src, int32_t line) {
    EvInstr *ins = _emit(b, OP_STORE, line);
    if (!ins) return;
    ins->src0 = src;
    ins->name = ev_arena_strdup(b->func->arena, name);
}

void ev_emit_def_fn(EvBuilder *b, const char *name, int32_t line) {
    EvInstr *ins = _emit(b, OP_DEF_FN, line);
    if (!ins) return;
    ins->name = ev_arena_strdup(b->func->arena, name);
}

/* ─────────────────────────────────────────────
 * LOWERING: EvNode AST → EvTAC
 * ───────────────────────────────────────────── */

/* Map AST binary-op kind → TAC opcode */
static EvOpcode _op_from_kind(EvNodeKind k) {
    switch (k) {
        case EV_NODE_ADD: return OP_ADD;
        case EV_NODE_SUB: return OP_SUB;
        case EV_NODE_MUL: return OP_MUL;
        case EV_NODE_DIV: return OP_DIV;
        case EV_NODE_LT:  return OP_LT;
        case EV_NODE_GT:  return OP_GT;
        case EV_NODE_LTE: return OP_LTE;
        case EV_NODE_GTE: return OP_GTE;
        case EV_NODE_EQ:  return OP_EQ;
        case EV_NODE_NEQ: return OP_NEQ;
        default:          return OP_NOP;
    }
}

static EvBlock *new_block(EvBuilder *b) {
    EvBlock *blk = ev_func_new_block(b->func);
    if (!blk) ev_lower_fail(b, "out of arena memory while lowering");
    return blk;
}

EvReg ev_lower_node(EvBuilder *b, const EvNode *n) {
    if (!n) return ev_reg_void();

    switch ((EvNodeKind)n->kind) {

        case EV_NODE_VOID:
            return ev_reg_void();

        case EV_NODE_BOOL:
            return ev_emit_const(b, ev_bool(n->lit.as_bool), n->line);

        case EV_NODE_INT:
            return ev_emit_const(b, ev_int(n->lit.as_int), n->line);

        case EV_NODE_REAL:
            return ev_emit_const(b, ev_real(n->lit.as_real), n->line);

        case EV_NODE_TEXT:
            if (n->str && strlen(n->str) >= EV_INLINE_MAX) {
                ev_lower_fail(b, "text literal exceeds the inline TEXT capacity");
                return ev_reg_void();
            }
            return ev_emit_const(b, ev_text(n->str ? n->str : ""), n->line);

        case EV_NODE_VAR:
            /* type and confidence unknown at lower time — resolved at runtime */
            return ev_emit_load(b, n->str ? n->str : "?",
                                EV_VOID, E_INTAKE, n->line);

        case EV_NODE_ADD: case EV_NODE_SUB:
        case EV_NODE_MUL: case EV_NODE_DIV:
        case EV_NODE_LT:  case EV_NODE_GT:
        case EV_NODE_LTE: case EV_NODE_GTE:
        case EV_NODE_EQ:  case EV_NODE_NEQ: {
            if (n->child_count < 2) return ev_reg_void();
            EvReg lhs = ev_lower_node(b, n->children[0]);
            EvReg rhs = ev_lower_node(b, n->children[1]);
            return ev_emit_binop(b, _op_from_kind((EvNodeKind)n->kind),
                                 lhs, rhs, n->line);
        }

        case EV_NODE_HEAL: {
            /* The primary decides the branch. The strategy and fallback
               are lowered into the repair path only, so an untaken repair
               is never evaluated, as in the Python reference. */
            if (n->child_count < 3) return ev_reg_void();
            ev_emit_cause_open(b, n->line);
            EvReg primary = ev_lower_node(b, n->children[0]);
            EvReg reason  = ev_emit_cause_close(b, primary, n->line);

            EvBlock *trust_blk  = new_block(b);
            EvBlock *repair_blk = new_block(b);
            if (!trust_blk || !repair_blk) return ev_reg_void();

            char phi_name[32];
            snprintf(phi_name, sizeof phi_name, "_phi_%d", b->func->reg_counter);

            /* We'll create the merge block last so it's the final block in the function. */
            /* But we need its ID for the jumps. We can pre-allocate it or just use a placeholder.
               Actually, the easiest way is to create it now, but ensure it's the one we end with.
               The blocks array is just a list. The interpreter uses the ID. */
            EvBlock *merge_blk  = new_block(b);
            if (!merge_blk) return ev_reg_void();

            ev_emit_heal(b, primary, trust_blk->id, repair_blk->id, n->line);

            ev_builder_switch_block(b, trust_blk);
            ev_emit_store(b, phi_name, primary, n->line);
            ev_emit_jump(b, merge_blk->id, n->line);

            ev_builder_switch_block(b, repair_blk);
            ev_emit_cause_open(b, n->line);
            EvReg strat = ev_lower_node(b, n->children[1]);
            ev_emit_cause_drop(b, n->line);
            EvReg rec = ev_emit_recovery(b, primary, strat, reason, n->line);

            /* Branch on the repair's outcome (evaluate → plan → execute), never
               on the value: a repaired 0 or false is still a success. */
            EvReg state = ev_emit_repair_state(b, n->line);
            EvReg sub_flag = ev_emit_binop(b, OP_EQ, state,
                ev_emit_const(b, ev_int(EV_HEAL_SUBSTITUTE), n->line), n->line);
            EvReg fail_flag = ev_emit_binop(b, OP_EQ, state,
                ev_emit_const(b, ev_int(EV_HEAL_FAILED), n->line), n->line);

            EvBlock *sub_blk  = new_block(b);
            EvBlock *chk_blk  = new_block(b);
            EvBlock *fail_blk = new_block(b);
            EvBlock *fb_blk   = new_block(b);
            if (!sub_blk || !chk_blk || !fail_blk || !fb_blk) return ev_reg_void();

            ev_emit_jump_if(b, sub_flag, sub_blk->id, chk_blk->id, chk_blk->id, n->line);

            ev_builder_switch_block(b, sub_blk);
            ev_emit_store(b, phi_name, rec, n->line);
            ev_emit_jump(b, merge_blk->id, n->line);

            ev_builder_switch_block(b, chk_blk);
            ev_emit_jump_if(b, fail_flag, fail_blk->id, fb_blk->id, fb_blk->id, n->line);

            ev_builder_switch_block(b, fail_blk);
            EvReg zed = ev_emit_const(b, ev_void(), n->line);
            ev_emit_store(b, phi_name, zed, n->line);
            ev_emit_jump(b, merge_blk->id, n->line);

            ev_builder_switch_block(b, fb_blk);
            ev_emit_cause_open(b, n->line);
            EvReg fallback = ev_lower_node(b, n->children[2]);
            ev_emit_cause_drop(b, n->line);
            ev_emit_store(b, phi_name, fallback, n->line);
            ev_emit_jump(b, merge_blk->id, n->line);

            ev_builder_switch_block(b, merge_blk);
            int16_t conf = _binconf(primary, fallback);
            int32_t typ  = (primary.type != EV_VOID) ? primary.type : fallback.type;
            EvReg result = ev_emit_load(b, phi_name, typ, conf, n->line);
            /* a z result is the failure the heal could not repair: it hands that
               reason up to the enclosing frame, as _settle does in scope.py */
            ev_emit_settle(b, result, reason, n->line);
            return result;
        }

        case EV_NODE_IF: {
            /* Lower the condition */
            if (n->child_count < 3) return ev_reg_void();
            EvReg cond = ev_lower_node(b, n->children[0]);

            /* Blocks for then, else, unknown condition, and merge */
            EvBlock *then_blk  = new_block(b);
            EvBlock *else_blk  = new_block(b);
            EvBlock *unk_blk   = new_block(b);
            EvBlock *merge_blk = new_block(b);
            if (!then_blk || !else_blk || !unk_blk || !merge_blk)
                return ev_reg_void();

            ev_emit_jump_if(b, cond, then_blk->id, else_blk->id,
                            unk_blk->id, n->line);

            /* Build a synthetic name for the phi slot */
            char phi_name[32];
            snprintf(phi_name, sizeof phi_name, "_phi_%d", b->func->reg_counter);

            /* Then branch: evaluate and STORE result into the phi slot */
            ev_builder_switch_block(b, then_blk);
            EvReg then_val = ev_lower_node(b, n->children[1]);
            ev_emit_store(b, phi_name, then_val, n->line);
            ev_emit_jump(b, merge_blk->id, n->line);

            /* Else branch: evaluate and STORE result into the same phi slot */
            ev_builder_switch_block(b, else_blk);
            EvReg else_val = ev_lower_node(b, n->children[2]);
            ev_emit_store(b, phi_name, else_val, n->line);
            ev_emit_jump(b, merge_blk->id, n->line);

            /* Unknown condition: the result is z, not either arm */
            ev_builder_switch_block(b, unk_blk);
            EvReg zv = ev_emit_const(b, ev_void(), n->line);
            ev_emit_store(b, phi_name, zv, n->line);
            ev_emit_jump(b, merge_blk->id, n->line);

            /* Merge block: LOAD from the phi slot — one value regardless of branch */
            ev_builder_switch_block(b, merge_blk);
            int16_t conf = _binconf(then_val, else_val);
            if (cond.confidence < conf) conf = cond.confidence;
            int32_t typ  = (then_val.type != EV_VOID) ? then_val.type : else_val.type;
            EvReg   result = ev_emit_load(b, phi_name, typ, conf, n->line);
            return result;
        }

        case EV_NODE_CALL: {
            int32_t na = n->child_count;
            EvReg *args = NULL;
            if (na > 0) {
                args = (EvReg*)ev_arena_alloc(b->func->arena,
                                              (size_t)na * sizeof(EvReg));
                if (!args) {
                    ev_lower_fail(b, "out of arena memory while lowering");
                    return ev_reg_void();
                }
            }
            for (int32_t i = 0; i < na; i++)
                args[i] = ev_lower_node(b, n->children[i]);
            return ev_emit_call(b, n->str ? n->str : "?",
                                args, na, n->line);
        }

        case EV_NODE_DEF: {
            /* Emit a DEF_FN marker in the current block, then lower body
               into a new function added to the module */
            ev_emit_def_fn(b, n->str ? n->str : "?", n->line);
            if (b->module) ev_lower_func(b->module, n);
            return ev_reg_void();
        }

        case EV_NODE_Z:
            /* an explicit unknown: a failure, named as the Python reference names it */
            ev_emit_note(b, "declared unknown", n->line);
            return ev_reg_void();

        case EV_NODE_ERR:
            return ev_reg_void();

        case EV_NODE_LIST:
        case EV_NODE_RECORD:
            ev_lower_fail(b, "list and record values are not supported by the C interpreter");
            return ev_reg_void();

        default:
            ev_lower_fail(b, "node kind is not supported by the C interpreter");
            return ev_reg_void();
    }
}

static void module_fail(EvModule *m, const char *msg) {
    if (m && !m->lower_error) m->lower_error = msg;
}

EvFunc *ev_lower_func(EvModule *m, const EvNode *fn_node) {
    if (!m || !fn_node || fn_node->kind != EV_NODE_DEF)
        return NULL;

    const char *name    = fn_node->str ? fn_node->str : "?";
    const char **params = fn_node->params;
    int32_t     np      = fn_node->param_count;

    EvFunc  *f   = ev_module_add_func(m, name, params, np);
    EvBlock *blk = f ? ev_func_new_block(f) : NULL;
    if (!blk) {
        module_fail(m, "out of arena memory while lowering");
        return NULL;
    }

    EvBuilder b = ev_builder(m, f, blk);

    /* Emit LOAD for each parameter into a named register */
    for (int32_t i = 0; i < np; i++) {
        ev_emit_load(&b, params[i], EV_VOID, E_CERTAIN, 1);
    }

    /* Lower the body */
    EvReg result = (fn_node->child_count > 0)
        ? ev_lower_node(&b, fn_node->children[0])
        : ev_reg_void();

    ev_emit_return(&b, result, fn_node->line);
    return f;
}

EvModule *ev_lower_module(const char *name, EvNode *root) {
    /* Always create a fresh arena so ev_module_free() fully owns its memory.
     * The caller's arena (which owns 'root') remains valid throughout. */
    EvArena *ma = ev_arena_new(name ? name : "module");
    if (!ma) return NULL;
    EvModule *m = ev_module_new(name, ma);
    if (!m || !root) { ev_arena_free(ma); return NULL; }

    EvBlock *gb = ev_func_new_block(m->global_body);
    if (!gb) { ev_module_free(m); return NULL; }

    EvBuilder b = ev_builder(m, m->global_body, gb);
    EvReg res = ev_lower_node(&b, root);
    /* emit an explicit RETURN so the interpreter and dead-reg pass know
       this result is live — without RETURN the result looks dead */
    ev_emit_return(&b, res, root ? root->line : 1);
    if (m->lower_error) { ev_module_free(m); return NULL; }
    return m;
}

/* ─────────────────────────────────────────────
 * OPTIMISATION PASSES
 * ───────────────────────────────────────────── */

/* Pass 1: constant folding — fold binary ops where both sources are CONST */
int ev_pass_const_fold(EvFunc *f) {
    int changes = 0;
    for (int32_t bi = 0; bi < f->nblocks; bi++) {
        EvBlock *blk = f->blocks[bi];
        for (int32_t ii = 0; ii < blk->len; ii++) {
            EvInstr *ins = &blk->instrs[ii];
            if (!ev_opcode_is_binary(ins->op) &&
                !ev_opcode_is_cmp(ins->op)) continue;

            /* Find preceding CONST instrs for src0 and src1 */
            EValue *cv0 = NULL, *cv1 = NULL;
            for (int32_t ji = 0; ji < ii; ji++) {
                EvInstr *prev = &blk->instrs[ji];
                if (prev->op != OP_CONST) continue;
                if (prev->dest.id == ins->src0.id) cv0 = &prev->literal;
                if (prev->dest.id == ins->src1.id) cv1 = &prev->literal;
            }
            if (!cv0 || !cv1) continue;
            if (cv0->tag != EV_INT && cv0->tag != EV_REAL) continue;
            if (cv1->tag != EV_INT && cv1->tag != EV_REAL) continue;

            double a = (cv0->tag == EV_INT) ? (double)cv0->body.as_int
                                            : cv0->body.as_real;
            double b_ = (cv1->tag == EV_INT) ? (double)cv1->body.as_int
                                             : cv1->body.as_real;
            EValue folded = ev_void();
            int fold = 1;
            switch (ins->op) {
                case OP_ADD: folded = (cv0->tag==EV_INT && cv1->tag==EV_INT)
                                      ? ev_int((int64_t)(a+b_))
                                      : ev_real(a+b_); break;
                case OP_SUB: folded = (cv0->tag==EV_INT && cv1->tag==EV_INT)
                                      ? ev_int((int64_t)(a-b_))
                                      : ev_real(a-b_); break;
                case OP_MUL: folded = (cv0->tag==EV_INT && cv1->tag==EV_INT)
                                      ? ev_int((int64_t)(a*b_))
                                      : ev_real(a*b_); break;
                case OP_DIV: if (b_ == 0.0) { fold=0; break; }
                             folded = ev_real(a/b_); break;
                case OP_LT:  folded = ev_bool(a <  b_); break;
                case OP_GT:  folded = ev_bool(a >  b_); break;
                case OP_LTE: folded = ev_bool(a <= b_); break;
                case OP_GTE: folded = ev_bool(a >= b_); break;
                case OP_EQ:  folded = ev_bool(a == b_); break;
                case OP_NEQ: folded = ev_bool(a != b_); break;
                default:     fold = 0;
            }
            if (fold && folded.tag != EV_VOID) {
                ins->op      = OP_CONST;
                ins->literal = folded;
                ins->dest.type = folded.tag;
                ins->dest.confidence = E_CERTAIN;
                changes++;
            }
        }
    }
    return changes;
}

/* Pass 2: dead-register elimination */
/* Build a use-count array for each register id */
int ev_pass_dead_regs(EvFunc *f) {
    /* count up to reg_counter registers */
    int32_t nregs = f->reg_counter;
    if (nregs <= 0) return 0;
    int *uses = (int*)calloc((size_t)nregs, sizeof(int));
    if (!uses) return 0;

    /* count uses */
    for (int32_t bi = 0; bi < f->nblocks; bi++) {
        EvBlock *blk = f->blocks[bi];
        for (int32_t ii = 0; ii < blk->len; ii++) {
            EvInstr *ins = &blk->instrs[ii];
            if (!ev_reg_is_void(ins->src0)) uses[ins->src0.id]++;
            if (!ev_reg_is_void(ins->src1)) uses[ins->src1.id]++;
            if (!ev_reg_is_void(ins->src2)) uses[ins->src2.id]++;
            /* a void argument (a z value) is not a register: counting it
               would credit register 0, the void sentinel */
            for (int32_t ai = 0; ai < ins->nargs; ai++)
                if (!ev_reg_is_void(ins->args[ai])) uses[ins->args[ai].id]++;
            /* RETURN / STORE always count as a use of dest */
            if (ins->op == OP_RETURN || ins->op == OP_STORE)
                if (!ev_reg_is_void(ins->src0)) uses[ins->src0.id]++;
        }
    }

    int changes = 0;
    for (int32_t bi = 0; bi < f->nblocks; bi++) {
        EvBlock *blk = f->blocks[bi];
        for (int32_t ii = 0; ii < blk->len; ii++) {
            EvInstr *ins = &blk->instrs[ii];
            if (ev_reg_is_void(ins->dest)) continue;
            if (ins->op == OP_CALL) continue; /* calls may have side-effects */
            if (ins->op == OP_STORE || ins->op == OP_DEF_FN) continue;
            if (uses[ins->dest.id] == 0) {
                ins->op = OP_NOP;
                changes++;
            }
        }
    }
    free(uses);
    return changes;
}

/* Pass 3: confidence propagation. A computed register starts at its
   build-time confidence and can only fall: it takes the minimum of its
   own value and every source. */
int ev_pass_conf_prop(EvFunc *f) {
    int32_t nregs = f->reg_counter;
    if (nregs <= 0) return 0;
    int16_t *conf = (int16_t*)calloc((size_t)nregs, sizeof(int16_t));
    if (!conf) return 0;
    for (int32_t bi = 0; bi < f->nblocks; bi++) {
        EvBlock *blk = f->blocks[bi];
        for (int32_t ii = 0; ii < blk->len; ii++) {
            EvInstr *ins = &blk->instrs[ii];
            if (ev_reg_is_void(ins->dest)) continue;
            if (ins->op == OP_CONST)
                conf[ins->dest.id] = E_CERTAIN;
            else if (ins->op == OP_LOAD)
                conf[ins->dest.id] = E_INTAKE;
            else
                conf[ins->dest.id] = ins->dest.confidence;
        }
    }
    /* propagate: two passes are enough for our depth-bounded recursion */
    int changes = 0;
    for (int pass = 0; pass < 2; pass++) {
        for (int32_t bi = 0; bi < f->nblocks; bi++) {
            EvBlock *blk = f->blocks[bi];
            for (int32_t ii = 0; ii < blk->len; ii++) {
                EvInstr *ins = &blk->instrs[ii];
                if (ev_reg_is_void(ins->dest)) continue;
                int16_t c = conf[ins->dest.id];
                int16_t newc = c;
                if (!ev_reg_is_void(ins->src0) &&
                        conf[ins->src0.id] < newc)
                    newc = conf[ins->src0.id];
                if (!ev_reg_is_void(ins->src1) &&
                        conf[ins->src1.id] < newc)
                    newc = conf[ins->src1.id];
                if (!ev_reg_is_void(ins->src2) &&
                        conf[ins->src2.id] < newc)
                    newc = conf[ins->src2.id];
                for (int32_t ai = 0; ai < ins->nargs; ai++)
                    if (conf[ins->args[ai].id] < newc)
                        newc = conf[ins->args[ai].id];
                if (newc != c) {
                    conf[ins->dest.id] = newc;
                    ins->dest.confidence = newc;
                    changes++;
                }
            }
        }
    }
    free(conf);
    return changes;
}

int ev_optimise(EvFunc *f) {
    int total = 0;
    total += ev_pass_const_fold(f);
    total += ev_pass_dead_regs(f);
    total += ev_pass_conf_prop(f);
    return total;
}

/* ─────────────────────────────────────────────
 * INTERPRETER — execute TAC directly
 * ───────────────────────────────────────────── */

#ifndef E_DEPTH_CEILING
#define E_DEPTH_CEILING 3
#endif

#define EV_MAX_DEPTH  8

typedef struct { const char *name; EValue val; int16_t conf; } EvNamedSlot;

/* ─────────────────────────────────────────────
 * CALL FRAMES
 *
 * The register file and the named-slot table are interpreter-wide.
 * Without frames, a recursive call binds its own parameters over the
 * caller's registers, and when it returns the caller reads the
 * callee's values.
 *
 * The symptom is quiet and wrong rather than a crash: fact(n) returns
 * 2^(n-1). For n=3 the inner fact(2) rebinds n to 2, so the outer
 * frame computes 2*2 instead of 3*2. Every value is a plausible
 * number, which is why this survived until a kitchen-sink test
 * called fact past the base case.
 *
 * One save slot per depth, allocated once. On entry a frame snapshots
 * the caller's state; on exit it puts it back. The returned EValue is
 * copied out before the restore, so results cross the boundary while
 * bindings do not.
 * ───────────────────────────────────────────── */
typedef struct {
    EValue      *regs;
    int16_t     *reg_conf;
    EvNamedSlot *named;
    int32_t      nnamed;
    int32_t      named_cap;
} EvFrameSave;

/* A cause frame: the first failure noted while a heal's primary runs. The
   reason is copied in, so it outlives the register that carried the z.
   Mirrors heal_order.py's cause_frame. */
typedef struct {
    char    text[EV_INLINE_MAX];
    int32_t set;
} EvCause;

struct EvInterp {
    EvModule    *module;
    int32_t      nregs;      /* register file size: highest reg_counter  */
    EValue      *regs;
    int16_t     *reg_conf;   /* runtime confidence of each register's value */
    EvNamedSlot *named;
    int32_t      nnamed;
    int32_t      named_cap;
    EvFrameSave *frames;     /* EV_MAX_DEPTH+2 save slots */
    int16_t      ret_conf;   /* confidence of the value last returned */
    int          failed;     /* set when the interpreter ran out of memory */
    EvCause      cause;      /* the innermost frame's first failure          */
    EvCause     *cause_stack; /* the frames each enclosing heal left open    */
    int32_t      ncause;
    int32_t      cause_cap;
    int32_t      heal_count;       /* heals evaluated (see ev_interp_heal_trace) */
    int32_t      heal_action;      /* EV_HEAL_* outcome of the last repair       */
    int16_t      heal_conf;        /* confidence of a substituted repair, else 0 */
};

EvHealTrace ev_interp_heal_trace(const EvInterp *ip) {
    EvHealTrace t = { 0, EV_HEAL_KEEP, 0 };
    if (!ip) return t;
    t.count  = ip->heal_count;
    t.action = ip->heal_action;
    t.conf   = ip->heal_conf;
    return t;
}

static int named_reserve(EvNamedSlot **buf, int32_t *cap, int32_t need) {
    if (need <= *cap) return 1;
    int32_t nc = (*cap > 0) ? *cap : 16;
    while (nc < need) nc *= 2;
    EvNamedSlot *nb = (EvNamedSlot*)realloc(*buf,
                                            (size_t)nc * sizeof(EvNamedSlot));
    if (!nb) return 0;
    *buf = nb;
    *cap = nc;
    return 1;
}

static EValue reg_get(const EvInterp *ip, EvReg r) {
    if (r.id < 0 || r.id >= ip->nregs) return ev_void();
    return ip->regs[r.id];
}

static int16_t reg_conf_get(const EvInterp *ip, EvReg r) {
    if (r.id < 0 || r.id >= ip->nregs) return 0;
    return ip->reg_conf[r.id];
}

static EvNamedSlot *named_find(const EvInterp *ip, const char *name) {
    for (int32_t k = 0; k < ip->nnamed; k++)
        if (ip->named[k].name && strcmp(ip->named[k].name, name) == 0)
            return &ip->named[k];
    return NULL;
}

/* A failure happened here. The frame keeps the first one: a later z is a
   consequence of it, not a second cause (scope.py's heal_order.note). */
static void cause_note(EvInterp *ip, const char *reason) {
    if (ip->cause.set) return;
    snprintf(ip->cause.text, sizeof ip->cause.text, "%s", reason);
    ip->cause.set = 1;
}

/* A heal's primary begins: the enclosing frame is saved, and a fresh one opens. */
static void cause_push(EvInterp *ip) {
    if (ip->ncause == ip->cause_cap) {
        int32_t nc = (ip->cause_cap > 0) ? ip->cause_cap * 2 : 8;
        EvCause *nb = (EvCause*)realloc(ip->cause_stack,
                                        (size_t)nc * sizeof(EvCause));
        if (!nb) { ip->failed = 1; return; }
        ip->cause_stack = nb;
        ip->cause_cap   = nc;
    }
    ip->cause_stack[ip->ncause++] = ip->cause;
    ip->cause.set = 0;
}

/* The frame closes: it is returned, and the enclosing one is restored. */
static EvCause cause_pop(EvInterp *ip) {
    EvCause inner = ip->cause;
    if (ip->ncause > 0) ip->cause = ip->cause_stack[--ip->ncause];
    else                ip->cause.set = 0;
    return inner;
}

static int frame_push(EvInterp *ip, EvFrameSave *s) {
    if (!s->regs)     s->regs     = (EValue*)calloc((size_t)ip->nregs, sizeof(EValue));
    if (!s->reg_conf) s->reg_conf = (int16_t*)calloc((size_t)ip->nregs, sizeof(int16_t));
    if (!s->regs || !s->reg_conf) return 0;
    if (!named_reserve(&s->named, &s->named_cap, ip->nnamed)) return 0;
    memcpy(s->regs,     ip->regs,     (size_t)ip->nregs * sizeof(EValue));
    memcpy(s->reg_conf, ip->reg_conf, (size_t)ip->nregs * sizeof(int16_t));
    if (ip->nnamed > 0)
        memcpy(s->named, ip->named, (size_t)ip->nnamed * sizeof(EvNamedSlot));
    s->nnamed = ip->nnamed;
    return 1;
}

static int frame_pop(EvInterp *ip, const EvFrameSave *s) {
    if (!named_reserve(&ip->named, &ip->named_cap, s->nnamed)) return 0;
    memcpy(ip->regs,     s->regs,     (size_t)ip->nregs * sizeof(EValue));
    memcpy(ip->reg_conf, s->reg_conf, (size_t)ip->nregs * sizeof(int16_t));
    if (s->nnamed > 0)
        memcpy(ip->named, s->named, (size_t)s->nnamed * sizeof(EvNamedSlot));
    ip->nnamed = s->nnamed;
    return 1;
}

EvInterp *ev_interp_new(EvModule *m) {
    if (!m) return NULL;
    EvInterp *ip = (EvInterp*)calloc(1, sizeof *ip);
    if (!ip) return NULL;
    ip->module = m;
    int32_t top = EV_REG_FIRST;
    for (int32_t i = 0; i < m->nfuncs; i++)
        if (m->funcs[i]->reg_counter > top) top = m->funcs[i]->reg_counter;
    if (m->global_body && m->global_body->reg_counter > top)
        top = m->global_body->reg_counter;
    ip->nregs = top;
    ip->regs     = (EValue*)calloc((size_t)top, sizeof(EValue));
    ip->reg_conf = (int16_t*)calloc((size_t)top, sizeof(int16_t));
    ip->frames   = (EvFrameSave*)calloc((size_t)EV_MAX_DEPTH + 2,
                                        sizeof(EvFrameSave));
    if (!ip->regs || !ip->reg_conf || !ip->frames) {
        ev_interp_free(ip);
        return NULL;
    }
    return ip;
}

void ev_interp_free(EvInterp *ip) {
    if (!ip) return;
    if (ip->frames) {
        for (int d = 0; d < EV_MAX_DEPTH + 2; d++) {
            free(ip->frames[d].regs);
            free(ip->frames[d].reg_conf);
            free(ip->frames[d].named);
        }
    }
    free(ip->frames);
    free(ip->regs);
    free(ip->reg_conf);
    free(ip->named);
    free(ip->cause_stack);
    free(ip);
}

static EValue interp_func(EvInterp *ip, EvFunc *f, EValue *args,
                          const int16_t *arg_conf, int32_t nargs, int depth);

static EValue interp_block(EvInterp *ip, EvFunc *f, EvBlock *start_blk,
                            int depth) {
    EvBlock *cur = start_blk;
    EValue last  = ev_void();

    while (cur) {
        EvBlock *next = NULL;
        for (int32_t ii = 0; ii < cur->len; ii++) {
            EvInstr *ins = &cur->instrs[ii];
            EValue res = ev_void();
            int16_t rc = 0;

            switch (ins->op) {
                case OP_NOP: break;
                case OP_CONST:
                    res = ins->literal;
                    rc  = ins->dest.confidence;
                    break;
                case OP_COPY:
                    res = reg_get(ip, ins->src0);
                    rc  = reg_conf_get(ip, ins->src0);
                    break;

                case OP_ADD: case OP_SUB: case OP_MUL: case OP_DIV:
                case OP_LT:  case OP_GT:  case OP_LTE: case OP_GTE:
                case OP_EQ:  case OP_NEQ: {
                    EValue a = reg_get(ip, ins->src0);
                    EValue b_val = reg_get(ip, ins->src1);
                    /* Z-CONTAGION. Zero-absolute is a STATE, so it is
                       checked before arithmetic rather than folded into
                       it. Reading a void's body as a double is what
                       turns an unknown into a confident wrong number. */
                    if (a.tag == EV_VOID || b_val.tag == EV_VOID) {
                        /* the failure was named where it arose: passing the z on
                         * notes nothing, so heal((1 / 0) + 1) names the division */
                        res = ev_void();
                        break;
                    }
                    {
                        int16_t ca = reg_conf_get(ip, ins->src0);
                        int16_t cb = reg_conf_get(ip, ins->src1);
                        rc = (ca < cb) ? ca : cb;
                    }
                    double da = (a.tag==EV_INT)  ? (double)a.body.as_int
                                                 : a.body.as_real;
                    double db = (b_val.tag==EV_INT) ? (double)b_val.body.as_int
                                                    : b_val.body.as_real;
                    switch (ins->op) {
                        case OP_ADD: res=(a.tag==EV_INT&&b_val.tag==EV_INT)
                                         ?ev_int(a.body.as_int+b_val.body.as_int)
                                         :ev_real(da+db); break;
                        case OP_SUB: res=(a.tag==EV_INT&&b_val.tag==EV_INT)
                                         ?ev_int(a.body.as_int-b_val.body.as_int)
                                         :ev_real(da-db); break;
                        case OP_MUL: res=(a.tag==EV_INT&&b_val.tag==EV_INT)
                                         ?ev_int(a.body.as_int*b_val.body.as_int)
                                         :ev_real(da*db); break;
                        case OP_DIV:
                            if (db != 0.0) {
                                res = ev_real(da/db);
                            } else {
                                res = ev_void();
                                cause_note(ip, "division by zero");
                            }
                            break;
                        case OP_LT:  res=ev_bool(da< db); break;
                        case OP_GT:  res=ev_bool(da> db); break;
                        case OP_LTE: res=ev_bool(da<=db); break;
                        case OP_GTE: res=ev_bool(da>=db); break;
                        case OP_EQ:  res=ev_bool(da==db); break;
                        case OP_NEQ: res=ev_bool(da!=db); break;
                        default: break;
                    }
                    break;
                }

                case OP_LOAD: {
                    int bound = 0;   /* a binding of this name exists, even a z one */
                    if (ins->name) {
                        /* 1. Check named slot store (phi slots from if/else) */
                        EvNamedSlot *slot = named_find(ip, ins->name);
                        if (slot) {
                            res = slot->val;
                            rc  = slot->conf;
                            break;
                        }
                        /* 2. Check param bindings: scan block 0 for a LOAD
                           with same name that has been bound by interp_func */
                        EvBlock *eb = f->blocks[0];
                        for (int32_t ki = 0; ki < eb->len; ki++) {
                            EvInstr *ki_ins = &eb->instrs[ki];
                            if (ki_ins->op != OP_LOAD) continue;
                            if (!ki_ins->name) continue;
                            if (strcmp(ki_ins->name, ins->name) != 0) continue;
                            if (ev_reg_is_void(ki_ins->dest)) continue;
                            bound = 1;
                            EValue candidate = reg_get(ip, ki_ins->dest);
                            if (candidate.tag != EV_VOID) {
                                res = candidate;
                                rc  = reg_conf_get(ip, ki_ins->dest);
                                break;
                            }
                        }
                    }
                    /* a name nothing binds is unbound. The lowering's own _phi_
                       slots are not names a program can leave unbound. */
                    if (!bound && ins->name && strncmp(ins->name, "_phi_", 5) != 0) {
                        char why[EV_INLINE_MAX];
                        snprintf(why, sizeof why, "%s was never bound", ins->name);
                        cause_note(ip, why);
                    }
                    break;
                }

                case OP_STORE: {
                    /* Save src0's current value and confidence to the named slot */
                    if (ins->name) {
                        EvNamedSlot *slot = named_find(ip, ins->name);
                        if (!slot) {
                            if (!named_reserve(&ip->named, &ip->named_cap,
                                               ip->nnamed + 1)) {
                                ip->failed = 1;
                                break;
                            }
                            slot = &ip->named[ip->nnamed++];
                            slot->name = ins->name;
                        }
                        slot->val  = reg_get(ip, ins->src0);
                        slot->conf = reg_conf_get(ip, ins->src0);
                    }
                    break;
                }

                case OP_CALL: {
                    if (!ins->name) break;
                    /* find function in module */
                    EvFunc *callee = NULL;
                    for (int32_t fi = 0; fi < ip->module->nfuncs; fi++) {
                        if (strcmp(ip->module->funcs[fi]->name, ins->name)==0) {
                            callee = ip->module->funcs[fi]; break;
                        }
                    }
                    if (!callee) {
                        char why[EV_INLINE_MAX];
                        snprintf(why, sizeof why, "%s was never bound", ins->name);
                        cause_note(ip, why);
                        res = ev_void();
                        break;
                    }
                    /* Language rule: unanchored recursion may not
                       exceed depth ceiling floor(pi) = 3. Beyond it the
                       call yields z.
                       CORRECTED BACK from a `depth + 1 >= ceiling`
                       version added earlier this session. That version
                       was validated only against ev_interp_call(), an
                       entry point that skips this very gate for the
                       outermost invocation — it calls interp_func()
                       directly. No real .ever program calls that way;
                       every call, including the first, is an ordinary
                       expression evaluated through this OP_CALL case.
                       Under THAT path — the one that actually runs
                       real programs — the plain `depth >= ceiling`
                       check below is correct and matches the Python
                       evaluator (scope.py) exactly, confirmed by full
                       regression rather than an isolated probe.
                       EV_MAX_DEPTH remains as a hard backstop. */
                    if (depth >= E_DEPTH_CEILING ||
                        depth >= EV_MAX_DEPTH) {
                        cause_note(ip, "depth ceiling reached");
                        res = ev_void(); break;
                    }

                    int32_t na = ins->nargs;
                    EValue  call_args[na > 0 ? na : 1];
                    int16_t call_conf[na > 0 ? na : 1];
                    for (int32_t ai = 0; ai < na; ai++) {
                        call_args[ai] = reg_get(ip, ins->args[ai]);
                        call_conf[ai] = reg_conf_get(ip, ins->args[ai]);
                    }
                    res = interp_func(ip, callee, call_args, call_conf, na, depth+1);
                    rc  = ip->ret_conf;
                    break;
                }

                case OP_RETURN:
                    if (!ev_reg_is_void(ins->src0)) {
                        last = reg_get(ip, ins->src0);
                        ip->ret_conf = reg_conf_get(ip, ins->src0);
                    } else {
                        ip->ret_conf = 0;
                    }
                    return last;

                case OP_JUMP:
                    if (ins->true_label >= 0 &&
                            ins->true_label < f->nblocks)
                        next = f->blocks[ins->true_label];
                    goto next_block;

                case OP_JUMP_IF: {
                    /* Ever truthiness: a bool is itself, a number is
                       non-zero, text is non-empty. A z or composite
                       condition takes neither arm. */
                    EValue cond = reg_get(ip, ins->src0);
                    int32_t lbl;
                    switch (cond.tag) {
                        case EV_BOOL: lbl = cond.body.as_bool ? ins->true_label : ins->false_label; break;
                        case EV_INT:  lbl = (cond.body.as_int != 0) ? ins->true_label : ins->false_label; break;
                        case EV_REAL: lbl = (cond.body.as_real != 0.0) ? ins->true_label : ins->false_label; break;
                        case EV_TEXT: lbl = (cond.text[0] != '\0') ? ins->true_label : ins->false_label; break;
                        default:      lbl = ins->unknown_label; break;
                    }
                    if (lbl >= 0 && lbl < f->nblocks)
                        next = f->blocks[lbl];
                    goto next_block;
                }

                case OP_HEAL: {
                    /* Trusted when the primary is a value (not z) and its
                       confidence reaches the execute floor. */
                    EValue primary = reg_get(ip, ins->src0);
                    int trusted = primary.tag != EV_VOID &&
                                  reg_conf_get(ip, ins->src0) >= E_EXECUTE_FLOOR;
                    ip->heal_count++;
                    if (trusted) {
                        ip->heal_action = EV_HEAL_KEEP;
                        ip->heal_conf   = reg_conf_get(ip, ins->src0);
                    }
                    int32_t lbl = trusted ? ins->true_label : ins->false_label;
                    if (lbl >= 0 && lbl < f->nblocks)
                        next = f->blocks[lbl];
                    goto next_block;
                }
                case OP_RECOVERY: {
                    /* the reason is the one the heal's frame named (src2); the
                     * primary (src0) is only the base the repair starts from */
                    EValue reason_ev = reg_get(ip, ins->src2);
                    EValue strategy_ev = reg_get(ip, ins->src1);
                    const char *reason = (reason_ev.tag == EV_TEXT && reason_ev.text[0])
                                         ? reason_ev.text : NULL;
                    int32_t kind = 0;
                    const char *fixture = NULL;
                    /* a strategy with no text matches wildcard repairs only */
                    const char *strat = (strategy_ev.tag == EV_TEXT) ? strategy_ev.text : NULL;
                    if (reason)
                        fixture = ev_repair_find(g_repair_registry, reason, strat, &kind);
                    /* base as in repair.py: E_INTAKE when the primary is z,
                       otherwise its own confidence */
                    int16_t base = (reg_get(ip, ins->src0).tag == EV_VOID) ? E_INTAKE
                                   : reg_conf_get(ip, ins->src0);
                    int16_t cost = (kind == 0) ? E_REPAIR_PLAIN : E_REPAIR_INFERRED;

                    res = ev_void();
                    rc  = 0;
                    if (!fixture || base - cost <= 0) {
                        /* PLAN: no archived repair, or one that cannot add trust */
                        ip->heal_action = EV_HEAL_FALLBACK;
                    } else {
                        /* EXECUTE: an unusable or z fixture is FAILED: the
                           result is z, never the fallback */
                        EValue value = ev_parse_constant(fixture);
                        if (value.tag == EV_VOID) {
                            ip->heal_action = EV_HEAL_FAILED;
                        } else {
                            res = value;
                            rc  = (int16_t)(base - cost);
                            ip->heal_action = EV_HEAL_SUBSTITUTE;
                        }
                    }
                    ip->heal_conf = (ip->heal_action == EV_HEAL_SUBSTITUTE) ? rc : 0;
                    break;
                }
                case OP_REPAIR_STATE:
                    res = ev_int(ip->heal_action);
                    rc  = E_INTAKE;
                    break;

                case OP_CAUSE_OPEN:
                    cause_push(ip);
                    break;

                case OP_CAUSE_CLOSE: {
                    EvCause inner = cause_pop(ip);
                    if (ev_reg_is_void(ins->dest)) break;   /* a drop: pop only */
                    /* the same three cases as scope.py's _primary_assessment */
                    const char *why;
                    if (reg_get(ip, ins->src0).tag == EV_VOID)
                        why = inner.set ? inner.text : "unverified";
                    else if (reg_conf_get(ip, ins->src0) >= E_EXECUTE_FLOOR)
                        why = "";
                    else
                        why = "low confidence";
                    res = ev_text(why);
                    rc  = E_CERTAIN;
                    break;
                }

                case OP_NOTE:
                    cause_note(ip, ins->name);
                    break;

                case OP_SETTLE: {
                    /* a z result is the failure the heal could not repair */
                    EValue result = reg_get(ip, ins->src0);
                    EValue why    = reg_get(ip, ins->src1);
                    if (result.tag == EV_VOID && why.tag == EV_TEXT && why.text[0])
                        cause_note(ip, why.text);
                    break;
                }

                case OP_DEF_FN: break; /* function already in module */
                default: break;
            }

            if (res.tag == EV_VOID) rc = 0;
            if (!ev_reg_is_void(ins->dest) && ins->dest.id < ip->nregs) {
                ip->regs[ins->dest.id]     = res;
                ip->reg_conf[ins->dest.id] = rc;
            }
            last = res;
        }
        next_block:
        cur = next;
    }
    return last;
}

static EValue interp_func(EvInterp *ip, EvFunc *f, EValue *args,
                          const int16_t *arg_conf, int32_t nargs, int depth) {
    if (!f || f->nblocks == 0) return ev_void();
    if (depth < 0 || depth > EV_MAX_DEPTH) return ev_void();

    /* ── PUSH FRAME ──────────────────────────────────────────
     * Snapshot the caller before this frame touches anything.
     * Arguments were already evaluated in the caller's registers
     * and arrive here by value, so they survive the snapshot. */
    EvFrameSave *save = &ip->frames[depth];
    if (!frame_push(ip, save)) {
        ip->failed = 1;
        return ev_void();
    }

    /* Bind params: find LOAD instrs for param names in block 0 */
    EvBlock *entry = f->blocks[0];
    int32_t pa = 0;
    for (int32_t ii = 0; ii < entry->len && pa < nargs; ii++) {
        EvInstr *ins = &entry->instrs[ii];
        if (ins->op == OP_LOAD && ins->name &&
                pa < f->nparam &&
                strcmp(ins->name, f->params[pa]) == 0) {
            if (!ev_reg_is_void(ins->dest) && ins->dest.id < ip->nregs) {
                ip->regs[ins->dest.id]     = args[pa];
                ip->reg_conf[ins->dest.id] = arg_conf[pa];
            }
            pa++;
        }
    }

    ip->ret_conf = 0;
    EValue result = interp_block(ip, f, entry, depth);

    /* ── POP FRAME ───────────────────────────────────────────
     * result is a by-value copy taken before the restore, so the
     * return value crosses the boundary and the bindings do not. */
    /* the cause is not reset here: a failure in a callee belongs to the heal
     * whose primary made the call, as it does in scope.py */
    if (!frame_pop(ip, save)) ip->failed = 1;
    return result;
}

EValue ev_interp_call(EvInterp *ip, const char *fn_name,
                       EValue *args, int32_t nargs) {
    if (!ip || !fn_name) return ev_void();
    if (E_DEPTH_CEILING <= 0) return ev_void();
    for (int32_t i = 0; i < ip->module->nfuncs; i++) {
        if (strcmp(ip->module->funcs[i]->name, fn_name) == 0) {
            /* depth=1: matches a real top-level `fact(n)` expression,
               which enters fact's body at depth 1 (the global body's
               own OP_CALL check runs at depth 0 first). Calling this
               at depth=0 let one extra level of recursion through
               versus every real program's actual entry path.
               Host-supplied arguments enter at E_INTAKE. */
            int16_t conf_in[nargs > 0 ? nargs : 1];
            for (int32_t a = 0; a < nargs; a++) conf_in[a] = E_INTAKE;
            ip->failed = 0;
            EValue r = interp_func(ip, ip->module->funcs[i], args, conf_in,
                                   nargs, 1);
            return ip->failed ? ev_void() : r;
        }
    }
    return ev_void();
}

EValue ev_interp_run(EvInterp *ip) {
    if (!ip || !ip->module->global_body ||
            ip->module->global_body->nblocks == 0)
        return ev_void();
    ip->failed = 0;
    ip->ncause = 0;
    ip->cause.set = 0;
    EValue r = interp_block(ip, ip->module->global_body,
                            ip->module->global_body->blocks[0], 0);
    return ip->failed ? ev_void() : r;
}

/* ─────────────────────────────────────────────
 * PRETTY PRINTER
 * ───────────────────────────────────────────── */

static void print_reg(EvReg r) {
    if (r.id == EV_REG_VOID) { printf("_"); return; }
    if (r.name)  printf("%s", r.name);
    else         printf("t%d", r.id);
    if (r.confidence < E_CERTAIN) printf("@%d", r.confidence);
}

void ev_print_instr(const EvInstr *ins, const EvBlock *b) {
    (void)b;
    printf("    ");
    switch (ins->op) {
        case OP_NOP: printf("NOP"); break;
        case OP_CONST:
            printf("CONST  "); print_reg(ins->dest); printf(" = ");
            switch (ins->literal.tag) {
                case EV_INT:  printf("%lld", (long long)ins->literal.body.as_int); break;
                case EV_REAL: printf("%.6g", ins->literal.body.as_real); break;
                case EV_BOOL: printf("%s", ins->literal.body.as_bool?"true":"false"); break;
                case EV_TEXT: printf("\"%s\"", ins->literal.text); break;
                default:      printf("void"); break;
            } break;
        case OP_COPY:
            printf("COPY   "); print_reg(ins->dest);
            printf(" <- "); print_reg(ins->src0); break;
        case OP_LOAD:
            printf("LOAD   "); print_reg(ins->dest);
            printf(" <- scope[\"%s\"]", ins->name ? ins->name : "?"); break;
        case OP_STORE:
            printf("STORE  scope[\"%s\"] <- ", ins->name ? ins->name : "?");
            print_reg(ins->src0); break;
        case OP_DEF_FN:
            printf("DEF_FN \"%s\"", ins->name ? ins->name : "?"); break;
        case OP_RETURN:
            printf("RETURN "); print_reg(ins->src0); break;
        case OP_JUMP:
            printf("JUMP   B%d", ins->true_label); break;
        case OP_JUMP_IF:
            printf("JUMP_IF "); print_reg(ins->src0);
            printf(" ? B%d : B%d / z B%d", ins->true_label, ins->false_label,
                   ins->unknown_label); break;
        case OP_HEAL:
            printf("HEAL   "); print_reg(ins->src0);
            printf(" ? B%d : B%d", ins->true_label, ins->false_label); break;
        case OP_CALL:
            print_reg(ins->dest); printf(" = CALL %s(",
            ins->name ? ins->name : "?");
            for (int32_t i = 0; i < ins->nargs; i++) {
                if (i) printf(", ");
                print_reg(ins->args[i]);
            }
            printf(")"); break;
        default:
            if (ev_opcode_is_binary(ins->op) || ev_opcode_is_cmp(ins->op)) {
                print_reg(ins->dest); printf(" = ");
                print_reg(ins->src0); printf(" %s ", ev_opcode_name(ins->op));
                print_reg(ins->src1);
            } else {
                printf("%s", ev_opcode_name(ins->op));
            }
    }
    printf("\n");
}

void ev_print_block(const EvBlock *b) {
    printf("  B%d:\n", b->id);
    for (int32_t i = 0; i < b->len; i++)
        ev_print_instr(&b->instrs[i], b);
}

void ev_print_func(const EvFunc *f) {
    printf("fn %s(", f->name);
    for (int32_t i = 0; i < f->nparam; i++) {
        if (i) printf(", ");
        printf("%s", f->params[i]);
    }
    printf(")  [%d regs, %d blocks]\n", f->reg_counter-1, f->nblocks);
    for (int32_t i = 0; i < f->nblocks; i++)
        ev_print_block(f->blocks[i]);
}

void ev_print_module(const EvModule *m) {
    printf("\n=== Module: %s ===\n", m->name);
    for (int32_t i = 0; i < m->nfuncs; i++) ev_print_func(m->funcs[i]);
    if (m->global_body && m->global_body->nblocks > 0) {
        printf("--- global body ---\n");
        ev_print_func(m->global_body);
    }
}
