/*
 * tac.h — Ever / Tapestry, Three-Address IR (EvTAC)
 *
 * THE INTERPRETER LAYER.
 *
 * EvNode (ir.h) is the parse-tree. It mirrors source syntax —
 * nested if/then/else children, recursive call trees, literals
 * buried inside expressions. Every optimisation pass has to
 * tree-walk. Every type check re-discovers the same types.
 * Every backend re-invents the same traversal.
 *
 * EvTAC is the flat, linear form that sits between the parse tree
 * and the execution engine:
 *
 *   SOURCE   →   EvNode (AST)   →   EvTAC   →   interpreter / transpiler
 *
 * THREE-ADDRESS FORM
 * ──────────────────
 *   Every instruction has at most one operation, one destination,
 *   and at most two sources:
 *
 *     t2 = t0 + t1          ADD   dest=t2  src0=t0  src1=t1
 *     t3 = fact(t2)         CALL  dest=t3  name=fact args=[t2]
 *     if t3 goto B1         JUMP_IF  t3  B1  B2
 *
 *   The nested AST  x * fact(n-1)  becomes:
 *     t0 = n - 1
 *     t1 = fact(t0)
 *     t2 = x * t1
 *
 *   Each virtual register (EvReg) is written exactly once.
 *   That is Static Single Assignment (SSA) lite — enough for:
 *     • constant folding   (t0 = 3-1 → t0 = 2 at build time)
 *     • dead-code removal  (unused t-registers pruned)
 *     • confidence flow    (each reg carries the MIN of its sources)
 *     • type annotation    (each reg has a known type at IR-build time)
 *     • target emission    (Rust/Go/TS pattern-match on opcodes)
 *
 * STRUCTURE
 * ─────────
 *   EvModule  — top-level container
 *     EvFunc  — one function (or the global body)
 *       EvBlock — one basic block (linear run with one exit)
 *         EvInstr — one three-address instruction
 *
 * VIRTUAL REGISTERS
 * ─────────────────
 *   EvReg — an ID + type + confidence + optional name.
 *   Temps are numbered: t0, t1, t2, …
 *   Named regs map to source-level bindings: x, y, fact.
 *   The special reg EV_REG_VOID (id=0) means "no value".
 *
 * CONFIDENCE PROPAGATION
 * ──────────────────────
 *   Every EvReg has a confidence field (0..256).
 *   The propagation rule:
 *     binary op:   conf(dest) = min(conf(src0), conf(src1))
 *     call:        conf(dest) = min(conf(fn), min(conf(args)))
 *     constant:    conf = E_CERTAIN (256) — program constants are certain
 *     external in: conf = E_INTAKE (120) — data from outside is not
 *   This flows at IR-build time, not at runtime.
 *
 * OWNERSHIP  (same rules as ir.h)
 * ────────────────────────────────
 *   All strings, block arrays, instr arrays: arena-owned.
 *   Callers never free individual instructions.
 *   ev_module_free() releases the arena and everything in it.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef EVER_TAC_H
#define EVER_TAC_H

#include <stdint.h>
#include <stddef.h>
#include "evalue.h"    /* EValue, ev_type            */
#include "ir.h"        /* EvNode, EvArena, EvNodeKind */

/* ─────────────────────────────────────────────
 * TAC OPCODES
 * The complete instruction set for the Ever interpreter layer.
 * Pattern-matched by the interpreter and by every transpiler backend.
 * ───────────────────────────────────────────── */

typedef enum {
    /* Value moves */
    OP_CONST  =  0,   /* dest = literal_value                         */
    OP_COPY   =  1,   /* dest = src0                                  */

    /* Arithmetic */
    OP_ADD    = 10,   /* dest = src0 + src1                           */
    OP_SUB    = 11,   /* dest = src0 - src1                           */
    OP_MUL    = 12,   /* dest = src0 * src1                           */
    OP_DIV    = 13,   /* dest = src0 / src1                           */
    OP_NEG    = 14,   /* dest = -src0                                 */

    /* Comparison  (result is BOOL) */
    OP_LT     = 20,
    OP_GT     = 21,
    OP_LTE    = 22,
    OP_GTE    = 23,
    OP_EQ     = 24,
    OP_NEQ    = 25,

    /* Control flow */
    OP_LABEL  = 30,   /* label declaration (block start marker)       */
    OP_JUMP   = 31,   /* unconditional: goto label_id                 */
    OP_JUMP_IF= 32,   /* if src0 goto true_label else false_label     */
    OP_RETURN = 33,   /* return src0                                  */

    /* Calls */
    OP_CALL   = 40,   /* dest = name(args[0..nargs-1])                */
    OP_ARG    = 41,   /* push arg before CALL (used by some backends) */

    /* Confidence */
    OP_CONF   = 50,   /* dest = confidence_of(src0)  → INT 0..256    */
    OP_TRUST  = 51,   /* dest = src0 with confidence clamped to src1  */

    /* Scope / binding */
    OP_LOAD   = 60,   /* dest = scope[name]                           */
    OP_STORE  = 61,   /* scope[name] = src0                           */
    OP_DEF_FN = 62,   /* register function name in scope              */

    /* Composite */
    OP_LIST   = 70,   /* dest = [args...]                             */
    OP_RECORD = 71,   /* dest = {keys[i]: args[i]}                   */
    OP_GET    = 72,   /* dest = src0[key]                             */
    OP_SET    = 73,   /* dest[key] = src1                             */

    /* Error / unknown */
    OP_NOP    = 99,
    OP_ERR    = 100,
} EvOpcode;

