/* flare_rt.h — header-only runtime for Flare v0 (C99 + GCC extensions). */
#ifndef FLARE_RT_H
#define FLARE_RT_H

#include <ctype.h>
#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* ------------------------------------------------------------------ */
/* strings                                                             */
/* ------------------------------------------------------------------ */

static inline char *flare_strdup(const char *s) {
  size_t n = strlen(s) + 1;
  char *r = (char *)malloc(n);
  if (!r) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
  memcpy(r, s, n);
  return r;
}

static inline char *str_concat(const char *a, const char *b) {
  size_t la = strlen(a), lb = strlen(b);
  char *r = (char *)malloc(la + lb + 1);
  if (!r) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
  memcpy(r, a, la);
  memcpy(r + la, b, lb + 1);
  return r;
}

/* ------------------------------------------------------------------ */
/* closures: a function pointer plus its captured environment          */
/* ------------------------------------------------------------------ */

typedef struct {
  void *fn;  /* C function; cast to the real signature at call sites */
  void *env; /* Env_<qualname>* allocated by the enclosing function  */
} FlClosure;

/* ------------------------------------------------------------------ */
/* exceptions: catchable runtime errors via setjmp/longjmp              */
/* A try statement pushes a FlHandler; fl_raise() unwinds to the        */
/* innermost handler, or prints "flare: <msg>" and exits(1) if none.   */
/* ------------------------------------------------------------------ */

#include <setjmp.h>

typedef struct FlHandler {
  jmp_buf jb;
  struct FlHandler *prev;
  int saved_depth; /* recursion depth at try entry; restored on raise */
} FlHandler;

static FlHandler *_flare_top = NULL;
static char _flare_errtype[64];
static char _flare_errmsg[512];

#ifndef FLARE_MAX_DEPTH
#define FLARE_MAX_DEPTH 10000
#endif

/* Depth counter: on x86-64 it lives in a fixed register (no memory traffic
 * per call; requires -ffixed-r15 on the cc command line, passed by the
 * Flare driver). On other architectures (notably AArch64, where clang
 * rejects global register variables) it falls back to a plain global:
 * one memory access per call instead of zero, with identical guard
 * semantics.
 * (Global register vars cannot have initializers; zeroed in _flare_anchor.) */
#if defined(__x86_64__)
register int _flare_depth __asm__("r15");
#else
int _flare_depth;
#endif

static inline __attribute__((noreturn)) void fl_raise(const char *type,
                                                      const char *msg) {
  if (_flare_top) {
    char tmp[512]; /* copy first: msg may alias _flare_errmsg */
    snprintf(tmp, sizeof tmp, "%s", msg);
    snprintf(_flare_errtype, sizeof _flare_errtype, "%s", type);
    snprintf(_flare_errmsg, sizeof _flare_errmsg, "%s", tmp);
    FlHandler *h = _flare_top;
    _flare_top = h->prev;
    _flare_depth = h->saved_depth;
    longjmp(h->jb, 1);
  }
  fprintf(stderr, "flare: %s\n", msg);
  exit(1);
}

static inline __attribute__((noreturn)) void fl_reraise(void) {
  /* re-raise the current error: unwind without touching the
     type/message buffers (they already hold the in-flight error) */
  if (_flare_top) {
    FlHandler *h = _flare_top;
    _flare_top = h->prev;
    _flare_depth = h->saved_depth;
    longjmp(h->jb, 1);
  }
  fprintf(stderr, "flare: %s\n", _flare_errmsg);
  exit(1);
}

#define FL_RAISE_FMT(type, ...)                                                \
  do {                                                                         \
    snprintf(_flare_errmsg, sizeof _flare_errmsg, __VA_ARGS__);                \
    fl_raise(type, _flare_errmsg);                                             \
  } while (0)

static inline void _flare_enter(void) {
  if (_flare_depth + 1 > FLARE_MAX_DEPTH) {
    FL_RAISE_FMT("RecursionError", "recursion limit exceeded (depth > %d)",
                 FLARE_MAX_DEPTH);
  }
  ++_flare_depth;
}

static inline void _flare_leave(void) { --_flare_depth; }

/* dynamic Value (boxed fallback)                                      */
/* ------------------------------------------------------------------ */

/* Container tags: a Value may box any heap container by pointer. The tag
   records the exact struct type, so boxing is zero-copy (no conversion,
   aliasing preserved) and every operation dispatches on the tag.
   List tags sort before dict tags; fl_tag_is_container() relies on the
   container tags following the scalar tags. */
typedef enum {
  FT_I64,
  FT_F64,
  FT_BOOL,
  FT_STR,
  FT_LIST_I64,
  FT_LIST_F64,
  FT_LIST_STR,
  FT_LIST_DYN,
  FT_LIST_PAIR,
  FT_DICT_I64,
  FT_DICT_F64,
  FT_DICT_STR,
  FT_DICT_DYN
} FlTag;

typedef struct {
  FlTag tag;
  union {
    int64_t i;
    double f;
    bool b;
    char *s;
    void *p;
  } as;
} Value;

static inline Value v_i64(int64_t x) {
  Value v;
  v.tag = FT_I64;
  v.as.i = x;
  return v;
}
static inline Value v_f64(double x) {
  Value v;
  v.tag = FT_F64;
  v.as.f = x;
  return v;
}
static inline Value v_bool(bool x) {
  Value v;
  v.tag = FT_BOOL;
  v.as.b = x;
  return v;
}
static inline Value v_str(char *x) {
  Value v;
  v.tag = FT_STR;
  v.as.s = x;
  return v;
}

static inline bool fl_tag_is_container(FlTag t) { return t >= FT_LIST_I64; }
static inline bool fl_tag_is_list(FlTag t) {
  return t >= FT_LIST_I64 && t <= FT_LIST_PAIR;
}

/* Container helpers defined after the list/dict/indexing sections
   (they need the concrete struct types). */
static char *fl_repr_boxed(Value v);
static bool fl_boxed_eq(Value a, Value b);
static bool fl_boxed_truthy(Value v);
static int64_t fl_boxed_len(Value v);
static Value fl_boxed_index(Value v, int64_t i);
static Value fl_boxed_dict_get(Value v, const char *k);
static bool fl_boxed_contains(Value hay, Value needle);

static inline int64_t v_to_i64(Value v) {
  if (v.tag == FT_I64)
    return v.as.i;
  if (v.tag == FT_F64)
    return (int64_t)v.as.f;
  if (v.tag == FT_BOOL)
    return v.as.b ? 1 : 0;
  fl_raise("TypeError", "not a number");
}
static inline double v_to_f64(Value v) {
  if (v.tag == FT_F64)
    return v.as.f;
  if (v.tag == FT_I64)
    return (double)v.as.i;
  fl_raise("TypeError", "not a number");
}
static inline bool v_to_bool(Value v) {
  if (fl_tag_is_container(v.tag))
    return fl_boxed_truthy(v);
  return v_to_i64(v) != 0;
}
static inline char *v_to_str(Value v) {
  if (v.tag == FT_STR)
    return v.as.s;
  fl_raise("TypeError", "not a string");
}

static inline bool value_truthy(Value v) {
  switch (v.tag) {
  case FT_I64:
    return v.as.i != 0;
  case FT_F64:
    return v.as.f != 0.0;
  case FT_BOOL:
    return v.as.b;
  case FT_STR:
    return v.as.s[0] != '\0';
  default:
    break;
  }
  if (fl_tag_is_container(v.tag))
    return fl_boxed_truthy(v);
  return false;
}

/* ------------------------------------------------------------------ */
/* Python-floored modulo (C's % truncates toward zero) */
static inline int64_t fl_mod_i64(int64_t a, int64_t b) {
  if (b == 0)
    fl_raise("ZeroDivisionError", "modulo by zero");
  int64_t r = a % b;
  if (r != 0 && ((r < 0) != (b < 0)))
    r += b;
  return r;
}
static inline double fl_mod_f64(double a, double b) {
  if (b == 0.0)
    fl_raise("ZeroDivisionError", "modulo by zero");
  double r = fmod(a, b);
  if (r != 0.0 && ((r < 0.0) != (b < 0.0)))
    r += b;
  return r;
}

/* Python-repr-style float printing: shortest precision that round-trips.
   Prefers plain notation (Python only uses 1e+.. for huge/tiny magnitudes). */
static inline void fl_fmt_f64(double x, char *buf, size_t n) {
  if (isnan(x)) {
    snprintf(buf, n, "nan");
    return;
  }
  if (isinf(x)) {
    snprintf(buf, n, x < 0 ? "-inf" : "inf");
    return;
  }
  bool done = false;
  for (int pass = 0; pass < 2 && !done; pass++) {
    for (int prec = 1; prec <= 17; prec++) {
      snprintf(buf, n, "%.*g", prec, x);
      if (strtod(buf, NULL) != x)
        continue;
      if (pass == 0 && strchr(buf, 'e'))
        continue; /* prefer plain */
      done = true;
      break;
    }
  }
  if (!strchr(buf, '.') && !strchr(buf, 'e') && !strchr(buf, 'n') &&
      !strchr(buf, 'i')) {
    size_t m = strlen(buf);
    if (m + 2 < n) {
      buf[m] = '.';
      buf[m + 1] = '0';
      buf[m + 2] = '\0';
    }
  }
}

static inline void fl_print_f64(double x) {
  char buf[32];
  fl_fmt_f64(x, buf, sizeof buf);
  fputs(buf, stdout);
}

/* ------------------------------------------------------------------ */
/* f-string interpolation: values -> freshly malloc'd strings           */
/* ------------------------------------------------------------------ */

static inline char *fl_str_i64(int64_t x) {
  char b[32];
  snprintf(b, sizeof b, "%" PRId64, x);
  return flare_strdup(b);
}

static inline char *fl_str_f64(double x) {
  char b[32];
  fl_fmt_f64(x, b, sizeof b);
  return flare_strdup(b);
}

static inline char *fl_str_bool(bool x) {
  return flare_strdup(x ? "True" : "False");
}

static inline char *fl_str_value(Value v) {
  switch (v.tag) {
  case FT_I64:
    return fl_str_i64(v.as.i);
  case FT_F64:
    return fl_str_f64(v.as.f);
  case FT_BOOL:
    return fl_str_bool(v.as.b);
  case FT_STR:
    return flare_strdup(v.as.s);
  default:
    break;
  }
  if (fl_tag_is_container(v.tag))
    return fl_repr_boxed(v);
  return flare_strdup("?");
}

