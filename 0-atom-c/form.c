/*
 * form.c — Ever / Tapestry, generic structural IR implementation
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "form.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#ifndef E_INTAKE
#define E_INTAKE 120
#endif
#ifndef E_CERTAIN
#define E_CERTAIN 256
#endif

/* ─────────────────────────────────────────────
 * THE CONTRACT TABLE
 *
 * One row per form. This table is the single source of truth about
 * what a well-formed tree looks like. Every pass can consult it;
 * no pass needs its own idea of correct shape.
 * ───────────────────────────────────────────── */
static const EvFormContract CONTRACTS[EV_FORM_KIND_COUNT] = {
    /* form                 name           min max sym  shape                     */
    { EV_FORM_ATOM,        "ATOM",          0,  0, 0, "leaf, payload holds value" },
    { EV_FORM_REFERENCE,   "REFERENCE",     0,  0, 1, "leaf, symbol is the name"  },
    { EV_FORM_APPLICATION, "APPLICATION",   1, -1, 0, "1+ operands"               },
    { EV_FORM_BRANCH,      "BRANCH",        2, -1, 0, "selector + 1..N arms"      },
    { EV_FORM_SEQUENCE,    "SEQUENCE",      0, -1, 0, "0..N ordered forms"        },
    { EV_FORM_BINDING,     "BINDING",       1,  1, 1, "exactly 1 value"           },
    { EV_FORM_ABSTRACTION, "ABSTRACTION",   1,  1, 1, "exactly 1 body"            },
    { EV_FORM_AGGREGATE,   "AGGREGATE",     0, -1, 0, "0..N elements"             },
    { EV_FORM_ACCESS,      "ACCESS",        2,  2, 0, "target + key"              },
    { EV_FORM_ANNOTATION,  "ANNOTATION",    1,  1, 0, "exactly 1 subject"         },
    { EV_FORM_DEFECT,      "DEFECT",        0,  0, 1, "leaf, symbol is message"   }
};

const EvFormContract *ev_form_contract(EvFormKind form) {
    if (form < 0 || form >= EV_FORM_KIND_COUNT) return NULL;
    return &CONTRACTS[form];
}

const char *ev_form_name(EvFormKind form) {
    const EvFormContract *c = ev_form_contract(form);
    return c ? c->name : "UNKNOWN";
}

/* ─────────────────────────────────────────────
 * ROLE TABLE
 * ───────────────────────────────────────────── */
typedef struct { EvRole role; const char *name; EvFormKind owner; } RoleRow;

static const RoleRow ROLES[] = {
    { EV_ROLE_NONE,        "NONE",        EV_FORM_ATOM        },
    { EV_ROLE_LIT_VOID,    "LIT_VOID",    EV_FORM_ATOM        },
    { EV_ROLE_LIT_BOOL,    "LIT_BOOL",    EV_FORM_ATOM        },
    { EV_ROLE_LIT_INT,     "LIT_INT",     EV_FORM_ATOM        },
    { EV_ROLE_LIT_REAL,    "LIT_REAL",    EV_FORM_ATOM        },
    { EV_ROLE_LIT_TEXT,    "LIT_TEXT",    EV_FORM_ATOM        },
    { EV_ROLE_LIT_Z,       "LIT_Z",       EV_FORM_ATOM        },
    { EV_ROLE_REF_VAR,     "REF_VAR",     EV_FORM_REFERENCE   },
    { EV_ROLE_REF_PARAM,   "REF_PARAM",   EV_FORM_REFERENCE   },
    { EV_ROLE_REF_FN,      "REF_FN",      EV_FORM_REFERENCE   },
    { EV_ROLE_ADD,         "ADD",         EV_FORM_APPLICATION },
    { EV_ROLE_SUB,         "SUB",         EV_FORM_APPLICATION },
    { EV_ROLE_MUL,         "MUL",         EV_FORM_APPLICATION },
    { EV_ROLE_DIV,         "DIV",         EV_FORM_APPLICATION },
    { EV_ROLE_MOD,         "MOD",         EV_FORM_APPLICATION },
    { EV_ROLE_POW,         "POW",         EV_FORM_APPLICATION },
    { EV_ROLE_NEG,         "NEG",         EV_FORM_APPLICATION },
    { EV_ROLE_LT,          "LT",          EV_FORM_APPLICATION },
    { EV_ROLE_GT,          "GT",          EV_FORM_APPLICATION },
    { EV_ROLE_LTE,         "LTE",         EV_FORM_APPLICATION },
    { EV_ROLE_GTE,         "GTE",         EV_FORM_APPLICATION },
    { EV_ROLE_EQ,          "EQ",          EV_FORM_APPLICATION },
    { EV_ROLE_NEQ,         "NEQ",         EV_FORM_APPLICATION },
    { EV_ROLE_AND,         "AND",         EV_FORM_APPLICATION },
    { EV_ROLE_OR,          "OR",          EV_FORM_APPLICATION },
    { EV_ROLE_NOT,         "NOT",         EV_FORM_APPLICATION },
    { EV_ROLE_CALL,        "CALL",        EV_FORM_APPLICATION },
    { EV_ROLE_BUILTIN,     "BUILTIN",     EV_FORM_APPLICATION },
    { EV_ROLE_IF,          "IF",          EV_FORM_BRANCH      },
    { EV_ROLE_MATCH,       "MATCH",       EV_FORM_BRANCH      },
    { EV_ROLE_GUARD,       "GUARD",       EV_FORM_BRANCH      },
    { EV_ROLE_BLOCK,       "BLOCK",       EV_FORM_SEQUENCE    },
    { EV_ROLE_PROGRAM,     "PROGRAM",     EV_FORM_SEQUENCE    },
    { EV_ROLE_BIND_LET,    "BIND_LET",    EV_FORM_BINDING     },
    { EV_ROLE_BIND_EVER,   "BIND_EVER",   EV_FORM_BINDING     },
    { EV_ROLE_BIND_FIELD,  "BIND_FIELD",  EV_FORM_BINDING     },
    { EV_ROLE_FN_DEF,      "FN_DEF",      EV_FORM_ABSTRACTION },
    { EV_ROLE_FN_LAMBDA,   "FN_LAMBDA",   EV_FORM_ABSTRACTION },
    { EV_ROLE_AGG_LIST,    "AGG_LIST",    EV_FORM_AGGREGATE   },
    { EV_ROLE_AGG_RECORD,  "AGG_RECORD",  EV_FORM_AGGREGATE   },
    { EV_ROLE_AGG_TUPLE,   "AGG_TUPLE",   EV_FORM_AGGREGATE   },
    { EV_ROLE_ACC_INDEX,   "ACC_INDEX",   EV_FORM_ACCESS      },
    { EV_ROLE_ACC_FIELD,   "ACC_FIELD",   EV_FORM_ACCESS      },
    { EV_ROLE_ANN_ANCHOR,  "ANN_ANCHOR",  EV_FORM_ANNOTATION  },
    { EV_ROLE_ANN_ASSM,    "ANN_ASSM",    EV_FORM_ANNOTATION  },
    { EV_ROLE_ANN_CONF,    "ANN_CONF",    EV_FORM_ANNOTATION  },
    { EV_ROLE_DEF_PARSE,   "DEF_PARSE",   EV_FORM_DEFECT      },
    { EV_ROLE_DEF_SEMANT,  "DEF_SEMANT",  EV_FORM_DEFECT      },
    { EV_ROLE_DEF_CEILING, "DEF_CEILING", EV_FORM_DEFECT      }
};

