/*
 * ev_test.h — Ever / Tapestry, native C unit test framework
 *
 * DESIGN GOALS
 * ─────────────
 * 1. Zero dependencies beyond the C standard library.
 *    Catch2 and GoogleTest pull in C++11/14 and a build system.
 *    Ever's C layer is C99. This framework is C99.
 *
 * 2. Self-contained single header. Include once, start testing.
 *
 * 3. ASSERT_EQ shows EXPECTED vs GOT on failure — the thing
 *    hand-rolled ok(name, cond) never does.
 *
 * 4. Fixture support: EV_SUITE / EV_TEARDOWN run setup and cleanup
 *    per test group without global state.
 *
 * 5. Tag filtering: EV_TAG("bridge") lets the harness run only
 *    tagged subsets: ./test --tag bridge
 *
 * 6. Parameterised tests: EV_PARAMS iterates a table row by row.
 *
 * 7. Exit code: 0 if all pass, 1 if any fail — compatible with
 *    run_all.py's subprocess.run(check=...) pattern.
 *
 * USAGE
 * ─────
 *   #include "ev_test.h"
 *
 *   EV_SUITE(arithmetic) {
 *       ASSERT_EQ_INT(2,  1 + 1);
 *       ASSERT_EQ_INT(42, 6 * 7);
 *       ASSERT_EQ_STR("Ever", my_name());
 *   }
 *
 *   EV_SUITE(with_teardown) {
 *       MyThing *t = my_thing_new();
 *       ASSERT(t != NULL);
 *       ASSERT_EQ_INT(0, t->count);
 *   EV_TEARDOWN:
 *       my_thing_free(t);
 *   }
 *
 *   EV_MAIN   // expands to int main(int argc, char **argv)
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef EV_TEST_H
#define EV_TEST_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ─────────────────────────────────────────────
 * Registry — test functions are registered at startup via
 * a constructor attribute or an explicit call in EV_MAIN.
 * ───────────────────────────────────────────── */

#define EV_MAX_SUITES  256
#define EV_MAX_TAGS     16

typedef void (*ev_suite_fn)(void);

typedef struct {
    const char  *name;
    const char  *file;
    int          line;
    const char  *tags[EV_MAX_TAGS];
    int          ntags;
    ev_suite_fn  fn;
} EvTestEntry;

/* Global registry */
static EvTestEntry _ev_registry[EV_MAX_SUITES];
static int         _ev_count    = 0;

/* Per-run counters — reset per suite */
static int _ev_pass  = 0;   /* assertions passed this suite    */
static int _ev_fail  = 0;   /* assertions failed this suite    */
static int _ev_total_pass = 0;
static int _ev_total_fail = 0;
static int _ev_suite_fail = 0;  /* suites with ≥1 failure       */
static int _ev_suite_pass = 0;

static const char *_ev_filter_tag = NULL;
static int         _ev_verbose    = 0;

/* ─────────────────────────────────────────────
 * Registration macro
 * ───────────────────────────────────────────── */

static inline void ev_register(const char *name, const char *file, int line,
                                const char **tags, int ntags, ev_suite_fn fn) {
    if (_ev_count >= EV_MAX_SUITES) return;
    EvTestEntry *e = &_ev_registry[_ev_count++];
    e->name   = name;
    e->file   = file;
    e->line   = line;
    e->fn     = fn;
    e->ntags  = ntags < EV_MAX_TAGS ? ntags : EV_MAX_TAGS;
    for (int i = 0; i < e->ntags; i++) e->tags[i] = tags[i];
}

/* ─────────────────────────────────────────────
 * ASSERT macros — all print EXPECTED vs GOT on failure
 * ───────────────────────────────────────────── */

#define _EV_PASS(fmt, ...) do {                               \
    _ev_pass++;                                               \
    if (_ev_verbose)                                          \
        printf("    \u2713  " fmt "\n", ##__VA_ARGS__);       \
} while(0)