/* tiny string builder for container interpolation */
typedef struct {
  char *p;
  size_t len, cap;
} FlBuf;

static inline void flb_init(FlBuf *b) {
  b->cap = 64;
  b->len = 0;
  b->p = (char *)malloc(b->cap);
  if (!b->p) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
}

static inline void flb_reserve(FlBuf *b, size_t extra) {
  while (b->len + extra + 1 > b->cap) {
    b->cap *= 2;
    b->p = (char *)realloc(b->p, b->cap);
    if (!b->p) {
      fprintf(stderr, "out of memory\n");
      exit(1);
    }
  }
}

static inline void flb_puts(FlBuf *b, const char *s) {
  size_t n = strlen(s);
  flb_reserve(b, n);
  memcpy(b->p + b->len, s, n);
  b->len += n;
}

static inline void flb_putc(FlBuf *b, char c) {
  flb_reserve(b, 1);
  b->p[b->len++] = c;
}

static inline char *flb_done(FlBuf *b) {
  flb_putc(b, '\0');
  return b->p;
}

/* range values (feature: range() usable in expressions) */
typedef struct {
  int64_t lo, hi, step;
} FlRange;

static inline FlRange fl_make_range(int64_t lo, int64_t hi, int64_t step) {
  if (step == 0) {
    FL_RAISE_FMT("ValueError", "range() arg 3 must not be zero");
  }
  FlRange r = {lo, hi, step};
  return r;
}

static inline int64_t fl_range_len(FlRange r) {
  if (r.step > 0) {
    if (r.lo >= r.hi)
      return 0;
    return (r.hi - r.lo + r.step - 1) / r.step;
  } else {
    if (r.lo <= r.hi)
      return 0;
    return (r.lo - r.hi - r.step - 1) / (-r.step);
  }
}

static inline int64_t fl_range_sum(FlRange r) {
  int64_t n = fl_range_len(r);
  if (n == 0)
    return 0;
  // arithmetic series: n * (first + last) / 2
  int64_t first = r.lo;
  int64_t last = r.lo + (n - 1) * r.step;
  return n * (first + last) / 2;
}

static inline bool fl_range_contains(FlRange r, int64_t v) {
  if (r.step > 0) {
    return v >= r.lo && v < r.hi && (v - r.lo) % r.step == 0;
  } else {
    return v <= r.lo && v > r.hi && (r.lo - v) % (-r.step) == 0;
  }
}

static inline char *fl_str_range(FlRange r) {
  char b[96];
  if (r.step == 1)
    snprintf(b, sizeof b, "range(%" PRId64 ", %" PRId64 ")", r.lo, r.hi);
  else
    snprintf(b, sizeof b, "range(%" PRId64 ", %" PRId64 ", %" PRId64 ")", r.lo,
             r.hi, r.step);
  return flare_strdup(b);
}

static inline char *fl_str_class(const char *cname, void *ptr) {
  char b[128];
  snprintf(b, sizeof b, "<%s object at %p>", cname, ptr);
  return flare_strdup(b);
}

static inline void print_value(Value v) {
  switch (v.tag) {
  case FT_I64:
    printf("%" PRId64, v.as.i);
    break;
  case FT_F64:
    fl_print_f64(v.as.f);
    break;
  case FT_BOOL:
    fputs(v.as.b ? "True" : "False", stdout);
    break;
  case FT_STR:
    fputs(v.as.s, stdout);
    break;
  default:
    fputs(fl_repr_boxed(v), stdout);
    break;
  }
}

static inline double _vnum(Value v) {
  return v.tag == FT_F64 ? v.as.f : (double)v_to_i64(v);
}

static inline Value value_add(Value a, Value b) {
  if (a.tag == FT_STR && b.tag == FT_STR)
    return v_str(str_concat(a.as.s, b.as.s));
  if (a.tag == FT_F64 || b.tag == FT_F64)
    return v_f64(_vnum(a) + _vnum(b));
  return v_i64(v_to_i64(a) + v_to_i64(b));
}
static inline Value value_sub(Value a, Value b) {
  if (a.tag == FT_F64 || b.tag == FT_F64)
    return v_f64(_vnum(a) - _vnum(b));
  return v_i64(v_to_i64(a) - v_to_i64(b));
}
static inline Value value_mul(Value a, Value b) {
  if (a.tag == FT_F64 || b.tag == FT_F64)
    return v_f64(_vnum(a) * _vnum(b));
  return v_i64(v_to_i64(a) * v_to_i64(b));
}
static inline Value value_div(Value a, Value b) {
  double d = _vnum(b);
  if (d == 0.0)
    fl_raise("ZeroDivisionError", "division by zero");
  return v_f64(_vnum(a) / d);
}
static inline Value value_mod(Value a, Value b) {
  if (a.tag == FT_F64 || b.tag == FT_F64)
    return v_f64(fl_mod_f64(_vnum(a), _vnum(b)));
  return v_i64(fl_mod_i64(v_to_i64(a), v_to_i64(b)));
}
static inline Value value_neg(Value a) {
  if (a.tag == FT_F64)
    return v_f64(-a.as.f);
  return v_i64(-v_to_i64(a));
}
static inline int64_t value_len(Value v) {
  if (v.tag == FT_STR)
    return (int64_t)strlen(v.as.s);
  if (fl_tag_is_container(v.tag))
    return fl_boxed_len(v);
  fl_raise("TypeError", "len() of non-sized value");
}
static inline Value value_index(Value v, int64_t i) {
  if (fl_tag_is_container(v.tag))
    return fl_boxed_index(v, i);
  fl_raise("TypeError", "indexing a dynamic non-list");
}

static inline bool value_eq(Value a, Value b) {
  if (fl_tag_is_container(a.tag) || fl_tag_is_container(b.tag)) {
    /* structural equality for containers; storage-agnostic (a
       dict[i64] and a dict[dyn] with equal entries compare equal);
       a container never equals a scalar */
    return fl_boxed_eq(a, b);
  }
  if (a.tag == FT_STR || b.tag == FT_STR) {
    if (a.tag == FT_BOOL || b.tag == FT_BOOL)
      return value_truthy(a) == value_truthy(b);
    if (a.tag != b.tag)
      return false; /* str vs number: never equal */
    return strcmp(a.as.s, b.as.s) == 0;
  }
  if (a.tag == FT_BOOL || b.tag == FT_BOOL)
    return value_truthy(a) == value_truthy(b);
  if (a.tag == FT_F64 || b.tag == FT_F64)
    return _vnum(a) == _vnum(b);
  return v_to_i64(a) == v_to_i64(b);
}
static inline bool value_ne(Value a, Value b) { return !value_eq(a, b); }
static inline bool value_lt(Value a, Value b) {
  if (fl_tag_is_container(a.tag) || fl_tag_is_container(b.tag))
    fl_raise("TypeError", "unorderable types");
  if (a.tag == FT_STR && b.tag == FT_STR)
    return strcmp(a.as.s, b.as.s) < 0;
  return _vnum(a) < _vnum(b);
}
static inline bool value_gt(Value a, Value b) {
  if (fl_tag_is_container(a.tag) || fl_tag_is_container(b.tag))
    fl_raise("TypeError", "unorderable types");
  if (a.tag == FT_STR && b.tag == FT_STR)
    return strcmp(a.as.s, b.as.s) > 0;
  return _vnum(a) > _vnum(b);
}
static inline bool value_le(Value a, Value b) { return !value_gt(a, b); }
static inline bool value_ge(Value a, Value b) { return !value_lt(a, b); }

/* ------------------------------------------------------------------ */
/* lists                                                               */
/* ------------------------------------------------------------------ */

#define _FL_LIST(T, NAME)                                                      \
  typedef struct {                                                             \
    T *data;                                                                   \
    int64_t len, cap;                                                          \
  } FlList##NAME;                                                              \
  static inline FlList##NAME *list_##NAME##_new(void) {                        \
    FlList##NAME *l = (FlList##NAME *)calloc(1, sizeof(FlList##NAME));         \
    if (!l) {                                                                  \
      fprintf(stderr, "out of memory\n");                                      \
      exit(1);                                                                 \
    }                                                                          \
    return l;                                                                  \
  }                                                                            \
  static inline void list_##NAME##_append(FlList##NAME *l, T x) {              \
    if (l->len == l->cap) {                                                    \
      l->cap = l->cap ? l->cap * 2 : 8;                                        \
      l->data = (T *)realloc(l->data, (size_t)l->cap * sizeof(T));             \
      if (!l->data) {                                                          \
        fprintf(stderr, "out of memory\n");                                    \
        exit(1);                                                               \
      }                                                                        \
    }                                                                          \
    l->data[l->len++] = x;                                                     \
  }

_FL_LIST(int64_t, I64)
_FL_LIST(double, F64)
_FL_LIST(char *, Str)
_FL_LIST(Value, Dyn)

static inline FlListI64 *fl_range_to_list(FlRange r) {
  int64_t n = fl_range_len(r);
  FlListI64 *out = list_I64_new();
  // preallocate
  if (out->cap < n) {
    out->cap = n;
    out->data = (int64_t *)realloc(out->data, n * sizeof(int64_t));
  }
  int64_t v = r.lo;
  for (int64_t i = 0; i < n; i++) {
    out->data[i] = v;
    v += r.step;
  }
  out->len = n;
  return out;
}

static inline void print_list_I64(FlListI64 *l) {
  putchar('[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      fputs(", ", stdout);
    printf("%" PRId64, l->data[i]);
  }
  putchar(']');
}
static inline void print_list_F64(FlListF64 *l) {
  putchar('[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      fputs(", ", stdout);
    printf("%g", l->data[i]);
  }
  putchar(']');
}
static inline void print_list_Str(FlListStr *l) {
  putchar('[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      fputs(", ", stdout);
    printf("'%s'", l->data[i]);
  }
  putchar(']');
}
static inline void print_list_Dyn(FlListDyn *l) {
  putchar('[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      fputs(", ", stdout);
    print_value(l->data[i]);
  }
  putchar(']');
}

/* ------------------------------------------------------------------ */
/* dicts: string keys, homogeneous values, open addressing              */
/* ------------------------------------------------------------------ */

static inline uint64_t fl_hash_str(const char *s) {
  uint64_t h = 1469598103934665603ULL;
  while (*s) {
    h ^= (unsigned char)*s++;
    h *= 1099511628211ULL;
  }
  return h;
}

