/*
 * form.h — Ever / Tapestry, the GENERIC STRUCTURAL IR
 *
 * ─────────────────────────────────────────────────────────────
 * THE PROBLEM THIS SOLVES
 * ─────────────────────────────────────────────────────────────
 *
 * EvNode (ir.h) has 24 node kinds, each one glued to a piece of
 * surface syntax:
 *
 *     EV_NODE_ADD  EV_NODE_SUB  EV_NODE_MUL  EV_NODE_DIV
 *     EV_NODE_LT   EV_NODE_GT   EV_NODE_LTE  EV_NODE_GTE
 *     EV_NODE_IF   EV_NODE_CALL EV_NODE_DEF  ...
 *
 * Every pass that touches the IR must therefore know about all 24.
 * ev_lower_node has 24 switch cases. Const-folding has 10. Adding
 * one new surface construct — `unless`, `elif`, `match`, `while`,
 * `a ?: b` — means editing every pass. The IR is a mirror of the
 * grammar, so grammar churn becomes IR churn becomes pass churn.
 *
 * That is a tight syntax schema. It does not scale.
 *
 * ─────────────────────────────────────────────────────────────
 * THE FIX: SHAPE, NOT SPELLING
 * ─────────────────────────────────────────────────────────────
 *
 * There are only so many things a program construct can BE,
 * structurally, regardless of how a language spells it:
 *
 *   ATOM         an irreducible value
 *   REFERENCE    a name standing for something bound elsewhere
 *   APPLICATION  an operator applied to operands
 *   BRANCH       a selector choosing between arms
 *   SEQUENCE     forms evaluated in order
 *   BINDING      a name associated with a form
 *   ABSTRACTION  parameters plus a body
 *   AGGREGATE    a composite built from parts
 *   ACCESS       a projection out of a composite
 *   ANNOTATION   metadata riding along with a form
 *   DEFECT       a carrier for something that went wrong
 *
 * Eleven forms. `a + b`, `max(a,b)`, `a < b`, and `print(x)` are
 * all ONE form — APPLICATION — differing only in which operator
 * sits in a data field. `if/then/else`, `unless`, `match`, and a
 * ternary are all ONE form — BRANCH — differing only in arm count.
 *
 * The operator is DATA (EvRole). The shape is TYPE (EvFormKind).
 * Passes switch on the shape. Roles flow through untouched.
 *
 * ─────────────────────────────────────────────────────────────
 * WHAT THIS BUYS
 * ─────────────────────────────────────────────────────────────
 *
 * 1. Lowering drops from 24 cases to 11.
 * 2. New surface syntax costs ZERO IR changes. `unless c then a`
 *    lowers to BRANCH with the arms swapped. `elif` is a BRANCH
 *    whose else-arm is another BRANCH. `while` is a BRANCH plus a
 *    back-edge. None of them touch form.c, tac.c, or any pass.
 * 3. Structural contracts are checkable. Each form declares its
 *    legal shape (arity, required parts) in ONE table. A malformed
 *    tree is caught by ev_form_validate before any pass runs, with
 *    a precise message, instead of segfaulting three passes later.
 * 4. Back-ends pattern-match on 11 shapes. A Rust emitter, a Go
 *    emitter, and a TypeScript emitter each need 11 cases, not 24.
 *
 * ─────────────────────────────────────────────────────────────
 * MIGRATION SAFETY
 * ─────────────────────────────────────────────────────────────
 *
 * EvNode is NOT deleted. ev_form_from_node() normalises a legacy
 * EvNode tree into forms, so both paths run side by side and the
 * equivalence suite asserts they produce identical results. The
 * old path stays green while the new one proves itself.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef EV_FORM_H
#define EV_FORM_H

#include <stdint.h>
#include <stddef.h>
#include "evalue.h"
#include "ir.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ─────────────────────────────────────────────
 * EvFormKind — the eleven structural shapes.
 *
 * This enum is CLOSED. It should essentially never grow. If a new
 * language construct does not fit one of these eleven, that is a
 * signal to re-examine the construct, not to add a twelfth form.
 * ───────────────────────────────────────────── */
typedef enum {
    EV_FORM_ATOM        = 0,  /* irreducible value                       */
    EV_FORM_REFERENCE   = 1,  /* name → something bound elsewhere        */
    EV_FORM_APPLICATION = 2,  /* operator applied to operands            */
    EV_FORM_BRANCH      = 3,  /* selector + arms                         */
    EV_FORM_SEQUENCE    = 4,  /* ordered evaluation                      */
    EV_FORM_BINDING     = 5,  /* name ↔ form                             */
    EV_FORM_ABSTRACTION = 6,  /* params + body                           */
    EV_FORM_AGGREGATE   = 7,  /* composite construction                  */
    EV_FORM_ACCESS      = 8,  /* projection out of a composite           */
    EV_FORM_ANNOTATION  = 9,  /* metadata attached to a form             */
    EV_FORM_DEFECT      = 10  /* error carrier                           */
} EvFormKind;

