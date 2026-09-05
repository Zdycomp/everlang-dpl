/*
 * tapestry.c — Ever / Tapestry, the atom and the six A-operators
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#include "tapestry.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <math.h>

/* ─────────────────────────────────────────────
 * helpers
 * ───────────────────────────────────────────── */

static int64_t now_ms(void) { return (int64_t)time(NULL) * 1000; }

static void set_str(char *dst, size_t cap, const char *src) {
    if (!src) { dst[0] = '\0'; return; }
    size_t n = strlen(src);
    if (n >= cap) n = cap - 1;
    memcpy(dst, src, n);
    dst[n] = '\0';
}

static e_particle blank(void) {
    e_particle p;
    memset(&p, 0, sizeof p);
    p.archive_id = -1;
    p.born_ms    = now_ms();
    p.lang       = E_LANG_EVER;
    p.type       = E_TYPE_VOID;
    p.defect     = E_DEFECT_NONE;
    p.anchor_id  = 0;
    return p;
}

/* ─────────────────────────────────────────────
 * constructors
 * ───────────────────────────────────────────── */

e_particle e_z(const char *ident, const char *reason) {
    return e_z_defect(ident, reason, E_DEFECT_UNBOUND);
}

e_particle e_z_defect(const char *ident, const char *reason, e_defect d) {
    e_particle p = blank();
    p.state      = E_STATE_Z;
    p.defect     = d;
    p.confidence = E_ZERO;
    p.lo = p.hi  = E_ZERO;
    set_str(p.ident,  E_IDENT_MAX,  ident);
    set_str(p.reason, E_REASON_MAX, reason ? reason : "unverified");
    return p;
}

/* A value with a confidence. Degree outside 1..256 is not laundered. */
static e_particle valued(const char *ident, int16_t conf, e_lang lang) {
    e_particle p = blank();
    p.lang = lang;
    if (conf <= E_ZERO) {
        p.state = E_STATE_Z;
        p.defect = E_DEFECT_UNBOUND;
        p.confidence = E_ZERO;
        set_str(p.reason, E_REASON_MAX, "confidence collapsed to zero");
    } else if (conf >= E_CERTAIN) {
        p.state = E_STATE_CERTAIN;
        p.confidence = E_CERTAIN;
    } else {
        p.state = E_STATE_CONFIDENT;
        p.confidence = conf;
    }
    p.lo = p.hi = p.confidence;
    set_str(p.ident, E_IDENT_MAX, ident);
    return p;
}

e_particle e_int(const char *ident, int64_t v, int16_t conf, e_lang lang) {
    e_particle p = valued(ident, conf, lang);
    p.type = E_TYPE_INT;
    p.value.as_int = v;
    return p;
}

e_particle e_real(const char *ident, double v, int16_t conf, e_lang lang) {
    e_particle p = valued(ident, conf, lang);
    p.type = E_TYPE_REAL;
    p.value.as_real = v;
    return p;
}

e_particle e_bool(const char *ident, int v, int16_t conf, e_lang lang) {
    e_particle p = valued(ident, conf, lang);
    p.type = E_TYPE_BOOL;
    p.value.as_bool = v ? 1 : 0;
    return p;
}

e_particle e_text(const char *ident, const char *v, int16_t conf, e_lang lang) {
    e_particle p = valued(ident, conf, lang);
    p.type = E_TYPE_TEXT;
    set_str(p.text, E_TEXT_MAX, v);
    return p;
}

e_particle e_equivalence(const char *ident, int16_t lo, int16_t hi, e_lang lang) {
    if (lo > hi) { int16_t t = lo; lo = hi; hi = t; }
    e_particle p = blank();
    p.state      = E_STATE_EQUIV;
    p.type       = E_TYPE_INT;
    p.lang       = lang;
    p.lo = lo; p.hi = hi;
    p.confidence = (int16_t)((lo + hi) / 2);
    p.value.as_int = p.confidence;
    set_str(p.ident, E_IDENT_MAX, ident);
    return p;
}