static inline void fl_print_quoted(const char *s) { printf("\"%s\"", s); }
static inline void fl_print_i64v(int64_t v) { printf("%" PRId64, v); }
static inline void fl_print_value_quoted(Value v) {
  if (v.tag == FT_STR)
    fl_print_quoted(v.as.s);
  else
    print_value(v);
}

#define FL_DICT_BODY(Suf, T, PRINTER)                                          \
  typedef struct {                                                             \
    char *key;                                                                 \
    T val;                                                                     \
    uint8_t used;                                                              \
  } FlDictE_##Suf;                                                             \
  typedef struct {                                                             \
    FlDictE_##Suf *tab;                                                        \
    int64_t len;                                                               \
    int64_t cap;                                                               \
  } FlDict_##Suf;                                                              \
                                                                               \
  static FlDict_##Suf *dict_##Suf##_new(void) {                                \
    FlDict_##Suf *d = malloc(sizeof *d);                                       \
    if (!d) {                                                                  \
      fprintf(stderr, "flare: out of memory\n");                               \
      exit(1);                                                                 \
    }                                                                          \
    d->cap = 16;                                                               \
    d->len = 0;                                                                \
    d->tab = calloc((size_t)d->cap, sizeof d->tab[0]);                         \
    if (!d->tab) {                                                             \
      fprintf(stderr, "flare: out of memory\n");                               \
      exit(1);                                                                 \
    }                                                                          \
    return d;                                                                  \
  }                                                                            \
                                                                               \
  static int64_t dict_##Suf##_slot(FlDict_##Suf *d, const char *k,             \
                                   bool *found) {                              \
    uint64_t h = fl_hash_str(k);                                               \
    int64_t i = (int64_t)(h & (uint64_t)(d->cap - 1));                         \
    for (;;) {                                                                 \
      FlDictE_##Suf *e = &d->tab[i];                                           \
      if (!e->used) {                                                          \
        *found = false;                                                        \
        return i;                                                              \
      }                                                                        \
      if (strcmp(e->key, k) == 0) {                                            \
        *found = true;                                                         \
        return i;                                                              \
      }                                                                        \
      i = (i + 1) & (d->cap - 1);                                              \
    }                                                                          \
  }                                                                            \
                                                                               \
  static void dict_##Suf##_grow(FlDict_##Suf *d) {                             \
    int64_t oldcap = d->cap;                                                   \
    FlDictE_##Suf *oldtab = d->tab;                                            \
    d->cap *= 2;                                                               \
    d->tab = calloc((size_t)d->cap, sizeof d->tab[0]);                         \
    if (!d->tab) {                                                             \
      fprintf(stderr, "flare: out of memory\n");                               \
      exit(1);                                                                 \
    }                                                                          \
    d->len = 0;                                                                \
    for (int64_t i = 0; i < oldcap; i++) {                                     \
      if (oldtab[i].used) {                                                    \
        bool f;                                                                \
        int64_t s = dict_##Suf##_slot(d, oldtab[i].key, &f);                   \
        d->tab[s] = oldtab[i];                                                 \
        d->len++;                                                              \
      }                                                                        \
    }                                                                          \
    free(oldtab);                                                              \
  }                                                                            \
                                                                               \
  static void dict_##Suf##_set(FlDict_##Suf *d, const char *k, T v) {          \
    if (d->len * 4 >= d->cap * 3)                                              \
      dict_##Suf##_grow(d);                                                    \
    bool f;                                                                    \
    int64_t s = dict_##Suf##_slot(d, k, &f);                                   \
    if (!f) {                                                                  \
      d->tab[s].key = flare_strdup(k);                                         \
      d->tab[s].used = 1;                                                      \
      d->len++;                                                                \
    }                                                                          \
    d->tab[s].val = v;                                                         \
  }                                                                            \
                                                                               \
  static T dict_##Suf##_get(FlDict_##Suf *d, const char *k) {                  \
    bool f;                                                                    \
    int64_t s = dict_##Suf##_slot(d, k, &f);                                   \
    if (!f) {                                                                  \
      FL_RAISE_FMT("KeyError", "key \"%s\" not found", k);                     \
    }                                                                          \
    return d->tab[s].val;                                                      \
  }                                                                            \
                                                                               \
  static bool dict_##Suf##_has(FlDict_##Suf *d, const char *k) {               \
    bool f;                                                                    \
    dict_##Suf##_slot(d, k, &f);                                               \
    return f;                                                                  \
  }                                                                            \
                                                                               \
  static FlListStr *dict_##Suf##_keys(FlDict_##Suf *d) {                       \
    FlListStr *out = list_Str_new();                                           \
    for (int64_t i = 0; i < d->cap; i++)                                       \
      if (d->tab[i].used)                                                      \
        list_Str_append(out, d->tab[i].key);                                   \
    return out;                                                                \
  }                                                                            \
                                                                               \
  static void dict_##Suf##_print(FlDict_##Suf *d) {                            \
    putchar('{');                                                              \
    bool first = true;                                                         \
    for (int64_t i = 0; i < d->cap; i++) {                                     \
      if (!d->tab[i].used)                                                     \
        continue;                                                              \
      if (!first)                                                              \
        fputs(", ", stdout);                                                   \
      first = false;                                                           \
      printf("\"%s\": ", d->tab[i].key);                                       \
      PRINTER(d->tab[i].val);                                                  \
    }                                                                          \
    putchar('}');                                                              \
  }

FL_DICT_BODY(I64, int64_t, fl_print_i64v)
FL_DICT_BODY(F64, double, fl_print_f64)
FL_DICT_BODY(Str, char *, fl_print_quoted)
FL_DICT_BODY(Dyn, Value, fl_print_value_quoted)

static inline char *fl_str_list_I64(FlListI64 *l) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      flb_puts(&b, ", ");
    char tmp[32];
    snprintf(tmp, sizeof tmp, "%" PRId64, l->data[i]);
    flb_puts(&b, tmp);
  }
  flb_putc(&b, ']');
  return flb_done(&b);
}

static inline char *fl_str_list_F64(FlListF64 *l) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      flb_puts(&b, ", ");
    char tmp[32];
    fl_fmt_f64(l->data[i], tmp, sizeof tmp);
    flb_puts(&b, tmp);
  }
  flb_putc(&b, ']');
  return flb_done(&b);
}

static inline char *fl_str_list_Str(FlListStr *l) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      flb_puts(&b, ", ");
    flb_putc(&b, '\'');
    flb_puts(&b, l->data[i]);
    flb_putc(&b, '\'');
  }
  flb_putc(&b, ']');
  return flb_done(&b);
}

static inline char *fl_str_list_Dyn(FlListDyn *l) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      flb_puts(&b, ", ");
    char *s = fl_str_value(l->data[i]);
    flb_puts(&b, s);
    free(s);
  }
  flb_putc(&b, ']');
  return flb_done(&b);
}

static inline char *fl_str_dict_I64(FlDict_I64 *d) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '{');
  bool first = true;
  for (int64_t i = 0; i < d->cap; i++) {
    if (!d->tab[i].used)
      continue;
    if (!first)
      flb_puts(&b, ", ");
    first = false;
    flb_putc(&b, '"');
    flb_puts(&b, d->tab[i].key);
    flb_puts(&b, "\": ");
    char tmp[32];
    snprintf(tmp, sizeof tmp, "%" PRId64, d->tab[i].val);
    flb_puts(&b, tmp);
  }
  flb_putc(&b, '}');
  return flb_done(&b);
}

static inline char *fl_str_dict_F64(FlDict_F64 *d) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '{');
  bool first = true;
  for (int64_t i = 0; i < d->cap; i++) {
    if (!d->tab[i].used)
      continue;
    if (!first)
      flb_puts(&b, ", ");
    first = false;
    flb_putc(&b, '"');
    flb_puts(&b, d->tab[i].key);
    flb_puts(&b, "\": ");
    char tmp[32];
    fl_fmt_f64(d->tab[i].val, tmp, sizeof tmp);
    flb_puts(&b, tmp);
  }
  flb_putc(&b, '}');
  return flb_done(&b);
}

static inline char *fl_str_dict_Str(FlDict_Str *d) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '{');
  bool first = true;
  for (int64_t i = 0; i < d->cap; i++) {
    if (!d->tab[i].used)
      continue;
    if (!first)
      flb_puts(&b, ", ");
    first = false;
    flb_putc(&b, '"');
    flb_puts(&b, d->tab[i].key);
    flb_puts(&b, "\": \"");
    flb_puts(&b, d->tab[i].val);
    flb_putc(&b, '"');
  }
  flb_putc(&b, '}');
  return flb_done(&b);
}

static inline char *fl_str_dict_Dyn(FlDict_Dyn *d) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '{');
  bool first = true;
  for (int64_t i = 0; i < d->cap; i++) {
    if (!d->tab[i].used)
      continue;
    if (!first)
      flb_puts(&b, ", ");
    first = false;
    flb_putc(&b, '"');
    flb_puts(&b, d->tab[i].key);
    flb_puts(&b, "\": ");
    char *s = fl_str_value(d->tab[i].val);
    flb_puts(&b, s);
    free(s);
  }
  flb_putc(&b, '}');
  return flb_done(&b);
}

/* `in` operator helpers */
static inline bool fl_contains_I64(FlListI64 *l, int64_t v) {
  for (int64_t i = 0; i < l->len; i++)
    if (l->data[i] == v)
      return true;
  return false;
}
static inline bool fl_contains_F64(FlListF64 *l, double v) {
  for (int64_t i = 0; i < l->len; i++)
    if (l->data[i] == v)
      return true;
  return false;
}
static inline bool fl_contains_Str(FlListStr *l, const char *v) {
  for (int64_t i = 0; i < l->len; i++)
    if (strcmp(l->data[i], v) == 0)
      return true;
  return false;
}
static inline bool fl_contains_Dyn(FlListDyn *l, Value v) {
  for (int64_t i = 0; i < l->len; i++)
    if (value_eq(l->data[i], v))
      return true;
  return false;
}
static inline bool value_contains(Value hay, Value needle) {
  if (hay.tag == FT_STR && needle.tag == FT_STR)
    return strstr(hay.as.s, needle.as.s) != NULL;
  if (fl_tag_is_container(hay.tag))
    return fl_boxed_contains(hay, needle);
  fl_raise("TypeError", "'in' not supported for these types");
  return false;
}

/* ------------------------------------------------------------------ */
/* stdlib: math constants                                              */
/* ------------------------------------------------------------------ */

#define FL_PI 3.14159265358979323846
#define FL_E 2.71828182845904523536