#define ROLE_COUNT ((int)(sizeof(ROLES)/sizeof(ROLES[0])))

const char *ev_role_name(EvRole role) {
    for (int i = 0; i < ROLE_COUNT; i++)
        if (ROLES[i].role == role) return ROLES[i].name;
    return "ROLE?";
}

EvFormKind ev_role_form(EvRole role) {
    for (int i = 0; i < ROLE_COUNT; i++)
        if (ROLES[i].role == role) return ROLES[i].owner;
    return EV_FORM_DEFECT;
}

/* ─────────────────────────────────────────────
 * CONSTRUCTION
 * ───────────────────────────────────────────── */

EvForm *ev_form_new(EvArena *a, EvFormKind form, EvRole role, int32_t line) {
    if (!a) return NULL;
    EvForm *f = (EvForm *)ev_arena_alloc(a, sizeof(EvForm));
    if (!f) return NULL;
    memset(f, 0, sizeof(EvForm));
    f->form       = form;
    f->role       = role;
    f->line       = line;
    f->payload    = ev_void();
    f->confidence = E_CERTAIN;
    f->size       = 1;
    f->depth      = 1;
    f->arena      = a;
    return f;
}

static void _ensure_cap(EvForm *f, int32_t need) {
    if (need <= f->part_cap) return;
    int32_t ncap = f->part_cap ? f->part_cap * 2 : 4;
    while (ncap < need) ncap *= 2;
    EvForm    **np = (EvForm **)ev_arena_alloc(f->arena, sizeof(EvForm*) * ncap);
    const char **nl = (const char **)ev_arena_alloc(f->arena, sizeof(char*) * ncap);
    if (!np || !nl) return;
    memset(np, 0, sizeof(EvForm*) * ncap);
    memset(nl, 0, sizeof(char*) * ncap);
    for (int32_t i = 0; i < f->part_count; i++) {
        np[i] = f->parts[i];
        nl[i] = f->labels ? f->labels[i] : NULL;
    }
    f->parts    = np;
    f->labels   = nl;
    f->part_cap = ncap;
}

void ev_form_add_part(EvForm *f, EvForm *part, const char *label) {
    if (!f) return;
    _ensure_cap(f, f->part_count + 1);
    if (f->part_count >= f->part_cap) return;
    f->parts[f->part_count]  = part;
    f->labels[f->part_count] = label ? ev_arena_strdup(f->arena, label) : NULL;
    f->part_count++;
}

