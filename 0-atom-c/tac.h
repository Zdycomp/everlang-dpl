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

#include "repair.h"
#define E_REPAIR_PLAIN    8   /* mirrors repair.py: E_REPAIR_PLAIN */
#define E_REPAIR_INFERRED 32  /* mirrors repair.py: E_REPAIR_INFERRED */
#include <stdint.h>
#include <stddef.h>
#include "evalue.h"    /* EValue, ev_type            */
#include "ir.h"

extern EvRepairRegistry *g_repair_registry;        /* EvNode, EvArena, EvNodeKind */

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
    OP_HEAL     = 100,   /* block terminator: src0 trusted ? true : false */
    OP_RECOVERY = 101,   /* query registry for repair of src0 using src1 */
    OP_ERR      = 102,
    OP_REPAIR_STATE = 103,  /* dest = action code of the last repair (EV_HEAL_*) */
    OP_CAUSE_OPEN   = 104,  /* a heal's primary begins: push a cause frame        */
    OP_CAUSE_CLOSE  = 105,  /* pop it; dest = its reason (TEXT), or void: drop    */
    OP_NOTE         = 106,  /* name: a failure happened here; note it in the frame */
    OP_SETTLE       = 107,  /* src0 void: hand src1's reason (TEXT) up the frame  */
    OP_REPAIR_RESTORE = 108, /* src0 = EV_HEAL_* of this heal: re-record it after its fallback ran */
} EvOpcode;

/* The order's outcome for one heal (evaluate → plan → execute). The codes are
 * what OP_REPAIR_STATE yields, so the lowered branch never reads a value's
 * truthiness: a fixture of 0 or false is still a successful repair. */
#define EV_HEAL_KEEP       0   /* primary trusted; no repair ran              */
#define EV_HEAL_SUBSTITUTE 1   /* archived fixture ran; its value is trusted   */
#define EV_HEAL_FALLBACK   2   /* no usable repair; the fallback ran           */
#define EV_HEAL_FAILED     3   /* a repair was chosen but could not run: z     */

/* Trace of the heals a program has run: how many, and the last outcome. */
typedef struct {
    int32_t count;      /* heals evaluated in this interpreter          */
    int32_t action;     /* EV_HEAL_* of the most recent heal            */
    int16_t conf;       /* confidence the most recent heal produced     */
} EvHealTrace;

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
    EvReg       src2;         /* third source (void if not used)         */

    /* For CONST: inline literal */
    EValue      literal;

    /* For CALL / DEF_FN / LOAD / STORE: name */
    const char *name;

    /* For CALL / LIST / RECORD: variable-length argument list */
    EvReg      *args;         /* arena-allocated                         */
    int32_t     nargs;

    /* For RECORD: parallel key array */
    const char **keys;

    /* For JUMP / JUMP_IF / HEAL: target block ids */
    int32_t     true_label;   /* block id for true branch (HEAL: trusted) */
    int32_t     false_label;  /* block id for false branch (HEAL: repair) */
    int32_t     unknown_label; /* JUMP_IF: block for an unknown (z) cond  */

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

    /* SEMANTICS §4: the function's own state. The front end supplies the
       measure; the Examples runner and anchors set the rest. */
    int32_t      active;          /* activations of this function on the stack   */
    int32_t      anchor_id;       /* 0 = unanchored (§4.4)                       */
    int32_t      measure;         /* parameter that strictly decreases, or -1    */
    int32_t      has_last;        /* the innermost activation has a measure      */
    double       last_measure;    /* that activation's measure                   */
    int32_t      examples_passed;
    int32_t      examples_failed;
    int32_t      refused;         /* an anchor was refused: z for good (§4.4)    */
    char         reason[160];     /* why it is z, when it is                     */
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
    const char  *lower_error;  /* first lowering refusal; NULL if none   */
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
/* A constant that stands for a value with an earned confidence (a literal IR
   node carries it). ev_emit_const is this with E_CERTAIN. */
EvReg ev_emit_const_conf(EvBuilder *b, EValue lit, int16_t conf, int32_t line);
EvReg ev_emit_copy(EvBuilder *b, EvReg src, int32_t line);
EvReg ev_emit_binop(EvBuilder *b, EvOpcode op,
                    EvReg src0, EvReg src1, int32_t line);
EvReg ev_emit_recovery(EvBuilder *b, EvReg primary, EvReg strategy,
                       EvReg reason, int32_t line);
