/*
 * ir.c — Ever / Tapestry, arena allocator + platform-independent IR
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "ir.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

/* ─────────────────────────────────────────────
 * ARENA
 * ───────────────────────────────────────────── */

static ev_slab *slab_new(size_t min_cap) {
    ev_slab *s = (ev_slab*)malloc(sizeof *s);
    if (!s) return NULL;
    size_t cap = min_cap > EV_ARENA_SLAB_SIZE ? min_cap : EV_ARENA_SLAB_SIZE;
    s->mem  = (uint8_t*)malloc(cap);
    if (!s->mem) { free(s); return NULL; }
    s->used = 0;
    s->cap  = cap;
    s->next = NULL;
    return s;
}

EvArena *ev_arena_new(const char *tag) {
    EvArena *a = (EvArena*)malloc(sizeof *a);
    if (!a) return NULL;
    a->head             = slab_new(EV_ARENA_SLAB_SIZE);
    a->total_allocated  = 0;
    a->total_freed      = 0;
    a->slab_count       = 1;
    a->debug_tag        = tag ? tag : "?";
    if (!a->head) { free(a); return NULL; }
    return a;
}

void *ev_arena_alloc(EvArena *a, size_t sz) {
    if (!a || !sz) return NULL;
    /* align to 8 bytes */
    sz = (sz + 7) & ~(size_t)7;

    if (a->head->used + sz > a->head->cap) {
        if (a->slab_count >= EV_ARENA_MAX_SLABS) return NULL;
        ev_slab *ns = slab_new(sz);
        if (!ns) return NULL;
        ns->next  = a->head;
        a->head   = ns;
        a->slab_count++;
    }
    void *p = a->head->mem + a->head->used;
    a->head->used      += sz;
    a->total_allocated += sz;
    memset(p, 0, sz);
    return p;
}

char *ev_arena_strdup(EvArena *a, const char *s) {
    if (!s) return NULL;
    size_t n = strlen(s) + 1;
    char  *p = (char*)ev_arena_alloc(a, n);
    if (p) memcpy(p, s, n);
    return p;
}

void ev_arena_free(EvArena *a) {
    if (!a) return;
    ev_slab *s = a->head;
    while (s) {
        ev_slab *next = s->next;
        free(s->mem);
        free(s);
        s = next;
    }
    a->total_freed = a->total_allocated;
    free(a);
}

void ev_arena_stats(const EvArena *a, char *buf, size_t cap) {
    if (!a || !buf || !cap) return;
    snprintf(buf, cap,
        "arena[%s] slabs=%d alloc=%zu freed=%zu live=%zu",
        a->debug_tag, a->slab_count,
        a->total_allocated, a->total_freed,
        a->total_allocated - a->total_freed);
}

/* ─────────────────────────────────────────────
 * NODE KIND NAMES
 * ───────────────────────────────────────────── */

const char *ev_node_kind_name(EvNodeKind k) {
    switch (k) {
        case EV_NODE_VOID:   return "void";
        case EV_NODE_BOOL:   return "bool";
        case EV_NODE_INT:    return "int";
        case EV_NODE_REAL:   return "real";
        case EV_NODE_TEXT:   return "text";
        case EV_NODE_VAR:    return "var";
        case EV_NODE_DEF:    return "def";
        case EV_NODE_CALL:   return "call";
        case EV_NODE_ADD:    return "+";
        case EV_NODE_SUB:    return "-";
        case EV_NODE_MUL:    return "*";
        case EV_NODE_DIV:    return "/";
        case EV_NODE_LT:     return "<";
        case EV_NODE_GT:     return ">";
        case EV_NODE_LTE:    return "<=";
        case EV_NODE_GTE:    return ">=";
        case EV_NODE_EQ:     return "==";
        case EV_NODE_NEQ:    return "!=";
        case EV_NODE_IF:     return "if";
        case EV_NODE_LIST:   return "list";
        case EV_NODE_RECORD: return "record";
        case EV_NODE_Z:      return "z";
        case EV_NODE_ANCHOR: return "anchor";
        case EV_NODE_ASSM:   return "assimilate";
        case EV_NODE_ERR:    return "error";
        default:             return "?";
    }
}

/* ─────────────────────────────────────────────
 * NODE CONSTRUCTORS — all arena-allocated
 * ───────────────────────────────────────────── */

EvNode *ev_node_new(EvArena *a, EvNodeKind kind, int32_t line) {
    EvNode *n = (EvNode*)ev_arena_alloc(a, sizeof *n);
    if (!n) return NULL;
    n->kind  = kind;
    n->line  = line;
    n->arena = a;
    return n;
}