static inline Value value_abs(Value v) {
  if (v.tag == FT_F64)
    return v_f64(fabs(v.as.f));
  int64_t x = v_to_i64(v);
  return v_i64(x < 0 ? -x : x);
}

/* ------------------------------------------------------------------ */
/* stdlib: strings                                                     */
/* ------------------------------------------------------------------ */

static inline FlListStr *str_split(const char *s, const char *delim) {
  FlListStr *l = list_Str_new();
  size_t dl = strlen(delim);
  const char *p = s;
  if (dl == 0) {
    /* CPython raises ValueError for an empty separator */
    fl_raise("ValueError", "empty separator");
  }
  const char *q;
  while ((q = strstr(p, delim)) != NULL) {
    size_t n = (size_t)(q - p);
    char *tok = (char *)malloc(n + 1);
    if (!tok) {
      fprintf(stderr, "out of memory\n");
      exit(1);
    }
    memcpy(tok, p, n);
    tok[n] = 0;
    list_Str_append(l, tok);
    p = q + dl;
  }
  list_Str_append(l, flare_strdup(p));
  return l;
}

static inline char *str_join(const char *delim, FlListStr *l) {
  if (l->len == 0)
    return flare_strdup("");
  size_t dl = strlen(delim), total = 0;
  for (int64_t i = 0; i < l->len; i++)
    total += strlen(l->data[i]);
  total += dl * (size_t)(l->len - 1);
  char *r = (char *)malloc(total + 1);
  if (!r) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
  char *w = r;
  for (int64_t i = 0; i < l->len; i++) {
    if (i) {
      memcpy(w, delim, dl);
      w += dl;
    }
    size_t n = strlen(l->data[i]);
    memcpy(w, l->data[i], n);
    w += n;
  }
  *w = 0;
  return r;
}

static inline char *str_upper(const char *s) {
  char *r = flare_strdup(s);
  for (char *p = r; *p; p++)
    *p = (char)toupper((unsigned char)*p);
  return r;
}

static inline char *str_lower(const char *s) {
  char *r = flare_strdup(s);
  for (char *p = r; *p; p++)
    *p = (char)tolower((unsigned char)*p);
  return r;
}

static inline char *str_strip(const char *s) {
  while (*s && isspace((unsigned char)*s))
    s++;
  const char *e = s + strlen(s);
  while (e > s && isspace((unsigned char)*(e - 1)))
    e--;
  size_t n = (size_t)(e - s);
  char *r = (char *)malloc(n + 1);
  if (!r) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
  memcpy(r, s, n);
  r[n] = 0;
  return r;
}

static inline char *str_replace(const char *s, const char *old_,
                                const char *new_) {
  size_t lo = strlen(old_), ln = strlen(new_);
  if (lo == 0)
    return flare_strdup(s);
  size_t count = 0;
  const char *p = s;
  while ((p = strstr(p, old_)) != NULL) {
    count++;
    p += lo;
  }
  size_t total = strlen(s) + count * (ln - lo);
  char *r = (char *)malloc(total + 1);
  if (!r) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
  char *w = r;
  p = s;
  const char *q;
  while ((q = strstr(p, old_)) != NULL) {
    size_t n = (size_t)(q - p);
    memcpy(w, p, n);
    w += n;
    memcpy(w, new_, ln);
    w += ln;
    p = q + lo;
  }
  strcpy(w, p);
  return r;
}

static inline int64_t str_find(const char *s, const char *sub) {
  const char *p = strstr(s, sub);
  return p ? (int64_t)(p - s) : -1;
}

static inline bool str_startswith(const char *s, const char *pre) {
  return strncmp(s, pre, strlen(pre)) == 0;
}

static inline bool str_endswith(const char *s, const char *suf) {
  size_t ls = strlen(s), lf = strlen(suf);
  return lf <= ls && strcmp(s + ls - lf, suf) == 0;
}

/* ------------------------------------------------------------------ */
/* stdlib: list algorithms                                             */
/* ------------------------------------------------------------------ */

static int _cmp_i64(const void *a, const void *b) {
  int64_t x = *(const int64_t *)a, y = *(const int64_t *)b;
  return (x > y) - (x < y);
}
static int _cmp_f64(const void *a, const void *b) {
  double x = *(const double *)a, y = *(const double *)b;
  return (x > y) - (x < y);
}
static int _cmp_str(const void *a, const void *b) {
  return strcmp(*(char *const *)a, *(char *const *)b);
}
static inline void list_I64_sort(FlListI64 *l) {
  qsort(l->data, (size_t)l->len, sizeof(int64_t), _cmp_i64);
}
static inline void list_F64_sort(FlListF64 *l) {
  qsort(l->data, (size_t)l->len, sizeof(double), _cmp_f64);
}
static inline void list_Str_sort(FlListStr *l) {
  qsort(l->data, (size_t)l->len, sizeof(char *), _cmp_str);
}

static inline void list_I64_reverse(FlListI64 *l) {
  for (int64_t i = 0, j = l->len - 1; i < j; i++, j--) {
    int64_t t = l->data[i];
    l->data[i] = l->data[j];
    l->data[j] = t;
  }
}
/* copies for sorted()/reversed() (eager, like CPython's sorted()) */
#define _FL_LIST_COPY(T, NAME)                                                 \
  static inline FlList##NAME *list_##NAME##_copy(FlList##NAME *l) {            \
    FlList##NAME *out = list_##NAME##_new();                                   \
    if (out->cap < l->len) {                                                   \
      out->cap = l->len;                                                       \
      out->data = (T *)realloc(out->data, (size_t)l->len * sizeof(T));         \
    }                                                                          \
    for (int64_t i = 0; i < l->len; i++)                                       \
      out->data[i] = l->data[i];                                               \
    out->len = l->len;                                                         \
    return out;                                                                \
  }
_FL_LIST_COPY(int64_t, I64)
_FL_LIST_COPY(double, F64)
_FL_LIST_COPY(char *, Str)
_FL_LIST_COPY(Value, Dyn)

/* list of lists (for enumerate/zip pairs) */
typedef struct {
  FlListDyn **data;
  int64_t len, cap;
} FlListListDyn;

static inline FlListListDyn *list_ListDyn_new(void) {
  FlListListDyn *l = (FlListListDyn *)malloc(sizeof(FlListListDyn));
  l->len = 0;
  l->cap = 8;
  l->data = (FlListDyn **)malloc(8 * sizeof(FlListDyn *));
  return l;
}

static inline void list_ListDyn_append(FlListListDyn *l, FlListDyn *v) {
  if (l->len >= l->cap) {
    l->cap *= 2;
    l->data =
        (FlListDyn **)realloc(l->data, (size_t)l->cap * sizeof(FlListDyn *));
  }
  l->data[l->len++] = v;
}

static inline void print_list_ListDyn(FlListListDyn *l) {
  putchar('[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i) {
      putchar(',');
      putchar(' ');
    }
    // print as [a, b] (Python prints tuples as (a, b), but we use lists)
    putchar('[');
    FlListDyn *p = l->data[i];
    for (int64_t j = 0; j < p->len; j++) {
      if (j) {
        putchar(',');
        putchar(' ');
      }
      print_value(p->data[j]);
    }
    putchar(']');
  }
  putchar(']');
}

static inline FlListDyn *fl_index_ListDyn(FlListListDyn *l, int64_t i) {
  int64_t orig = i;
  if (i < 0)
    i += l->len;
  if (i < 0 || i >= l->len) {
    FL_RAISE_FMT("IndexError",
                 "index %" PRId64 " out of range (len %" PRId64 ")", orig,
                 l->len);
  }
  return l->data[i];
}
static inline void list_F64_reverse(FlListF64 *l) {
  for (int64_t i = 0, j = l->len - 1; i < j; i++, j--) {
    double t = l->data[i];
    l->data[i] = l->data[j];
    l->data[j] = t;
  }
}
static inline void list_Str_reverse(FlListStr *l) {
  for (int64_t i = 0, j = l->len - 1; i < j; i++, j--) {
    char *t = l->data[i];
    l->data[i] = l->data[j];
    l->data[j] = t;
  }
}
static inline void list_Dyn_reverse(FlListDyn *l) {
  for (int64_t i = 0, j = l->len - 1; i < j; i++, j--) {
    Value t = l->data[i];
    l->data[i] = l->data[j];
    l->data[j] = t;
  }
}

static inline FlListI64 *fl_range_to_rev_list(FlRange r) {
  FlListI64 *out = fl_range_to_list(r);
  list_I64_reverse(out);
  return out;
}

static inline int64_t list_I64_sum(FlListI64 *l) {
  int64_t s = 0;
  for (int64_t i = 0; i < l->len; i++)
    s += l->data[i];
  return s;
}
static inline double list_F64_sum(FlListF64 *l) {
  double s = 0;
  for (int64_t i = 0; i < l->len; i++)
    s += l->data[i];
  return s;
}
static inline int64_t list_I64_min(FlListI64 *l) {
  if (!l->len) {
    fl_raise("ValueError", "min() of empty list");
  }
  int64_t m = l->data[0];
  for (int64_t i = 1; i < l->len; i++)
    if (l->data[i] < m)
      m = l->data[i];
  return m;
}
static inline int64_t list_I64_max(FlListI64 *l) {
  if (!l->len) {
    fl_raise("ValueError", "max() of empty list");
  }
  int64_t m = l->data[0];
  for (int64_t i = 1; i < l->len; i++)
    if (l->data[i] > m)
      m = l->data[i];
  return m;
}
static inline double list_F64_min(FlListF64 *l) {
  if (!l->len) {
    fl_raise("ValueError", "min() of empty list");
  }
  double m = l->data[0];
  for (int64_t i = 1; i < l->len; i++)
    if (l->data[i] < m)
      m = l->data[i];
  return m;
}
static inline double list_F64_max(FlListF64 *l) {
  if (!l->len) {
    fl_raise("ValueError", "max() of empty list");
  }
  double m = l->data[0];
  for (int64_t i = 1; i < l->len; i++)
    if (l->data[i] > m)
      m = l->data[i];
  return m;
}
static inline char *list_Str_min(FlListStr *l) {
  if (!l->len) {
    fl_raise("ValueError", "min() of empty list");
  }
  char *m = l->data[0];
  for (int64_t i = 1; i < l->len; i++)
    if (strcmp(l->data[i], m) < 0)
      m = l->data[i];
  return m;
}
static inline char *list_Str_max(FlListStr *l) {
  if (!l->len) {
    fl_raise("ValueError", "max() of empty list");
  }
  char *m = l->data[0];
  for (int64_t i = 1; i < l->len; i++)
    if (strcmp(l->data[i], m) > 0)
      m = l->data[i];
  return m;
}