#define EV_FORM_KIND_COUNT 11

/* ─────────────────────────────────────────────
 * EvRole — WHICH operator/variant, within a form.
 *
 * This enum is OPEN. It grows freely as the surface language grows.
 * Adding a role never forces a pass to change: passes that care
 * about a role look it up, passes that do not simply carry it.
 *
 * Roles are grouped by the form they belong to. The grouping is a
 * convention enforced by ev_role_form(), not by the type system.
 * ───────────────────────────────────────────── */
typedef enum {
    EV_ROLE_NONE        = 0,

    /* ── ATOM roles ────────────────────────────────────── 1..19 */
    EV_ROLE_LIT_VOID    = 1,
    EV_ROLE_LIT_BOOL    = 2,
    EV_ROLE_LIT_INT     = 3,
    EV_ROLE_LIT_REAL    = 4,
    EV_ROLE_LIT_TEXT    = 5,
    EV_ROLE_LIT_Z       = 6,   /* explicit unknown — zero-absolute    */

    /* ── REFERENCE roles ──────────────────────────────── 20..29 */
    EV_ROLE_REF_VAR     = 20,  /* ordinary variable                   */
    EV_ROLE_REF_PARAM   = 21,  /* a bound parameter                   */
    EV_ROLE_REF_FN      = 22,  /* a function used as a value          */

    /* ── APPLICATION roles ────────────────────────────── 30..69 */
    EV_ROLE_ADD         = 30,
    EV_ROLE_SUB         = 31,
    EV_ROLE_MUL         = 32,
    EV_ROLE_DIV         = 33,
    EV_ROLE_MOD         = 34,
    EV_ROLE_POW         = 35,
    EV_ROLE_NEG         = 36,  /* unary                               */

    EV_ROLE_LT          = 40,
    EV_ROLE_GT          = 41,
    EV_ROLE_LTE         = 42,
    EV_ROLE_GTE         = 43,
    EV_ROLE_EQ          = 44,
    EV_ROLE_NEQ         = 45,

    EV_ROLE_AND         = 50,
    EV_ROLE_OR          = 51,
    EV_ROLE_NOT         = 52,  /* unary                               */

    EV_ROLE_CALL        = 60,  /* named function application          */
    EV_ROLE_BUILTIN     = 61,  /* builtin application                 */

    /* ── BRANCH roles ─────────────────────────────────── 70..79 */
    EV_ROLE_IF          = 70,  /* selector + 2 arms                   */
    EV_ROLE_MATCH       = 71,  /* selector + N arms                   */
    EV_ROLE_GUARD       = 72,  /* selector + 1 arm (no else)          */

    /* ── SEQUENCE roles ───────────────────────────────── 80..89 */
    EV_ROLE_BLOCK       = 80,  /* { a; b; c }                         */
    EV_ROLE_PROGRAM     = 81,  /* top level                           */

    /* ── BINDING roles ────────────────────────────────── 90..99 */
    EV_ROLE_BIND_LET    = 90,  /* immutable binding                   */
    EV_ROLE_BIND_EVER   = 91,  /* tracked binding                     */
    EV_ROLE_BIND_FIELD  = 92,  /* record field                        */

    /* ── ABSTRACTION roles ──────────────────────────── 100..109 */
    EV_ROLE_FN_DEF      = 100, /* named function                      */
    EV_ROLE_FN_LAMBDA   = 101, /* anonymous                           */

    /* ── AGGREGATE roles ────────────────────────────── 110..119 */
    EV_ROLE_AGG_LIST    = 110,
    EV_ROLE_AGG_RECORD  = 111,
    EV_ROLE_AGG_TUPLE   = 112,

    /* ── ACCESS roles ───────────────────────────────── 120..129 */
    EV_ROLE_ACC_INDEX   = 120, /* xs[i]                               */
    EV_ROLE_ACC_FIELD   = 121, /* r.k                                 */

    /* ── ANNOTATION roles ───────────────────────────── 130..139 */
    EV_ROLE_ANN_ANCHOR  = 130, /* anchor a binding (lifts ceiling)    */
    EV_ROLE_ANN_ASSM    = 131, /* assimilate to another language      */
    EV_ROLE_ANN_CONF    = 132, /* explicit confidence assertion       */

    /* ── DEFECT roles ───────────────────────────────── 140..149 */
    EV_ROLE_DEF_PARSE   = 140,
    EV_ROLE_DEF_SEMANT  = 141,
    EV_ROLE_DEF_CEILING = 142  /* depth ceiling exceeded              */
} EvRole;

