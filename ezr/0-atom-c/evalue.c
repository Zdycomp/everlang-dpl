/*
 * evalue.c — Ever / Tapestry, the unified variant type
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "evalue.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

/* ─────────────────────────────────────────────
 * Global pool
 * ───────────────────────────────────────────── */

ev_pool g_pool;

static int g_pool_inited = 0;

static ev_pool *default_pool(ev_pool *p) {
    if (p) return p;
    if (!g_pool_inited) { ev_pool_init(&g_pool); g_pool_inited = 1; }
    return &g_pool;
}

void ev_pool_init(ev_pool *pool) {
    pool->used = 1; /* slot 0 reserved — invalid ref */
    memset(pool->types, 0, sizeof(pool->types));
    memset(pool->slots, 0, sizeof(pool->slots));
}

int32_t ev_pool_alloc(ev_pool *pool, ev_type type) {
    pool = default_pool(pool);
    if (pool->used >= EV_POOL_MAX) return 0;
    int32_t ref = pool->used++;
    pool->types[ref] = type;
    pool->slots[ref].raw = NULL;
    return ref;
}

void *ev_pool_get(ev_pool *pool, int32_t ref) {
    pool = default_pool(pool);
    if (ref <= 0 || ref >= pool->used) return NULL;
    return pool->slots[ref].raw;
}

ev_blob *ev_pool_blob(ev_pool *pool, int32_t ref) {
    pool = default_pool(pool);
    if (ref <= 0 || ref >= pool->used) return NULL;
    if (pool->types[ref] != EV_BLOB) return NULL;
    return pool->slots[ref].blob;
}

ev_list *ev_pool_list(ev_pool *pool, int32_t ref) {
    pool = default_pool(pool);
    if (ref <= 0 || ref >= pool->used) return NULL;
    if (pool->types[ref] != EV_LIST) return NULL;
    return pool->slots[ref].list;
}

ev_record *ev_pool_record(ev_pool *pool, int32_t ref) {
    pool = default_pool(pool);
    if (ref <= 0 || ref >= pool->used) return NULL;
    if (pool->types[ref] != EV_RECORD) return NULL;
    return pool->slots[ref].rec;
}

void ev_pool_clear(ev_pool *pool) {
    pool = default_pool(pool);
    /* Walk every live slot. ev_pool_free is index-safe and ignores
       slots already emptied, so a double call is harmless. */
    for (int32_t ref = 1; ref < pool->used; ref++)
        ev_pool_free(pool, ref);
    pool->used = 1;          /* ref 0 stays reserved as "not pooled" */
    return;
}

void ev_pool_free(ev_pool *pool, int32_t ref) {
    pool = default_pool(pool);
    if (ref <= 0 || ref >= pool->used) return;
    void *raw = pool->slots[ref].raw;
    if (!raw) return;
    switch (pool->types[ref]) {
        case EV_BLOB: {
            ev_blob *b = pool->slots[ref].blob;
            if (b) { free(b->data); free(b); }
            break;
        }
        case EV_LIST: {
            ev_list *l = pool->slots[ref].list;
            if (l) { free(l->items); free(l); }
            break;
        }
        case EV_RECORD: {
            ev_record *r = pool->slots[ref].rec;
            if (r) { free(r->fields); free(r); }
            break;
        }
        default: free(raw); break;
    }
    pool->slots[ref].raw = NULL;
}

/* ─────────────────────────────────────────────
 * Type name
 * ───────────────────────────────────────────── */

const char *ev_type_name(ev_type t) {
    switch (t) {
        case EV_VOID:   return "void";
        case EV_BOOL:   return "bool";
        case EV_INT:    return "int";
        case EV_REAL:   return "real";
        case EV_TEXT:   return "text";
        case EV_BLOB:   return "blob";
        case EV_LIST:   return "list";
        case EV_RECORD: return "record";
        default:        return "?";
    }
}

/* ─────────────────────────────────────────────
 * Constructors
 * ───────────────────────────────────────────── */

EValue ev_void(void) {
    EValue v; memset(&v, 0, sizeof v);
    v.tag = EV_VOID;
    return v;
}

EValue ev_bool(int b) {
    EValue v; memset(&v, 0, sizeof v);
    v.tag = EV_BOOL; v.body.as_bool = b ? 1 : 0;
    return v;
}