/* ── ATOM ── */
EvForm *ev_form_atom(EvArena *a, EValue v, int32_t line) {
    EvRole r = EV_ROLE_LIT_VOID;
    switch (v.tag) {
        case EV_BOOL: r = EV_ROLE_LIT_BOOL; break;
        case EV_INT:  r = EV_ROLE_LIT_INT;  break;
        case EV_REAL: r = EV_ROLE_LIT_REAL; break;
        case EV_TEXT: r = EV_ROLE_LIT_TEXT; break;
        default:      r = EV_ROLE_LIT_VOID; break;
    }
    EvForm *f = ev_form_new(a, EV_FORM_ATOM, r, line);
    if (f) f->payload = v;
    return f;
}
EvForm *ev_form_int (EvArena *a, int64_t v, int32_t line) { return ev_form_atom(a, ev_int(v),  line); }
EvForm *ev_form_real(EvArena *a, double  v, int32_t line) { return ev_form_atom(a, ev_real(v), line); }
EvForm *ev_form_bool(EvArena *a, int32_t v, int32_t line) { return ev_form_atom(a, ev_bool(v), line); }
EvForm *ev_form_text(EvArena *a, const char *v, int32_t line) { return ev_form_atom(a, ev_text(v), line); }
EvForm *ev_form_void(EvArena *a, int32_t line) { return ev_form_atom(a, ev_void(), line); }

EvForm *ev_form_z(EvArena *a, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_ATOM, EV_ROLE_LIT_Z, line);
    if (f) { f->payload = ev_void(); f->confidence = 0; }
    return f;
}

/* ── REFERENCE ── */
EvForm *ev_form_ref(EvArena *a, const char *name, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_REFERENCE, EV_ROLE_REF_VAR, line);
    if (f) f->symbol = ev_arena_strdup(a, name ? name : "");
    return f;
}

/* ── APPLICATION ── */
EvForm *ev_form_apply(EvArena *a, EvRole role, const char *symbol,
                      EvForm **operands, int32_t n, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_APPLICATION, role, line);
    if (!f) return NULL;
    if (symbol) f->symbol = ev_arena_strdup(a, symbol);
    for (int32_t i = 0; i < n; i++)
        ev_form_add_part(f, operands[i], NULL);
    return f;
}

EvForm *ev_form_apply2(EvArena *a, EvRole role,
                       EvForm *lhs, EvForm *rhs, int32_t line) {
    EvForm *ops[2]; ops[0] = lhs; ops[1] = rhs;
    return ev_form_apply(a, role, NULL, ops, 2, line);
}

/* ── BRANCH ── */
EvForm *ev_form_branch(EvArena *a, EvRole role, EvForm *selector,
                       EvForm **arms, int32_t n, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_BRANCH, role, line);
    if (!f) return NULL;
    ev_form_add_part(f, selector, "selector");
    for (int32_t i = 0; i < n; i++) {
        char lbl[24];
        snprintf(lbl, sizeof lbl, "arm%d", (int)i);
        ev_form_add_part(f, arms[i], lbl);
    }
    return f;
}

/* ── SEQUENCE ── */
EvForm *ev_form_sequence(EvArena *a, EvRole role,
                         EvForm **items, int32_t n, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_SEQUENCE, role, line);
    if (!f) return NULL;
    for (int32_t i = 0; i < n; i++) ev_form_add_part(f, items[i], NULL);
    return f;
}

/* ── BINDING ── */
EvForm *ev_form_binding(EvArena *a, EvRole role, const char *name,
                        EvForm *value, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_BINDING, role, line);
    if (!f) return NULL;
    f->symbol = ev_arena_strdup(a, name ? name : "");
    ev_form_add_part(f, value, "value");
    return f;
}

/* ── ABSTRACTION ── */
EvForm *ev_form_abstraction(EvArena *a, EvRole role, const char *name,
                            const char **params, int32_t np,
                            EvForm *body, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_ABSTRACTION, role, line);
    if (!f) return NULL;
    f->symbol = ev_arena_strdup(a, name ? name : "");
    ev_form_add_part(f, body, "body");
    /* parameter names live in labels[] beyond the body slot, so an
       abstraction needs no dedicated params array */
    if (np > 0) {
        _ensure_cap(f, 1 + np);
        for (int32_t i = 0; i < np; i++) {
            f->parts[1 + i]  = NULL;                 /* no form, name only */
            f->labels[1 + i] = ev_arena_strdup(a, params[i] ? params[i] : "");
        }
        /* part_count stays 1 — params are metadata, not evaluable parts */
    }
    return f;
}

/* Read parameter names back out of an abstraction */
static int32_t _abstraction_param_count(const EvForm *f) {
    if (!f || f->form != EV_FORM_ABSTRACTION) return 0;
    int32_t n = 0;
    for (int32_t i = 1; i < f->part_cap; i++) {
        if (f->labels && f->labels[i] && f->parts[i] == NULL) n++;
        else break;
    }
    return n;
}
static const char *_abstraction_param(const EvForm *f, int32_t i) {
    if (!f || !f->labels) return NULL;
    return f->labels[1 + i];
}