e_particle e_expression(const char *ident, e_type t, e_lang lang) {
    e_particle p = blank();
    p.state      = E_STATE_EXPRESS;
    p.type       = t;
    p.lang       = lang;
    p.confidence = E_ZERO;
    set_str(p.ident,  E_IDENT_MAX, ident);
    set_str(p.reason, E_REASON_MAX, "shape bound, value pending");
    return p;
}

e_particle e_error(const char *ident, const char *reason, e_defect d, int16_t at) {
    e_particle p = blank();
    p.state      = E_STATE_ERROR;
    p.defect     = d;
    p.confidence = E_ZERO;
    p.lo = p.hi  = at;
    set_str(p.ident,  E_IDENT_MAX,  ident);
    set_str(p.reason, E_REASON_MAX, reason ? reason : "unspecified failure");
    return p;
}

/* ─────────────────────────────────────────────
 * predicates
 * ───────────────────────────────────────────── */

int e_is_z(const e_particle *p) { return p->state == E_STATE_Z; }

int e_is_cleared(const e_particle *p) {
    if (p->state == E_STATE_Z || p->state == E_STATE_ERROR ||
        p->state == E_STATE_ABSENT) return 0;
    return p->confidence > E_ZERO;
}

int e_can_execute(const e_particle *p) {
    return e_is_cleared(p) && p->confidence >= E_EXECUTE_FLOOR;
}

int e_has_value(const e_particle *p) {
    if (p->type == E_TYPE_VOID) return 0;
    if (p->state == E_STATE_EXPRESS) return 0;
    return e_is_cleared(p);
}

int e_is_anchored(const e_particle *p) { return p->anchor_id != 0; }

int e_width(const e_particle *p) { return (int)(p->hi - p->lo); }

e_pi_status e_pi_check(const e_particle *p) {
    int w = e_width(p);
    if (w > E_PI_WIDTH_WARN)      return E_PI_APPROACHING_Z;
    if (w > E_PI_WIDTH_ENUMERATE) return E_PI_ENUMERATE;
    return E_PI_ACCEPTABLE;
}

/* ═════════════════════════════════════════════
 * A-OPERATORS
 * ═════════════════════════════════════════════ */

/* ── ANY ──────────────────────────────────────
 * Lift a literal from any language into a particle. Intake confidence is
 * deliberately below the execute floor: parsing a literal tells you its
 * shape, not that it is right. It must Ascend to become executable.
 */
e_particle a_any(const char *ident, const char *literal, e_lang from) {
    if (!literal || !*literal)
        return e_z_defect(ident, "no literal to lift", E_DEFECT_UNBOUND);

    const char *s = literal;
    while (*s == ' ' || *s == '\t') s++;

    /* the language's own words for nothing all lift to Z, not to a value */
    if (!strcmp(s, "null") || !strcmp(s, "nil") || !strcmp(s, "None") ||
        !strcmp(s, "NULL") || !strcmp(s, "undefined") || !strcmp(s, "nullptr"))
        return e_z_defect(ident, "source language expressed nothing",
                          E_DEFECT_UNBOUND);

    if (!strcmp(s, "true") || !strcmp(s, "True") || !strcmp(s, "TRUE"))
        return e_bool(ident, 1, 120, from);
    if (!strcmp(s, "false") || !strcmp(s, "False") || !strcmp(s, "FALSE"))
        return e_bool(ident, 0, 120, from);

    /* quoted text */
    if (*s == '"' || *s == '\'') {
        char q = *s;
        size_t len = strlen(s);
        if (len >= 2 && s[len - 1] == q) {
            char buf[E_TEXT_MAX];
            size_t n = len - 2;
            if (n >= E_TEXT_MAX) n = E_TEXT_MAX - 1;
            memcpy(buf, s + 1, n);
            buf[n] = '\0';
            return e_text(ident, buf, 120, from);
        }
        return e_z_defect(ident, "unterminated string literal",
                          E_DEFECT_UNBOUNDED);
    }

    /* numeric */
    char *end = NULL;
    long long iv = strtoll(s, &end, 10);
    if (end && *end == '\0' && end != s)
        return e_int(ident, (int64_t)iv, 120, from);

    end = NULL;
    double dv = strtod(s, &end);
    if (end && *end == '\0' && end != s)
        return e_real(ident, dv, 120, from);

    /* anything else is carried as foreign rather than guessed at */
    e_particle p = e_text(ident, s, 100, from);
    p.type = E_TYPE_FOREIGN;
    set_str(p.reason, E_REASON_MAX, "lifted as foreign, shape unresolved");
    return p;
}