const char *ev_opcode_name(EvOpcode op);
int         ev_opcode_is_binary(EvOpcode op);
int         ev_opcode_is_cmp(EvOpcode op);
int         ev_opcode_is_branch(EvOpcode op);

/* ─────────────────────────────────────────────
 * VIRTUAL REGISTERS
 * ───────────────────────────────────────────── */

#define EV_REG_VOID   0    /* "no value" — not a real register         */
#define EV_REG_FIRST  1    /* first usable register id                  */

typedef struct {
    int32_t     id;          /* unique within a function; 0=void        */
    int32_t     type;        /* ev_type tag: INT/REAL/BOOL/TEXT/VOID/…  */
    int16_t     confidence;  /* 0..256                                  */
    int16_t     _pad;
    const char *name;        /* human name or NULL for temps (t0, t1…)  */
} EvReg;

EvReg ev_reg_void(void);
EvReg ev_reg_temp(int32_t id, int32_t type, int16_t conf);
EvReg ev_reg_named(int32_t id, const char *name,
                   int32_t type, int16_t conf, EvArena *a);
int   ev_reg_is_void(EvReg r);

/* ─────────────────────────────────────────────
 * ONE INSTRUCTION
 * ───────────────────────────────────────────── */

#define EV_INSTR_MAXARGS 16

typedef struct {
    EvOpcode    op;
    EvReg       dest;         /* result register; ev_reg_void() if none */
    EvReg       src0;         /* first source (or only source)           */
    EvReg       src1;         /* second source (void if not used)        */

    /* For CONST: inline literal */
    EValue      literal;

    /* For CALL / DEF_FN / LOAD / STORE: name */
    const char *name;

    /* For CALL / LIST / RECORD: variable-length argument list */
    EvReg      *args;         /* arena-allocated                         */
    int32_t     nargs;

    /* For RECORD: parallel key array */
    const char **keys;

    /* For JUMP / JUMP_IF: target block ids */
    int32_t     true_label;   /* block id for true branch                */
    int32_t     false_label;  /* block id for false branch               */

    /* Source position */
    int32_t     line;
} EvInstr;

/* ─────────────────────────────────────────────
 * BASIC BLOCK
 * A linear sequence of instructions with exactly one exit.
 * ───────────────────────────────────────────── */

typedef struct {
    int32_t    id;           /* block id, matches OP_LABEL               */
    EvInstr   *instrs;       /* arena-allocated array                    */
    int32_t    len;
    int32_t    cap;
    /* Successors derived from the exit instruction */
    int32_t    succ[2];      /* block ids; -1 = none                     */
    int32_t    nsucc;
} EvBlock;

/* ─────────────────────────────────────────────
 * FUNCTION
 * ───────────────────────────────────────────── */

typedef struct {
    const char  *name;
    const char **params;     /* arena-owned                             */
    int32_t      nparam;
    int32_t      param_types[EV_INSTR_MAXARGS]; /* ev_type per param   */

    EvBlock    **blocks;     /* arena-allocated block pointer array      */
    int32_t      nblocks;
    int32_t      block_cap;

    int32_t      reg_counter; /* next temp id to assign                 */
    int16_t      confidence;  /* function's own trust level             */
    int16_t      _pad;
    EvArena     *arena;
} EvFunc;

/* ─────────────────────────────────────────────
 * MODULE
 * ───────────────────────────────────────────── */

typedef struct {
    const char  *name;
    EvFunc     **funcs;
    int32_t      nfuncs;
    int32_t      func_cap;
    EvFunc      *global_body; /* top-level statements as implicit fn     */
    EvArena     *arena;
} EvModule;