#define _EV_FAIL(fmt, ...) do {                               \
    _ev_fail++;                                               \
    printf("    \u2717  " fmt "\n", ##__VA_ARGS__);           \
} while(0)

/* Basic boolean */
#define ASSERT(cond) do {                                     \
    if (cond) { _EV_PASS("%s", #cond); }                     \
    else { _EV_FAIL("ASSERT(%s)  at %s:%d", #cond,           \
                    __FILE__, __LINE__); }                    \
} while(0)

/* Integer equality — shows both values */
#define ASSERT_EQ_INT(expected, got) do {                     \
    long long _e = (long long)(expected);                     \
    long long _g = (long long)(got);                          \
    if (_e == _g) {                                           \
        _EV_PASS("EQ_INT  %s == %lld", #got, _g);            \
    } else {                                                  \
        _EV_FAIL("EQ_INT  %s\n"                               \
                 "         expected: %lld\n"                  \
                 "         got:      %lld  at %s:%d",         \
                 #got, _e, _g, __FILE__, __LINE__);           \
    }                                                         \
} while(0)

/* Double/float equality with tolerance */
#define ASSERT_EQ_REAL(expected, got, tol) do {               \
    double _e = (double)(expected);                           \
    double _g = (double)(got);                                \
    double _t = (double)(tol);                                \
    if (fabs(_e - _g) <= _t) {                               \
        _EV_PASS("EQ_REAL %s ≈ %g", #got, _g);               \
    } else {                                                  \
        _EV_FAIL("EQ_REAL %s\n"                               \
                 "         expected: %g\n"                    \
                 "         got:      %g  at %s:%d",           \
                 #got, _e, _g, __FILE__, __LINE__);           \
    }                                                         \
} while(0)

/* String equality */
#define ASSERT_EQ_STR(expected, got) do {                     \
    const char *_e = (expected);                              \
    const char *_g = (got);                                   \
    if (_g && _e && strcmp(_e, _g) == 0) {                   \
        _EV_PASS("EQ_STR  %s == \"%s\"", #got, _g);          \
    } else {                                                  \
        _EV_FAIL("EQ_STR  %s\n"                               \
                 "         expected: \"%s\"\n"                 \
                 "         got:      \"%s\"  at %s:%d",       \
                 #got, _e ? _e : "(null)", _g ? _g : "(null)",\
                 __FILE__, __LINE__);                          \
    }                                                         \
} while(0)

/* Pointer non-null */
#define ASSERT_NOT_NULL(ptr) do {                             \
    if ((ptr) != NULL) { _EV_PASS("NOT_NULL %s", #ptr); }    \
    else { _EV_FAIL("NOT_NULL %s is NULL  at %s:%d",          \
                    #ptr, __FILE__, __LINE__); }               \
} while(0)

/* Pointer null */
#define ASSERT_NULL(ptr) do {                                 \
    if ((ptr) == NULL) { _EV_PASS("NULL     %s", #ptr); }    \
    else { _EV_FAIL("NULL     %s is NOT null  at %s:%d",      \
                    #ptr, __FILE__, __LINE__); }               \
} while(0)

/* ─────────────────────────────────────────────
 * Parameterised test helper
 * ───────────────────────────────────────────── */

/* Usage:
 *   struct { int a; int b; int want; } _cases[] = {
 *       {1, 1, 2}, {6, 7, 42}, {0, 0, 0}
 *   };
 *   EV_PARAMS(_cases, c) {
 *       ASSERT_EQ_INT(c.want, c.a + c.b);
 *   }
 */
#define EV_PARAMS(table, var)                                 \
    for (size_t _pi = 0;                                      \
         _pi < sizeof(table)/sizeof((table)[0]);              \
         _pi++)                                               \
        for (__typeof__((table)[0]) var = (table)[_pi];       \
             _pi < sizeof(table)/sizeof((table)[0]);          \
             _pi = sizeof(table)/sizeof((table)[0]))

/* ─────────────────────────────────────────────
 * Suite declaration
 * ───────────────────────────────────────────── */

/* EV_SUITE(name) { ... } — simple suite, no tags */
#define EV_SUITE(name)                                        \
    static void _ev_fn_##name(void);                          \
    static void __attribute__((constructor))                  \
        _ev_reg_##name(void) {                                \
        ev_register(#name, __FILE__, __LINE__, NULL, 0,       \
                    _ev_fn_##name);                           \
    }                                                         \
    static void _ev_fn_##name(void)

/* EV_SUITE_TAGGED(name, "tag1", "tag2") */
#define EV_SUITE_TAGGED(name, ...)                            \
    static void _ev_fn_##name(void);                          \
    static void __attribute__((constructor))                  \
        _ev_reg_##name(void) {                                \
        const char *_t[] = { __VA_ARGS__ };                   \
        ev_register(#name, __FILE__, __LINE__, _t,            \
                    (int)(sizeof(_t)/sizeof(_t[0])),          \
                    _ev_fn_##name);                           \
    }                                                         \
    static void _ev_fn_##name(void)

/* EV_TEARDOWN — label inside a suite for cleanup code.
 * Works because the suite function body is:
 *   { ... your code ... EV_TEARDOWN: ... cleanup ... } */
#define EV_TEARDOWN  ev_teardown_label_

/* ─────────────────────────────────────────────
 * Main runner
 * ───────────────────────────────────────────── */

static inline int ev_has_tag(const EvTestEntry *e, const char *tag) {
    for (int i = 0; i < e->ntags; i++)
        if (strcmp(e->tags[i], tag) == 0) return 1;
    return 0;
}

#define EV_MAIN                                               \
int main(int argc, char **argv) {                             \
    for (int i = 1; i < argc; i++) {                         \
        if (strcmp(argv[i], "--tag") == 0 && i+1 < argc)     \
            _ev_filter_tag = argv[++i];                       \
        if (strcmp(argv[i], "-v") == 0)                       \
            _ev_verbose = 1;                                  \
    }                                                         \
    printf("\n=== Ever native test suite ===\n\n");           \
    for (int i = 0; i < _ev_count; i++) {                    \
        EvTestEntry *e = &_ev_registry[i];                    \
        if (_ev_filter_tag && !ev_has_tag(e, _ev_filter_tag)) \
            continue;                                         \
        _ev_pass = _ev_fail = 0;                              \
        printf("  Suite: %s\n", e->name);                     \
        e->fn();                                              \
        _ev_total_pass += _ev_pass;                           \
        _ev_total_fail += _ev_fail;                           \
        if (_ev_fail == 0) {                                  \
            _ev_suite_pass++;                                  \
            printf("    \u2192  %d passed\n\n", _ev_pass);   \
        } else {                                              \
            _ev_suite_fail++;                                  \
            printf("    \u2192  %d passed  %d FAILED\n\n",   \
                   _ev_pass, _ev_fail);                       \
        }                                                     \
    }                                                         \
    printf("─────────────────────────────────────────\n");    \
    printf("  Assertions : %d passed  %d failed\n",           \
           _ev_total_pass, _ev_total_fail);                   \
    printf("  Suites     : %d passed  %d failed\n",           \
           _ev_suite_pass, _ev_suite_fail);                   \
    printf("─────────────────────────────────────────\n\n");  \
    return _ev_total_fail == 0 ? 0 : 1;                       \
}

/* Compatibility shim: let the old ok() macro still work in existing test files
   so we don't break 543 passing tests while migrating.                        */
#ifndef EV_NO_COMPAT
static int _compat_pass = 0, _compat_fail = 0;
#define ok(name, cond) do {                                   \
    if (cond) { _compat_pass++; _ev_pass++;                   \
                if(_ev_verbose) printf("  \u2713 %s\n",name);}\
    else      { _compat_fail++; _ev_fail++;                   \
                printf("  \u2717 %s\n", name); }              \
} while(0)
#endif /* EV_NO_COMPAT */

#endif /* EV_TEST_H */