/* ─────────────────────────────────────────────
 * EvForm — one node of the generic IR.
 *
 * Compare with EvNode: EvNode has `params`, `keys`, `str`, `error`
 * as separate special-purpose fields because each was added for one
 * specific syntax construct. EvForm has a uniform layout: a shape, a
 * role, a payload, parts, and labels for those parts. Every construct
 * uses the same five slots.
 * ───────────────────────────────────────────── */
typedef struct EvForm EvForm;

struct EvForm {
    EvFormKind   form;      /* the shape — passes switch on this      */
    EvRole       role;      /* the variant — passes carry this        */
    int32_t      line;      /* source line for diagnostics            */

    EValue       payload;   /* ATOM value; empty otherwise            */
    const char  *symbol;    /* REFERENCE name, CALL target, BINDING
                               name, ABSTRACTION name, DEFECT message */

    EvForm     **parts;     /* children — meaning depends on form      */
    const char **labels;    /* parallel names for parts, or NULL       */
    int32_t      part_count;
    int32_t      part_cap;

    int16_t      confidence;/* trust carried by this form, 0..256      */

    /* Structural metrics, filled by ev_form_measure */
    int32_t      size;      /* forms in this subtree                   */
    int32_t      depth;     /* subtree depth                           */

    EvArena     *arena;     /* owning arena, never NULL                */
};

/* ─────────────────────────────────────────────
 * PART CONVENTIONS — what parts[] means per form
 *
 *  ATOM         parts = {}                    payload holds the value
 *  REFERENCE    parts = {}                    symbol holds the name
 *  APPLICATION  parts = {operand...}          symbol = callee if CALL
 *  BRANCH       parts = {selector, arm...}    parts[0] is the selector
 *  SEQUENCE     parts = {form...}             evaluated in order
 *  BINDING      parts = {value}               symbol = bound name
 *  ABSTRACTION  parts = {body}                labels = parameter names
 *  AGGREGATE    parts = {element...}          labels = keys if RECORD
 *  ACCESS       parts = {target, key}         key may be ATOM or REF
 *  ANNOTATION   parts = {subject}             symbol = annotation arg
 *  DEFECT       parts = {}                    symbol = message
 * ───────────────────────────────────────────── */

/* ─────────────────────────────────────────────
 * STRUCTURAL CONTRACT
 *
 * Each form declares its legal shape once, here. ev_form_validate
 * walks a tree and reports the first violation with a precise
 * message. This is what "generic structural definition" means made
 * literal: the IR knows what a well-formed BRANCH is, and does not
 * care whether the surface wrote `if`, `unless`, or `match`.
 * ───────────────────────────────────────────── */
typedef struct {
    EvFormKind  form;
    const char *name;
    int32_t     min_parts;
    int32_t     max_parts;   /* -1 = unbounded                        */
    int32_t     needs_symbol;/* 1 = symbol must be non-NULL           */
    const char *shape_desc;
} EvFormContract;

const EvFormContract *ev_form_contract(EvFormKind form);
const char           *ev_form_name(EvFormKind form);
const char           *ev_role_name(EvRole role);
EvFormKind            ev_role_form(EvRole role);  /* which form owns it */

/* ─────────────────────────────────────────────
 * CONSTRUCTORS — all arena-allocated
 * ───────────────────────────────────────────── */

EvForm *ev_form_new(EvArena *a, EvFormKind form, EvRole role, int32_t line);

/* ATOM */
EvForm *ev_form_atom(EvArena *a, EValue v, int32_t line);
EvForm *ev_form_int(EvArena *a, int64_t v, int32_t line);
EvForm *ev_form_real(EvArena *a, double v, int32_t line);
EvForm *ev_form_bool(EvArena *a, int32_t v, int32_t line);
EvForm *ev_form_text(EvArena *a, const char *v, int32_t line);
EvForm *ev_form_void(EvArena *a, int32_t line);
EvForm *ev_form_z(EvArena *a, int32_t line);

/* REFERENCE */
EvForm *ev_form_ref(EvArena *a, const char *name, int32_t line);

/* APPLICATION — one call covers every operator and every call */
EvForm *ev_form_apply(EvArena *a, EvRole role, const char *symbol,
                      EvForm **operands, int32_t n, int32_t line);