/* ------------------------------------------------------------------ */
/* stdlib: files                                                       */
/* ------------------------------------------------------------------ */

static inline char *file_read_all(const char *path) {
  FILE *f = fopen(path, "rb");
  if (!f) {
    FL_RAISE_FMT("OSError", "cannot open '%s'", path);
  }
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  fseek(f, 0, SEEK_SET);
  char *r = (char *)malloc((size_t)n + 1);
  if (!r) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
  if (n > 0 && fread(r, 1, (size_t)n, f) != (size_t)n) {
    FL_RAISE_FMT("OSError", "cannot read '%s'", path);
  }
  r[n] = 0;
  fclose(f);
  return r;
}

static inline void file_write_all(const char *path, const char *content) {
  FILE *f = fopen(path, "wb");
  if (!f) {
    FL_RAISE_FMT("OSError", "cannot write '%s'", path);
  }
  size_t n = strlen(content);
  if (n > 0 && fwrite(content, 1, n, f) != n) {
    FL_RAISE_FMT("OSError", "cannot write '%s'", path);
  }
  fclose(f);
}

static inline FlListStr *file_read_lines(const char *path) {
  char *all = file_read_all(path);
  FlListStr *l = str_split(all, "\n");
  free(all);
  if (l->len > 0 && l->data[l->len - 1][0] == '\0')
    l->len--;
  return l;
}

/* ------------------------------------------------------------------ */
/* stdlib: time & random                                               */
/* ------------------------------------------------------------------ */

static inline double time_now(void) {
  struct timespec ts;
  clock_gettime(CLOCK_REALTIME, &ts);
  return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static inline void time_sleep(double s) {
  struct timespec ts;
  ts.tv_sec = (time_t)s;
  ts.tv_nsec = (long)((s - (double)ts.tv_sec) * 1e9);
  nanosleep(&ts, NULL);
}

static inline double rand01(void) { return (double)rand() / (double)RAND_MAX; }

/* ------------------------------------------------------------------ */
/* execution anchor: no raw segfaults, ever. Three layers:             */
/*  1. recursion depth guard (nice error for deep recursion)           */
/*  2. stack-pointer guard (precise, frame-size independent)           */
/*  3. signal net (last resort: SIGSEGV/SIGFPE/SIGABRT/SIGILL -> msg)  */
/* ------------------------------------------------------------------ */

#include <signal.h>
#include <unistd.h>

static void _flare_fatal(int sig) {
  const char *name = "unknown signal";
  if (sig == SIGSEGV)
    name = "segmentation fault";
  else if (sig == SIGFPE)
    name = "arithmetic fault";
  else if (sig == SIGABRT)
    name = "abort";
  else if (sig == SIGILL)
    name = "illegal instruction";
  fprintf(stderr, "flare: fatal %s - execution stopped safely\n", name);
  _exit(1);
}

static inline void _flare_anchor(void) {
  _flare_depth = 0;
  signal(SIGSEGV, _flare_fatal);
  signal(SIGFPE, _flare_fatal);
  signal(SIGABRT, _flare_fatal);
  signal(SIGILL, _flare_fatal);
}

/* bounds-checked indexing: clean error instead of a segfault.
   Negative indices count from the end, like Python. */
static inline int64_t fl_index_I64(FlListI64 *l, int64_t i) {
  int64_t orig = i;
  if (i < 0)
    i += l->len;
  if (i < 0 || i >= l->len) {
    FL_RAISE_FMT("IndexError",
                 "index %" PRId64 " out of range (len %" PRId64 ")", orig,
                 l->len);
  }
  return l->data[i];
}
static inline double fl_index_F64(FlListF64 *l, int64_t i) {
  int64_t orig = i;
  if (i < 0)
    i += l->len;
  if (i < 0 || i >= l->len) {
    FL_RAISE_FMT("IndexError",
                 "index %" PRId64 " out of range (len %" PRId64 ")", orig,
                 l->len);
  }
  return l->data[i];
}
static inline char *fl_index_Str(FlListStr *l, int64_t i) {
  int64_t orig = i;
  if (i < 0)
    i += l->len;
  if (i < 0 || i >= l->len) {
    FL_RAISE_FMT("IndexError",
                 "index %" PRId64 " out of range (len %" PRId64 ")", orig,
                 l->len);
  }
  return l->data[i];
}
static inline Value fl_index_Dyn(FlListDyn *l, int64_t i) {
  int64_t orig = i;
  if (i < 0)
    i += l->len;
  if (i < 0 || i >= l->len) {
    FL_RAISE_FMT("IndexError",
                 "index %" PRId64 " out of range (len %" PRId64 ")", orig,
                 l->len);
  }
  return l->data[i];
}

/* Python slice.indices() normalization: clamp lo/hi to the length,
   following CPython's PySlice_AdjustIndices exactly. */
static inline void fl_norm_slice(int64_t len, int64_t lo, int64_t hi,
                                 int64_t step, int has_lo, int has_hi,
                                 int has_step, int64_t *o_lo, int64_t *o_hi,
                                 int64_t *o_step) {
  int64_t st = has_step ? step : 1;
  if (st == 0)
    fl_raise("ValueError", "slice step cannot be zero");
  int64_t l = has_lo ? lo : (st > 0 ? 0 : len - 1);
  int64_t h = has_hi ? hi : (st > 0 ? len : -1);
  if (st > 0) {
    if (l < 0) {
      l += len;
      if (l < 0)
        l = 0;
    } else if (l > len)
      l = len;
    if (h < 0) {
      h += len;
      if (h < 0)
        h = 0;
    } else if (h > len)
      h = len;
  } else {
    /* only adjust explicitly-given bounds; missing lo/hi already hold
       the correct defaults (len-1 / -1) */
    if (has_lo) {
      if (l < 0) {
        l += len;
        if (l < 0)
          l = -1;
      } else if (l >= len)
        l = len - 1;
    }
    if (has_hi) {
      if (h < 0) {
        h += len;
        if (h < 0)
          h = -1;
      } else if (h >= len)
        h = len - 1;
    }
  }
  *o_lo = l;
  *o_hi = h;
  *o_step = st;
}

#define FL_SLICE_LIST(Suf, T)                                                  \
  static inline FlList##Suf *fl_slice_##Suf(                                   \
      FlList##Suf *l, int64_t lo, int64_t hi, int64_t step, int has_lo,        \
      int has_hi, int has_step) {                                              \
    int64_t a, b, st;                                                          \
    fl_norm_slice(l->len, lo, hi, step, has_lo, has_hi, has_step, &a, &b,      \
                  &st);                                                        \
    FlList##Suf *out = list_##Suf##_new();                                     \
    if (st > 0) {                                                              \
      for (int64_t i = a; i < b; i += st)                                      \
        list_##Suf##_append(out, l->data[i]);                                  \
    } else {                                                                   \
      for (int64_t i = a; i > b; i += st)                                      \
        list_##Suf##_append(out, l->data[i]);                                  \
    }                                                                          \
    return out;                                                                \
  }

FL_SLICE_LIST(I64, int64_t)
FL_SLICE_LIST(F64, double)
FL_SLICE_LIST(Str, char *)
FL_SLICE_LIST(Dyn, Value)

/* string indexing: s[i] -> one-character string (negative counts from end) */
static inline char *fl_str_index(const char *s, int64_t i) {
  int64_t len = (int64_t)strlen(s);
  int64_t orig = i;
  if (i < 0)
    i += len;
  if (i < 0 || i >= len) {
    FL_RAISE_FMT("IndexError",
                 "string index %" PRId64 " out of range (len %" PRId64 ")",
                 orig, len);
  }
  char *r = (char *)malloc(2);
  if (!r) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
  r[0] = s[i];
  r[1] = 0;
  return r;
}

/* string slicing (byte-based): s[lo:hi:step] -> new string */
static inline char *fl_str_slice(const char *s, int64_t lo, int64_t hi,
                                 int64_t step, int has_lo, int has_hi,
                                 int has_step) {
  int64_t len = (int64_t)strlen(s);
  int64_t a, b, st;
  fl_norm_slice(len, lo, hi, step, has_lo, has_hi, has_step, &a, &b, &st);
  int64_t n = 0;
  if (st > 0) {
    for (int64_t i = a; i < b; i += st)
      n++;
  } else {
    for (int64_t i = a; i > b; i += st)
      n++;
  }
  char *out = (char *)malloc((size_t)n + 1);
  if (!out) {
    fprintf(stderr, "out of memory\n");
    exit(1);
  }
  int64_t w = 0;
  if (st > 0) {
    for (int64_t i = a; i < b; i += st)
      out[w++] = s[i];
  } else {
    for (int64_t i = a; i > b; i += st)
      out[w++] = s[i];
  }
  out[w] = 0;
  return out;
}

/* list element assignment: a[i] = v (bounds-checked, negative ok) */
#define FL_SET_LIST(Suf, T)                                                    \
  static inline void fl_set_##Suf(FlList##Suf *l, int64_t i, T v) {            \
    int64_t orig = i;                                                          \
    if (i < 0)                                                                 \
      i += l->len;                                                             \
    if (i < 0 || i >= l->len) {                                                \
      FL_RAISE_FMT("IndexError",                                               \
                   "index %" PRId64 " out of range (len %" PRId64 ")", orig,   \
                   l->len);                                                    \
    }                                                                          \
    l->data[i] = v;                                                            \
  }

FL_SET_LIST(I64, int64_t)
FL_SET_LIST(F64, double)
FL_SET_LIST(Str, char *)
FL_SET_LIST(Dyn, Value)

static inline double fl_div_f64(double a, double b) {
  if (b == 0.0)
    fl_raise("ZeroDivisionError", "division by zero");
  return a / b;
}

static inline int64_t randint_ab(int64_t a, int64_t b) {
  if (b < a) {
    int64_t t = a;
    a = b;
    b = t;
  }
  uint64_t span = (uint64_t)(b - a) + 1;
  return a + (int64_t)(rand01() * (double)span);
}

/* ------------------------------------------------------------------ */
/* boxed containers: nested lists/dicts inside dynamic Values          */
/* Boxing is zero-copy: the Value just carries the heap pointer plus a  */
/* tag naming the exact struct type. Ownership follows the existing    */
/* string convention (heap-allocated, never freed by the runtime).     */
/* ------------------------------------------------------------------ */

