/* unknown_composite_test.c — pool getters never return NULL.
 * A ref the pool did not issue as the requested type returns a defined
 * Unknown composite (type EV_VOID, ref 0). Exit 0 pass, 1 fail. */
#include <stdio.h>
#include <string.h>
#include "evalue.h"

static int fails = 0;
#define CHECK(cond, msg) do { if (!(cond)) { fails++; printf("FAIL %s\n", msg); } } while (0)

int main(void) {
    ev_pool pool;
    ev_pool_init(&pool);

    /* refs the pool never issued */
    CHECK(ev_pool_blob(&pool, 0)   != NULL, "blob(0) is not NULL");
    CHECK(ev_pool_blob(&pool, 999) != NULL, "blob(999) is not NULL");
    CHECK(ev_pool_list(&pool, -1)  != NULL, "list(-1) is not NULL");
    CHECK(ev_pool_record(&pool, 0) != NULL, "record(0) is not NULL");
    CHECK(ev_pool_get(&pool, 999)  != NULL, "get(999) is not NULL");

    CHECK(ev_pool_is_unknown(ev_pool_blob(&pool, 0)),   "blob(0) reads Unknown");
    CHECK(ev_pool_is_unknown(ev_pool_list(&pool, 0)),   "list(0) reads Unknown");
    CHECK(ev_pool_is_unknown(ev_pool_record(&pool, 999)), "record(999) reads Unknown");
    CHECK(ev_pool_blob(&pool, 0)->h.len == 0, "unknown composite has length 0");
    CHECK(ev_pool_record(&pool, 0)->h.ref == 0, "unknown composite has ref 0");

    /* a real record (built by its constructor) is known */
    EValue rec = ev_record_new(&pool);
    CHECK(rec.body.pool_ref > 0, "built a record");
    CHECK(!ev_pool_is_unknown(ev_pool_record(&pool, rec.body.pool_ref)), "built record is known");

    /* a ref allocated but never filled is unknown, never NULL */
    int32_t empty = ev_pool_alloc(&pool, EV_RECORD);
    CHECK(ev_pool_record(&pool, empty) != NULL, "allocated-but-empty record is not NULL");
    CHECK(ev_pool_is_unknown(ev_pool_record(&pool, empty)), "allocated-but-empty record is unknown");

    /* wrong type for a valid ref is also unknown, never NULL */
    EValue blob = ev_blob_new((const uint8_t *)"ab", 2, &pool);
    CHECK(ev_pool_is_unknown(ev_pool_record(&pool, blob.body.pool_ref)), "blob ref read as record is unknown");
    CHECK(ev_pool_is_unknown(ev_pool_list(&pool, blob.body.pool_ref)),   "blob ref read as list is unknown");

    /* a NULL handed to the check is unknown too */
    CHECK(ev_pool_is_unknown(NULL), "NULL is treated as unknown");

    if (fails) { printf("unknown composites: %d failure(s)\n", fails); return 1; }
    printf("unknown composites: no NULL from any getter, all checks pass\n");
    return 0;
}
