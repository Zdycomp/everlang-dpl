/* reason.h — the reason-code registry, C side.
 *
 * spec/reason_codes.tsv is the source of truth. This table is checked
 * against it, code for code and meaning for meaning, by
 * tests/test_reason_registry.py. Change the spec first, then this.
 *
 * Unknown codes say why an answer does not exist. Note codes say why a
 * known value is trusted the way it is. An out-of-range code is itself
 * malformed input, so it reads back as EV_REASON_MALFORMED and never NULL.
 */
#ifndef EV_REASON_H
#define EV_REASON_H

typedef enum {
    EV_REASON_MISSING_INPUT = 0,
    EV_REASON_CONFLICTING_SOURCES,
    EV_REASON_BELOW_THRESHOLD,
    EV_REASON_TIMEOUT,
    EV_REASON_OUT_OF_RANGE,
    EV_REASON_UNVERIFIED_SOURCE,
    EV_REASON_MALFORMED,
    EV_REASON_INTAKE_SOURCE,
    EV_REASON_GROUNDED,
    EV_REASON_CORROBORATED,
    EV_REASON_UNCORROBORATED,
    EV_REASON_CERTAIN_LITERAL,
    EV_REASON_DERIVED,
    EV_REASON_COUNT
} ev_reason;

typedef struct {
    const char *code;
    int         is_unknown;   /* 1 = Unknown code, 0 = note code */
    const char *meaning;
} ev_reason_info;

static const ev_reason_info EV_REASON_TABLE[EV_REASON_COUNT] = {
    {"MISSING_INPUT",       1, "A value needed for the answer was not supplied, or there was nothing to compute over."},
    {"CONFLICTING_SOURCES", 1, "Two sources that should agree do not, and nothing settles which one is right."},
    {"BELOW_THRESHOLD",     1, "A value exists but its confidence is under the floor the caller required to act on it."},
    {"TIMEOUT",             1, "The source did not answer in time, so no answer exists."},
    {"OUT_OF_RANGE",        1, "The operation has no defined result here: division by zero, overflow, NaN or infinity."},
    {"UNVERIFIED_SOURCE",   1, "The claimed answer could not be checked against its source, so it is not taken as given."},
    {"MALFORMED",           1, "The input does not have the shape the operation needs: bad syntax, mismatched lengths, a wrong type."},
    {"INTAKE_SOURCE",       0, "The value came from outside the program (a file, an API, a model). Its confidence is at most INTAKE (120)."},
    {"GROUNDED",            0, "The quoted text appears verbatim in the document it was read from."},
    {"CORROBORATED",        0, "A rule independent of the source matches the same passage and agrees with it."},
    {"UNCORROBORATED",      0, "No independent rule matches. The read rests on its source alone."},
    {"CERTAIN_LITERAL",     0, "A value written directly in the program or the call. Its confidence is CERTAIN (256)."},
    {"DERIVED",             0, "Computed from its inputs. Its confidence is the least of them, unless a stated rule says otherwise."}
};

/* The code's name. Never NULL: an out-of-range value is MALFORMED. */
static inline const char *ev_reason_name(ev_reason r) {
    if ((int)r < 0 || (int)r >= EV_REASON_COUNT) r = EV_REASON_MALFORMED;
    return EV_REASON_TABLE[(int)r].code;
}

/* The code's meaning. Never NULL. */
static inline const char *ev_reason_meaning(ev_reason r) {
    if ((int)r < 0 || (int)r >= EV_REASON_COUNT) r = EV_REASON_MALFORMED;
    return EV_REASON_TABLE[(int)r].meaning;
}

/* 1 if the code is an Unknown, 0 if it is a note. An out-of-range code is an Unknown. */
static inline int ev_reason_is_unknown(ev_reason r) {
    if ((int)r < 0 || (int)r >= EV_REASON_COUNT) return 1;
    return EV_REASON_TABLE[(int)r].is_unknown;
}

#endif /* EV_REASON_H */