EValue ev_int(int64_t n) {
    EValue v; memset(&v, 0, sizeof v);
    v.tag = EV_INT; v.body.as_int = n;
    return v;
}

EValue ev_real(double d) {
    EValue v; memset(&v, 0, sizeof v);
    v.tag = EV_REAL; v.body.as_real = d;
    return v;
}

EValue ev_text(const char *s) {
    EValue v; memset(&v, 0, sizeof v);
    v.tag = EV_TEXT;
    if (s) { strncpy(v.text, s, EV_INLINE_MAX - 1); v.text[EV_INLINE_MAX-1] = '\0'; }
    return v;
}

EValue ev_blob_new(const uint8_t *data, int32_t len, ev_pool *pool) {
    pool = default_pool(pool);
    EValue v; memset(&v, 0, sizeof v);
    v.tag = EV_BLOB;
    int32_t ref = ev_pool_alloc(pool, EV_BLOB);
    if (!ref) return ev_text("[blob alloc failed]");
    ev_blob *b = (ev_blob*)calloc(1, sizeof *b);
    if (!b) return ev_text("[blob alloc failed]");
    b->h.ref = ref; b->h.type = EV_BLOB; b->h.len = len; b->h.capacity = len;
    b->data = (uint8_t*)malloc(len > 0 ? len : 1);
    if (!b->data) { free(b); return ev_text("[blob alloc failed]"); }
    if (data && len > 0) memcpy(b->data, data, len);
    pool->slots[ref].blob = b;
    v.body.pool_ref = ref;
    return v;
}

EValue ev_list_new(ev_pool *pool) {
    pool = default_pool(pool);
    EValue v; memset(&v, 0, sizeof v);
    v.tag = EV_LIST;
    int32_t ref = ev_pool_alloc(pool, EV_LIST);
    if (!ref) return ev_void();
    ev_list *l = (ev_list*)calloc(1, sizeof *l);
    if (!l) return ev_void();
    l->h.ref = ref; l->h.type = EV_LIST; l->h.len = 0; l->h.capacity = 8;
    l->items = (EValue*)calloc(8, sizeof(EValue));
    l->confidence = E_CERTAIN;
    pool->slots[ref].list = l;
    v.body.pool_ref = ref;
    return v;
}

EValue ev_record_new(ev_pool *pool) {
    pool = default_pool(pool);
    EValue v; memset(&v, 0, sizeof v);
    v.tag = EV_RECORD;
    int32_t ref = ev_pool_alloc(pool, EV_RECORD);
    if (!ref) return ev_void();
    ev_record *r = (ev_record*)calloc(1, sizeof *r);
    if (!r) return ev_void();
    r->h.ref = ref; r->h.type = EV_RECORD; r->h.len = 0; r->h.capacity = 8;
    r->fields = (ev_field*)calloc(8, sizeof(ev_field));
    r->confidence = E_CERTAIN;
    pool->slots[ref].rec = r;
    v.body.pool_ref = ref;
    return v;
}

/* ─────────────────────────────────────────────
 * Composite operations
 * ───────────────────────────────────────────── */

int ev_list_push(EValue *list, EValue item, ev_pool *pool) {
    if (list->tag != EV_LIST) return 0;
    ev_list *l = ev_pool_list(pool, list->body.pool_ref);
    if (!l) return 0;
    if (l->h.len >= l->h.capacity) {
        int32_t newcap = l->h.capacity * 2;
        EValue *newbuf = (EValue*)realloc(l->items, newcap * sizeof(EValue));
        if (!newbuf) return 0;
        l->items = newbuf; l->h.capacity = newcap;
    }
    l->items[l->h.len++] = item;
    return 1;
}

EValue ev_list_get(const EValue *list, int32_t idx, ev_pool *pool) {
    if (list->tag != EV_LIST) return ev_void();
    ev_list *l = ev_pool_list(pool, list->body.pool_ref);
    if (!l || idx < 0 || idx >= l->h.len) return ev_void();
    return l->items[idx];
}

int32_t ev_list_len(const EValue *list, ev_pool *pool) {
    if (list->tag != EV_LIST) return 0;
    ev_list *l = ev_pool_list(pool, list->body.pool_ref);
    return l ? l->h.len : 0;
}

