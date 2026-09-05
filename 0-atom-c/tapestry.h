/*
 * tapestry.h — Ever / Tapestry, the atom
 *
 * The E-particle, restored to E<T>.
 *
 * v1 bound  name -> trust.        Correct for a checker.
 * v2 binds  name -> thing -> trust. Required for a language you write in.
 *
 * A thread in the weave. Every thread carries what it holds, how much it
 * is trusted, where it came from, and an anchor that survives translation
 * into any other language. Pull one thread and you can trace it through
 * the whole cloth.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 * Theory of Relative E:  E = MC²
 */

#ifndef TAPESTRY_H
#define TAPESTRY_H

#include <stdint.h>
#include <stddef.h>

/* ─────────────────────────────────────────────
 * ABI BOUNDARY
 *
 * Every field in e_particle has an explicit size and an explicit offset.
 * Implicit compiler padding is disabled. Static assertions enforce the
 * layout at compile time so the Python ctypes layer, the C++ phase
 * engine, and the C atom stay in agreement whether they are compiled by
 * gcc, clang, or MSVC.
 *
 * The layout is the contract. The assertions are the proof.
 * ───────────────────────────────────────────── */

#if defined(_MSC_VER)
  #define E_PACK_BEGIN __pragma(pack(push, 1))
  #define E_PACK_END   __pragma(pack(pop))
#elif defined(__GNUC__) || defined(__clang__)
  #define E_PACK_BEGIN _Pragma("pack(push, 1)")
  #define E_PACK_END   _Pragma("pack(pop)")
#else
  #define E_PACK_BEGIN
  #define E_PACK_END
  #warning "Unknown compiler: ABI packing not guaranteed"
#endif

/* ─────────────────────────────────────────────
 * The scale. Unchanged from v1 — these are load bearing.
 * ───────────────────────────────────────────── */

#define E_ZERO               0     /* Z. zero-absolute.              */
#define E_CERTAIN            256   /* 4^4. the states of a byte.     */
#define E_EXECUTE_FLOOR      128   /* 256 / 2                        */
#define E_PI_WIDTH_WARN      81    /* floor(256 / pi)                */
#define E_PI_WIDTH_ENUMERATE 25    /* floor(256 / pi^2)              */
#define E_EMULATE_CEILING    3     /* floor(pi)                      */
#define E_PHI_SCALED         1618  /* phi * 1000, integer math       */
#define E_PHI_DENOM          1000
#define E_ASCEND_POINTS      3     /* aligned points to earn a rise  */

/* ─────────────────────────────────────────────
 * Binding modes. A binding is a name pointing at a thing; these are
 * the ways that can stand, and the ways it can fail.
 * ───────────────────────────────────────────── */

typedef enum {
    E_STATE_Z         = 0,  /* unbound. unknown. contagious.            */
    E_STATE_CONFIDENT = 1,  /* bound, trusted 1..255                    */
    E_STATE_CERTAIN   = 2,  /* bound, verified at 256. earned only.     */
    E_STATE_EQUIV     = 3,  /* bound to a range. pi governs width.      */
    E_STATE_EXPRESS   = 4,  /* shape bound, value pending               */
    E_STATE_EMULATING = 5,  /* running on a neighbour's pattern         */
    E_STATE_EVOLVED   = 6,  /* advanced through a closed force loop     */
    E_STATE_ANCHORED  = 7,  /* identity pinned across translation       */
    E_STATE_ABSENT    = 8,  /* not present, reason preserved            */
    E_STATE_ERROR     = 9   /* misbound. archived as a boundary marker. */
} e_state;

/* The five ways a binding fails. Every structurally checkable error in
 * every language reduces to one of these. */
typedef enum {
    E_DEFECT_NONE       = 0,
    E_DEFECT_UNBOUND    = 1,  /* name points at nothing               */
    E_DEFECT_MISBOUND   = 2,  /* name points at the wrong kind        */
    E_DEFECT_UNBOUNDED  = 3,  /* extent never delimited               */
    E_DEFECT_OVERBOUND  = 4,  /* many names, one thing, no order      */
    E_DEFECT_ORPHANED   = 5   /* thing outlives every name reaching it */
} e_defect;

/* Source language. Ever accepts all of them; Assimilate moves between. */
typedef enum {
    E_LANG_C = 0, E_LANG_CPP = 1, E_LANG_PYTHON = 2, E_LANG_RUBY = 3,
    E_LANG_SQL = 4, E_LANG_JAVA = 5, E_LANG_HTML = 6, E_LANG_RUST = 7,
    E_LANG_GO = 8, E_LANG_TS = 9, E_LANG_SWIFT = 10, E_LANG_EVER = 11
} e_lang;