/* ── AGGREGATE ── */
EvForm *ev_form_aggregate(EvArena *a, EvRole role, EvForm **items,
                          const char **keys, int32_t n, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_AGGREGATE, role, line);
    if (!f) return NULL;
    for (int32_t i = 0; i < n; i++)
        ev_form_add_part(f, items[i], keys ? keys[i] : NULL);
    return f;
}

/* ── ACCESS ── */
EvForm *ev_form_access(EvArena *a, EvRole role, EvForm *target,
                       EvForm *key, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_ACCESS, role, line);
    if (!f) return NULL;
    ev_form_add_part(f, target, "target");
    ev_form_add_part(f, key,    "key");
    return f;
}

/* ── ANNOTATION ── */
EvForm *ev_form_annotate(EvArena *a, EvRole role, const char *arg,
                         EvForm *subject, int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_ANNOTATION, role, line);
    if (!f) return NULL;
    if (arg) f->symbol = ev_arena_strdup(a, arg);
    ev_form_add_part(f, subject, "subject");
    return f;
}

/* ── DEFECT ── */
EvForm *ev_form_defect(EvArena *a, EvRole role, const char *msg,
                       int32_t line) {
    EvForm *f = ev_form_new(a, EV_FORM_DEFECT, role, line);
    if (!f) return NULL;
    f->symbol     = ev_arena_strdup(a, msg ? msg : "defect");
    f->confidence = 0;
    return f;
}

/* ─────────────────────────────────────────────
 * ACCESSORS
 * ───────────────────────────────────────────── */
EvForm *ev_form_selector(const EvForm *b) {
    return (b && b->part_count > 0) ? b->parts[0] : NULL;
}
EvForm *ev_form_arm(const EvForm *b, int32_t i) {
    return (b && i + 1 < b->part_count) ? b->parts[i + 1] : NULL;
}
int32_t ev_form_arm_count(const EvForm *b) {
    return (b && b->part_count > 0) ? b->part_count - 1 : 0;
}
EvForm *ev_form_body(const EvForm *f) {
    return (f && f->part_count > 0) ? f->parts[0] : NULL;
}
EvForm *ev_form_value(const EvForm *f) {
    return (f && f->part_count > 0) ? f->parts[0] : NULL;
}
EvForm *ev_form_subject(const EvForm *f) {
    return (f && f->part_count > 0) ? f->parts[0] : NULL;
}
EvForm *ev_form_target(const EvForm *f) {
    return (f && f->part_count > 0) ? f->parts[0] : NULL;
}
EvForm *ev_form_key(const EvForm *f) {
    return (f && f->part_count > 1) ? f->parts[1] : NULL;
}
EvForm *ev_form_operand(const EvForm *f, int32_t i) {
    return (f && i < f->part_count) ? f->parts[i] : NULL;
}

/* ─────────────────────────────────────────────
 * ANALYSIS
 * ───────────────────────────────────────────── */

void ev_form_measure(EvForm *f) {
    if (!f) return;
    int32_t size = 1, maxd = 0;
    for (int32_t i = 0; i < f->part_count; i++) {
        EvForm *p = f->parts[i];
        if (!p) continue;
        ev_form_measure(p);
        size += p->size;
        if (p->depth > maxd) maxd = p->depth;
    }
    f->size  = size;
    f->depth = maxd + 1;
}

int ev_form_validate(const EvForm *f, char *err, size_t errlen) {
    if (!f) {
        if (err && errlen) snprintf(err, errlen, "null form");
        return 0;
    }
    const EvFormContract *c = ev_form_contract(f->form);
    if (!c) {
        if (err && errlen)
            snprintf(err, errlen, "line %d: unknown form kind %d",
                     (int)f->line, (int)f->form);
        return 0;
    }
    /* arity */
    if (f->part_count < c->min_parts) {
        if (err && errlen)
            snprintf(err, errlen,
                     "line %d: %s[%s] has %d parts, needs at least %d (%s)",
                     (int)f->line, c->name, ev_role_name(f->role),
                     (int)f->part_count, (int)c->min_parts, c->shape_desc);
        return 0;
    }
    if (c->max_parts >= 0 && f->part_count > c->max_parts) {
        if (err && errlen)
            snprintf(err, errlen,
                     "line %d: %s[%s] has %d parts, allows at most %d (%s)",
                     (int)f->line, c->name, ev_role_name(f->role),
                     (int)f->part_count, (int)c->max_parts, c->shape_desc);
        return 0;
    }
    /* symbol requirement */
    if (c->needs_symbol && (!f->symbol || f->symbol[0] == '\0')) {
        if (err && errlen)
            snprintf(err, errlen, "line %d: %s[%s] requires a symbol",
                     (int)f->line, c->name, ev_role_name(f->role));
        return 0;
    }
    /* role must belong to this form */
    if (f->role != EV_ROLE_NONE && ev_role_form(f->role) != f->form) {
        if (err && errlen)
            snprintf(err, errlen,
                     "line %d: role %s does not belong to form %s",
                     (int)f->line, ev_role_name(f->role), c->name);
        return 0;
    }
    /* recurse */
    for (int32_t i = 0; i < f->part_count; i++) {
        if (!f->parts[i]) {
            if (err && errlen)
                snprintf(err, errlen, "line %d: %s part %d is null",
                         (int)f->line, c->name, (int)i);
            return 0;
        }
        if (!ev_form_validate(f->parts[i], err, errlen)) return 0;
    }
    return 1;
}

