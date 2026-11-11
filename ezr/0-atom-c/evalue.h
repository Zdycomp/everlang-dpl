/*
 * evalue.h — Ever / Tapestry, the unified variant type
 *
 * ONE TYPE ACROSS ALL LAYERS.
 *
 * An e_particle holds what it holds — its T — through an EValue.
 * Every layer that Ever threads through maps to exactly one EValue
 * variant, and the mapping is stated here rather than scattered
 * across seven implementations.
 *
 *   SCALAR (inline in the 440-byte ABI particle):
 *     VOID    — nothing, but explicit. distinct from Z.
 *     BOOL    — true / false
 *     INT     — int64_t. covers SQL INTEGER, Python int (≤64 bit), C int.
 *     REAL    — double.  covers SQL REAL, Python float, C double.
 *     TEXT    — char[E_TEXT_MAX]. short strings, identifiers, names.
 *
 *   COMPOSITE (pool-backed; particle carries int32_t pool_ref):
 *     BLOB    — arbitrary bytes. long strings, HTML source, binary.
 *     LIST    — ordered sequence of EValue. Python list, SQL result column.
 *     RECORD  — named fields, each an EValue. SQL row, HTML element, object.
 *
 * The pool is the shared backing store. The same RECORD is visible
 * identically from Python (via abi.py), C++ (via evalue.cpp), and
 * SQL (via the archive's evalue_pool table).
 *
 * What each language maps to:
 *   Python int          INT    inline
 *   Python float        REAL   inline
 *   Python bool         BOOL   inline
 *   Python str (short)  TEXT   inline
 *   Python str (long)   BLOB   pool
 *   Python list         LIST   pool
 *   Python dict         RECORD pool
 *   SQL INTEGER         INT    inline
 *   SQL TEXT            TEXT   inline / BLOB pool
 *   SQL REAL            REAL   inline
 *   SQL row             RECORD pool
 *   HTML element        RECORD pool  (tag→TEXT, attrs→RECORD, children→LIST)
 *   HTML text node      TEXT   inline / BLOB pool
 *   C int64_t           INT    inline
 *   C double            REAL   inline
 *   C char*             TEXT   inline / BLOB pool
 *   C struct            RECORD pool
 *
 * ABI rules (same guarantees as e_particle):
 *   - _pack_ = 1 throughout
 *   - all enum fields stored as int32_t
 *   - E_LAYOUT_ASSERT-compatible offsets for cross-language checks
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef EVALUE_H
#define EVALUE_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "tapestry.h"   /* E_TEXT_MAX, E_PACK_BEGIN/END, E_LAYOUT_ASSERT */

/* ─────────────────────────────────────────────
 * The type tag
 * ───────────────────────────────────────────── */

typedef enum {
    EV_VOID   = 0,   /* no value, but explicit (≠ Z)                    */
    EV_BOOL   = 1,   /* int32_t 0 or 1                                  */
    EV_INT    = 2,   /* int64_t                                          */
    EV_REAL   = 3,   /* double                                           */
    EV_TEXT   = 4,   /* char[E_TEXT_MAX], inline, NUL-terminated         */
    EV_BLOB   = 5,   /* pool_ref → ev_blob                              */
    EV_LIST   = 6,   /* pool_ref → ev_list                              */
    EV_RECORD = 7,   /* pool_ref → ev_record                            */
} ev_type;

const char *ev_type_name(ev_type t);

/* ─────────────────────────────────────────────
 * The variant — inline scalars + pool ref for composites
 *
 * Total size: 4 (tag) + 4 (pad) + 8 (body) + 192 (text) = 208 bytes.
 * This fills exactly the first 208 bytes of e_particle, replacing the
 * current (type + _pad0 + value union + text) layout which was already
 * 208 bytes. The ABI is preserved.
 * ───────────────────────────────────────────── */

#define EV_INLINE_MAX  E_TEXT_MAX   /* 192 bytes, same as before       */

E_PACK_BEGIN
typedef struct {
    int32_t  tag;        /* ev_type, stored as int32_t     @  0 (4) */
    int32_t  _pad;       /* explicit padding                @  4 (4) */
    union {
        int32_t  as_bool;  /* EV_BOOL                        @  8     */
        int64_t  as_int;   /* EV_INT                         @  8     */
        double   as_real;  /* EV_REAL                        @  8     */
        int32_t  pool_ref; /* EV_BLOB / EV_LIST / EV_RECORD  @  8     */
    } body;              /*                                 @  8 (8) */
    char     text[EV_INLINE_MAX]; /* EV_TEXT inline         @ 16 (192)*/
} EValue;                /*                                 total 208 */
E_PACK_END

/* Layout assertions for EValue itself */
#define EV_SIZEOF 208
typedef char ev_check_size    [(sizeof(EValue)           == EV_SIZEOF) ? 1 : -1];
typedef char ev_check_tag     [(offsetof(EValue, tag)    ==  0)        ? 1 : -1];
typedef char ev_check_body    [(offsetof(EValue, body)   ==  8)        ? 1 : -1];
typedef char ev_check_text    [(offsetof(EValue, text)   == 16)        ? 1 : -1];

/* ─────────────────────────────────────────────
 * The pool — composite values that don't fit inline
 * ───────────────────────────────────────────── */

/* A pool entry header. Every composite type starts with this. */
E_PACK_BEGIN
typedef struct {
    int32_t  ref;        /* this entry's own id (for verification)  */
    int32_t  type;       /* ev_type of the composite                */
    int32_t  len;        /* items / bytes                           */
    int32_t  capacity;   /* allocated capacity                      */
} ev_pool_header;
E_PACK_END