int ev_record_set(EValue *rec, const char *name, EValue val,
                  int16_t conf, ev_pool *pool) {
    if (rec->tag != EV_RECORD || !name) return 0;
    ev_record *r = ev_pool_record(pool, rec->body.pool_ref);
    if (!r) return 0;
    /* update existing field */
    for (int i = 0; i < r->h.len; i++) {
        if (strncmp(r->fields[i].name, name, EV_FIELD_NAME_MAX-1) == 0) {
            r->fields[i].value = val;
            r->fields[i].confidence = conf;
            return 1;
        }
    }
    /* add new field */
    if (r->h.len >= r->h.capacity) {
        int32_t newcap = r->h.capacity * 2;
        ev_field *nb = (ev_field*)realloc(r->fields, newcap * sizeof(ev_field));
        if (!nb) return 0;
        r->fields = nb; r->h.capacity = newcap;
    }
    ev_field *f = &r->fields[r->h.len++];
    memset(f, 0, sizeof *f);
    strncpy(f->name, name, EV_FIELD_NAME_MAX-1);
    f->value = val; f->confidence = conf;
    return 1;
}

EValue ev_record_get(const EValue *rec, const char *name, ev_pool *pool) {
    if (rec->tag != EV_RECORD || !name) return ev_void();
    ev_record *r = ev_pool_record(pool, rec->body.pool_ref);
    if (!r) return ev_void();
    for (int i = 0; i < r->h.len; i++)
        if (strncmp(r->fields[i].name, name, EV_FIELD_NAME_MAX-1) == 0)
            return r->fields[i].value;
    return ev_void();
}

int ev_record_has(const EValue *rec, const char *name, ev_pool *pool) {
    if (rec->tag != EV_RECORD || !name) return 0;
    ev_record *r = ev_pool_record(pool, rec->body.pool_ref);
    if (!r) return 0;
    for (int i = 0; i < r->h.len; i++)
        if (strncmp(r->fields[i].name, name, EV_FIELD_NAME_MAX-1) == 0)
            return 1;
    return 0;
}

/* ─────────────────────────────────────────────
 * Predicates and equality
 * ───────────────────────────────────────────── */

int ev_is_void(const EValue *v)      { return v->tag == EV_VOID; }
int ev_is_scalar(const EValue *v)    { return v->tag <= EV_TEXT; }
int ev_is_composite(const EValue *v) { return v->tag >= EV_BLOB; }

int ev_equal(const EValue *a, const EValue *b, ev_pool *pool) {
    if (a->tag != b->tag) {
        /* INT and REAL interoperate */
        if ((a->tag == EV_INT && b->tag == EV_REAL))
            return (double)a->body.as_int == b->body.as_real;
        if ((a->tag == EV_REAL && b->tag == EV_INT))
            return a->body.as_real == (double)b->body.as_int;
        return 0;
    }
    switch ((ev_type)a->tag) {
        case EV_VOID:   return 1;
        case EV_BOOL:   return a->body.as_bool == b->body.as_bool;
        case EV_INT:    return a->body.as_int  == b->body.as_int;
        case EV_REAL:   return fabs(a->body.as_real - b->body.as_real) < 1e-12;
        case EV_TEXT:   return strncmp(a->text, b->text, EV_INLINE_MAX) == 0;
        case EV_BLOB: {
            ev_blob *ba = ev_pool_blob(pool, a->body.pool_ref);
            ev_blob *bb = ev_pool_blob(pool, b->body.pool_ref);
            if (!ba || !bb) return 0;
            return ba->h.len == bb->h.len &&
                   memcmp(ba->data, bb->data, ba->h.len) == 0;
        }
        case EV_LIST: {
            ev_list *la = ev_pool_list(pool, a->body.pool_ref);
            ev_list *lb = ev_pool_list(pool, b->body.pool_ref);
            if (!la || !lb || la->h.len != lb->h.len) return 0;
            for (int i = 0; i < la->h.len; i++)
                if (!ev_equal(&la->items[i], &lb->items[i], pool)) return 0;
            return 1;
        }
        case EV_RECORD: {
            ev_record *ra = ev_pool_record(pool, a->body.pool_ref);
            ev_record *rb = ev_pool_record(pool, b->body.pool_ref);
            if (!ra || !rb || ra->h.len != rb->h.len) return 0;
            for (int i = 0; i < ra->h.len; i++) {
                ev_field *f = &ra->fields[i];
                EValue bval = ev_record_get(b, f->name, pool);
                if (!ev_equal(&f->value, &bval, pool)) return 0;
            }
            return 1;
        }
        default: return 0;
    }
}