EvNode *ev_node_bool(EvArena *a, int32_t b, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_BOOL, line);
    if (n) n->lit.as_bool = b ? 1 : 0;
    return n;
}

EvNode *ev_node_int(EvArena *a, int64_t v, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_INT, line);
    if (n) n->lit.as_int = v;
    return n;
}

EvNode *ev_node_real(EvArena *a, double v, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_REAL, line);
    if (n) n->lit.as_real = v;
    return n;
}

EvNode *ev_node_text(EvArena *a, const char *s, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_TEXT, line);
    if (n) n->str = ev_arena_strdup(a, s);
    return n;
}

EvNode *ev_node_var(EvArena *a, const char *name, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_VAR, line);
    if (n) n->str = ev_arena_strdup(a, name);
    return n;
}

EvNode *ev_node_def(EvArena *a, const char *name,
                    const char **params, int32_t np,
                    EvNode *body, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_DEF, line);
    if (!n) return NULL;
    n->str         = ev_arena_strdup(a, name);
    n->param_count = np;
    if (np > 0) {
        n->params = (const char**)ev_arena_alloc(a, np * sizeof(char*));
        if (!n->params) return NULL;
        for (int i = 0; i < np; i++)
            n->params[i] = ev_arena_strdup(a, params[i]);
    }
    ev_node_add_child(n, body);
    return n;
}

EvNode *ev_node_call(EvArena *a, const char *name,
                     EvNode **args, int32_t na, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_CALL, line);
    if (!n) return NULL;
    n->str = ev_arena_strdup(a, name);
    for (int32_t i = 0; i < na; i++)
        ev_node_add_child(n, args[i]);
    return n;
}

EvNode *ev_node_binop(EvArena *a, EvNodeKind op,
                      EvNode *left, EvNode *right, int32_t line) {
    EvNode *n = ev_node_new(a, op, line);
    if (!n) return NULL;
    ev_node_add_child(n, left);
    ev_node_add_child(n, right);
    return n;
}

EvNode *ev_node_if(EvArena *a, EvNode *cond,
                   EvNode *then_n, EvNode *else_n, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_IF, line);
    if (!n) return NULL;
    ev_node_add_child(n, cond);
    ev_node_add_child(n, then_n);
    ev_node_add_child(n, else_n);
    return n;
}

EvNode *ev_node_error(EvArena *a, const char *msg, int32_t line) {
    EvNode *n = ev_node_new(a, EV_NODE_ERR, line);
    if (n) { n->error = ev_arena_strdup(a, msg); }
    return n;
}

int ev_node_add_child(EvNode *n, EvNode *child) {
    if (!n || !child) return 0;
    if (n->child_count >= n->child_cap) {
        int32_t newcap = n->child_cap == 0 ? 4 : n->child_cap * 2;
        EvNode **nb = (EvNode**)ev_arena_alloc(n->arena,
                                               newcap * sizeof(EvNode*));
        if (!nb) return 0;
        if (n->children)
            memcpy(nb, n->children, n->child_count * sizeof(EvNode*));
        n->children  = nb;
        n->child_cap = newcap;
    }
    n->children[n->child_count++] = child;
    return 1;
}

/* ─────────────────────────────────────────────
 * STRUCTURAL METRICS
 * ───────────────────────────────────────────── */

void ev_node_measure(EvNode *n) {
    if (!n) return;
    n->size  = 1;
    n->depth = 0;
    for (int i = 0; i < n->child_count; i++) {
        ev_node_measure(n->children[i]);
        n->size += n->children[i]->size;
        if (n->children[i]->depth + 1 > n->depth)
            n->depth = n->children[i]->depth + 1;
    }
}

/* shape: structure with constants preserved */
const char *ev_node_shape(EvNode *n, EvArena *a) {
    if (!n || !a) return "?";
    char buf[4096]; int pos = 0;
    switch (n->kind) {
        case EV_NODE_INT:  pos = snprintf(buf, sizeof buf, "Num"); break;
        case EV_NODE_REAL: pos = snprintf(buf, sizeof buf, "Num"); break;
        case EV_NODE_BOOL: pos = snprintf(buf, sizeof buf, "Bool"); break;
        case EV_NODE_TEXT: pos = snprintf(buf, sizeof buf, "Str"); break;
        case EV_NODE_VAR:  pos = snprintf(buf, sizeof buf, "Var"); break;
        case EV_NODE_DEF:
        case EV_NODE_CALL:
            pos = snprintf(buf, sizeof buf, "%s(%s",
                           ev_node_kind_name(n->kind), n->str ? n->str : "");
            for (int i = 0; i < n->child_count; i++) {
                pos += snprintf(buf+pos, sizeof buf - pos,
                                ",%s", ev_node_shape(n->children[i], a));
            }
            pos += snprintf(buf+pos, sizeof buf - pos, ")");
            break;
        default: {
            pos = snprintf(buf, sizeof buf, "(%s",
                           ev_node_kind_name(n->kind));
            for (int i = 0; i < n->child_count; i++) {
                pos += snprintf(buf+pos, sizeof buf - pos,
                                " %s", ev_node_shape(n->children[i], a));
            }
            pos += snprintf(buf+pos, sizeof buf - pos, ")");
        }
    }
    return ev_arena_strdup(a, buf);
}

