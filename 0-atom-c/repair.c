/*
 * repair.c — Ever / Tapestry, the self-healing registry
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

/* strdup is POSIX, not C99: without this, -std=c99 on glibc leaves it
   undeclared, it defaults to int, and the returned pointer is truncated. */
#define _POSIX_C_SOURCE 200809L
#include "repair.h"
#include "tapestry.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Appends the UTF-8 encoding of one code point. */
static size_t put_utf8(char *out, uint32_t cp) {
    if (cp < 0x80)    { out[0] = (char)cp; return 1; }
    if (cp < 0x800)   { out[0] = (char)(0xC0 | (cp >> 6));
                        out[1] = (char)(0x80 | (cp & 0x3F)); return 2; }
    out[0] = (char)(0xE0 | (cp >> 12));
    out[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
    out[2] = (char)(0x80 | (cp & 0x3F));
    return 3;
}

/* The value of a JSON string field, with its escapes decoded the way the
   Java and Python readers decode them. NULL when the field is absent, or
   when the string is not terminated. */
static char *json_extract(const char *line, const char *key) {
    char search[64];
    snprintf(search, sizeof search, "\"%s\": \"", key);
    const char *p = strstr(line, search);
    if (!p) return NULL;
    p += strlen(search);
    char *out = malloc(strlen(p) * 3 + 4);      /* a \uXXXX escape is 3 bytes out */
    if (!out) return NULL;
    size_t n = 0;
    while (*p && *p != '"') {
        if (*p != '\\') { out[n++] = *p++; continue; }
        p++;
        switch (*p) {
            case 'n': out[n++] = '\n'; break;
            case 't': out[n++] = '\t'; break;
            case 'r': out[n++] = '\r'; break;
            case 'b': out[n++] = '\b'; break;
            case 'f': out[n++] = '\f'; break;
            case 'u': {
                unsigned cp = 0;
                for (int i = 1; i <= 4; i++) {
                    char c = p[i];
                    int v = (c >= '0' && c <= '9') ? c - '0'
                          : (c >= 'a' && c <= 'f') ? c - 'a' + 10
                          : (c >= 'A' && c <= 'F') ? c - 'A' + 10 : -1;
                    if (v < 0) { free(out); return NULL; }
                    cp = cp * 16 + (unsigned)v;
                }
                n += put_utf8(out + n, cp);
                p += 4;
                break;
            }
            case '\0': free(out); return NULL;
            default:   out[n++] = *p; break;     /* \" \\ \/ */
        }
        p++;
    }
    if (*p != '"') { free(out); return NULL; }   /* unterminated */
    out[n] = '\0';
    return out;
}

/* One line of any length, without the newline. NULL at end of file. */
static char *read_line(FILE *f) {
    size_t cap = 256, n = 0;
    char *buf = malloc(cap);
    if (!buf) return NULL;
    int c;
    while ((c = fgetc(f)) != EOF && c != '\n') {
        if (n + 1 >= cap) {
            char *nb = realloc(buf, cap * 2);
            if (!nb) { free(buf); return NULL; }
            buf = nb;
            cap *= 2;
        }
        buf[n++] = (char)c;
    }
    if (c == EOF && n == 0) { free(buf); return NULL; }
    buf[n] = '\0';
    return buf;
}

static int32_t json_int(const char *line, const char *key, int32_t fallback) {
    char search[64];
    snprintf(search, sizeof search, "\"%s\": ", key);
    const char *start = strstr(line, search);
    if (!start) return fallback;
    return (int32_t)strtol(start + strlen(search), NULL, 10);
}

EvRepairRegistry *ev_repair_registry_new(const char *path) {
    EvRepairRegistry *reg = calloc(1, sizeof(EvRepairRegistry));
    if (!reg) return NULL;
    reg->archive_path = path ? strdup(path) : NULL;
    reg->cap = 16;
    reg->repairs = malloc(sizeof(EvRepair *) * reg->cap);
    if (!reg->repairs) { free(reg); return NULL; }

    if (!path) return reg;

    FILE *f = fopen(path, "r");
    if (!f) return reg;

    char *line;
    while ((line = read_line(f)) != NULL) {
        if (line[0] == '\0') { free(line); continue; }
        char *fail = json_extract(line, "failure_text");
        char *fix = json_extract(line, "fixture_text");
        char *strat = json_extract(line, "strategy");   /* NULL: wildcard */
        if (!fail || !fix) {
            free(fail); free(fix); free(strat); free(line);
            continue;                                   /* malformed: skipped, as in Python */
        }

        if (reg->count >= reg->cap) {
            int32_t nc = reg->cap * 2;
            EvRepair **nr = realloc(reg->repairs, sizeof(EvRepair *) * nc);
            if (!nr) { free(fail); free(fix); free(strat); free(line); break; }
            reg->repairs = nr;
            reg->cap = nc;
        }

        EvRepair *r = malloc(sizeof(EvRepair));
        if (!r) { free(fail); free(fix); free(strat); free(line); break; }
        r->failure_text = fail;
        r->fixture_text = fix;
        r->kind = json_int(line, "kind", 0);
        r->strategy = strat;
        reg->repairs[reg->count++] = r;
        free(line);
    }
    fclose(f);
    return reg;
}

void ev_repair_registry_free(EvRepairRegistry *reg) {
    if (!reg) return;
    for (int i = 0; i < reg->count; i++) {
        free(reg->repairs[i]->failure_text);
        free(reg->repairs[i]->fixture_text);
        free(reg->repairs[i]->strategy);
        free(reg->repairs[i]);
    }
    free(reg->repairs);
    free(reg->archive_path);
    free(reg);
}

const char *ev_repair_find(EvRepairRegistry *reg, const char *reason,
                           const char *strategy, int32_t *kind_out) {
    if (!reg || !reason) return NULL;
    /* Same rule as repair.py: a repair tied to this strategy first, then the
       first wildcard. A NULL strategy (not text) matches wildcards only. */
    const EvRepair *exact = NULL, *wild = NULL;
    for (int i = 0; i < reg->count; i++) {
        const EvRepair *r = reg->repairs[i];
        if (strcmp(r->failure_text, reason) != 0) continue;
        if (!r->strategy) {
            if (!wild) wild = r;
        } else if (strategy && !exact && strcmp(r->strategy, strategy) == 0) {
            exact = r;
        }
    }
    const EvRepair *chosen = exact ? exact : wild;
    if (!chosen) return NULL;
    if (kind_out) *kind_out = chosen->kind;
    return chosen->fixture_text;
}

/* The fixture grammar, the same as EverRepair.parseFixture in Java:
     -?\d+                           an integer
     -?\d+\.\d+([eE][+-]?\d+)?       a real
     -?\d+[eE][+-]?\d+               a real
   Nothing else is a number: strtod's inf, nan and hex are not fixtures. */
static int fixture_is_int(const char *s) {
    if (*s == '-') s++;
    if (!*s) return 0;
    for (; *s; s++) if (*s < '0' || *s > '9') return 0;
    return 1;
}

static int fixture_is_real(const char *s) {
    if (*s == '-') s++;
    const char *d = s;
    while (*s >= '0' && *s <= '9') s++;
    if (s == d) return 0;
    if (*s == '.') {
        s++;
        const char *f = s;
        while (*s >= '0' && *s <= '9') s++;
        if (s == f) return 0;
    } else if (*s != 'e' && *s != 'E') {
        return 0;
    }
    if (*s == 'e' || *s == 'E') {
        s++;
        if (*s == '+' || *s == '-') s++;
        const char *x = s;
        while (*s >= '0' && *s <= '9') s++;
        if (s == x) return 0;
    }
    return *s == '\0';
}

static int fixture_space(char c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}

/* Reads a fixture as a value: true, false, z, an integer, a real, or a
   double-quoted text. Text that is not a value reads as void, which the
   repair branch reports as FAILED. */
EValue ev_parse_constant(const char *s) {
    if (!s) return ev_void();
    while (fixture_space(*s)) s++;
    size_t n = strlen(s);
    while (n > 0 && fixture_space(s[n - 1])) n--;
    if (n >= E_TEXT_MAX) return ev_void();
    char t[E_TEXT_MAX];
    memcpy(t, s, n);
    t[n] = '\0';

    if (strcmp(t, "true") == 0) return ev_bool(1);
    if (strcmp(t, "false") == 0) return ev_bool(0);
    if (strcmp(t, "z") == 0) return ev_void();
    if (n >= 2 && t[0] == '"' && t[n - 1] == '"') {
        char inner[E_TEXT_MAX];
        size_t len = n - 2;
        memcpy(inner, t + 1, len);
        inner[len] = '\0';
        return ev_text(inner);
    }
    if (fixture_is_int(t)) {
        errno = 0;
        long long v = strtoll(t, NULL, 10);
        if (errno != 0) return ev_void();
        return ev_int((int64_t)v);
    }
    if (fixture_is_real(t)) return ev_real(strtod(t, NULL));
    return ev_void();
}
