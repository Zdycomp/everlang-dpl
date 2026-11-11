/*
 * scope.c — Ever / Tapestry, universal map / global scope
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "scope.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

/* ─────────────────────────────────────────────
 * FNV-1a 32-bit — the only hash function in this codebase
 * ───────────────────────────────────────────── */

uint32_t ev_fnv1a(const char *key) {
    uint32_t h = 0x811c9dc5u;
    while (*key) {
        h ^= (uint8_t)*key++;
        h *= 0x01000193u;
    }
    return h;
}

/* ─────────────────────────────────────────────
 * Kind name
 * ───────────────────────────────────────────── */

const char *ev_scope_kind_name(EvScopeKind k) {
    switch (k) {
        case EV_SK_VAR:     return "var";
        case EV_SK_FN:      return "fn";
        case EV_SK_CLASS:   return "class";
        case EV_SK_MODULE:  return "module";
        case EV_SK_BUILTIN: return "builtin";
        default:            return "?";
    }
}

/* ─────────────────────────────────────────────
 * Internal: find slot for key (LIVE or first empty/tomb for insert)
 * ───────────────────────────────────────────── */

/* Returns index of: LIVE slot with this hash+key, OR first TOMB seen
   during probe (for insert reuse), OR first EMPTY (for fresh insert). */
static int32_t find_slot(const EvScopeEntry *slots, int32_t cap,
                          uint32_t h, const char *key) {
    int32_t mask  = cap - 1;
    int32_t idx   = (int32_t)(h & (uint32_t)mask);
    int32_t tomb  = -1;

    for (int32_t i = 0; i < cap; i++) {
        int32_t s = (idx + i) & mask;
        if (slots[s].state == EV_SLOT_EMPTY) {
            return (tomb >= 0) ? tomb : s;
        }
        if (slots[s].state == EV_SLOT_TOMB) {
            if (tomb < 0) tomb = s;
            continue;
        }
        /* LIVE: compare hash first, then string */
        if (slots[s].hash == h && slots[s].key &&
                strcmp(slots[s].key, key) == 0) {
            return s;
        }
    }
    return (tomb >= 0) ? tomb : -1;   /* -1 = full (shouldn't happen) */
}

/* ─────────────────────────────────────────────
 * Internal: resize the slot array
 * ───────────────────────────────────────────── */

static int grow(EvScope *scope) {
    int32_t newcap = scope->cap * 2;
    EvScopeEntry *ns = (EvScopeEntry*)calloc((size_t)newcap,
                                              sizeof(EvScopeEntry));
    if (!ns) return 0;

    /* rehash all LIVE entries */
    for (int32_t i = 0; i < scope->cap; i++) {
        if (scope->slots[i].state != EV_SLOT_LIVE) continue;
        int32_t s = find_slot(ns, newcap,
                               scope->slots[i].hash,
                               scope->slots[i].key);
        if (s < 0) { free(ns); return 0; }
        ns[s] = scope->slots[i];
    }

    free(scope->slots);
    scope->slots  = ns;
    scope->cap    = newcap;
    scope->tombs  = 0;   /* tombstones cleared on resize */
    return 1;
}

/* ─────────────────────────────────────────────
 * Lifecycle
 * ───────────────────────────────────────────── */

EvScope *ev_scope_new(EvArena *arena, EvScope *parent, const char *name) {
    if (!arena) return NULL;
    EvScope *s = (EvScope*)ev_arena_alloc(arena, sizeof *s);
    if (!s) return NULL;

    s->slots  = (EvScopeEntry*)calloc(EV_SCOPE_INIT_CAP,
                                       sizeof(EvScopeEntry));
    if (!s->slots) return NULL;

    s->cap    = EV_SCOPE_INIT_CAP;
    s->used   = 0;
    s->tombs  = 0;
    s->arena  = arena;
    s->parent = parent;
    s->name   = ev_arena_strdup(arena, name ? name : "scope");
    s->depth  = parent ? parent->depth + 1 : 0;
    return s;
}

void ev_scope_free(EvScope *scope) {
    if (scope && scope->slots) {
        free(scope->slots);
        scope->slots = NULL;
    }
}

/* ─────────────────────────────────────────────
 * Insert / update
 * ───────────────────────────────────────────── */