/* constructors: wrap a typed container pointer in a Value */
static inline Value v_list_I64(FlListI64 *p) {
  Value v;
  v.tag = FT_LIST_I64;
  v.as.p = p;
  return v;
}
static inline Value v_list_F64(FlListF64 *p) {
  Value v;
  v.tag = FT_LIST_F64;
  v.as.p = p;
  return v;
}
static inline Value v_list_Str(FlListStr *p) {
  Value v;
  v.tag = FT_LIST_STR;
  v.as.p = p;
  return v;
}
static inline Value v_list_DYN(FlListDyn *p) {
  Value v;
  v.tag = FT_LIST_DYN;
  v.as.p = p;
  return v;
}
static inline Value v_list_PAIR(FlListListDyn *p) {
  Value v;
  v.tag = FT_LIST_PAIR;
  v.as.p = p;
  return v;
}
static inline Value v_dict_I64(FlDict_I64 *p) {
  Value v;
  v.tag = FT_DICT_I64;
  v.as.p = p;
  return v;
}
static inline Value v_dict_F64(FlDict_F64 *p) {
  Value v;
  v.tag = FT_DICT_F64;
  v.as.p = p;
  return v;
}
static inline Value v_dict_Str(FlDict_Str *p) {
  Value v;
  v.tag = FT_DICT_STR;
  v.as.p = p;
  return v;
}
static inline Value v_dict_DYN(FlDict_Dyn *p) {
  Value v;
  v.tag = FT_DICT_DYN;
  v.as.p = p;
  return v;
}

/* unboxers: checked downcasts; a tag mismatch is a clean TypeError */
static inline FlListI64 *v_unbox_list_I64(Value v) {
  if (v.tag != FT_LIST_I64)
    fl_raise("TypeError", "expected a list");
  return (FlListI64 *)v.as.p;
}
static inline FlListF64 *v_unbox_list_F64(Value v) {
  if (v.tag != FT_LIST_F64)
    fl_raise("TypeError", "expected a list");
  return (FlListF64 *)v.as.p;
}
static inline FlListStr *v_unbox_list_Str(Value v) {
  if (v.tag != FT_LIST_STR)
    fl_raise("TypeError", "expected a list");
  return (FlListStr *)v.as.p;
}
static inline FlListDyn *v_unbox_list_DYN(Value v) {
  if (v.tag != FT_LIST_DYN)
    fl_raise("TypeError", "expected a list");
  return (FlListDyn *)v.as.p;
}
static inline FlListListDyn *v_unbox_list_PAIR(Value v) {
  if (v.tag != FT_LIST_PAIR)
    fl_raise("TypeError", "expected a list");
  return (FlListListDyn *)v.as.p;
}
static inline FlDict_I64 *v_unbox_dict_I64(Value v) {
  if (v.tag != FT_DICT_I64)
    fl_raise("TypeError", "expected a dict");
  return (FlDict_I64 *)v.as.p;
}
static inline FlDict_F64 *v_unbox_dict_F64(Value v) {
  if (v.tag != FT_DICT_F64)
    fl_raise("TypeError", "expected a dict");
  return (FlDict_F64 *)v.as.p;
}
static inline FlDict_Str *v_unbox_dict_Str(Value v) {
  if (v.tag != FT_DICT_STR)
    fl_raise("TypeError", "expected a dict");
  return (FlDict_Str *)v.as.p;
}
static inline FlDict_Dyn *v_unbox_dict_DYN(Value v) {
  if (v.tag != FT_DICT_DYN)
    fl_raise("TypeError", "expected a dict");
  return (FlDict_Dyn *)v.as.p;
}

/* Python-style repr for nested containers (single-quoted strings, like
   CPython). Used by print()/f-strings when a container sits inside a
   dynamic Value. Top-level typed containers keep their existing
   printers untouched.
   Depth-limited: cyclic or absurdly deep structures raise a clean
   RecursionError instead of overflowing the C stack (like CPython). */
#define FL_MAX_NEST 1000

static inline void fl_repr_str(FlBuf *b, const char *s) {
  bool has_sq = strchr(s, '\'') != NULL;
  bool has_dq = strchr(s, '"') != NULL;
  char q = (has_sq && !has_dq) ? '"' : '\'';
  flb_putc(b, q);
  for (const char *p = s; *p; p++) {
    if (*p == '\n') {
      flb_puts(b, "\\n");
      continue;
    }
    if (*p == '\t') {
      flb_puts(b, "\\t");
      continue;
    }
    if (*p == '\r') {
      flb_puts(b, "\\r");
      continue;
    }
    if (*p == q || *p == '\\')
      flb_putc(b, '\\');
    flb_putc(b, *p);
  }
  flb_putc(b, q);
}

static void fl_repr_into(FlBuf *b, Value v, int depth) {
  char t[32];
  int64_t i, j;
  bool first;
  if (depth > FL_MAX_NEST)
    fl_raise("RecursionError", "maximum nesting depth exceeded");
  switch (v.tag) {
  case FT_I64:
    snprintf(t, sizeof t, "%" PRId64, v.as.i);
    flb_puts(b, t);
    break;
  case FT_F64:
    fl_fmt_f64(v.as.f, t, sizeof t);
    flb_puts(b, t);
    break;
  case FT_BOOL:
    flb_puts(b, v.as.b ? "True" : "False");
    break;
  case FT_STR:
    fl_repr_str(b, v.as.s);
    break;
  case FT_LIST_I64: {
    FlListI64 *l = (FlListI64 *)v.as.p;
    flb_putc(b, '[');
    for (i = 0; i < l->len; i++) {
      if (i)
        flb_puts(b, ", ");
      snprintf(t, sizeof t, "%" PRId64, l->data[i]);
      flb_puts(b, t);
    }
    flb_putc(b, ']');
    break;
  }
  case FT_LIST_F64: {
    FlListF64 *l = (FlListF64 *)v.as.p;
    flb_putc(b, '[');
    for (i = 0; i < l->len; i++) {
      if (i)
        flb_puts(b, ", ");
      fl_fmt_f64(l->data[i], t, sizeof t);
      flb_puts(b, t);
    }
    flb_putc(b, ']');
    break;
  }
  case FT_LIST_STR: {
    FlListStr *l = (FlListStr *)v.as.p;
    flb_putc(b, '[');
    for (i = 0; i < l->len; i++) {
      if (i)
        flb_puts(b, ", ");
      fl_repr_str(b, l->data[i]);
    }
    flb_putc(b, ']');
    break;
  }
  case FT_LIST_DYN: {
    FlListDyn *l = (FlListDyn *)v.as.p;
    flb_putc(b, '[');
    for (i = 0; i < l->len; i++) {
      if (i)
        flb_puts(b, ", ");
      fl_repr_into(b, l->data[i], depth + 1);
    }
    flb_putc(b, ']');
    break;
  }
  case FT_LIST_PAIR: {
    FlListListDyn *l = (FlListListDyn *)v.as.p;
    flb_putc(b, '[');
    for (i = 0; i < l->len; i++) {
      if (i)
        flb_puts(b, ", ");
      FlListDyn *p = l->data[i];
      flb_putc(b, '[');
      for (j = 0; j < p->len; j++) {
        if (j)
          flb_puts(b, ", ");
        fl_repr_into(b, p->data[j], depth + 1);
      }
      flb_putc(b, ']');
    }
    flb_putc(b, ']');
    break;
  }
  case FT_DICT_I64: {
    FlDict_I64 *d = (FlDict_I64 *)v.as.p;
    flb_putc(b, '{');
    first = true;
    for (i = 0; i < d->cap; i++) {
      if (!d->tab[i].used)
        continue;
      if (!first)
        flb_puts(b, ", ");
      first = false;
      fl_repr_str(b, d->tab[i].key);
      flb_puts(b, ": ");
      snprintf(t, sizeof t, "%" PRId64, d->tab[i].val);
      flb_puts(b, t);
    }
    flb_putc(b, '}');
    break;
  }
  case FT_DICT_F64: {
    FlDict_F64 *d = (FlDict_F64 *)v.as.p;
    flb_putc(b, '{');
    first = true;
    for (i = 0; i < d->cap; i++) {
      if (!d->tab[i].used)
        continue;
      if (!first)
        flb_puts(b, ", ");
      first = false;
      fl_repr_str(b, d->tab[i].key);
      flb_puts(b, ": ");
      fl_fmt_f64(d->tab[i].val, t, sizeof t);
      flb_puts(b, t);
    }
    flb_putc(b, '}');
    break;
  }
  case FT_DICT_STR: {
    FlDict_Str *d = (FlDict_Str *)v.as.p;
    flb_putc(b, '{');
    first = true;
    for (i = 0; i < d->cap; i++) {
      if (!d->tab[i].used)
        continue;
      if (!first)
        flb_puts(b, ", ");
      first = false;
      fl_repr_str(b, d->tab[i].key);
      flb_puts(b, ": ");
      fl_repr_str(b, d->tab[i].val);
    }
    flb_putc(b, '}');
    break;
  }
  case FT_DICT_DYN: {
    FlDict_Dyn *d = (FlDict_Dyn *)v.as.p;
    flb_putc(b, '{');
    first = true;
    for (i = 0; i < d->cap; i++) {
      if (!d->tab[i].used)
        continue;
      if (!first)
        flb_puts(b, ", ");
      first = false;
      fl_repr_str(b, d->tab[i].key);
      flb_puts(b, ": ");
      fl_repr_into(b, d->tab[i].val, depth + 1);
    }
    flb_putc(b, '}');
    break;
  }
  }
}

static char *fl_repr_boxed(Value v) {
  FlBuf b;
  flb_init(&b);
  fl_repr_into(&b, v, 0);
  return flb_done(&b);
}

/* structural equality (order-independent for dicts, storage-agnostic:
   a dict[i64] and a dict[dyn] with the same entries compare equal).
   Generic views over any boxed container: */
static int64_t fl_boxed_list_len(Value v) {
  switch (v.tag) {
  case FT_LIST_I64:
    return ((FlListI64 *)v.as.p)->len;
  case FT_LIST_F64:
    return ((FlListF64 *)v.as.p)->len;
  case FT_LIST_STR:
    return ((FlListStr *)v.as.p)->len;
  case FT_LIST_DYN:
    return ((FlListDyn *)v.as.p)->len;
  case FT_LIST_PAIR:
    return ((FlListListDyn *)v.as.p)->len;
  default:
    return -1;
  }
}