int32_t ev_form_count_kind(const EvForm *f, EvFormKind k) {
    if (!f) return 0;
    int32_t n = (f->form == k) ? 1 : 0;
    for (int32_t i = 0; i < f->part_count; i++)
        n += ev_form_count_kind(f->parts[i], k);
    return n;
}

int32_t ev_form_count_role(const EvForm *f, EvRole r) {
    if (!f) return 0;
    int32_t n = (f->role == r) ? 1 : 0;
    for (int32_t i = 0; i < f->part_count; i++)
        n += ev_form_count_role(f->parts[i], r);
    return n;
}

/* Skeleton: erase roles and values, keep pure shape.
   Two programs with the same skeleton have the same structure even if
   every operator and constant differs. */
static void _skeleton(const EvForm *f, char *buf, size_t cap, size_t *used) {
    if (!f || *used + 8 >= cap) return;
    const char *tok = "?";
    switch (f->form) {
        case EV_FORM_ATOM:        tok = "K";  break;
        case EV_FORM_REFERENCE:   tok = "V";  break;
        case EV_FORM_APPLICATION: tok = "AP"; break;
        case EV_FORM_BRANCH:      tok = "BR"; break;
        case EV_FORM_SEQUENCE:    tok = "SQ"; break;
        case EV_FORM_BINDING:     tok = "BD"; break;
        case EV_FORM_ABSTRACTION: tok = "AB"; break;
        case EV_FORM_AGGREGATE:   tok = "AG"; break;
        case EV_FORM_ACCESS:      tok = "AC"; break;
        case EV_FORM_ANNOTATION:  tok = "AN"; break;
        case EV_FORM_DEFECT:      tok = "XX"; break;
        default: break;
    }
    size_t n = strlen(tok);
    if (*used + n < cap) { memcpy(buf + *used, tok, n); *used += n; }
    if (f->part_count > 0) {
        if (*used + 1 < cap) buf[(*used)++] = '(';
        for (int32_t i = 0; i < f->part_count; i++) {
            if (i && *used + 1 < cap) buf[(*used)++] = ' ';
            _skeleton(f->parts[i], buf, cap, used);
        }
        if (*used + 1 < cap) buf[(*used)++] = ')';
    }
}

const char *ev_form_skeleton(const EvForm *f, EvArena *a) {
    char tmp[2048];
    size_t used = 0;
    _skeleton(f, tmp, sizeof tmp - 1, &used);
    tmp[used] = '\0';
    return ev_arena_strdup(a, tmp);
}

/* ─────────────────────────────────────────────
 * NORMALISATION — EvNode → EvForm
 *
 * THE MAPPING TABLE. This is the whole argument in one function:
 * 24 syntax-tied node kinds collapse onto 11 structural forms.
 * ───────────────────────────────────────────── */

static EvRole _binop_role(EvNodeKind k) {
    switch (k) {
        case EV_NODE_ADD: return EV_ROLE_ADD;
        case EV_NODE_SUB: return EV_ROLE_SUB;
        case EV_NODE_MUL: return EV_ROLE_MUL;
        case EV_NODE_DIV: return EV_ROLE_DIV;
        case EV_NODE_LT:  return EV_ROLE_LT;
        case EV_NODE_GT:  return EV_ROLE_GT;
        case EV_NODE_LTE: return EV_ROLE_LTE;
        case EV_NODE_GTE: return EV_ROLE_GTE;
        case EV_NODE_EQ:  return EV_ROLE_EQ;
        case EV_NODE_NEQ: return EV_ROLE_NEQ;
        default:          return EV_ROLE_NONE;
    }
}

