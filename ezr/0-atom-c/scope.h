/*
 * scope.h — Ever / Tapestry, universal map / global scope
 *
 * THE UNIVERSAL MAP.
 *
 * EvScope is an open-addressing hash map that is the global scope and every
 * local scope in the Ever runtime. It maps string names to their definitions —
 * variables, functions, classes, modules, builtins — identically across C,
 * C++, Python, Ruby, SQL, and HTML.
 *
 * DESIGN
 * ──────
 * Hash function : FNV-1a 32-bit.  No stdlib dependency.  Deterministic.
 * Collision      : Linear probe.   Cache-friendly.  O(1) amortised.
 * Capacity       : Power of 2.     Probe is slot & (cap-1), no modulo.
 * Load factor    : Resize at 75 %.  Rehash doubles capacity.
 * Deletion       : Tombstones (TOMB state).  Probe does not stop at TOMB.
 * Scope chain    : Every EvScope carries parent*.  NULL = global root.
 *                  ev_scope_lookup() walks the chain upward.
 *
 * OWNERSHIP  (same rules as ir.h)
 * ────────────────────────────────
 * All strings and EvNode pointers passed to ev_scope_set() must be
 * arena-owned.  The scope itself is arena-allocated via ev_scope_new().
 * ev_scope_free() releases the slot array; it does NOT free the arena —
 * the caller does that when the request completes.
 *
 * WIRE FORMAT
 * ───────────
 * ev_scope_serialise() flattens the scope to an EValue(RECORD) using the
 * same wire format as evalue.c, so the Python layer can read/write the
 * scope over the ABI boundary without a separate protocol.
 *
 * SCOPE KINDS
 * ───────────
 *   EV_SK_VAR     ordinary binding  (let x = 42)
 *   EV_SK_FN      function          (def f(n) = …)  carries EvNode* body
 *   EV_SK_CLASS   class definition  (class Foo { … })
 *   EV_SK_MODULE  module/namespace  (module Math { … })
 *   EV_SK_BUILTIN built-in op       (print, assert, …)
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef EVER_SCOPE_H
#define EVER_SCOPE_H

#include "evalue.h"   /* EValue, ev_pool       */
#include "ir.h"       /* EvNode, EvArena        */

/* ─────────────────────────────────────────────
 * Scope entry kind
 * ───────────────────────────────────────────── */

typedef enum {
    EV_SK_VAR     = 0,
    EV_SK_FN      = 1,
    EV_SK_CLASS   = 2,
    EV_SK_MODULE  = 3,
    EV_SK_BUILTIN = 4,
} EvScopeKind;

const char *ev_scope_kind_name(EvScopeKind k);

/* ─────────────────────────────────────────────
 * Slot states (open-addressing bookkeeping)
 * ───────────────────────────────────────────── */

#define EV_SLOT_EMPTY  0   /* never used                              */
#define EV_SLOT_LIVE   1   /* holds a valid entry                     */
#define EV_SLOT_TOMB   2   /* deleted; probe continues through TOMB   */

/* ─────────────────────────────────────────────
 * One entry in the hash table
 * ───────────────────────────────────────────── */

typedef struct {
    uint8_t      state;        /* EV_SLOT_EMPTY / LIVE / TOMB         */
    uint8_t      kind;         /* EvScopeKind                         */
    int16_t      lang;         /* e_lang of the defining layer        */
    int16_t      confidence;   /* 0..256                              */
    int16_t      _pad;         /* explicit padding                    */
    uint32_t     hash;         /* cached FNV-1a hash of key           */
    uint32_t     anchor_id;    /* 0 = unanchored                      */
    const char  *key;          /* arena-owned name string             */
    EValue       value;        /* the unified variant (208 bytes)     */
    EvNode      *node;         /* fn body, class body — NULL for VAR  */
    const char **params;       /* fn params, arena-owned (NULL if VAR)*/
    int32_t      param_count;
} EvScopeEntry;

/* ─────────────────────────────────────────────
 * The hash map / scope
 * ───────────────────────────────────────────── */

#define EV_SCOPE_INIT_CAP  64    /* must be a power of 2              */
#define EV_SCOPE_LOAD_NUM   3    /* resize when used > cap * 3 / 4    */
#define EV_SCOPE_LOAD_DEN   4