/* ─────────────────────────────────────────────
 * Serialisation — self-describing wire format
 *
 * Format (little-endian):
 *   [1 byte: tag]
 *   VOID:   (nothing)
 *   BOOL:   [1 byte: 0 or 1]
 *   INT:    [8 bytes: int64_t LE]
 *   REAL:   [8 bytes: double IEEE 754 LE]
 *   TEXT:   [2 bytes: length] [length bytes: UTF-8]
 *   BLOB:   [4 bytes: length] [length bytes]
 *   LIST:   [4 bytes: count]  [count × serialised EValue]
 *   RECORD: [4 bytes: nfields]
 *           [nfields × ([1 byte: namelen][name][serialised EValue])]
 * ───────────────────────────────────────────── */

static int32_t write_u8(uint8_t *buf, int32_t cap, int32_t pos, uint8_t v) {
    if (pos >= cap) return -1;
    buf[pos] = v; return pos + 1;
}
static int32_t write_u16le(uint8_t *buf, int32_t cap, int32_t pos, uint16_t v) {
    if (pos + 2 > cap) return -1;
    buf[pos]   = v & 0xFF;
    buf[pos+1] = (v >> 8) & 0xFF;
    return pos + 2;
}
static int32_t write_i32le(uint8_t *buf, int32_t cap, int32_t pos, int32_t v) {
    if (pos + 4 > cap) return -1;
    uint32_t u = (uint32_t)v;
    buf[pos]=u&0xFF; buf[pos+1]=(u>>8)&0xFF;
    buf[pos+2]=(u>>16)&0xFF; buf[pos+3]=(u>>24)&0xFF;
    return pos + 4;
}
static int32_t write_i64le(uint8_t *buf, int32_t cap, int32_t pos, int64_t v) {
    if (pos + 8 > cap) return -1;
    uint64_t u = (uint64_t)v;
    for (int i = 0; i < 8; i++) { buf[pos+i] = u & 0xFF; u >>= 8; }
    return pos + 8;
}

int32_t ev_serialise(const EValue *v, uint8_t *buf, int32_t cap, ev_pool *pool) {
    int32_t p = 0;
    p = write_u8(buf, cap, p, (uint8_t)v->tag);
    if (p < 0) return -1;
    switch ((ev_type)v->tag) {
        case EV_VOID: break;
        case EV_BOOL: p = write_u8(buf,cap,p,(uint8_t)v->body.as_bool); break;
        case EV_INT:  p = write_i64le(buf,cap,p,v->body.as_int); break;
        case EV_REAL: {
            int64_t bits; memcpy(&bits,&v->body.as_real,8);
            p = write_i64le(buf,cap,p,bits); break;
        }
        case EV_TEXT: {
            uint16_t slen = (uint16_t)strlen(v->text); if (slen >= EV_INLINE_MAX) slen = EV_INLINE_MAX-1;
            p = write_u16le(buf,cap,p,slen);
            if (p < 0 || p + slen > cap) return -1;
            memcpy(buf+p, v->text, slen); p += slen; break;
        }
        case EV_BLOB: {
            ev_blob *b = ev_pool_blob(pool, v->body.pool_ref);
            if (!b) return -1;
            p = write_i32le(buf,cap,p,b->h.len);
            if (p < 0 || p + b->h.len > cap) return -1;
            memcpy(buf+p, b->data, b->h.len); p += b->h.len; break;
        }
        case EV_LIST: {
            ev_list *l = ev_pool_list(pool, v->body.pool_ref);
            if (!l) return -1;
            p = write_i32le(buf,cap,p,l->h.len);
            if (p < 0) return -1;
            for (int i = 0; i < l->h.len; i++) {
                int32_t sub = ev_serialise(&l->items[i], buf+p, cap-p, pool);
                if (sub < 0) return -1;
                p += sub;
            }
            break;
        }
        case EV_RECORD: {
            ev_record *r = ev_pool_record(pool, v->body.pool_ref);
            if (!r) return -1;
            p = write_i32le(buf,cap,p,r->h.len);
            if (p < 0) return -1;
            for (int i = 0; i < r->h.len; i++) {
                ev_field *f = &r->fields[i];
                uint8_t nlen = (uint8_t)strlen(f->name); if (nlen >= EV_FIELD_NAME_MAX) nlen = EV_FIELD_NAME_MAX-1;
                p = write_u8(buf,cap,p,nlen);
                if (p < 0 || p + nlen > cap) return -1;
                memcpy(buf+p, f->name, nlen); p += nlen;
                int32_t sub = ev_serialise(&f->value, buf+p, cap-p, pool);
                if (sub < 0) return -1;
                p += sub;
            }
            break;
        }
        default: return -1;
    }
    return p;
}