/* ── ASSIMILATE ───────────────────────────────
 * Carry a particle into another language. Z does not cross. An anchored
 * particle crosses without loss; an unanchored one pays one confidence
 * per crossing, so drift is visible instead of silent.
 */
e_particle a_assimilate(const e_particle *p, e_lang to) {
    if (e_is_z(p))
        return e_z_defect(p->ident, "Z does not translate", p->defect);

    if (p->state == E_STATE_ERROR)
        return e_z_defect(p->ident, "misbound particle does not translate",
                          E_DEFECT_MISBOUND);

    if (p->lang == (int32_t)to) return *p;

    e_particle q = *p;
    q.lang       = to;
    q.born_ms    = now_ms();
    q.archive_id = -1;

    if (!e_is_anchored(p)) {
        if (q.confidence > 1) q.confidence -= 1;
        q.lo = q.hi = q.confidence;
        snprintf(q.reason, E_REASON_MAX,
                 "assimilated %s to %s, unanchored, -1 confidence",
                 e_lang_name(p->lang), e_lang_name(to));
    } else {
        snprintf(q.reason, E_REASON_MAX,
                 "assimilated %s to %s, anchor %u held",
                 e_lang_name(p->lang), e_lang_name(to), p->anchor_id);
    }
    return q;
}

/* ── ANCHOR ───────────────────────────────────
 * Pin an identity that survives translation. Refuses anything not
 * cleared: an anchor on an unverified binding propagates a lie into
 * every language it touches.
 */
e_particle a_anchor(const e_particle *p, uint32_t anchor_id) {
    if (anchor_id == 0)
        return e_z_defect(p->ident, "anchor id zero is reserved for unanchored",
                          E_DEFECT_UNBOUND);

    if (!e_is_cleared(p))
        return e_z_defect(p->ident, "cannot anchor an uncleared binding",
                          p->defect ? p->defect : E_DEFECT_UNBOUND);

    e_particle q = *p;
    q.anchor_id = anchor_id;
    q.state     = E_STATE_ANCHORED;
    snprintf(q.reason, E_REASON_MAX, "anchored %u at confidence %d",
             anchor_id, (int)q.confidence);
    return q;
}

/* ── ASCEND ───────────────────────────────────
 * The only path upward. One observation never lifts a binding; three
 * aligned ones do. Evidence that disagrees resets the count rather than
 * averaging the disagreement away.
 */
e_particle a_ascend(const e_particle *p, const e_particle *evidence) {
    if (e_is_z(p))
        return e_z_defect(p->ident, "Z cannot ascend; it must be resolved",
                          p->defect);

    if (!e_is_cleared(evidence))
        return *p;   /* uncleared evidence is not evidence */

    e_particle q = *p;

    /* aligned means the evidence sits within the pi-squared band */
    int gap = abs((int)evidence->confidence - (int)p->confidence);
    if (gap > E_PI_WIDTH_ENUMERATE) {
        q.ascend_points = 0;
        snprintf(q.reason, E_REASON_MAX,
                 "evidence disagreed by %d, ascent reset", gap);
        return q;
    }

    q.ascend_points = (uint8_t)(p->ascend_points + 1);

    if (q.ascend_points < E_ASCEND_POINTS) {
        snprintf(q.reason, E_REASON_MAX, "ascending: %u of %d points",
                 q.ascend_points, E_ASCEND_POINTS);
        return q;
    }

    /* three aligned points. Excel the evidence in and advance a generation. */
    q.confidence    = e_excel_formula(p->confidence, evidence->confidence);
    q.lo = q.hi     = q.confidence;
    q.ascend_points = 0;
    q.generation    = (uint8_t)(p->generation + 1);
    q.state = (q.confidence >= E_CERTAIN) ? E_STATE_CERTAIN : E_STATE_EVOLVED;
    snprintf(q.reason, E_REASON_MAX,
             "ascended on %d aligned points to %d, generation %u",
             E_ASCEND_POINTS, (int)q.confidence, q.generation);
    return q;
}