int ev_scope_set(EvScope *scope,
                 const char *key,
                 EvScopeKind kind,
                 EValue value,
                 int16_t confidence,
                 int16_t lang,
                 EvNode *node,
                 const char **params,
                 int32_t param_count) {

    if (!scope || !key || !*key) return 0;

    /* resize before we get to 75 % load */
    if ((scope->used + scope->tombs) * EV_SCOPE_LOAD_DEN
            >= scope->cap * EV_SCOPE_LOAD_NUM) {
        if (!grow(scope)) return 0;
    }

    uint32_t h = ev_fnv1a(key);
    int32_t  s = find_slot(scope->slots, scope->cap, h, key);
    if (s < 0) return 0;

    int is_new = (scope->slots[s].state != EV_SLOT_LIVE);

    scope->slots[s].state       = EV_SLOT_LIVE;
    scope->slots[s].kind        = (uint8_t)kind;
    scope->slots[s].lang        = lang;
    scope->slots[s].confidence  = confidence;
    scope->slots[s].hash        = h;
    scope->slots[s].anchor_id   = 0;
    scope->slots[s].key         = ev_arena_strdup(scope->arena, key);
    scope->slots[s].value       = value;
    scope->slots[s].node        = node;
    scope->slots[s].params      = params;
    scope->slots[s].param_count = param_count;

    if (is_new) scope->used++;
    return 1;
}

/* Convenience wrappers */
int ev_scope_set_var(EvScope *s, const char *key, EValue val,
                     int16_t conf, int16_t lang) {
    return ev_scope_set(s, key, EV_SK_VAR, val, conf, lang,
                        NULL, NULL, 0);
}

int ev_scope_set_fn(EvScope *s, const char *name, EvNode *body,
                    const char **params, int32_t np,
                    int16_t conf, int16_t lang) {
    return ev_scope_set(s, name, EV_SK_FN, ev_void(), conf, lang,
                        body, params, np);
}

int ev_scope_set_module(EvScope *s, const char *name,
                        EvScope *module_scope, int16_t lang) {
    /* store the module scope pointer inside the EValue as a blob ref;
       the real module lives in the arena — we just need a marker here */
    EValue mv = ev_text(name);   /* placeholder — lookup returns node */
    return ev_scope_set(s, name, EV_SK_MODULE, mv,
                        E_CERTAIN, lang,
                        (EvNode*)module_scope, NULL, 0);
}

/* ─────────────────────────────────────────────
 * Delete
 * ───────────────────────────────────────────── */

int ev_scope_delete(EvScope *scope, const char *key) {
    if (!scope || !key) return 0;
    uint32_t h = ev_fnv1a(key);
    int32_t  s = find_slot(scope->slots, scope->cap, h, key);
    if (s < 0 || scope->slots[s].state != EV_SLOT_LIVE) return 0;
    scope->slots[s].state = EV_SLOT_TOMB;
    scope->used--;
    scope->tombs++;
    return 1;
}

/* ─────────────────────────────────────────────
 * Lookup — this scope only
 * ───────────────────────────────────────────── */

EvScopeEntry *ev_scope_get(EvScope *scope, const char *key) {
    if (!scope || !key) return NULL;
    uint32_t h = ev_fnv1a(key);
    int32_t  s = find_slot(scope->slots, scope->cap, h, key);
    if (s < 0 || scope->slots[s].state != EV_SLOT_LIVE) return NULL;
    return &scope->slots[s];
}

/* ─────────────────────────────────────────────
 * Lookup — walk the scope chain upward
 * ───────────────────────────────────────────── */

EvScopeEntry *ev_scope_lookup(EvScope *scope, const char *key) {
    EvScope *cur = scope;
    while (cur) {
        EvScopeEntry *e = ev_scope_get(cur, key);
        if (e) return e;
        cur = cur->parent;
    }
    return NULL;
}

/* Typed helpers */
EValue ev_scope_get_value(EvScope *scope, const char *key) {
    EvScopeEntry *e = ev_scope_lookup(scope, key);
    return e ? e->value : ev_void();
}