typedef struct EvScope {
    EvScopeEntry  *slots;        /* heap-allocated slot array          */
    int32_t        cap;          /* total slots (power of 2)           */
    int32_t        used;         /* LIVE entries                       */
    int32_t        tombs;        /* TOMB entries (count for probe math)*/
    EvArena       *arena;        /* arena that owns all strings/nodes  */
    struct EvScope *parent;      /* enclosing scope; NULL for global   */
    const char    *name;         /* debug label ("global", "fn:fact")  */
    int32_t        depth;        /* 0 = global                         */
} EvScope;

/* ─────────────────────────────────────────────
 * Lifecycle
 * ───────────────────────────────────────────── */

/* Create a new scope.  arena must outlive the scope. */
EvScope *ev_scope_new(EvArena *arena, EvScope *parent, const char *name);

/* Release the slot array.  Does NOT free the arena. */
void ev_scope_free(EvScope *scope);

/* ─────────────────────────────────────────────
 * Insert / update / delete
 * ───────────────────────────────────────────── */

/*
 * ev_scope_set — bind a name to a value in this scope (not the chain).
 *
 * key, value, node, params must all be arena-owned.
 * Returns 1 on success, 0 on OOM.
 */
int ev_scope_set(EvScope *scope,
                 const char *key,
                 EvScopeKind kind,
                 EValue value,
                 int16_t confidence,
                 int16_t lang,
                 EvNode *node,
                 const char **params,
                 int32_t param_count);

/* Convenience wrappers */
int ev_scope_set_var(EvScope *s, const char *key, EValue val,
                     int16_t conf, int16_t lang);
int ev_scope_set_fn(EvScope *s, const char *name, EvNode *body,
                    const char **params, int32_t np,
                    int16_t conf, int16_t lang);
int ev_scope_set_module(EvScope *s, const char *name, EvScope *module_scope,
                        int16_t lang);

/* Remove a binding from this scope.  Returns 1 if it was present. */
int ev_scope_delete(EvScope *scope, const char *key);

/* ─────────────────────────────────────────────
 * Lookup
 * ───────────────────────────────────────────── */

/*
 * ev_scope_get — look up in THIS scope only.
 * Returns pointer to the live entry, or NULL if not found.
 */
EvScopeEntry *ev_scope_get(EvScope *scope, const char *key);

/*
 * ev_scope_lookup — walk the scope chain upward.
 * Returns the first live entry found, or NULL.
 */
EvScopeEntry *ev_scope_lookup(EvScope *scope, const char *key);

/* Typed helpers that also walk the chain */
EValue        ev_scope_get_value(EvScope *scope, const char *key);
EvNode       *ev_scope_get_fn(EvScope *scope, const char *name);
EvScope      *ev_scope_get_module(EvScope *scope, const char *name);

/* ─────────────────────────────────────────────
 * Iteration
 * ───────────────────────────────────────────── */

typedef void (*ev_scope_iter_fn)(const EvScopeEntry *entry, void *userdata);
void ev_scope_each(const EvScope *scope, ev_scope_iter_fn fn, void *userdata);

/* ─────────────────────────────────────────────
 * Wire format — scope ↔ EValue(RECORD)
 *
 * Converts the scope to/from an EValue(RECORD) so it can be sent over
 * the ABI boundary using the same wire protocol as evalue.c.
 * Values only — EvNode bodies are not serialised (they travel via ir.h).
 * ───────────────────────────────────────────── */

EValue  ev_scope_to_record(const EvScope *scope, ev_pool *pool);
int     ev_scope_from_record(EvScope *scope, const EValue *record,
                              ev_pool *pool, int16_t lang);

/* ─────────────────────────────────────────────
 * Diagnostics
 * ───────────────────────────────────────────── */

void ev_scope_dump(const EvScope *scope);
void ev_scope_stats(const EvScope *scope, char *buf, int32_t cap);

/* ─────────────────────────────────────────────
 * FNV-1a hash — exposed so tests and the Python layer can verify it
 * ───────────────────────────────────────────── */

uint32_t ev_fnv1a(const char *key);

#endif /* EVER_SCOPE_H */