/* ── APPLY2ALL ────────────────────────────────
 * Broadcast a transformation across a corpus. A Z encountered mid-set
 * halts the broadcast and reports where, rather than skipping quietly.
 */
int a_apply2all(e_particle *set, int n, a_transform fn, int *halted_at) {
    if (halted_at) *halted_at = -1;
    int done = 0;
    for (int i = 0; i < n; i++) {
        if (e_is_z(&set[i])) {
            if (halted_at) *halted_at = i;
            return done;
        }
        set[i] = fn(&set[i]);
        done++;
    }
    return done;
}

/* ── AUTO-DIDACT ──────────────────────────────
 * Derive a rule from the corpus's own history. Requires three aligned
 * observations, the same bar Ascend uses — the system does not get to
 * learn from less evidence than it would accept from anyone else.
 */
e_particle a_autodidact(const e_particle *history, int n, const char *about) {
    if (n < E_ASCEND_POINTS)
        return e_z_defect(about, "history too short to derive a rule",
                          E_DEFECT_UNBOUND);

    int cleared = 0, lo = E_CERTAIN, hi = E_ZERO;
    long sum = 0;
    e_defect common = E_DEFECT_NONE;
    int defect_count = 0;

    for (int i = 0; i < n; i++) {
        if (!e_is_cleared(&history[i])) {
            if (history[i].defect != E_DEFECT_NONE) {
                if (common == E_DEFECT_NONE) common = history[i].defect;
                if (history[i].defect == (int32_t)common) defect_count++;
            }
            continue;
        }
        cleared++;
        sum += history[i].confidence;
        if (history[i].confidence < lo) lo = history[i].confidence;
        if (history[i].confidence > hi) hi = history[i].confidence;
    }

    /* a recurring defect is itself a rule, and the more useful kind */
    if (defect_count >= E_ASCEND_POINTS) {
        e_particle r = e_text(about, e_defect_name(common), 180, E_LANG_EVER);
        snprintf(r.reason, E_REASON_MAX,
                 "derived: %s recurs %d times in history",
                 e_defect_name(common), defect_count);
        return r;
    }

    if (cleared < E_ASCEND_POINTS)
        return e_z_defect(about, "too few cleared observations to derive",
                          E_DEFECT_UNBOUND);

    int mean  = (int)(sum / cleared);
    int spread = hi - lo;

    if (spread > E_PI_WIDTH_WARN)
        return e_z_defect(about, "history too scattered to derive a rule",
                          E_DEFECT_UNBOUNDED);

    e_particle rule = e_int(about, mean,
                            (int16_t)(spread <= E_PI_WIDTH_ENUMERATE ? 200 : 150),
                            E_LANG_EVER);
    rule.lo = (int16_t)lo;
    rule.hi = (int16_t)hi;
    snprintf(rule.reason, E_REASON_MAX,
             "derived from %d observations, mean %d, spread %d",
             cleared, mean, spread);
    return rule;
}

/* ─────────────────────────────────────────────
 * propagation and arithmetic
 * ───────────────────────────────────────────── */

e_particle e_carry(const e_particle *src, const char *new_ident) {
    if (src->state == E_STATE_Z)
        return e_z_defect(new_ident, src->reason, src->defect);
    if (src->state == E_STATE_ERROR)
        return e_z_defect(new_ident, "upstream error", E_DEFECT_MISBOUND);
    if (src->state == E_STATE_ABSENT)
        return e_z_defect(new_ident, "upstream absent", E_DEFECT_UNBOUND);

    e_particle p = *src;
    set_str(p.ident, E_IDENT_MAX, new_ident);
    p.archive_id = -1;
    p.born_ms    = now_ms();
    return p;
}

e_particle e_cap(const e_particle *src, int16_t ceiling) {
    if (ceiling <= E_ZERO)
        return e_z_defect(src->ident, "capped to zero", E_DEFECT_UNBOUND);
    e_particle p = *src;
    if (p.confidence > ceiling) {
        p.confidence = ceiling;
        if (p.state == E_STATE_CERTAIN) p.state = E_STATE_CONFIDENT;
    }
    if (p.hi > ceiling) p.hi = ceiling;
    if (p.lo > ceiling) p.lo = ceiling;
    return p;
}

