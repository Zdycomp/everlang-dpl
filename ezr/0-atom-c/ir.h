/*
 * ir.h — Ever / Tapestry, the platform-independent intermediate representation
 *
 * The firewall between the parser and every runtime layer.
 *
 * PROBLEM BEING SOLVED
 * --------------------
 * Before this file existed:
 *
 *   - syntax.py called `from ever import e_equiv` INSIDE eval_ast().
 *     The parser was importing the runtime at execution time. Stages 1-3
 *     and stage 4 were tangled.
 *
 *   - C and C++ had no IR at all. They received strings or e_particle
 *     structs, never a parsed tree. ever.rb and ever.py produced different
 *     internal representations. There was no shared intermediate form.
 *
 *   - The ev_pool was a global (g_pool). Global state means ownership is
 *     nobody's — any layer can corrupt it silently.
 *
 *   - Python's encode() returned a buffer Python still owned. C received
 *     a pointer into that buffer. If Python GC collected the buffer before
 *     C finished reading, C read freed memory. A real segfault path.
 *
 * WHAT THIS FILE PROVIDES
 * -----------------------
 * 1. EvNode — a platform-independent IR that the C, C++, Python and Ruby
 *    layers all produce and consume. The parser emits EvNodes. The
 *    execution engine consumes EvNodes. Neither side needs to know what
 *    language the other is implemented in.
 *
 * 2. EvArena — a per-request arena allocator. One arena per
 *    parse/execute cycle. The arena owns everything allocated in that
 *    cycle. When the cycle ends, ev_arena_free() releases it all in one
 *    call. No GC races. No shared global. Ownership is explicit and
 *    lifetime-bounded.
 *
 * OWNERSHIP RULES (stated once, enforced everywhere)
 * ---------------------------------------------------
 *   RULE 1: Every allocation goes through ev_arena_alloc().
 *           malloc/calloc/new are not called directly by parser or execution
 *           code. Only the arena implementation calls them.
 *
 *   RULE 2: The arena owns its memory. Callers may READ arena memory as
 *           long as the arena is alive. They may not FREE it.
 *
 *   RULE 3: Cross-language boundaries copy, never alias.
 *           Python never passes a pointer into a buffer it still owns to C.
 *           C never returns a raw pointer into Python-managed memory.
 *           The ABI layer copies into arena memory before handing to C.
 *
 *   RULE 4: One arena per request. Parser creates it. Executor receives it.
 *           Caller frees it when the result has been consumed.
 *
 *   RULE 5: The ev_pool is gone from the global scope. Composites live in
 *           arenas. The global g_pool in evalue.c is a legacy fallback that
 *           no new code should use.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef EVER_IR_H
#define EVER_IR_H

#include <stdint.h>
#include <stddef.h>
#include "tapestry.h"
#include "evalue.h"

/* ─────────────────────────────────────────────
 * ARENA ALLOCATOR
 *
 * A slab-based bump allocator. All allocations during a parse/execute
 * cycle go through one arena. ev_arena_free() releases everything at once.
 * ───────────────────────────────────────────── */

#define EV_ARENA_SLAB_SIZE (64 * 1024)   /* 64 KB per slab */
#define EV_ARENA_MAX_SLABS 64

typedef struct ev_slab {
    uint8_t          *mem;
    size_t            used;
    size_t            cap;
    struct ev_slab   *next;
} ev_slab;

typedef struct {
    ev_slab  *head;
    size_t    total_allocated;
    size_t    total_freed;
    int       slab_count;
    const char *debug_tag;    /* which request owns this arena */
} EvArena;

EvArena *ev_arena_new(const char *tag);
void    *ev_arena_alloc(EvArena *a, size_t sz);
char    *ev_arena_strdup(EvArena *a, const char *s);
void     ev_arena_free(EvArena *a);   /* releases ALL memory in one call */
void     ev_arena_stats(const EvArena *a, char *buf, size_t cap);

/* ─────────────────────────────────────────────
 * NODE KINDS — the complete Ever grammar in one enum
 *
 * Every construct the parser can produce maps to exactly one EvNodeKind.
 * The execution engine switches on this value only; it never inspects
 * platform types.
 * ───────────────────────────────────────────── */

typedef enum {
    /* Literals */
    EV_NODE_VOID   = 0,
    EV_NODE_BOOL   = 1,
    EV_NODE_INT    = 2,
    EV_NODE_REAL   = 3,
    EV_NODE_TEXT   = 4,

    /* Binding */
    EV_NODE_VAR    = 10,   /* variable reference */
    EV_NODE_DEF    = 11,   /* function definition */
    EV_NODE_CALL   = 12,   /* function application */

    /* Arithmetic and comparison */
    EV_NODE_ADD    = 20,
    EV_NODE_SUB    = 21,
    EV_NODE_MUL    = 22,
    EV_NODE_DIV    = 23,
    EV_NODE_LT     = 24,
    EV_NODE_GT     = 25,
    EV_NODE_LTE    = 26,
    EV_NODE_GTE    = 27,
    EV_NODE_EQ     = 28,
    EV_NODE_NEQ    = 29,

    /* Control */
    EV_NODE_IF     = 30,   /* if/then/else */

    /* Composite construction */
    EV_NODE_LIST   = 40,   /* list literal  [a, b, c]   */
    EV_NODE_RECORD = 41,   /* record literal {k:v, ...} */

    /* Ever-specific */
    EV_NODE_Z      = 50,   /* explicit unknown */
    EV_NODE_ANCHOR = 51,   /* anchor a binding */
    EV_NODE_ASSM   = 52,   /* assimilate to another language */

    EV_NODE_ERR    = 99,   /* parse/semantic error node */
} EvNodeKind;