EvReg ev_emit_repair_state(EvBuilder *b, int32_t line);
/* This heal's own outcome, re-recorded once its fallback has run. A heal inside
   the fallback records its outcome later, so without this the trace would
   report the inner heal's action. */
void  ev_emit_repair_restore(EvBuilder *b, EvReg outcome, int32_t line);
/* The cause frame of a heal (see OP_CAUSE_OPEN). Open before the primary is
   lowered; close after it, which yields the reason; drop when a sub-evaluation
   is absorbed by the heal. note names a failure; settle hands a z reason up. */
void  ev_emit_cause_open(EvBuilder *b, int32_t line);
EvReg ev_emit_cause_close(EvBuilder *b, EvReg primary, int32_t line);
void  ev_emit_cause_drop(EvBuilder *b, int32_t line);
void  ev_emit_note(EvBuilder *b, const char *reason, int32_t line);
void  ev_emit_settle(EvBuilder *b, EvReg result, EvReg reason, int32_t line);
EvReg ev_emit_call(EvBuilder *b, const char *name,
                   EvReg *args, int32_t nargs, int32_t line);
void  ev_emit_return(EvBuilder *b, EvReg src, int32_t line);
void  ev_emit_jump(EvBuilder *b, int32_t label_id, int32_t line);
void  ev_emit_jump_if(EvBuilder *b, EvReg cond, int32_t true_lbl,
                      int32_t false_lbl, int32_t unknown_lbl, int32_t line);
void  ev_emit_heal(EvBuilder *b, EvReg primary, int32_t trusted_lbl,
                   int32_t repair_lbl, int32_t line);
EvReg ev_emit_load(EvBuilder *b, const char *name, int32_t type,
                   int16_t conf, int32_t line);
void  ev_emit_store(EvBuilder *b, const char *name, EvReg src, int32_t line);
void  ev_emit_def_fn(EvBuilder *b, const char *name, int32_t line);

/* Record a lowering refusal on the builder's module. Lowering functions
   return a void register on refusal; ev_lower_module returns NULL. */
void  ev_lower_fail(EvBuilder *b, const char *msg);

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
EvModule *ev_lower_module(const char *name, EvNode *root);

/* ─────────────────────────────────────────────
 * OPTIMISATION PASSES
 * Each pass operates on one EvFunc. They are composable and order-
 * independent (within documented constraints).
 * ───────────────────────────────────────────── */

/* Pass 1: constant folding — evaluate compile-time-known ops */
int ev_pass_const_fold(EvFunc *f);

/* Pass 2: dead-code elimination — a JUMP_IF on a CONST becomes a JUMP
 * to the arm the interpreter would take, and blocks no longer reachable
 * from block 0 are cleared. Runs after folding, before dead registers. */
int ev_pass_dead_code(EvFunc *f);

/* Pass 3: dead-register elimination — remove instructions whose
           dest reg is never used */
int ev_pass_dead_regs(EvFunc *f);

/* SEMANTICS §4 on the C side. The front end supplies the static fact (the
   measure). Examples and anchors are earned through these calls, which pass
   the same call gate as OP_CALL, so an Example takes the path a real call takes. */
EvFunc *ev_module_func(EvModule *m, const char *fname);
void    ev_module_set_measure(EvModule *m, const char *fname, int32_t param_index);
int     ev_module_example(EvModule *m, const char *fname, const EValue *args,
                          const int16_t *arg_conf, int32_t nargs, EValue expect);
int     ev_module_anchor(EvModule *m, const char *fname);

/* Pass 4: confidence propagation — fill every dest reg's confidence
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

/* The heal trace of an interpreter: count and last outcome */
EvHealTrace ev_interp_heal_trace(const EvInterp *ip);
/* Runtime confidence of the value the last RETURN gave (0 for z). Read it
   after ev_interp_run: a build-time register confidence is not what ran. */
int16_t ev_interp_ret_conf(const EvInterp *ip);

/* ─────────────────────────────────────────────
 * PRETTY PRINTER — for debugging and teaching
 * ───────────────────────────────────────────── */

void ev_print_instr(const EvInstr *i, const EvBlock *b);
void ev_print_block(const EvBlock *b);
void ev_print_func(const EvFunc *f);
void ev_print_module(const EvModule *m);

#endif /* EVER_TAC_H */