/* ─────────────────────────────────────────────
 * BUILDER — emit instructions into a function / block
 * ───────────────────────────────────────────── */

typedef struct {
    EvModule *module;
    EvFunc   *func;
    EvBlock  *block;          /* current block being built              */
} EvBuilder;

/* Lifecycle */
EvModule  *ev_module_new(const char *name, EvArena *arena);
void       ev_module_free(EvModule *m);      /* frees arena + everything */
EvFunc    *ev_module_add_func(EvModule *m, const char *name,
                               const char **params, int32_t np);
EvBlock   *ev_func_new_block(EvFunc *f);
EvBuilder  ev_builder(EvModule *m, EvFunc *f, EvBlock *b);
void       ev_builder_switch_block(EvBuilder *b, EvBlock *blk);

/* Register allocation */
EvReg ev_next_reg(EvBuilder *b, int32_t type, int16_t conf);

/* Emit instructions (all arena-alloc, return dest reg) */
EvReg ev_emit_const(EvBuilder *b, EValue lit, int32_t line);
EvReg ev_emit_copy(EvBuilder *b, EvReg src, int32_t line);
EvReg ev_emit_binop(EvBuilder *b, EvOpcode op,
                    EvReg src0, EvReg src1, int32_t line);
EvReg ev_emit_call(EvBuilder *b, const char *name,
                   EvReg *args, int32_t nargs, int32_t line);
void  ev_emit_return(EvBuilder *b, EvReg src, int32_t line);
void  ev_emit_jump(EvBuilder *b, int32_t label_id, int32_t line);
void  ev_emit_jump_if(EvBuilder *b, EvReg cond,
                      int32_t true_lbl, int32_t false_lbl, int32_t line);
EvReg ev_emit_load(EvBuilder *b, const char *name, int32_t type,
                   int16_t conf, int32_t line);
void  ev_emit_store(EvBuilder *b, const char *name, EvReg src, int32_t line);
void  ev_emit_def_fn(EvBuilder *b, const char *name, int32_t line);

/* ─────────────────────────────────────────────
 * LOWERING  — EvNode AST → EvTAC
 * ───────────────────────────────────────────── */

/*
 * ev_lower_node — recursively lower one EvNode into TAC instructions.
 * Returns the register holding the result (ev_reg_void if statement).
 * Called by ev_lower_func which drives the whole-function lowering.
 */
EvReg ev_lower_node(EvBuilder *b, const EvNode *n);

/*
 * ev_lower_func — lower an EvNode DEF into an EvFunc with basic blocks.
 * fn_node must have kind EV_NODE_DEF.
 */
EvFunc *ev_lower_func(EvModule *m, const EvNode *fn_node);

/*
 * ev_lower_module — lower all DEF nodes at the top level of a parse
 * result into a complete EvModule, with a global_body block for
 * non-def statements.
 */
EvModule *ev_lower_module(const char *name, EvNode *root, EvArena *arena);

/* ─────────────────────────────────────────────
 * OPTIMISATION PASSES
 * Each pass operates on one EvFunc. They are composable and order-
 * independent (within documented constraints).
 * ───────────────────────────────────────────── */

/* Pass 1: constant folding — evaluate compile-time-known ops */
int ev_pass_const_fold(EvFunc *f);

/* Pass 2: dead-register elimination — remove instructions whose
           dest reg is never used */
int ev_pass_dead_regs(EvFunc *f);

/* Pass 3: confidence propagation — fill every dest reg's confidence
           from its operands using the TAC propagation rules */
int ev_pass_conf_prop(EvFunc *f);

/* Run all passes in order. Returns total number of changes made. */
int ev_optimise(EvFunc *f);

/* ─────────────────────────────────────────────
 * INTERPRETER  — execute an EvModule directly
 * (no machine code, no bytecode — pure TAC evaluation)
 * ───────────────────────────────────────────── */

typedef struct EvInterp EvInterp;

EvInterp *ev_interp_new(EvModule *m);
void      ev_interp_free(EvInterp *ip);

/* Bind an argument and call a function by name */
EValue    ev_interp_call(EvInterp *ip, const char *fn_name,
                          EValue *args, int32_t nargs);

/* Execute the module's global body */
EValue    ev_interp_run(EvInterp *ip);

/* ─────────────────────────────────────────────
 * PRETTY PRINTER — for debugging and teaching
 * ───────────────────────────────────────────── */

void ev_print_instr(const EvInstr *i, const EvBlock *b);
void ev_print_block(const EvBlock *b);
void ev_print_func(const EvFunc *f);
void ev_print_module(const EvModule *m);

#endif /* EVER_TAC_H */