EvForm *ev_form_from_node(const EvNode *n, EvArena *a) {
    if (!n || !a) return NULL;

    switch (n->kind) {
        /* ── five literal kinds → ONE form ── */
        case EV_NODE_VOID: return ev_form_void(a, n->line);
        case EV_NODE_BOOL: return ev_form_bool(a, n->lit.as_bool, n->line);
        case EV_NODE_INT:  return ev_form_int (a, n->lit.as_int,  n->line);
        case EV_NODE_REAL: return ev_form_real(a, n->lit.as_real, n->line);
        case EV_NODE_TEXT: return ev_form_text(a, n->str ? n->str : "", n->line);
        case EV_NODE_Z:    return ev_form_z(a, n->line);

        /* ── variable → REFERENCE ── */
        case EV_NODE_VAR:  return ev_form_ref(a, n->str, n->line);

        /* ── ten binary operator kinds → ONE form ── */
        case EV_NODE_ADD: case EV_NODE_SUB:
        case EV_NODE_MUL: case EV_NODE_DIV:
        case EV_NODE_LT:  case EV_NODE_GT:
        case EV_NODE_LTE: case EV_NODE_GTE:
        case EV_NODE_EQ:  case EV_NODE_NEQ: {
            if (n->child_count < 2) return ev_form_defect(a, EV_ROLE_DEF_SEMANT,
                                        "binary operator needs 2 operands", n->line);
            EvForm *l = ev_form_from_node(n->children[0], a);
            EvForm *r = ev_form_from_node(n->children[1], a);
            return ev_form_apply2(a, _binop_role(n->kind), l, r, n->line);
        }

        /* ── call → same APPLICATION form, different role ── */
        case EV_NODE_CALL: {
            EvForm **args = NULL;
            if (n->child_count > 0) {
                args = (EvForm **)ev_arena_alloc(a, sizeof(EvForm*) * n->child_count);
                for (int32_t i = 0; i < n->child_count; i++)
                    args[i] = ev_form_from_node(n->children[i], a);
            }
            return ev_form_apply(a, EV_ROLE_CALL, n->str, args,
                                 n->child_count, n->line);
        }

        /* ── if → BRANCH with 2 arms ── */
        case EV_NODE_IF: {
            if (n->child_count < 3) return ev_form_defect(a, EV_ROLE_DEF_SEMANT,
                                        "if needs condition and two arms", n->line);
            EvForm *sel  = ev_form_from_node(n->children[0], a);
            EvForm *arms[2];
            arms[0] = ev_form_from_node(n->children[1], a);
            arms[1] = ev_form_from_node(n->children[2], a);
            return ev_form_branch(a, EV_ROLE_IF, sel, arms, 2, n->line);
        }

        /* ── def → ABSTRACTION ── */
        case EV_NODE_DEF: {
            EvForm *body = (n->child_count > 0)
                         ? ev_form_from_node(n->children[0], a) : NULL;
            if (!body) body = ev_form_void(a, n->line);
            return ev_form_abstraction(a, EV_ROLE_FN_DEF, n->str,
                                       n->params, n->param_count,
                                       body, n->line);
        }

        /* ── list / record → ONE aggregate form, two roles ── */
        case EV_NODE_LIST:
        case EV_NODE_RECORD: {
            EvForm **items = NULL;
            if (n->child_count > 0) {
                items = (EvForm **)ev_arena_alloc(a, sizeof(EvForm*) * n->child_count);
                for (int32_t i = 0; i < n->child_count; i++)
                    items[i] = ev_form_from_node(n->children[i], a);
            }
            EvRole r = (n->kind == EV_NODE_LIST)
                     ? EV_ROLE_AGG_LIST : EV_ROLE_AGG_RECORD;
            return ev_form_aggregate(a, r, items, n->keys,
                                     n->child_count, n->line);
        }

        /* ── anchor / assimilate → ONE annotation form, two roles ── */
        case EV_NODE_ANCHOR:
        case EV_NODE_ASSM: {
            EvForm *subj = (n->child_count > 0)
                         ? ev_form_from_node(n->children[0], a)
                         : ev_form_void(a, n->line);
            EvRole r = (n->kind == EV_NODE_ANCHOR)
                     ? EV_ROLE_ANN_ANCHOR : EV_ROLE_ANN_ASSM;
            return ev_form_annotate(a, r, n->str, subj, n->line);
        }

        /* ── error → DEFECT ── */
        case EV_NODE_ERR:
            return ev_form_defect(a, EV_ROLE_DEF_PARSE,
                                  n->error ? n->error : "parse error", n->line);

        default:
            return ev_form_defect(a, EV_ROLE_DEF_SEMANT,
                                  "unmapped node kind", n->line);
    }
}

/* ─────────────────────────────────────────────
 * DENORMALISATION — EvForm → EvNode (round-trip proof)
 * ───────────────────────────────────────────── */

static EvNodeKind _role_to_binop(EvRole r) {
    switch (r) {
        case EV_ROLE_ADD: return EV_NODE_ADD;
        case EV_ROLE_SUB: return EV_NODE_SUB;
        case EV_ROLE_MUL: return EV_NODE_MUL;
        case EV_ROLE_DIV: return EV_NODE_DIV;
        case EV_ROLE_LT:  return EV_NODE_LT;
        case EV_ROLE_GT:  return EV_NODE_GT;
        case EV_ROLE_LTE: return EV_NODE_LTE;
        case EV_ROLE_GTE: return EV_NODE_GTE;
        case EV_ROLE_EQ:  return EV_NODE_EQ;
        case EV_ROLE_NEQ: return EV_NODE_NEQ;
        default:          return EV_NODE_ERR;
    }
}