const char *ev_node_kind_name(EvNodeKind k);

/* ─────────────────────────────────────────────
 * EvNode — the IR node
 *
 * All strings are arena-owned. No platform objects. No GC handles.
 * An EvNode tree is fully described by its own memory and the arena
 * that backs it.
 * ───────────────────────────────────────────── */

typedef struct EvNode EvNode;

struct EvNode {
    EvNodeKind  kind;
    int32_t     line;          /* source line, for error messages       */

    /* Literal payload — which field is live depends on kind */
    union {
        int32_t  as_bool;      /* EV_NODE_BOOL                          */
        int64_t  as_int;       /* EV_NODE_INT                           */
        double   as_real;      /* EV_NODE_REAL                          */
    } lit;
    const char  *str;          /* EV_NODE_TEXT, VAR name, DEF name,
                                  CALL name, field name in RECORD        */

    /* Children — arena-allocated arrays */
    EvNode     **children;     /* args for CALL, elements for LIST/RECORD */
    int32_t     child_count;
    int32_t     child_cap;

    /* For DEF: parameter list */
    const char **params;
    int32_t      param_count;

    /* For RECORD: parallel key names for children */
    const char **keys;

    /* Structural metrics — computed by the semantic pass, used by
       synthesis (replaces the string-based shape/skeleton system) */
    int32_t     size;          /* node count in this subtree            */
    int32_t     depth;         /* tree depth                            */
    const char *shape;         /* structural shape, arena-owned string  */

    /* For ERR: the message */
    const char *error;

    /* Owning arena — never NULL */
    EvArena    *arena;
};

/* ─────────────────────────────────────────────
 * EvNode constructors — all arena-allocated
 * ───────────────────────────────────────────── */

EvNode *ev_node_new(EvArena *a, EvNodeKind kind, int32_t line);
EvNode *ev_node_bool(EvArena *a, int32_t b, int32_t line);
EvNode *ev_node_int(EvArena *a, int64_t v, int32_t line);
EvNode *ev_node_real(EvArena *a, double v, int32_t line);
EvNode *ev_node_text(EvArena *a, const char *s, int32_t line);
EvNode *ev_node_var(EvArena *a, const char *name, int32_t line);
EvNode *ev_node_def(EvArena *a, const char *name,
                    const char **params, int32_t nparam,
                    EvNode *body, int32_t line);
EvNode *ev_node_call(EvArena *a, const char *name,
                     EvNode **args, int32_t nargs, int32_t line);
EvNode *ev_node_binop(EvArena *a, EvNodeKind op,
                      EvNode *left, EvNode *right, int32_t line);
EvNode *ev_node_if(EvArena *a, EvNode *cond,
                   EvNode *then_n, EvNode *else_n, int32_t line);
EvNode *ev_node_error(EvArena *a, const char *msg, int32_t line);
int     ev_node_add_child(EvNode *n, EvNode *child);

/* ─────────────────────────────────────────────
 * Structural metrics (filled by semantic pass)
 * ───────────────────────────────────────────── */

void        ev_node_measure(EvNode *n);   /* fills size and depth */
const char *ev_node_shape(EvNode *n, EvArena *a);  /* structural shape */
const char *ev_node_skeleton(EvNode *n, EvArena *a); /* shape with consts erased */

/* ─────────────────────────────────────────────
 * Serialisation — EvNode tree to/from flat bytes
 *
 * This is the canonical cross-language IR transfer format. The Python
 * parser emits bytes; the C execution engine deserialises them. Neither
 * side needs to know the other's language.
 *
 * Wire format: little-endian self-describing byte stream.
 *   [1 byte: kind] [4 bytes: line] [payload depending on kind]
 * ───────────────────────────────────────────── */

#define EV_IR_BUF_MAX (256 * 1024)

int32_t ev_ir_serialise(const EvNode *n, uint8_t *buf, int32_t cap);
EvNode *ev_ir_deserialise(const uint8_t *buf, int32_t len,
                           int32_t *consumed, EvArena *a);

/* ─────────────────────────────────────────────
 * Parse result — returned to callers
 *
 * The arena lives as long as the result. The caller calls
 * ev_result_free() when done. All memory goes with it.
 * ───────────────────────────────────────────── */

typedef struct {
    EvNode  *root;          /* NULL on error                         */
    EvArena *arena;         /* owns root and all its descendants     */
    char    *error;         /* NULL on success, arena-owned on error */
    int32_t  error_line;
    int32_t  node_count;
    int32_t  depth;
} EvResult;

EvResult *ev_result_new(const char *src_tag);
void      ev_result_free(EvResult *r);  /* frees arena + everything */

#endif /* EVER_IR_H */