/* skeleton: structure with constants AND comparison operators erased.
   Same as the Python skeleton() that fixed cell 7 of the notebook batch,
   now at the C level so synthesis can use it without a Python round-trip. */
const char *ev_node_skeleton(EvNode *n, EvArena *a) {
    if (!n || !a) return "?";
    char buf[4096]; int pos = 0;
    switch (n->kind) {
        case EV_NODE_INT:
        case EV_NODE_REAL:
        case EV_NODE_BOOL: pos = snprintf(buf, sizeof buf, "K"); break;
        case EV_NODE_TEXT: pos = snprintf(buf, sizeof buf, "K"); break;
        case EV_NODE_VAR:  pos = snprintf(buf, sizeof buf, "V"); break;
        case EV_NODE_LT:
        case EV_NODE_GT:
        case EV_NODE_LTE:
        case EV_NODE_GTE:
        case EV_NODE_EQ:
        case EV_NODE_NEQ:
            pos = snprintf(buf, sizeof buf, "(V CMP %s)",
                           ev_node_skeleton(n->children[1], a));
            break;
        case EV_NODE_CALL:
            pos = snprintf(buf, sizeof buf, "CALL(%s",
                           n->str ? n->str : "");
            for (int i = 0; i < n->child_count; i++) {
                pos += snprintf(buf+pos, sizeof buf - pos,
                                ",%s", ev_node_skeleton(n->children[i], a));
            }
            pos += snprintf(buf+pos, sizeof buf - pos, ")");
            break;
        default: {
            pos = snprintf(buf, sizeof buf, "(%s",
                           ev_node_kind_name(n->kind));
            for (int i = 0; i < n->child_count; i++) {
                pos += snprintf(buf+pos, sizeof buf - pos,
                                " %s", ev_node_skeleton(n->children[i], a));
            }
            pos += snprintf(buf+pos, sizeof buf - pos, ")");
        }
    }
    return ev_arena_strdup(a, buf);
}

/* ─────────────────────────────────────────────
 * IR SERIALISATION — flat, self-describing, cross-platform
 *
 * Wire format (little-endian):
 *   [1 byte: kind]
 *   [4 bytes: line number]
 *   [payload: depends on kind]
 *   [4 bytes: child_count]
 *   [children: recursively serialised]
 *
 * For DEF: also [4 bytes: param_count] [[1+name] * param_count]
 * For CALL/VAR/TEXT/DEF: [2 bytes: namelen] [namelen bytes: name]
 * ───────────────────────────────────────────── */

#define WR8(b,p,v)  { (b)[(p)++] = (uint8_t)(v); }
#define WR16(b,p,v) { uint16_t _v=(uint16_t)(v); (b)[(p)]=(uint8_t)(_v&0xFF); (b)[(p)+1]=(uint8_t)((_v>>8)&0xFF); (p)+=2; }
#define WR32(b,p,v) { uint32_t _v=(uint32_t)(int32_t)(v); for(int _i=0;_i<4;_i++){(b)[(p)+_i]=(uint8_t)((_v>>(_i*8))&0xFF);}(p)+=4; }
#define WR64(b,p,v) { uint64_t _v=(uint64_t)(int64_t)(v); for(int _i=0;_i<8;_i++){(b)[(p)+_i]=(uint8_t)((_v>>(_i*8))&0xFF);}(p)+=8; }

static void wr_str(uint8_t *buf, int32_t *p, const char *s) {
    if (!s) s = "";
    uint16_t n = (uint16_t)(strlen(s) & 0xFFFF);
    WR16(buf, *p, n);
    memcpy(buf + *p, s, n); *p += n;
}