/* What the particle actually holds. This is the T. */
typedef enum {
    E_TYPE_VOID = 0, E_TYPE_INT = 1, E_TYPE_REAL = 2, E_TYPE_TEXT = 3,
    E_TYPE_BOOL = 4, E_TYPE_LIST = 5, E_TYPE_FOREIGN = 6
} e_type;

/* ─────────────────────────────────────────────
 * The thread
 * ───────────────────────────────────────────── */

#define E_IDENT_MAX  64
#define E_REASON_MAX 128
#define E_TEXT_MAX   192

E_PACK_BEGIN
typedef struct {
    /* ── what it holds ── the T that v1 dropped ──
     * All enum fields stored as fixed-width integers so the layout is
     * identical on 32-bit and 64-bit targets. */
    int32_t  type;                   /* e_type,    4 bytes @ 0   */
    int32_t  _pad0;                  /* explicit,  4 bytes @ 4   */
    union {
        int64_t as_int;
        double  as_real;
        int32_t as_bool;
        int32_t as_ref;
    } value;                         /* union,     8 bytes @ 8   */
    char     text[E_TEXT_MAX];       /* TEXT/FOREIGN, 192 @ 16   */

    /* ── how much it is trusted ── */
    int32_t  state;                  /* e_state,   4 bytes @ 208 */
    int32_t  defect;                 /* e_defect,  4 bytes @ 212 */
    int16_t  confidence;             /* 0..256,    2 bytes @ 216 */
    int16_t  lo;                     /* Equiv lo,  2 bytes @ 218 */
    int16_t  hi;                     /* Equiv hi,  2 bytes @ 220 */
    int16_t  _pad1;                  /* explicit,  2 bytes @ 222 */

    /* ── where it came from ── */
    int32_t  lang;                   /* e_lang,    4 bytes @ 224 */
    uint8_t  error_distance;         /*            1 byte  @ 228 */
    uint8_t  generation;             /*            1 byte  @ 229 */
    uint8_t  ascend_points;          /*            1 byte  @ 230 */
    uint8_t  _pad2;                  /* explicit,  1 byte  @ 231 */

    /* ── the anchor: identity that survives translation ── */
    uint32_t anchor_id;              /* 0=unanchored, 4 @ 232    */
    int32_t  archive_id;             /*            4 bytes @ 236 */
    int64_t  born_ms;                /*            8 bytes @ 240 */
    char     ident[E_IDENT_MAX];     /*           64 bytes @ 248 */
    char     reason[E_REASON_MAX];   /*          128 bytes @ 312 */
                                     /* total:         440 @ 440 */
} e_particle;
E_PACK_END

/* ─────────────────────────────────────────────
 * Static layout assertions: the contract, checked at compile time.
 * If any of these fail, a field moved and the ABI is broken.
 * Fix the struct above; never adjust the numbers below.
 * ───────────────────────────────────────────── */

/* E_LAYOUT_ASSERT: a compile-time check compatible with C89, C99, and
 * C11. Produces a readable error when a field has moved:
 *   error: size of array 'e_layout_check_N' is negative
 * If you see that, a field shifted and the ABI is broken.
 * Fix the struct definition; never adjust the numbers here. */
#define E_LAYOUT_ASSERT(tag, expr) \
    typedef char e_layout_check_##tag[(expr) ? 1 : -1]

E_LAYOUT_ASSERT(size,       sizeof(e_particle)             == 440);
E_LAYOUT_ASSERT(type,       offsetof(e_particle, type)     ==   0);
E_LAYOUT_ASSERT(value,      offsetof(e_particle, value)    ==   8);
E_LAYOUT_ASSERT(text,       offsetof(e_particle, text)     ==  16);
E_LAYOUT_ASSERT(state,      offsetof(e_particle, state)    == 208);
E_LAYOUT_ASSERT(defect,     offsetof(e_particle, defect)   == 212);
E_LAYOUT_ASSERT(confidence, offsetof(e_particle, confidence)== 216);
E_LAYOUT_ASSERT(lo,         offsetof(e_particle, lo)       == 218);
E_LAYOUT_ASSERT(hi,         offsetof(e_particle, hi)       == 220);
E_LAYOUT_ASSERT(lang,       offsetof(e_particle, lang)     == 224);
E_LAYOUT_ASSERT(anchor_id,  offsetof(e_particle, anchor_id)== 232);
E_LAYOUT_ASSERT(archive_id, offsetof(e_particle, archive_id)==236);
E_LAYOUT_ASSERT(born_ms,    offsetof(e_particle, born_ms)  == 240);
E_LAYOUT_ASSERT(ident,      offsetof(e_particle, ident)    == 248);
E_LAYOUT_ASSERT(reason,     offsetof(e_particle, reason)   == 312);