static Value fl_boxed_list_elem(Value v, int64_t i) {
  switch (v.tag) {
  case FT_LIST_I64:
    return v_i64(((FlListI64 *)v.as.p)->data[i]);
  case FT_LIST_F64:
    return v_f64(((FlListF64 *)v.as.p)->data[i]);
  case FT_LIST_STR:
    return v_str(((FlListStr *)v.as.p)->data[i]);
  case FT_LIST_DYN:
    return ((FlListDyn *)v.as.p)->data[i];
  case FT_LIST_PAIR:
    return v_list_DYN(((FlListListDyn *)v.as.p)->data[i]);
  default:
    return v_i64(0); /* unreachable */
  }
}

static int64_t fl_boxed_dict_len(Value v) {
  switch (v.tag) {
  case FT_DICT_I64:
    return ((FlDict_I64 *)v.as.p)->len;
  case FT_DICT_F64:
    return ((FlDict_F64 *)v.as.p)->len;
  case FT_DICT_STR:
    return ((FlDict_Str *)v.as.p)->len;
  case FT_DICT_DYN:
    return ((FlDict_Dyn *)v.as.p)->len;
  default:
    return -1;
  }
}

static FlListStr *fl_boxed_dict_keys(Value v) {
  FlListStr *out = list_Str_new();
  int64_t i;
  switch (v.tag) {
  case FT_DICT_I64: {
    FlDict_I64 *d = (FlDict_I64 *)v.as.p;
    for (i = 0; i < d->cap; i++)
      if (d->tab[i].used)
        list_Str_append(out, d->tab[i].key);
    break;
  }
  case FT_DICT_F64: {
    FlDict_F64 *d = (FlDict_F64 *)v.as.p;
    for (i = 0; i < d->cap; i++)
      if (d->tab[i].used)
        list_Str_append(out, d->tab[i].key);
    break;
  }
  case FT_DICT_STR: {
    FlDict_Str *d = (FlDict_Str *)v.as.p;
    for (i = 0; i < d->cap; i++)
      if (d->tab[i].used)
        list_Str_append(out, d->tab[i].key);
    break;
  }
  case FT_DICT_DYN: {
    FlDict_Dyn *d = (FlDict_Dyn *)v.as.p;
    for (i = 0; i < d->cap; i++)
      if (d->tab[i].used)
        list_Str_append(out, d->tab[i].key);
    break;
  }
  default:
    break;
  }
  return out;
}

/* get a dict value as a Value regardless of storage; false if missing */
static bool fl_boxed_dict_try_get(Value v, const char *k, Value *out) {
  switch (v.tag) {
  case FT_DICT_I64: {
    FlDict_I64 *d = (FlDict_I64 *)v.as.p;
    if (!dict_I64_has(d, k))
      return false;
    *out = v_i64(dict_I64_get(d, k));
    return true;
  }
  case FT_DICT_F64: {
    FlDict_F64 *d = (FlDict_F64 *)v.as.p;
    if (!dict_F64_has(d, k))
      return false;
    *out = v_f64(dict_F64_get(d, k));
    return true;
  }
  case FT_DICT_STR: {
    FlDict_Str *d = (FlDict_Str *)v.as.p;
    if (!dict_Str_has(d, k))
      return false;
    *out = v_str(dict_Str_get(d, k));
    return true;
  }
  case FT_DICT_DYN: {
    FlDict_Dyn *d = (FlDict_Dyn *)v.as.p;
    if (!dict_Dyn_has(d, k))
      return false;
    *out = dict_Dyn_get(d, k);
    return true;
  }
  default:
    return false;
  }
}

static bool fl_list_eq_any(Value a, Value b) {
  int64_t n = fl_boxed_list_len(a);
  if (n != fl_boxed_list_len(b))
    return false;
  for (int64_t i = 0; i < n; i++)
    if (!value_eq(fl_boxed_list_elem(a, i), fl_boxed_list_elem(b, i)))
      return false;
  return true;
}

static bool fl_dict_eq_any(Value a, Value b) {
  if (fl_boxed_dict_len(a) != fl_boxed_dict_len(b))
    return false;
  FlListStr *keys = fl_boxed_dict_keys(a);
  for (int64_t i = 0; i < keys->len; i++) {
    Value va, vb;
    if (!fl_boxed_dict_try_get(a, keys->data[i], &va))
      return false;
    if (!fl_boxed_dict_try_get(b, keys->data[i], &vb))
      return false;
    if (!value_eq(va, vb))
      return false;
  }
  return true;
}

static inline bool fl_list_eq_Dyn(FlListDyn *a, FlListDyn *b) {
  if (a->len != b->len)
    return false;
  for (int64_t i = 0; i < a->len; i++)
    if (!value_eq(a->data[i], b->data[i]))
      return false;
  return true;
}

static bool fl_boxed_eq(Value a, Value b) {
  /* identity implies equality (also makes `l == l` true for cyclic
     structures, like CPython); containers only — scalar bits must go
     through the normal path */
  if (fl_tag_is_container(a.tag) && a.tag == b.tag && a.as.p == b.as.p)
    return true;
  /* depth tripwire: cyclic structures would otherwise recurse forever */
  static int depth = 0;
  bool r;
  bool al = fl_tag_is_list(a.tag), bl = fl_tag_is_list(b.tag);
  if (++depth > FL_MAX_NEST) {
    --depth;
    fl_raise("RecursionError", "maximum nesting depth exceeded");
  }
  if (al != bl)
    r = false; /* list vs dict: never equal */
  else if (al)
    r = fl_list_eq_any(a, b);
  else
    r = fl_dict_eq_any(a, b);
  --depth;
  return r;
}

static bool fl_boxed_truthy(Value v) {
  switch (v.tag) {
  case FT_LIST_I64:
    return ((FlListI64 *)v.as.p)->len != 0;
  case FT_LIST_F64:
    return ((FlListF64 *)v.as.p)->len != 0;
  case FT_LIST_STR:
    return ((FlListStr *)v.as.p)->len != 0;
  case FT_LIST_DYN:
    return ((FlListDyn *)v.as.p)->len != 0;
  case FT_LIST_PAIR:
    return ((FlListListDyn *)v.as.p)->len != 0;
  case FT_DICT_I64:
    return ((FlDict_I64 *)v.as.p)->len != 0;
  case FT_DICT_F64:
    return ((FlDict_F64 *)v.as.p)->len != 0;
  case FT_DICT_STR:
    return ((FlDict_Str *)v.as.p)->len != 0;
  case FT_DICT_DYN:
    return ((FlDict_Dyn *)v.as.p)->len != 0;
  default:
    return false;
  }
}

static int64_t fl_boxed_len(Value v) {
  switch (v.tag) {
  case FT_LIST_I64:
    return ((FlListI64 *)v.as.p)->len;
  case FT_LIST_F64:
    return ((FlListF64 *)v.as.p)->len;
  case FT_LIST_STR:
    return ((FlListStr *)v.as.p)->len;
  case FT_LIST_DYN:
    return ((FlListDyn *)v.as.p)->len;
  case FT_LIST_PAIR:
    return ((FlListListDyn *)v.as.p)->len;
  case FT_DICT_I64:
    return ((FlDict_I64 *)v.as.p)->len;
  case FT_DICT_F64:
    return ((FlDict_F64 *)v.as.p)->len;
  case FT_DICT_STR:
    return ((FlDict_Str *)v.as.p)->len;
  case FT_DICT_DYN:
    return ((FlDict_Dyn *)v.as.p)->len;
  default:
    return 0;
  }
}

/* dynamic indexing/subscript through boxed containers */
static Value fl_boxed_index(Value v, int64_t i) {
  switch (v.tag) {
  case FT_LIST_I64:
    return v_i64(fl_index_I64((FlListI64 *)v.as.p, i));
  case FT_LIST_F64:
    return v_f64(fl_index_F64((FlListF64 *)v.as.p, i));
  case FT_LIST_STR:
    return v_str(fl_index_Str((FlListStr *)v.as.p, i));
  case FT_LIST_DYN:
    return fl_index_Dyn((FlListDyn *)v.as.p, i);
  case FT_LIST_PAIR:
    return v_list_DYN(fl_index_ListDyn((FlListListDyn *)v.as.p, i));
  default:
    fl_raise("TypeError", "list indices must be integers");
  }
}

static Value fl_boxed_dict_get(Value v, const char *k) {
  switch (v.tag) {
  case FT_DICT_I64:
    return v_i64(dict_I64_get((FlDict_I64 *)v.as.p, k));
  case FT_DICT_F64:
    return v_f64(dict_F64_get((FlDict_F64 *)v.as.p, k));
  case FT_DICT_STR:
    return v_str(dict_Str_get((FlDict_Str *)v.as.p, k));
  case FT_DICT_DYN:
    return dict_Dyn_get((FlDict_Dyn *)v.as.p, k);
  default:
    fl_raise("TypeError", "not a dict");
  }
}

static inline Value value_dict_get(Value v, const char *k) {
  if (fl_tag_is_container(v.tag))
    return fl_boxed_dict_get(v, k);
  fl_raise("TypeError", "not a dict");
}

static const char *fl_tag_name(FlTag t) {
  switch (t) {
  case FT_I64:
    return "int";
  case FT_F64:
    return "float";
  case FT_BOOL:
    return "bool";
  case FT_STR:
    return "str";
  default:
    return "container";
  }
}

/* Storing through a dynamic Value into a homogeneous typed container:
   the value must be of (or numerically coercible to) the element type. */
static inline void fl_check_storable(Value v, FlTag want, const char *ctx) {
  bool ok;
  if (want == FT_STR)
    ok = (v.tag == FT_STR);
  else
    ok = (v.tag == FT_I64 || v.tag == FT_F64 || v.tag == FT_BOOL);
  if (!ok) {
    FL_RAISE_FMT("TypeError", "cannot store %s in %s", fl_tag_name(v.tag), ctx);
  }
}

static inline void value_dict_set(Value v, const char *k, Value val) {
  switch (v.tag) {
  case FT_DICT_I64:
    fl_check_storable(val, FT_I64, "dict[int]");
    dict_I64_set((FlDict_I64 *)v.as.p, k, v_to_i64(val));
    return;
  case FT_DICT_F64:
    fl_check_storable(val, FT_F64, "dict[float]");
    dict_F64_set((FlDict_F64 *)v.as.p, k, v_to_f64(val));
    return;
  case FT_DICT_STR:
    fl_check_storable(val, FT_STR, "dict[str]");
    dict_Str_set((FlDict_Str *)v.as.p, k, val.as.s);
    return;
  case FT_DICT_DYN:
    dict_Dyn_set((FlDict_Dyn *)v.as.p, k, val);
    return;
  default:
    fl_raise("TypeError", "not a dict");
  }
}