int16_t e_excel_formula(int16_t a, int16_t b) {
    /* Excel is multiplicative uncertainty: u_result = u_a * u_b.
     * A product of non-zero ignorances is never zero, so combination can
     * approach Certain but never attain it. The integer scale used to
     * round the last fraction away and hand back 256, which manufactured
     * Certain out of accumulated evidence and broke the rule that Certain
     * is earned at runtime. Combination now caps one short. */
    int32_t v = (int32_t)a + (int32_t)b - (((int32_t)a * (int32_t)b) / E_CERTAIN);
    if (a >= E_CERTAIN && b >= E_CERTAIN) return E_CERTAIN;  /* both verified */
    if (v >= E_CERTAIN) v = E_CERTAIN - 1;
    if (v < E_ZERO)     v = E_ZERO;
    return (int16_t)v;
}

int16_t e_phi_equalize(int16_t value, int16_t set_mean) {
    if (set_mean <= 0) return value;
    int32_t hi_bound = ((int32_t)set_mean * E_PHI_SCALED) / E_PHI_DENOM;
    int32_t lo_bound = ((int32_t)set_mean * E_PHI_DENOM) / E_PHI_SCALED;
    if (value > hi_bound) return (int16_t)hi_bound;
    if (value < lo_bound) return (int16_t)lo_bound;
    return value;
}

e_particle e_emulate(const e_particle *broken, const e_particle *working,
                     uint8_t error_distance) {
    if (error_distance > E_EMULATE_CEILING)
        return e_z_defect(broken->ident,
                          "error distance exceeds emulate ceiling",
                          E_DEFECT_MISBOUND);
    if (!e_is_cleared(working))
        return e_z_defect(broken->ident, "no cleared neighbour to emulate",
                          E_DEFECT_UNBOUND);

    e_particle p    = *broken;
    p.state         = E_STATE_EMULATING;
    p.error_distance = error_distance;
    p.type          = working->type;
    p.value         = working->value;
    set_str(p.text, E_TEXT_MAX, working->text);

    int32_t borrowed = (int32_t)working->confidence - (30 * (int32_t)error_distance);
    if (borrowed < 1) borrowed = 1;
    p.confidence = (int16_t)borrowed;
    p.lo = p.hi  = p.confidence;
    p.archive_id = -1;
    p.born_ms    = now_ms();
    snprintf(p.reason, E_REASON_MAX, "emulating %s at distance %u",
             working->ident, (unsigned)error_distance);
    return p;
}

/* ─────────────────────────────────────────────
 * serialization — extended for payload and anchor
 * ───────────────────────────────────────────── */

size_t e_serialize(const e_particle *p, char *buf, size_t buflen) {
    char val[E_TEXT_MAX + 32];
    switch (p->type) {
        case E_TYPE_INT:  snprintf(val, sizeof val, "%lld",
                                   (long long)p->value.as_int); break;
        case E_TYPE_REAL: snprintf(val, sizeof val, "%.10g", p->value.as_real); break;
        case E_TYPE_BOOL: snprintf(val, sizeof val, "%d", p->value.as_bool); break;
        case E_TYPE_TEXT:
        case E_TYPE_FOREIGN: snprintf(val, sizeof val, "%s", p->text); break;
        default: val[0] = '\0'; break;
    }
    int n = snprintf(buf, buflen,
        "%d|%d|%d|%d|%d|%d|%d|%u|%u|%u|%u|%d|%lld|%s|%s|%s",
        (int)p->state, (int)p->type, (int)p->lang, (int)p->defect,
        (int)p->confidence, (int)p->lo, (int)p->hi,
        (unsigned)p->error_distance, (unsigned)p->generation,
        (unsigned)p->ascend_points, (unsigned)p->anchor_id,
        (int)p->archive_id, (long long)p->born_ms,
        p->ident, val, p->reason);
    return (n < 0) ? 0 : (size_t)n;
}