EvNode *ev_scope_get_fn(EvScope *scope, const char *name) {
    EvScopeEntry *e = ev_scope_lookup(scope, name);
    if (!e || e->kind != EV_SK_FN) return NULL;
    return e->node;
}

EvScope *ev_scope_get_module(EvScope *scope, const char *name) {
    EvScopeEntry *e = ev_scope_lookup(scope, name);
    if (!e || e->kind != EV_SK_MODULE) return NULL;
    return (EvScope*)e->node;   /* stored in node field */
}

/* ─────────────────────────────────────────────
 * Iteration
 * ───────────────────────────────────────────── */

void ev_scope_each(const EvScope *scope,
                   ev_scope_iter_fn fn, void *userdata) {
    if (!scope || !fn) return;
    for (int32_t i = 0; i < scope->cap; i++) {
        if (scope->slots[i].state == EV_SLOT_LIVE)
            fn(&scope->slots[i], userdata);
    }
}

/* ─────────────────────────────────────────────
 * Wire format — scope ↔ EValue(RECORD)
 * ───────────────────────────────────────────── */

typedef struct { ev_pool *pool; EValue *rec; } _to_rec_ctx;

static void _entry_to_field(const EvScopeEntry *e, void *ud) {
    _to_rec_ctx *ctx = (_to_rec_ctx*)ud;
    ev_record_set(ctx->rec, e->key, e->value,
                  e->confidence, ctx->pool);
}

EValue ev_scope_to_record(const EvScope *scope, ev_pool *pool) {
    EValue rec = ev_record_new(pool);
    _to_rec_ctx ctx = {pool, &rec};
    ev_scope_each(scope, _entry_to_field, &ctx);
    return rec;
}

int ev_scope_from_record(EvScope *scope, const EValue *rec,
                          ev_pool *pool, int16_t lang) {
    if (!scope || !rec || rec->tag != EV_RECORD) return 0;
    ev_record *r = ev_pool_record(pool, rec->body.pool_ref);
    if (!r) return 0;
    for (int i = 0; i < r->h.len; i++) {
        ev_field *f = &r->fields[i];
        ev_scope_set_var(scope, f->name, f->value, f->confidence, lang);
    }
    return 1;
}

/* ─────────────────────────────────────────────
 * Diagnostics
 * ───────────────────────────────────────────── */

static void _dump_entry(const EvScopeEntry *e, void *ud) {
    (void)ud;
    char desc[80];
    /* inline describe — can't call ev_describe without pool here */
    switch (e->value.tag) {
        case EV_INT:  snprintf(desc, sizeof desc, "%lld",
                               (long long)e->value.body.as_int); break;
        case EV_REAL: snprintf(desc, sizeof desc, "%.4g",
                               e->value.body.as_real); break;
        case EV_BOOL: snprintf(desc, sizeof desc, "%s",
                               e->value.body.as_bool ? "true" : "false"); break;
        case EV_TEXT: snprintf(desc, sizeof desc, "\"%.72s\"",
                               e->value.text); break;
        case EV_VOID: snprintf(desc, sizeof desc, "void"); break;
        default:      snprintf(desc, sizeof desc, "<%s>",
                               ev_type_name((ev_type)e->value.tag)); break;
    }
    printf("  %-24s  %-8s  conf=%-4d  lang=%d  %s\n",
           e->key, ev_scope_kind_name((EvScopeKind)e->kind),
           e->confidence, e->lang, desc);
}

void ev_scope_dump(const EvScope *scope) {
    if (!scope) { printf("(null scope)\n"); return; }
    printf("scope '%s' (depth=%d, %d entries, cap=%d)\n",
           scope->name, scope->depth, scope->used, scope->cap);
    ev_scope_each(scope, _dump_entry, NULL);
    if (scope->parent) {
        printf("  ^ parent: '%s'\n", scope->parent->name);
    }
}

void ev_scope_stats(const EvScope *scope, char *buf, int32_t cap) {
    if (!scope || !buf || cap < 1) return;
    snprintf(buf, (size_t)cap,
             "scope[%s] depth=%d used=%d tombs=%d cap=%d load=%.0f%%",
             scope->name, scope->depth, scope->used, scope->tombs,
             scope->cap,
             scope->cap > 0
                 ? (scope->used * 100.0 / scope->cap)
                 : 0.0);
}