/* ─────────────────────────────────────────────
 * Constructors
 * ───────────────────────────────────────────── */

e_particle e_z(const char *ident, const char *reason);
e_particle e_z_defect(const char *ident, const char *reason, e_defect d);
e_particle e_int(const char *ident, int64_t v, int16_t conf, e_lang lang);
e_particle e_real(const char *ident, double v, int16_t conf, e_lang lang);
e_particle e_bool(const char *ident, int v, int16_t conf, e_lang lang);
e_particle e_text(const char *ident, const char *v, int16_t conf, e_lang lang);
e_particle e_equivalence(const char *ident, int16_t lo, int16_t hi, e_lang lang);
e_particle e_expression(const char *ident, e_type t, e_lang lang);
e_particle e_error(const char *ident, const char *reason, e_defect d, int16_t at);

/* ─────────────────────────────────────────────
 * Predicates
 * ───────────────────────────────────────────── */

int e_is_z(const e_particle *p);
int e_is_cleared(const e_particle *p);
int e_can_execute(const e_particle *p);
int e_has_value(const e_particle *p);
int e_is_anchored(const e_particle *p);
int e_width(const e_particle *p);

typedef enum {
    E_PI_ACCEPTABLE = 0, E_PI_ENUMERATE = 1, E_PI_APPROACHING_Z = 2
} e_pi_status;

e_pi_status e_pi_check(const e_particle *p);

/* ═════════════════════════════════════════════
 * The six A-operators. Closed over E: every one takes particles and
 * returns particles, so they compose without leaving the system.
 * ═════════════════════════════════════════════ */

/* ANY — lift any source language's binding into a particle.
 * The universal intake. Cannot fail loudly; failure is a Z that says why. */
e_particle a_any(const char *ident, const char *literal, e_lang from);

/* ASSIMILATE — carry a particle across languages, preserving payload and
 * trust. Refuses rather than translating lossily. An unanchored particle
 * loses 1 confidence per crossing; an anchored one loses nothing, which
 * is the entire point of anchoring. */
e_particle a_assimilate(const e_particle *p, e_lang to);

/* ANCHOR — pin an identity that survives every translation. Refuses to
 * anchor anything not cleared: an anchor on an unverified binding is a
 * lie that propagates. */
e_particle a_anchor(const e_particle *p, uint32_t anchor_id);

/* ASCEND — earn confidence through evidence. The only path upward.
 * Three aligned points are required; a single observation never lifts. */
e_particle a_ascend(const e_particle *p, const e_particle *evidence);

/* APPLY2ALL — broadcast one transformation across a corpus.
 * Z-contagion halts the broadcast at the offending particle rather than
 * silently skipping it. Returns the count transformed. */
typedef e_particle (*a_transform)(const e_particle *);
int a_apply2all(e_particle *set, int n, a_transform fn, int *halted_at);

/* AUTO-DIDACT — derive a rule from the archive's own history.
 * C² made executable: the corpus correlating its own correlations.
 * Returns a particle whose text is the derived rule, or Z if the history
 * does not support one. */
e_particle a_autodidact(const e_particle *history, int n, const char *about);

/* ─────────────────────────────────────────────
 * Propagation and arithmetic — unchanged semantics from v1
 * ───────────────────────────────────────────── */

e_particle e_carry(const e_particle *src, const char *new_ident);
e_particle e_cap(const e_particle *src, int16_t ceiling);
int16_t    e_excel_formula(int16_t a, int16_t b);
int16_t    e_phi_equalize(int16_t value, int16_t set_mean);
e_particle e_emulate(const e_particle *broken, const e_particle *working,
                     uint8_t error_distance);

/* ─────────────────────────────────────────────
 * Serialization. Extended for the payload and the anchor.
 * ───────────────────────────────────────────── */

size_t e_serialize(const e_particle *p, char *buf, size_t buflen);
int    e_deserialize(const char *line, e_particle *out);

const char *e_state_name(e_state s);
const char *e_lang_name(e_lang l);
const char *e_type_name(e_type t);
const char *e_defect_name(e_defect d);

#endif /* TAPESTRY_H */