int e_deserialize(const char *line, e_particle *out) {
    e_particle p = blank();
    int state, type, lang, defect, conf, lo, hi, aid;
    unsigned ed, gen, ap, anchor;
    long long born;
    char ident[E_IDENT_MAX] = {0};
    char val[E_TEXT_MAX]    = {0};
    char reason[E_REASON_MAX] = {0};

    int got = sscanf(line,
        "%d|%d|%d|%d|%d|%d|%d|%u|%u|%u|%u|%d|%lld|%63[^|]|%191[^|]|%127[^\n]",
        &state, &type, &lang, &defect, &conf, &lo, &hi,
        &ed, &gen, &ap, &anchor, &aid, &born, ident, val, reason);
    if (got < 14) return 0;

    p.state = (e_state)state;   p.type = (e_type)type;
    p.lang  = (e_lang)lang;     p.defect = (e_defect)defect;
    p.confidence = (int16_t)conf; p.lo = (int16_t)lo; p.hi = (int16_t)hi;
    p.error_distance = (uint8_t)ed; p.generation = (uint8_t)gen;
    p.ascend_points = (uint8_t)ap;  p.anchor_id = (uint32_t)anchor;
    p.archive_id = aid;             p.born_ms = born;
    set_str(p.ident, E_IDENT_MAX, ident);
    set_str(p.reason, E_REASON_MAX, reason);

    switch (p.type) {
        case E_TYPE_INT:  p.value.as_int  = strtoll(val, NULL, 10); break;
        case E_TYPE_REAL: p.value.as_real = strtod(val, NULL); break;
        case E_TYPE_BOOL: p.value.as_bool = atoi(val); break;
        case E_TYPE_TEXT:
        case E_TYPE_FOREIGN: set_str(p.text, E_TEXT_MAX, val); break;
        default: break;
    }
    *out = p;
    return 1;
}

const char *e_state_name(e_state s) {
    switch (s) {
        case E_STATE_Z:         return "Z";
        case E_STATE_CONFIDENT: return "Confident";
        case E_STATE_CERTAIN:   return "Certain";
        case E_STATE_EQUIV:     return "Equivalence";
        case E_STATE_EXPRESS:   return "Expression";
        case E_STATE_EMULATING: return "Emulating";
        case E_STATE_EVOLVED:   return "Evolved";
        case E_STATE_ANCHORED:  return "Anchored";
        case E_STATE_ABSENT:    return "Absent";
        case E_STATE_ERROR:     return "EError";
        default:                return "Unknown";
    }
}

const char *e_lang_name(e_lang l) {
    switch (l) {
        case E_LANG_C:      return "C";
        case E_LANG_CPP:    return "C++";
        case E_LANG_PYTHON: return "Python";
        case E_LANG_RUBY:   return "Ruby";
        case E_LANG_SQL:    return "SQL";
        case E_LANG_JAVA:   return "Java";
        case E_LANG_HTML:   return "HTML";
        case E_LANG_RUST:   return "Rust";
        case E_LANG_GO:     return "Go";
        case E_LANG_TS:     return "TypeScript";
        case E_LANG_SWIFT:  return "Swift";
        case E_LANG_EVER:   return "Ever";
        default:            return "Unknown";
    }
}

const char *e_type_name(e_type t) {
    switch (t) {
        case E_TYPE_VOID:    return "void";
        case E_TYPE_INT:     return "int";
        case E_TYPE_REAL:    return "real";
        case E_TYPE_TEXT:    return "text";
        case E_TYPE_BOOL:    return "bool";
        case E_TYPE_LIST:    return "list";
        case E_TYPE_FOREIGN: return "foreign";
        default:             return "unknown";
    }
}

const char *e_defect_name(e_defect d) {
    switch (d) {
        case E_DEFECT_NONE:      return "none";
        case E_DEFECT_UNBOUND:   return "unbound";
        case E_DEFECT_MISBOUND:  return "misbound";
        case E_DEFECT_UNBOUNDED: return "unbounded";
        case E_DEFECT_OVERBOUND: return "overbound";
        case E_DEFECT_ORPHANED:  return "orphaned";
        default:                 return "unknown";
    }
}