EvForm *ev_form_apply2(EvArena *a, EvRole role,
                       EvForm *lhs, EvForm *rhs, int32_t line);

/* BRANCH — arms are variadic, so if/match/guard are one constructor */
EvForm *ev_form_branch(EvArena *a, EvRole role, EvForm *selector,
                       EvForm **arms, int32_t n, int32_t line);

/* SEQUENCE */
EvForm *ev_form_sequence(EvArena *a, EvRole role,
                         EvForm **items, int32_t n, int32_t line);

/* BINDING */
EvForm *ev_form_binding(EvArena *a, EvRole role, const char *name,
                        EvForm *value, int32_t line);

/* ABSTRACTION */
EvForm *ev_form_abstraction(EvArena *a, EvRole role, const char *name,
                            const char **params, int32_t np,
                            EvForm *body, int32_t line);

/* AGGREGATE */
EvForm *ev_form_aggregate(EvArena *a, EvRole role, EvForm **items,
                          const char **keys, int32_t n, int32_t line);

/* ACCESS */
EvForm *ev_form_access(EvArena *a, EvRole role, EvForm *target,
                       EvForm *key, int32_t line);

/* ANNOTATION */
EvForm *ev_form_annotate(EvArena *a, EvRole role, const char *arg,
                         EvForm *subject, int32_t line);

/* DEFECT */
EvForm *ev_form_defect(EvArena *a, EvRole role, const char *msg,
                       int32_t line);

/* Mutation */
void ev_form_add_part(EvForm *f, EvForm *part, const char *label);

/* ─────────────────────────────────────────────
 * ACCESSORS — named views onto parts[], so passes read intent
 * rather than counting indices.
 * ───────────────────────────────────────────── */
EvForm *ev_form_selector(const EvForm *branch);      /* parts[0]      */
EvForm *ev_form_arm(const EvForm *branch, int32_t i);/* parts[i+1]    */
int32_t ev_form_arm_count(const EvForm *branch);
EvForm *ev_form_body(const EvForm *abstraction);     /* parts[0]      */
EvForm *ev_form_value(const EvForm *binding);        /* parts[0]      */
EvForm *ev_form_subject(const EvForm *annotation);   /* parts[0]      */
EvForm *ev_form_target(const EvForm *access);        /* parts[0]      */
EvForm *ev_form_key(const EvForm *access);           /* parts[1]      */
EvForm *ev_form_operand(const EvForm *app, int32_t i);

/* ─────────────────────────────────────────────
 * ANALYSIS
 * ───────────────────────────────────────────── */
void        ev_form_measure(EvForm *f);      /* fills size + depth    */
int         ev_form_validate(const EvForm *f, char *err, size_t errlen);
const char *ev_form_skeleton(const EvForm *f, EvArena *a);
int32_t     ev_form_count_kind(const EvForm *f, EvFormKind k);
int32_t     ev_form_count_role(const EvForm *f, EvRole r);

/* ─────────────────────────────────────────────
 * NORMALISATION — legacy EvNode tree → generic forms
 *
 * This is the migration bridge. Every EvNode kind maps onto exactly
 * one (form, role) pair. The mapping table IS the proof that the
 * eleven forms cover the whole existing language.
 * ───────────────────────────────────────────── */
EvForm *ev_form_from_node(const EvNode *n, EvArena *a);
EvNode *ev_node_from_form(const EvForm *f, EvArena *a);  /* round trip */

/* ─────────────────────────────────────────────
 * WIRE FORMAT — same self-describing little-endian discipline as
 * EValue and EvNode, so forms cross the language boundary too.
 * ───────────────────────────────────────────── */
int32_t ev_form_serialise(const EvForm *f, uint8_t *buf, int32_t cap);
EvForm *ev_form_deserialise(const uint8_t *buf, int32_t len,
                            int32_t *consumed, EvArena *a);

/* Debug */
void ev_form_print(const EvForm *f);
void ev_form_print_indent(const EvForm *f, int32_t indent);

#ifdef __cplusplus
}
#endif

#endif /* EV_FORM_H */

/* ─────────────────────────────────────────────
 * FORM → TAC LOWERING  (form_lower.c)
 * Declared here rather than tac.h so the generic layer owns its
 * own interface and tac.h stays legacy-clean.
 * ───────────────────────────────────────────── */
#ifdef EVER_TAC_H
EvReg     ev_lower_form(EvBuilder *b, const EvForm *f);
EvFunc   *ev_lower_form_func(EvModule *m, const EvForm *fn);
EvModule *ev_lower_form_module(const char *name, const EvForm *root,
                               EvArena *arena);
#endif
