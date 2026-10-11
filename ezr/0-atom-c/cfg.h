/*
 * cfg.h — Ever / Tapestry, Control Flow Graph
 *
 * THE PROBLEM THIS SOLVES
 * ──────────────────────
 * The number one cause of app crashes is using a variable whose value
 * was never set — null pointer dereference, undefined data, "works on
 * my machine" bugs that only fire on the path the tester never took.
 *
 * A naive checker only asks: "was this name ever defined anywhere?"
 * That misses the real failure mode:
 *
 *   if condition then
 *     let x = compute()   ← x defined here
 *   else
 *     show "skipped"      ← x NOT defined here
 *   show x                ← CRASH: x undefined when condition = false
 *
 * DEFINITE ASSIGNMENT requires that a name be defined on EVERY PATH
 * from the start of the function to every use of that name.
 *
 * HOW THE CFG MAKES THIS CHECKABLE
 * ──────────────────────────────────
 * A Control Flow Graph turns an expression tree into a graph of
 * BasicBlocks connected by edges:
 *
 *   entry                 ← params are defined here
 *     │
 *   condition eval        ← one block, always executes
 *    ╱          ╲
 *  true          false    ← two blocks, one executes
 *    ╲          ╱
 *     join point          ← both paths arrive here
 *       │
 *   continuation
 *
 * At each join point we insert a Phi node:
 *   phi(x_from_true, x_from_false) → x_joined
 *
 * The DefinedSet at a join point = INTERSECTION of the DefinedSets of
 * all incoming blocks. If x is in the true-branch DefinedSet but not
 * the false-branch DefinedSet, x is NOT in the join DefinedSet.
 * Any use of x after the join is an error — before the program runs.
 *
 * EVER'S EXPRESSION LANGUAGE
 * ───────────────────────────
 * Ever is a pure expression language — every if has an else, and every
 * expression produces a value. This simplifies the CFG considerably:
 *
 *   - No statement-level control flow (no break, continue, goto)
 *   - Every branch produces a typed value
 *   - The only "maybe undefined" paths come from:
 *       (a) a name used before its definition (ordering error)
 *       (b) a name defined in only one branch of an if
 *       (c) a recursive call that might return Z on the base case
 *
 * OWNERSHIP
 * ──────────
 * All blocks and edges live in the CfgArena (which IS an EvArena).
 * One ev_arena_free() releases the entire CFG.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef EVER_CFG_H
#define EVER_CFG_H

#include <stdint.h>
#include <stddef.h>
#include "ir.h"       /* EvNode, EvArena */

/* ─────────────────────────────────────────────
 * Names (variable references within a CFG)
 *
 * Each distinct name in the program gets a NameId — a compact integer
 * index into the name table. Using integers instead of strings makes the
 * set operations (intersection, union, membership) fast and branchless.
 * ───────────────────────────────────────────── */

#define CFG_MAX_NAMES  256    /* max distinct names in one function   */
#define CFG_MAX_BLOCKS 1024   /* max basic blocks in one function     */
#define CFG_MAX_EDGES  2048   /* max edges in one CFG                 */
#define CFG_MAX_PHIS   512    /* max phi nodes in one CFG             */

typedef int16_t NameId;       /* -1 = invalid                         */

typedef struct {
    char      names[CFG_MAX_NAMES][64];
    int       count;
} NameTable;

NameId  name_intern(NameTable *t, const char *name);
NameId  name_find  (const NameTable *t, const char *name);
const char *name_str(const NameTable *t, NameId id);

/* ─────────────────────────────────────────────
 * DefinedSet — a bitset over NameIds
 *
 * A name N is in DefinedSet S if bit N of S is set.
 * The set fits in 4 uint64_t words (256 bits = 256 names).
 *
 * Intersection: MUST-define analysis — used at join points.
 *   join.defined = pred1.defined & pred2.defined
 *
 * Union: MAY-define analysis — used for liveness.
 *   live_out = union of (live_in of successors)
 * ───────────────────────────────────────────── */

#define DEFSET_WORDS  4   /* 4 × 64 = 256 bit positions */

typedef struct {
    uint64_t bits[DEFSET_WORDS];
} DefinedSet;

void    defset_clear    (DefinedSet *s);
void    defset_fill     (DefinedSet *s);   /* all 256 bits set */
void    defset_add      (DefinedSet *s, NameId id);
void    defset_remove   (DefinedSet *s, NameId id);
int     defset_has      (const DefinedSet *s, NameId id);
void    defset_intersect(DefinedSet *dst, const DefinedSet *src);
void    defset_union    (DefinedSet *dst, const DefinedSet *src);
int     defset_equal    (const DefinedSet *a, const DefinedSet *b);
int     defset_subset   (const DefinedSet *sub, const DefinedSet *super);

/* ─────────────────────────────────────────────
 * Phi node — at a join point, merges two versions of the same name
 *
 * phi(src_true, src_false) → dest
 *
 * Both src_true and src_false refer to the same name (same NameId)
 * but arriving from different predecessor blocks. After the phi, the
 * name is in scope regardless of which path was taken.
 * ───────────────────────────────────────────── */

typedef struct {
    NameId  name;        /* the name being merged                    */
    int32_t src_block[2];/* block indices of the two incoming values */
    int32_t dest_block;  /* the join block that holds this phi       */
} PhiNode;