static uint8_t  read_u8(const uint8_t*b,int32_t*p){return b[(*p)++];}
static uint16_t read_u16le(const uint8_t*b,int32_t*p){
    uint16_t v=b[*p]|(b[*p+1]<<8); *p+=2; return v;}
static int32_t read_i32le(const uint8_t*b,int32_t*p){
    uint32_t v=b[*p]|(b[*p+1]<<8)|(b[*p+2]<<16)|((uint32_t)b[*p+3]<<24);
    *p+=4; return (int32_t)v;}
static int64_t read_i64le(const uint8_t*b,int32_t*p){
    uint64_t v=0;
    for(int i=0;i<8;i++){v|=((uint64_t)b[*p+i]<<(8*i));}
    *p+=8; return (int64_t)v;}

EValue ev_deserialise(const uint8_t *buf, int32_t len,
                      int32_t *consumed, ev_pool *pool) {
    int32_t p = 0;
    if (len < 1) { if (consumed) *consumed=0; return ev_void(); }
    ev_type tag = (ev_type)read_u8(buf, &p);
    EValue v; memset(&v, 0, sizeof v); v.tag = tag;
    switch (tag) {
        case EV_VOID: break;
        case EV_BOOL: v.body.as_bool = read_u8(buf, &p); break;
        case EV_INT:  v.body.as_int  = read_i64le(buf, &p); break;
        case EV_REAL: {
            int64_t bits = read_i64le(buf, &p);
            memcpy(&v.body.as_real, &bits, 8); break;
        }
        case EV_TEXT: {
            uint16_t slen = read_u16le(buf, &p);
            if (slen >= EV_INLINE_MAX) slen = EV_INLINE_MAX - 1;
            memcpy(v.text, buf+p, slen); v.text[slen]='\0'; p+=slen; break;
        }
        case EV_BLOB: {
            int32_t blen = read_i32le(buf, &p);
            v = ev_blob_new(buf+p, blen, pool); p += blen; break;
        }
        case EV_LIST: {
            int32_t count = read_i32le(buf, &p);
            v = ev_list_new(pool);
            for (int i = 0; i < count; i++) {
                int32_t sub = 0;
                EValue item = ev_deserialise(buf+p, len-p, &sub, pool);
                ev_list_push(&v, item, pool);
                p += sub;
            }
            break;
        }
        case EV_RECORD: {
            int32_t nf = read_i32le(buf, &p);
            v = ev_record_new(pool);
            for (int i = 0; i < nf; i++) {
                uint8_t nlen = read_u8(buf, &p);
                char name[EV_FIELD_NAME_MAX]; memset(name,0,sizeof name);
                memcpy(name, buf+p, nlen); p += nlen;
                int32_t sub = 0;
                EValue fval = ev_deserialise(buf+p, len-p, &sub, pool);
                ev_record_set(&v, name, fval, E_CERTAIN, pool);
                p += sub;
            }
            break;
        }
        default: v = ev_void(); break;
    }
    if (consumed) *consumed = p;
    return v;
}

/* ─────────────────────────────────────────────
 * Lift from source languages
 * ───────────────────────────────────────────── */

