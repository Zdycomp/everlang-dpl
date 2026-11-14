/* reason_test.c — the C reason registry: names, kinds, and no NULL. */
#include <stdio.h>
#include <string.h>
#include "reason.h"

static int fails = 0;
#define CHECK(cond, msg) do { if (!(cond)) { fails++; printf("FAIL %s\n", msg); } } while (0)

int main(void) {
    int unknown = 0, notes = 0;
    for (int i = 0; i < EV_REASON_COUNT; i++) {
        ev_reason r = (ev_reason)i;
        CHECK(ev_reason_name(r) != NULL, "name is never NULL");
        CHECK(ev_reason_meaning(r) != NULL, "meaning is never NULL");
        CHECK(strlen(ev_reason_meaning(r)) > 0, "meaning is non-empty");
        if (ev_reason_is_unknown(r)) unknown++; else notes++;
    }
    CHECK(unknown == 7, "seven Unknown codes");
    CHECK(notes == 6, "six note codes");
    CHECK(strcmp(ev_reason_name(EV_REASON_TIMEOUT), "TIMEOUT") == 0, "TIMEOUT name");
    CHECK(ev_reason_is_unknown(EV_REASON_TIMEOUT) == 1, "TIMEOUT is unknown");
    CHECK(ev_reason_is_unknown(EV_REASON_GROUNDED) == 0, "GROUNDED is a note");
    CHECK(strcmp(ev_reason_name((ev_reason)99), "MALFORMED") == 0, "out of range reads MALFORMED");
    CHECK(strcmp(ev_reason_name((ev_reason)-1), "MALFORMED") == 0, "negative reads MALFORMED");
    CHECK(ev_reason_is_unknown((ev_reason)99) == 1, "out of range is unknown");
    if (fails) { printf("reason registry (C): %d failure(s)\n", fails); return 1; }
    printf("reason registry (C): %d codes, no NULL, all checks pass\n", EV_REASON_COUNT);
    return 0;
}