static inline void value_list_set(Value v, int64_t i, Value val) {
  switch (v.tag) {
  case FT_LIST_I64:
    fl_check_storable(val, FT_I64, "list[int]");
    fl_set_I64((FlListI64 *)v.as.p, i, v_to_i64(val));
    return;
  case FT_LIST_F64:
    fl_check_storable(val, FT_F64, "list[float]");
    fl_set_F64((FlListF64 *)v.as.p, i, v_to_f64(val));
    return;
  case FT_LIST_STR:
    fl_check_storable(val, FT_STR, "list[str]");
    fl_set_Str((FlListStr *)v.as.p, i, val.as.s);
    return;
  case FT_LIST_DYN:
    fl_set_Dyn((FlListDyn *)v.as.p, i, val);
    return;
  case FT_LIST_PAIR: {
    FlListListDyn *l = (FlListListDyn *)v.as.p;
    int64_t orig = i;
    if (i < 0)
      i += l->len;
    if (i < 0 || i >= l->len) {
      FL_RAISE_FMT("IndexError",
                   "index %" PRId64 " out of range (len %" PRId64 ")", orig,
                   l->len);
    }
    l->data[i] = v_unbox_list_DYN(val);
    return;
  }
  default:
    fl_raise("TypeError", "not a list");
  }
}

/* dynamic append: `expr.append(v)` where expr is a boxed Value */
static inline void value_list_append(Value l, Value v) {
  switch (l.tag) {
  case FT_LIST_I64:
    fl_check_storable(v, FT_I64, "list[int]");
    list_I64_append((FlListI64 *)l.as.p, v_to_i64(v));
    return;
  case FT_LIST_F64:
    fl_check_storable(v, FT_F64, "list[float]");
    list_F64_append((FlListF64 *)l.as.p, v_to_f64(v));
    return;
  case FT_LIST_STR:
    fl_check_storable(v, FT_STR, "list[str]");
    list_Str_append((FlListStr *)l.as.p, v.as.s);
    return;
  case FT_LIST_DYN:
    list_Dyn_append((FlListDyn *)l.as.p, v);
    return;
  case FT_LIST_PAIR:
    if (v.tag != FT_LIST_DYN)
      fl_raise("TypeError", "can only append a list to a list of pairs");
    list_ListDyn_append((FlListListDyn *)l.as.p, (FlListDyn *)v.as.p);
    return;
  default:
    fl_raise("TypeError", "not a list");
  }
}

/* fully dynamic subscript: obj[key] where both are Values */
static Value value_subscript(Value obj, Value key) {
  if (!fl_tag_is_container(obj.tag))
    fl_raise("TypeError", "not subscriptable");
  if (fl_tag_is_list(obj.tag)) {
    if (key.tag == FT_I64)
      return fl_boxed_index(obj, key.as.i);
    if (key.tag == FT_BOOL)
      return fl_boxed_index(obj, key.as.b ? 1 : 0);
    fl_raise("TypeError", "list indices must be integers");
  }
  if (key.tag == FT_STR)
    return fl_boxed_dict_get(obj, key.as.s);
  fl_raise("TypeError", "dict keys must be strings");
}

static void value_setitem(Value obj, Value key, Value val) {
  if (!fl_tag_is_container(obj.tag))
    fl_raise("TypeError", "not subscriptable");
  if (fl_tag_is_list(obj.tag)) {
    int64_t i;
    if (key.tag == FT_I64)
      i = key.as.i;
    else if (key.tag == FT_BOOL)
      i = key.as.b ? 1 : 0;
    else
      fl_raise("TypeError", "list indices must be integers");
    value_list_set(obj, i, val);
    return;
  }
  if (key.tag == FT_STR) {
    value_dict_set(obj, key.as.s, val);
    return;
  }
  fl_raise("TypeError", "dict keys must be strings");
}

static bool fl_boxed_contains(Value hay, Value needle) {
  int64_t i;
  switch (hay.tag) {
  case FT_LIST_I64: {
    FlListI64 *l = (FlListI64 *)hay.as.p;
    for (i = 0; i < l->len; i++)
      if (value_eq(v_i64(l->data[i]), needle))
        return true;
    return false;
  }
  case FT_LIST_F64: {
    FlListF64 *l = (FlListF64 *)hay.as.p;
    for (i = 0; i < l->len; i++)
      if (value_eq(v_f64(l->data[i]), needle))
        return true;
    return false;
  }
  case FT_LIST_STR: {
    FlListStr *l = (FlListStr *)hay.as.p;
    for (i = 0; i < l->len; i++)
      if (value_eq(v_str(l->data[i]), needle))
        return true;
    return false;
  }
  case FT_LIST_DYN: {
    FlListDyn *l = (FlListDyn *)hay.as.p;
    for (i = 0; i < l->len; i++)
      if (value_eq(l->data[i], needle))
        return true;
    return false;
  }
  case FT_LIST_PAIR: {
    FlListListDyn *l = (FlListListDyn *)hay.as.p;
    if (needle.tag != FT_LIST_DYN)
      return false;
    FlListDyn *p = (FlListDyn *)needle.as.p;
    for (i = 0; i < l->len; i++)
      if (fl_list_eq_Dyn(l->data[i], p))
        return true;
    return false;
  }
  case FT_DICT_I64:
    return needle.tag == FT_STR &&
           dict_I64_has((FlDict_I64 *)hay.as.p, needle.as.s);
  case FT_DICT_F64:
    return needle.tag == FT_STR &&
           dict_F64_has((FlDict_F64 *)hay.as.p, needle.as.s);
  case FT_DICT_STR:
    return needle.tag == FT_STR &&
           dict_Str_has((FlDict_Str *)hay.as.p, needle.as.s);
  case FT_DICT_DYN:
    return needle.tag == FT_STR &&
           dict_Dyn_has((FlDict_Dyn *)hay.as.p, needle.as.s);
  default:
    return false;
  }
}

/* ------------------------------------------------------------------ */
/* storage converters: typed list/dict -> their Dyn (Value) forms.     */
/* Used when type inference widens a variable across storage classes,  */
/* e.g. x = [1] later joined with ["a"] becomes ("list", DYN). The     */
/* copy is one-way (typed -> dyn); dyn -> typed is a checked unbox.    */
/* ------------------------------------------------------------------ */

static inline FlListDyn *fl_list_I64_to_Dyn(FlListI64 *l) {
  FlListDyn *out = list_Dyn_new();
  for (int64_t i = 0; i < l->len; i++)
    list_Dyn_append(out, v_i64(l->data[i]));
  return out;
}
static inline FlListDyn *fl_list_F64_to_Dyn(FlListF64 *l) {
  FlListDyn *out = list_Dyn_new();
  for (int64_t i = 0; i < l->len; i++)
    list_Dyn_append(out, v_f64(l->data[i]));
  return out;
}
static inline FlListDyn *fl_list_Str_to_Dyn(FlListStr *l) {
  FlListDyn *out = list_Dyn_new();
  for (int64_t i = 0; i < l->len; i++)
    list_Dyn_append(out, v_str(l->data[i]));
  return out;
}
static inline FlListDyn *fl_list_PAIR_to_Dyn(FlListListDyn *l) {
  FlListDyn *out = list_Dyn_new();
  for (int64_t i = 0; i < l->len; i++)
    list_Dyn_append(out, v_list_DYN(l->data[i]));
  return out;
}
static inline FlDict_Dyn *fl_dict_I64_to_Dyn(FlDict_I64 *d) {
  FlDict_Dyn *out = dict_Dyn_new();
  for (int64_t i = 0; i < d->cap; i++)
    if (d->tab[i].used)
      dict_Dyn_set(out, d->tab[i].key, v_i64(d->tab[i].val));
  return out;
}
static inline FlDict_Dyn *fl_dict_F64_to_Dyn(FlDict_F64 *d) {
  FlDict_Dyn *out = dict_Dyn_new();
  for (int64_t i = 0; i < d->cap; i++)
    if (d->tab[i].used)
      dict_Dyn_set(out, d->tab[i].key, v_f64(d->tab[i].val));
  return out;
}
static inline FlDict_Dyn *fl_dict_Str_to_Dyn(FlDict_Str *d) {
  FlDict_Dyn *out = dict_Dyn_new();
  for (int64_t i = 0; i < d->cap; i++)
    if (d->tab[i].used)
      dict_Dyn_set(out, d->tab[i].key, v_str(d->tab[i].val));
  return out;
}

/* element assignment for the enumerate()/zip() pair-list representation */
static inline void fl_set_ListDyn(FlListListDyn *l, int64_t i, FlListDyn *v) {
  int64_t orig = i;
  if (i < 0)
    i += l->len;
  if (i < 0 || i >= l->len) {
    FL_RAISE_FMT("IndexError",
                 "index %" PRId64 " out of range (len %" PRId64 ")", orig,
                 l->len);
  }
  l->data[i] = v;
}

static inline bool fl_contains_ListDyn(FlListListDyn *l, Value v) {
  if (v.tag != FT_LIST_DYN)
    return false;
  FlListDyn *p = (FlListDyn *)v.as.p;
  for (int64_t i = 0; i < l->len; i++)
    if (fl_list_eq_Dyn(l->data[i], p))
      return true;
  return false;
}

/* dynamic iteration: `for v in <dyn>` dispatches on the boxed list */
static int64_t fl_dyn_iter_len(Value v) {
  if (!fl_tag_is_list(v.tag))
    fl_raise("TypeError", "not iterable");
  return fl_boxed_list_len(v);
}
static Value fl_dyn_iter_elem(Value v, int64_t i) {
  if (!fl_tag_is_list(v.tag))
    fl_raise("TypeError", "not iterable");
  return fl_boxed_index(v, i);
}

/* f-string interpolation for the pair-list representation */
static inline char *fl_str_list_PAIR(FlListListDyn *l) {
  FlBuf b;
  flb_init(&b);
  flb_putc(&b, '[');
  for (int64_t i = 0; i < l->len; i++) {
    if (i)
      flb_puts(&b, ", ");
    flb_putc(&b, '[');
    FlListDyn *p = l->data[i];
    for (int64_t j = 0; j < p->len; j++) {
      if (j)
        flb_puts(&b, ", ");
      char *s = fl_str_value(p->data[j]);
      flb_puts(&b, s);
      free(s);
    }
    flb_putc(&b, ']');
  }
  flb_putc(&b, ']');
  return flb_done(&b);
}

#endif /* FLARE_RT_H */