EValue ev_from_literal(const char *literal, e_lang lang, ev_pool *pool) {
    if (!literal || !*literal) return ev_void();
    /* NULL spellings */
    const char *nulls[] = {"null","nil","None","NULL","undefined","",NULL};
    for (int i = 0; nulls[i]; i++)
        if (strcmp(literal, nulls[i]) == 0) return ev_void();
    /* bool */
    if (!strcmp(literal,"true")||!strcmp(literal,"True")) return ev_bool(1);
    if (!strcmp(literal,"false")||!strcmp(literal,"False")) return ev_bool(0);
    /* int */
    char *end; long long iv = strtoll(literal, &end, 10);
    if (*end == '\0') return ev_int((int64_t)iv);
    /* real */
    double dv = strtod(literal, &end);
    if (*end == '\0') return ev_real(dv);
    /* quoted string */
    size_t slen = strlen(literal);
    if (slen >= 2 && (literal[0]=='"'||literal[0]=='\'') &&
        literal[slen-1]==literal[0]) {
        if (slen - 2 < EV_INLINE_MAX) {
            char tmp[EV_INLINE_MAX]; memset(tmp,0,sizeof tmp);
            memcpy(tmp, literal+1, slen-2); tmp[slen-2]='\0';
            return ev_text(tmp);
        }
        return ev_blob_new((const uint8_t*)literal+1, (int32_t)(slen-2), pool);
    }
    /* fall back to text */
    return ev_text(literal);
    (void)lang;
}

EValue ev_from_sql_row(const char **cols, const char **vals,
                       int ncols, ev_pool *pool) {
    EValue rec = ev_record_new(pool);
    for (int i = 0; i < ncols; i++) {
        EValue fval = vals[i]
            ? ev_from_literal(vals[i], E_LANG_SQL, pool)
            : ev_void();
        ev_record_set(&rec, cols[i], fval, E_CERTAIN, pool);
    }
    return rec;
}

EValue ev_from_html_element(const char *tag, const char **attrs,
                             int nattrs, ev_pool *pool) {
    EValue rec = ev_record_new(pool);
    ev_record_set(&rec, "tag", ev_text(tag), E_CERTAIN, pool);
    EValue arec = ev_record_new(pool);
    for (int i = 0; i + 1 < nattrs; i += 2)
        ev_record_set(&arec, attrs[i], ev_text(attrs[i+1]), E_CERTAIN, pool);
    ev_record_set(&rec, "attrs", arec, E_CERTAIN, pool);
    EValue children = ev_list_new(pool);
    ev_record_set(&rec, "children", children, E_CERTAIN, pool);
    return rec;
}

/* ─────────────────────────────────────────────
 * Plain-language description (for the teaching layer)
 * ───────────────────────────────────────────── */

const char *ev_describe(const EValue *v, ev_pool *pool,
                        char *buf, int32_t cap) {
    switch ((ev_type)v->tag) {
        case EV_VOID:   snprintf(buf,cap,"nothing"); break;
        case EV_BOOL:   snprintf(buf,cap,v->body.as_bool ? "true" : "false"); break;
        case EV_INT:    snprintf(buf,cap,"%lld",(long long)v->body.as_int); break;
        case EV_REAL:   snprintf(buf,cap,"%.6g",v->body.as_real); break;
        case EV_TEXT:   snprintf(buf,cap,"\"%s\"",v->text); break;
        case EV_BLOB: {
            ev_blob *b = ev_pool_blob(pool, v->body.pool_ref);
            snprintf(buf,cap,"<blob %d bytes>", b ? b->h.len : 0); break;
        }
        case EV_LIST: {
            ev_list *l = ev_pool_list(pool, v->body.pool_ref);
            snprintf(buf,cap,"<list %d items>", l ? l->h.len : 0); break;
        }
        case EV_RECORD: {
            ev_record *r = ev_pool_record(pool, v->body.pool_ref);
            if (!r) { snprintf(buf,cap,"<record>"); break; }
            int pos = snprintf(buf,cap,"{");
            for (int i = 0; i < r->h.len && pos < cap-4; i++) {
                pos += snprintf(buf+pos, cap-pos, "%s%s",
                    r->fields[i].name, i < r->h.len-1 ? ", " : "");
            }
            snprintf(buf+pos, cap-pos, "}"); break;
        }
        default: snprintf(buf,cap,"?"); break;
    }
    return buf;
}