int32_t ev_ir_serialise(const EvNode *n, uint8_t *buf, int32_t cap) {
    if (!n || !buf || cap < 16) return -1;
    int32_t p = 0;
    WR8(buf, p, (uint8_t)n->kind);
    WR32(buf, p, n->line);

    switch (n->kind) {
        case EV_NODE_BOOL: WR8(buf, p, (uint8_t)n->lit.as_bool);  break;
        case EV_NODE_INT:  WR64(buf, p, n->lit.as_int);  break;
        case EV_NODE_REAL: { uint64_t bits; memcpy(&bits,&n->lit.as_real,8); WR64(buf,p,bits); } break;
        case EV_NODE_TEXT:
        case EV_NODE_VAR:
        case EV_NODE_CALL:
        case EV_NODE_ANCHOR:
        case EV_NODE_ASSM:
        case EV_NODE_ERR:
            wr_str(buf, &p, n->str ? n->str : (n->error ? n->error : ""));
            break;
        case EV_NODE_DEF:
            wr_str(buf, &p, n->str ? n->str : "");
            WR32(buf, p, n->param_count);
            for (int i = 0; i < n->param_count; i++)
                wr_str(buf, &p, n->params[i] ? n->params[i] : "");
            break;
        default: break;
    }

    WR32(buf, p, n->child_count);
    for (int32_t i = 0; i < n->child_count; i++) {
        int32_t sub = ev_ir_serialise(n->children[i], buf+p, cap-p);
        if (sub < 0) return -1;
        p += sub;
    }
    return p;
}

#define RD8(b,p)   ((b)[(p)++])
#define RD16(b,p)  ({ uint16_t _v=(uint16_t)((b)[(p)]|((b)[(p)+1]<<8)); (p)+=2; _v; })
#define RD32(b,p)  ({ uint32_t _v=0; for(int _i=0;_i<4;_i++) _v|=((uint32_t)(b)[(p)+_i]<<(_i*8)); (p)+=4; (int32_t)_v; })
#define RD64(b,p)  ({ uint64_t _v=0; for(int _i=0;_i<8;_i++) _v|=((uint64_t)(b)[(p)+_i]<<(_i*8)); (p)+=8; (int64_t)_v; })

static const char *rd_str(const uint8_t *buf, int32_t *p, EvArena *a) {
    uint16_t n = RD16(buf, *p);
    char *s = (char*)ev_arena_alloc(a, (size_t)n+1);
    if (!s) return "";
    memcpy(s, buf + *p, n); s[n] = '\0'; *p += n;
    return s;
}

EvNode *ev_ir_deserialise(const uint8_t *buf, int32_t len,
                           int32_t *consumed, EvArena *a) {
    if (!buf || len < 5 || !a) return NULL;
    int32_t p = 0;
    EvNodeKind kind = (EvNodeKind)RD8(buf, p);
    int32_t    line = RD32(buf, p);
    EvNode *n = ev_node_new(a, kind, line);
    if (!n) return NULL;

    switch (kind) {
        case EV_NODE_BOOL: n->lit.as_bool = RD8(buf, p); break;
        case EV_NODE_INT:  n->lit.as_int  = RD64(buf, p); break;
        case EV_NODE_REAL: {
            int64_t bits = RD64(buf, p);
            memcpy(&n->lit.as_real, &bits, 8); break;
        }
        case EV_NODE_TEXT:
        case EV_NODE_VAR:
        case EV_NODE_CALL:
        case EV_NODE_ANCHOR:
        case EV_NODE_ASSM:
        case EV_NODE_ERR:
            n->str = rd_str(buf, &p, a);
            if (kind == EV_NODE_ERR) n->error = n->str;
            break;
        case EV_NODE_DEF: {
            n->str         = rd_str(buf, &p, a);
            n->param_count = RD32(buf, p);
            if (n->param_count > 0) {
                n->params = (const char**)ev_arena_alloc(
                    a, n->param_count * sizeof(char*));
                for (int i = 0; i < n->param_count; i++)
                    n->params[i] = rd_str(buf, &p, a);
            }
            break;
        }
        default: break;
    }

    int32_t nc = RD32(buf, p);
    for (int32_t i = 0; i < nc; i++) {
        int32_t sub = 0;
        EvNode *child = ev_ir_deserialise(buf+p, len-p, &sub, a);
        if (!child) return NULL;
        ev_node_add_child(n, child);
        p += sub;
    }
    if (consumed) *consumed = p;
    return n;
}

/* ─────────────────────────────────────────────
 * PARSE RESULT
 * ───────────────────────────────────────────── */

EvResult *ev_result_new(const char *src_tag) {
    EvArena  *a = ev_arena_new(src_tag);
    if (!a) return NULL;
    EvResult *r = (EvResult*)ev_arena_alloc(a, sizeof *r);
    if (!r) { ev_arena_free(a); return NULL; }
    r->arena = a;
    return r;
}

void ev_result_free(EvResult *r) {
    if (!r) return;
    EvArena *a = r->arena;
    ev_arena_free(a);   /* r itself lives in the arena — freed here too */
}