/* ─────────────────────────────────────────────
 * BasicBlock — a maximal straight-line sequence with no branches
 *
 * A block has:
 *   - zero or more instructions (EvNodes that execute unconditionally)
 *   - a terminator: jump / branch / return
 *   - a DefinedSet computed by the dataflow pass (def_in, def_out)
 *   - a LiveSet (live_in, live_out)
 *   - a list of phi nodes at its head
 * ───────────────────────────────────────────── */

#define CFG_BLOCK_PREDS_MAX 2   /* max predecessors (binary branching only) */
#define CFG_BLOCK_SUCCS_MAX 2   /* max successors */
#define CFG_BLOCK_PHIS_MAX  32  /* max phis per block */
#define CFG_BLOCK_NODES_MAX 64  /* max IR nodes in one block */

typedef enum {
    CFG_TERM_JUMP   = 0,  /* unconditional jump to succ[0]           */
    CFG_TERM_BRANCH = 1,  /* cond branch: succ[0]=true, succ[1]=false*/
    CFG_TERM_RETURN = 2,  /* function return; value in ret_node      */
} CfgTermKind;

typedef struct CfgBlock {
    int32_t      id;
    const char  *label;        /* human-readable name for debug        */

    /* straight-line nodes (no branches) */
    EvNode      *nodes[CFG_BLOCK_NODES_MAX];
    int32_t      node_count;

    /* terminator */
    CfgTermKind  term;
    EvNode      *cond_node;    /* for BRANCH: the condition expression */
    EvNode      *ret_node;     /* for RETURN: the return expression    */
    int32_t      succ[CFG_BLOCK_SUCCS_MAX];  /* block ids             */
    int32_t      pred[CFG_BLOCK_PREDS_MAX];  /* block ids             */
    int32_t      succ_count;
    int32_t      pred_count;

    /* dataflow results (filled by cfg_analyse) */
    DefinedSet   def_gen;   /* names defined in this block            */
    DefinedSet   def_kill;  /* names that become undefined here       */
    DefinedSet   def_in;    /* names definitely defined before block  */
    DefinedSet   def_out;   /* names definitely defined after block   */

    /* liveness (filled by cfg_liveness) */
    DefinedSet   use;       /* names used before any def in block     */
    DefinedSet   live_in;
    DefinedSet   live_out;

    /* phi nodes at head of this block */
    PhiNode      phis[CFG_BLOCK_PHIS_MAX];
    int32_t      phi_count;
} CfgBlock;

/* ─────────────────────────────────────────────
 * DefError — a definite-assignment violation found by the analyser
 * ───────────────────────────────────────────── */

#define CFG_MAX_ERRORS 64

typedef enum {
    CFG_ERR_USE_BEFORE_DEF = 0,   /* name used before definition       */
    CFG_ERR_PARTIAL_DEF    = 1,   /* name defined in only one branch   */
    CFG_ERR_UNDEF_AFTER_JOIN = 2, /* name used after join; not in all  */
} CfgErrKind;

typedef struct {
    CfgErrKind   kind;
    NameId       name;
    int32_t      block_id;
    int32_t      line;
    char         message[128];
} DefError;

/* ─────────────────────────────────────────────
 * Cfg — the full control flow graph for one function
 * ───────────────────────────────────────────── */

typedef struct {
    EvArena    *arena;
    NameTable   names;
    CfgBlock   *blocks[CFG_MAX_BLOCKS];
    int32_t     block_count;
    int32_t     entry_id;   /* always 0 */
    int32_t     exit_id;    /* the return block */

    /* phi nodes (global list for easy iteration) */
    PhiNode    *phis[CFG_MAX_PHIS];
    int32_t     phi_count;

    /* errors found by cfg_analyse + cfg_check */
    DefError    errors[CFG_MAX_ERRORS];
    int32_t     error_count;

    /* summary */
    const char *fn_name;
    int32_t     param_count;
} Cfg;

/* ─────────────────────────────────────────────
 * API
 * ───────────────────────────────────────────── */

/* Allocate a new CFG for one function */
Cfg *cfg_new(EvArena *arena, const char *fn_name);

/* Build the CFG from an EvNode function def */
Cfg *cfg_build(EvNode *fn_def, EvArena *arena);

/* Allocate a new block inside cfg */
CfgBlock *cfg_block_new(Cfg *cfg, const char *label);

/* Connect two blocks */
void cfg_connect(Cfg *cfg, int32_t from_id, int32_t to_id);

/* ── Dataflow passes ── */

/* MUST-definition analysis (forward, intersection).
   Computes def_in and def_out for every block. */
void cfg_analyse(Cfg *cfg);

/* Liveness analysis (backward, union).
   Computes live_in and live_out for every block. */
void cfg_liveness(Cfg *cfg);

/* Insert phi nodes at join points for all names that need them. */
void cfg_insert_phis(Cfg *cfg);

/* ── The definite-assignment check ── */

/* Check every USE against def_in. Populate cfg->errors.
   Returns the number of errors found. */
int cfg_check_definite_assignment(Cfg *cfg);

/* ── Diagnostics ── */
void cfg_dump(const Cfg *cfg, const char *title);
void cfg_print_errors(const Cfg *cfg);

#endif /* EVER_CFG_H */