EvNode *ev_node_from_form(const EvForm *f, EvArena *a) {
    if (!f || !a) return NULL;

    switch (f->form) {
        case EV_FORM_ATOM:
            if (f->role == EV_ROLE_LIT_Z)
                return ev_node_new(a, EV_NODE_Z, f->line);
            switch (f->payload.tag) {
                case EV_BOOL: return ev_node_bool(a, f->payload.body.as_bool, f->line);
                case EV_INT:  return ev_node_int (a, f->payload.body.as_int,  f->line);
                case EV_REAL: return ev_node_real(a, f->payload.body.as_real, f->line);
                case EV_TEXT: return ev_node_text(a, f->payload.text, f->line);
                default:      return ev_node_new(a, EV_NODE_VOID, f->line);
            }

        case EV_FORM_REFERENCE:
            return ev_node_var(a, f->symbol, f->line);

        case EV_FORM_APPLICATION: {
            if (f->role == EV_ROLE_CALL || f->role == EV_ROLE_BUILTIN) {
                EvNode **args = NULL;
                if (f->part_count > 0) {
                    args = (EvNode **)ev_arena_alloc(a, sizeof(EvNode*) * f->part_count);
                    for (int32_t i = 0; i < f->part_count; i++)
                        args[i] = ev_node_from_form(f->parts[i], a);
                }
                return ev_node_call(a, f->symbol, args, f->part_count, f->line);
            }
            if (f->part_count < 2)
                return ev_node_error(a, "application needs 2 operands", f->line);
            EvNode *l = ev_node_from_form(f->parts[0], a);
            EvNode *r = ev_node_from_form(f->parts[1], a);
            return ev_node_binop(a, _role_to_binop(f->role), l, r, f->line);
        }

        case EV_FORM_BRANCH: {
            EvNode *sel = ev_node_from_form(ev_form_selector(f), a);
            EvNode *t   = ev_node_from_form(ev_form_arm(f, 0), a);
            EvNode *e   = (ev_form_arm_count(f) > 1)
                        ? ev_node_from_form(ev_form_arm(f, 1), a)
                        : ev_node_new(a, EV_NODE_VOID, f->line);
            return ev_node_if(a, sel, t, e, f->line);
        }

        case EV_FORM_ABSTRACTION: {
            int32_t np = _abstraction_param_count(f);
            const char **ps = NULL;
            if (np > 0) {
                ps = (const char **)ev_arena_alloc(a, sizeof(char*) * np);
                for (int32_t i = 0; i < np; i++)
                    ps[i] = _abstraction_param(f, i);
            }
            EvNode *body = ev_node_from_form(ev_form_body(f), a);
            return ev_node_def(a, f->symbol, ps, np, body, f->line);
        }

        case EV_FORM_DEFECT:
            return ev_node_error(a, f->symbol, f->line);

        default:
            return ev_node_error(a, "form has no EvNode equivalent", f->line);
    }
}

/* ─────────────────────────────────────────────
 * WIRE FORMAT
 *
 * [form:i32][role:i32][line:i32][conf:i16][flags:i16]
 * [symlen:i32][sym bytes]
 * [payload_len:i32][payload bytes]
 * [part_count:i32]
 *   per part: [lablen:i32][label bytes][sub-form...]
 * ───────────────────────────────────────────── */

static int32_t _put_i32(uint8_t *b, int32_t off, int32_t cap, int32_t v) {
    if (off + 4 > cap) return -1;
    b[off]   = (uint8_t)( v        & 0xFF);
    b[off+1] = (uint8_t)((v >> 8)  & 0xFF);
    b[off+2] = (uint8_t)((v >> 16) & 0xFF);
    b[off+3] = (uint8_t)((v >> 24) & 0xFF);
    return off + 4;
}
static int32_t _get_i32(const uint8_t *b, int32_t off, int32_t len, int32_t *out) {
    if (off + 4 > len) return -1;
    *out = (int32_t)((uint32_t)b[off]        |
                     ((uint32_t)b[off+1] << 8) |
                     ((uint32_t)b[off+2] << 16)|
                     ((uint32_t)b[off+3] << 24));
    return off + 4;
}
static int32_t _put_i16(uint8_t *b, int32_t off, int32_t cap, int16_t v) {
    if (off + 2 > cap) return -1;
    b[off]   = (uint8_t)( v       & 0xFF);
    b[off+1] = (uint8_t)((v >> 8) & 0xFF);
    return off + 2;
}
static int32_t _get_i16(const uint8_t *b, int32_t off, int32_t len, int16_t *out) {
    if (off + 2 > len) return -1;
    *out = (int16_t)((uint16_t)b[off] | ((uint16_t)b[off+1] << 8));
    return off + 2;
}
static int32_t _put_str(uint8_t *b, int32_t off, int32_t cap, const char *s) {
    int32_t n = s ? (int32_t)strlen(s) : 0;
    off = _put_i32(b, off, cap, n);
    if (off < 0) return -1;
    if (n > 0) {
        if (off + n > cap) return -1;
        memcpy(b + off, s, (size_t)n);
        off += n;
    }
    return off;
}