/* BLOB — arbitrary bytes, arbitrary length */
E_PACK_BEGIN
typedef struct {
    ev_pool_header h;
    uint8_t *data;       /* heap-allocated                          */
} ev_blob;
E_PACK_END

/* LIST — ordered sequence of EValue */
E_PACK_BEGIN
typedef struct {
    ev_pool_header h;
    EValue  *items;      /* heap-allocated array of EValue          */
    int16_t  confidence; /* the list's own trust level              */
    int16_t  _pad;
} ev_list;
E_PACK_END

/* FIELD — one named field in a RECORD */
#define EV_FIELD_NAME_MAX 64
E_PACK_BEGIN
typedef struct {
    char    name[EV_FIELD_NAME_MAX];
    EValue  value;
    int16_t confidence;  /* field-level trust                       */
    int16_t _pad;
} ev_field;
E_PACK_END

/* RECORD — named fields, each an EValue.
 * Maps to: SQL row, HTML element, Python dict, C struct, JSON object. */
E_PACK_BEGIN
typedef struct {
    ev_pool_header h;
    ev_field *fields;    /* heap-allocated array of ev_field        */
    int16_t   confidence;
    int16_t   _pad;
} ev_record;
E_PACK_END

/* ─────────────────────────────────────────────
 * The pool allocator
 *
 * A flat array of pool slots. Every composite gets a slot_id.
 * Slot 0 is always invalid (like NULL).
 * The pool is per-thread-or-per-arena; the archive persists it to SQL.
 * ───────────────────────────────────────────── */

#define EV_POOL_MAX 4096

typedef struct {
    int      used;
    ev_type  types[EV_POOL_MAX];
    union {
        ev_blob   *blob;
        ev_list   *list;
        ev_record *rec;
        void      *raw;
    } slots[EV_POOL_MAX];
} ev_pool;

/* global pool — one per process; threads use arenas */
extern ev_pool g_pool;

void       ev_pool_init(ev_pool *pool);
int32_t    ev_pool_alloc(ev_pool *pool, ev_type type);
void      *ev_pool_get(ev_pool *pool, int32_t ref);
ev_blob   *ev_pool_blob(ev_pool *pool, int32_t ref);
ev_list   *ev_pool_list(ev_pool *pool, int32_t ref);
ev_record *ev_pool_record(ev_pool *pool, int32_t ref);
void       ev_pool_free(ev_pool *pool, int32_t ref);

/*
 * ev_pool_clear — release EVERY entry in the pool and reset it.
 *
 * ev_pool_free releases one ref. A pool is documented as per-request,
 * so without a bulk teardown a caller must remember every ref it ever
 * minted — including refs created inside nested composites it never
 * named. That is not a discipline a server can keep, and it is the
 * same reason EvArena owns its slabs rather than handing out
 * individually-freed blocks.
 *
 * Safe to call twice; safe on a pool that was only ever init'd.
 */
void       ev_pool_clear(ev_pool *pool);

/* ─────────────────────────────────────────────
 * Constructors
 * ───────────────────────────────────────────── */

EValue ev_void(void);
EValue ev_bool(int b);
EValue ev_int(int64_t v);
EValue ev_real(double v);
EValue ev_text(const char *s);          /* copies; truncates at EV_INLINE_MAX */
EValue ev_blob_new(const uint8_t *data, int32_t len, ev_pool *pool);
EValue ev_list_new(ev_pool *pool);
EValue ev_record_new(ev_pool *pool);

/* ─────────────────────────────────────────────
 * Composite operations
 * ───────────────────────────────────────────── */

/* LIST */
int     ev_list_push(EValue *list, EValue item, ev_pool *pool);
EValue  ev_list_get(const EValue *list, int32_t idx, ev_pool *pool);
int32_t ev_list_len(const EValue *list, ev_pool *pool);

/* RECORD */
int    ev_record_set(EValue *rec, const char *name, EValue val,
                     int16_t conf, ev_pool *pool);
EValue ev_record_get(const EValue *rec, const char *name, ev_pool *pool);
int    ev_record_has(const EValue *rec, const char *name, ev_pool *pool);

/* ─────────────────────────────────────────────
 * Predicates and comparison
 * ───────────────────────────────────────────── */

int ev_is_void(const EValue *v);
int ev_is_scalar(const EValue *v);
int ev_is_composite(const EValue *v);
int ev_equal(const EValue *a, const EValue *b, ev_pool *pool);

/* ─────────────────────────────────────────────
 * Serialisation — the flat wire format
 *
 * An EValue serialises to a self-describing byte stream:
 *   [1 byte tag] [payload]
 * Scalars fit in ≤9 bytes. Composites recurse. The format is the same
 * for SQL BLOB columns, the ABI buffer, and network transfer.
 * ───────────────────────────────────────────── */

#define EV_SERIAL_MAX 65536

int32_t ev_serialise(const EValue *v, uint8_t *buf, int32_t cap,
                     ev_pool *pool);
EValue  ev_deserialise(const uint8_t *buf, int32_t len,
                       int32_t *consumed, ev_pool *pool);

/* ─────────────────────────────────────────────
 * Lift from source languages
 *
 * Each lifter is the C implementation of A-ANY for that language's
 * native literal syntax. Python, Ruby, SQL and HTML all call into
 * these through the ABI layer.
 * ───────────────────────────────────────────── */

EValue ev_from_literal(const char *literal, e_lang lang, ev_pool *pool);
EValue ev_from_sql_row(const char **cols, const char **vals,
                       int ncols, ev_pool *pool);
EValue ev_from_html_element(const char *tag, const char **attrs,
                             int nattrs, ev_pool *pool);

/* Describe an EValue in plain language (for the teaching layer) */
const char *ev_describe(const EValue *v, ev_pool *pool,
                        char *buf, int32_t cap);

#endif /* EVALUE_H */