static int32_t _ser(const EvForm *f, uint8_t *b, int32_t off, int32_t cap) {
    if (!f) return -1;
    off = _put_i32(b, off, cap, (int32_t)f->form);   if (off < 0) return -1;
    off = _put_i32(b, off, cap, (int32_t)f->role);   if (off < 0) return -1;
    off = _put_i32(b, off, cap, f->line);            if (off < 0) return -1;
    off = _put_i16(b, off, cap, f->confidence);      if (off < 0) return -1;
    off = _put_str(b, off, cap, f->symbol);          if (off < 0) return -1;

    /* payload via EValue's own wire format */
    if (off + 4 > cap) return -1;
    int32_t plen_off = off; off += 4;
    ev_pool tmp; ev_pool_init(&tmp);
    int32_t plen = ev_serialise(&f->payload, b + off, cap - off, &tmp);
    if (plen < 0) return -1;
    _put_i32(b, plen_off, cap, plen);
    off += plen;

    off = _put_i32(b, off, cap, f->part_count);      if (off < 0) return -1;
    for (int32_t i = 0; i < f->part_count; i++) {
        off = _put_str(b, off, cap, f->labels ? f->labels[i] : NULL);
        if (off < 0) return -1;
        off = _ser(f->parts[i], b, off, cap);
        if (off < 0) return -1;
    }
    return off;
}

int32_t ev_form_serialise(const EvForm *f, uint8_t *buf, int32_t cap) {
    int32_t end = _ser(f, buf, 0, cap);
    return end < 0 ? -1 : end;
}

static EvForm *_deser(const uint8_t *b, int32_t len, int32_t *off, EvArena *a) {
    int32_t form, role, line;
    int16_t conf;
    int32_t o = *off;
    o = _get_i32(b, o, len, &form); if (o < 0) return NULL;
    o = _get_i32(b, o, len, &role); if (o < 0) return NULL;
    o = _get_i32(b, o, len, &line); if (o < 0) return NULL;
    o = _get_i16(b, o, len, &conf); if (o < 0) return NULL;

    int32_t slen;
    o = _get_i32(b, o, len, &slen); if (o < 0) return NULL;
    char sym[256] = {0};
    if (slen > 0) {
        if (o + slen > len) return NULL;
        int32_t cpy = slen < 255 ? slen : 255;
        memcpy(sym, b + o, (size_t)cpy);
        sym[cpy] = '\0';
        o += slen;
    }

    int32_t plen;
    o = _get_i32(b, o, len, &plen); if (o < 0) return NULL;
    ev_pool tmp; ev_pool_init(&tmp);
    int32_t consumed = 0;
    EValue payload = ev_void();
    if (plen > 0) {
        if (o + plen > len) return NULL;
        payload = ev_deserialise(b + o, plen, &consumed, &tmp);
        o += plen;
    }

    EvForm *f = ev_form_new(a, (EvFormKind)form, (EvRole)role, line);
    if (!f) return NULL;
    f->confidence = conf;
    f->payload    = payload;
    if (slen > 0) f->symbol = ev_arena_strdup(a, sym);

    int32_t pc;
    o = _get_i32(b, o, len, &pc); if (o < 0) return NULL;
    for (int32_t i = 0; i < pc; i++) {
        int32_t llen;
        o = _get_i32(b, o, len, &llen); if (o < 0) return NULL;
        char lab[128] = {0};
        if (llen > 0) {
            if (o + llen > len) return NULL;
            int32_t cpy = llen < 127 ? llen : 127;
            memcpy(lab, b + o, (size_t)cpy);
            lab[cpy] = '\0';
            o += llen;
        }
        int32_t sub_off = o;
        EvForm *child = _deser(b, len, &sub_off, a);
        if (!child) return NULL;
        o = sub_off;
        ev_form_add_part(f, child, llen > 0 ? lab : NULL);
    }
    *off = o;
    return f;
}

EvForm *ev_form_deserialise(const uint8_t *buf, int32_t len,
                            int32_t *consumed, EvArena *a) {
    int32_t off = 0;
    EvForm *f = _deser(buf, len, &off, a);
    if (consumed) *consumed = off;
    return f;
}

/* ─────────────────────────────────────────────
 * DEBUG PRINT
 * ───────────────────────────────────────────── */
void ev_form_print_indent(const EvForm *f, int32_t indent) {
    if (!f) { printf("%*s<null>\n", indent, ""); return; }
    printf("%*s%s[%s]", indent, "", ev_form_name(f->form), ev_role_name(f->role));
    if (f->symbol && f->symbol[0]) printf(" '%s'", f->symbol);
    if (f->form == EV_FORM_ATOM) {
        switch (f->payload.tag) {
            case EV_INT:  printf(" = %lld", (long long)f->payload.body.as_int); break;
            case EV_REAL: printf(" = %g",   f->payload.body.as_real);            break;
            case EV_BOOL: printf(" = %s",   f->payload.body.as_bool?"true":"false"); break;
            case EV_TEXT: printf(" = \"%s\"", f->payload.text);                  break;
            default: break;
        }
    }
    if (f->confidence != E_CERTAIN) printf("  [%d/256]", (int)f->confidence);
    printf("\n");
    for (int32_t i = 0; i < f->part_count; i++) {
        if (f->labels && f->labels[i])
            printf("%*s.%s:\n", indent + 2, "", f->labels[i]);
        ev_form_print_indent(f->parts[i], indent + 4);
    }
}

void ev_form_print(const EvForm *f) { ev_form_print_indent(f, 0); }
