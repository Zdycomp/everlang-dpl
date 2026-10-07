/*
 * evalue_test.c — Ever / Tapestry, unified variant type verification
 *
 * Tests every type, every composite operation, the wire format, and all
 * three source-language lifters. The goal is to prove that a SQL row, an
 * HTML element, and a Python list are the same thing at the C foundation.
 */

#include <stdio.h>
#include <string.h>
#include <math.h>
#include "evalue.h"

static int passed = 0, failed = 0;

static void ok(const char *name, int cond) {
    if (cond) { passed++; printf("  \u2713 %s\n", name); }
    else       { failed++; printf("  \u2717 %s\n", name); }
}

int main(void) {
    ev_pool pool;
    ev_pool_init(&pool);

    printf("\n=== Ever \u2014 unified variant type (EValue) ===\n\n");

    /* ── Layout ── */
    printf("ABI layout assertions\n");
    ok("sizeof(EValue) == 208",    sizeof(EValue)         == 208);
    ok("tag at offset 0",          offsetof(EValue, tag)  ==   0);
    ok("body at offset 8",         offsetof(EValue, body) ==   8);
    ok("text at offset 16",        offsetof(EValue, text) ==  16);

    /* ── Scalars ── */
    printf("\nScalars — inline, no pool\n");
    EValue vv = ev_void();
    ok("void tag",           vv.tag == EV_VOID);
    ok("void is scalar",     ev_is_scalar(&vv));

    EValue bt = ev_bool(1), bf = ev_bool(0);
    ok("bool true",          bt.body.as_bool == 1);
    ok("bool false",         bf.body.as_bool == 0);
    ok("bool equal same",    ev_equal(&bt, &bt, &pool));
    ok("bool different",     !ev_equal(&bt, &bf, &pool));

    EValue i1 = ev_int(42), i2 = ev_int(-99);
    ok("int positive",       i1.body.as_int == 42);
    ok("int negative",       i2.body.as_int == -99);
    ok("int equal",          ev_equal(&i1, &i1, &pool));
    ok("int not equal",      !ev_equal(&i1, &i2, &pool));

    EValue r1 = ev_real(3.14159), r2 = ev_real(-0.0);
    ok("real value",         fabs(r1.body.as_real - 3.14159) < 1e-9);
    ok("real equal",         ev_equal(&r1, &r1, &pool));
    { EValue _i3=ev_int(3), _r3=ev_real(3.0), _r31=ev_real(3.1);
    ok("int-real interop",   ev_equal(&_i3, &_r3,  &pool));
    ok("int-real neq",       !ev_equal(&_i3, &_r31, &pool)); }
    (void)r2;

    EValue t1 = ev_text("Codric"), t2 = ev_text("Ever");
    ok("text stored",        strcmp(t1.text, "Codric") == 0);
    ok("text equal",         ev_equal(&t1, &t1, &pool));
    ok("text not equal",     !ev_equal(&t1, &t2, &pool));
    ok("empty text",         ev_text("").text[0] == '\0');

    /* ── BLOB ── */
    printf("\nBLOB \u2014 long strings and binary\n");
    const uint8_t data[] = {0x45, 0x76, 0x65, 0x72};  /* "Ever" */
    EValue blob = ev_blob_new(data, 4, &pool);
    ok("blob tag",           blob.tag == EV_BLOB);
    ok("blob is composite",  ev_is_composite(&blob));
    ok("blob not scalar",    !ev_is_scalar(&blob));
    ev_blob *bp = ev_pool_blob(&pool, blob.body.pool_ref);
    ok("blob data correct",  bp && memcmp(bp->data, data, 4) == 0);
    ok("blob length correct",bp && bp->h.len == 4);

    EValue blob2 = ev_blob_new(data, 4, &pool);
    ok("blobs equal by content", ev_equal(&blob, &blob2, &pool));

    /* ── LIST ── */
    printf("\nLIST \u2014 Python list, SQL result column\n");
    EValue lst = ev_list_new(&pool);
    ok("list tag",           lst.tag == EV_LIST);
    ok("list empty",         ev_list_len(&lst, &pool) == 0);

    ev_list_push(&lst, ev_int(10), &pool);
    ev_list_push(&lst, ev_int(20), &pool);
    ev_list_push(&lst, ev_text("Codric"), &pool);
    ok("list length 3",      ev_list_len(&lst, &pool) == 3);

    EValue g0 = ev_list_get(&lst, 0, &pool);
    EValue g1 = ev_list_get(&lst, 1, &pool);
    EValue g2 = ev_list_get(&lst, 2, &pool);
    ok("list[0] = 10",       g0.body.as_int == 10);
    ok("list[1] = 20",       g1.body.as_int == 20);
    ok("list[2] = Codric",   strcmp(g2.text, "Codric") == 0);
    ok("list out of bounds", ev_list_get(&lst, 99, &pool).tag == EV_VOID);

    EValue lst2 = ev_list_new(&pool);
    ev_list_push(&lst2, ev_int(10), &pool);
    ev_list_push(&lst2, ev_int(20), &pool);
    ev_list_push(&lst2, ev_text("Codric"), &pool);
    ok("equal lists",        ev_equal(&lst, &lst2, &pool));

    ev_list_push(&lst2, ev_int(99), &pool);
    ok("unequal lists",      !ev_equal(&lst, &lst2, &pool));

    /* grow beyond initial capacity */
    EValue big = ev_list_new(&pool);
    for (int i = 0; i < 20; i++) ev_list_push(&big, ev_int(i), &pool);
    ok("list grows past 8",  ev_list_len(&big, &pool) == 20);
    ok("list[15] = 15",      ev_list_get(&big, 15, &pool).body.as_int == 15);

    /* ── RECORD ── */
    printf("\nRECORD \u2014 SQL row, HTML element, Python dict, C struct\n");
    EValue rec = ev_record_new(&pool);
    ok("record tag",         rec.tag == EV_RECORD);

    ev_record_set(&rec, "name",  ev_text("Alice"),   E_CERTAIN, &pool);
    ev_record_set(&rec, "age",   ev_int(30),          E_CERTAIN, &pool);
    ev_record_set(&rec, "score", ev_real(98.6),       E_CERTAIN, &pool);
    ev_record_set(&rec, "admin", ev_bool(1),           E_CERTAIN, &pool);

    ok("has name",           ev_record_has(&rec, "name", &pool));
    ok("has age",            ev_record_has(&rec, "age",  &pool));
    ok("no such field",      !ev_record_has(&rec, "xxxx", &pool));

    EValue fname = ev_record_get(&rec, "name",  &pool);
    EValue fage  = ev_record_get(&rec, "age",   &pool);
    ok("get name = Alice",   strcmp(fname.text, "Alice") == 0);
    ok("get age = 30",       fage.body.as_int == 30);
    ok("get missing = void", ev_record_get(&rec, "zzz", &pool).tag == EV_VOID);

    /* update an existing field */
    ev_record_set(&rec, "age", ev_int(31), E_CERTAIN, &pool);
    ok("update field",       ev_record_get(&rec, "age", &pool).body.as_int == 31);

    ev_record *rp = ev_pool_record(&pool, rec.body.pool_ref);
    ok("four unique fields", rp && rp->h.len == 4);

    /* nested: a list inside a record */
    EValue tags = ev_list_new(&pool);
    ev_list_push(&tags, ev_text("sql"), &pool);
    ev_list_push(&tags, ev_text("ever"), &pool);
    ev_record_set(&rec, "tags", tags, E_CERTAIN, &pool);
    EValue got_tags = ev_record_get(&rec, "tags", &pool);
    ok("nested list in record",
       ev_list_len(&got_tags, &pool) == 2);
    ok("nested list[1] = ever",
       strcmp(ev_list_get(&got_tags, 1, &pool).text, "ever") == 0);

    /* ── Source language lifters ── */
    printf("\nLifters \u2014 same type from different language literals\n");

    /* Python / Ruby / Ever */
    ok("lift int",   ev_from_literal("42",  E_LANG_PYTHON, &pool).tag == EV_INT);
    ok("lift real",  ev_from_literal("3.14",E_LANG_PYTHON, &pool).tag == EV_REAL);
    ok("lift bool",  ev_from_literal("true",E_LANG_PYTHON, &pool).body.as_bool == 1);
    ok("lift False", ev_from_literal("False",E_LANG_RUBY,  &pool).body.as_bool == 0);
    EValue ls = ev_from_literal("\"Codric\"", E_LANG_PYTHON, &pool);
    ok("lift quoted string",       strcmp(ls.text, "Codric") == 0);
    ok("lift null → void",         ev_from_literal("null", E_LANG_JAVA, &pool).tag == EV_VOID);
    ok("lift nil → void",          ev_from_literal("nil",  E_LANG_RUBY, &pool).tag == EV_VOID);
    ok("lift None → void",         ev_from_literal("None", E_LANG_PYTHON, &pool).tag == EV_VOID);

    /* SQL row */
    const char *cols[] = {"id","name","score"};
    const char *vals[] = {"1","Alice","98.6"};
    EValue row = ev_from_sql_row(cols, vals, 3, &pool);
    ok("SQL row is record",        row.tag == EV_RECORD);
    ok("SQL id → int",             ev_record_get(&row, "id",    &pool).tag == EV_INT);
    ok("SQL name → text",          ev_record_get(&row, "name",  &pool).tag == EV_TEXT);
    ok("SQL score → real",
       ev_record_get(&row, "score", &pool).tag == EV_REAL);
    ok("SQL name value",
       strcmp(ev_record_get(&row, "name", &pool).text, "Alice") == 0);

    /* HTML element */
    const char *attrs[] = {"class","header","id","h1"};
    EValue elem = ev_from_html_element("h1", attrs, 4, &pool);
    ok("HTML is record",           elem.tag == EV_RECORD);
    ok("HTML tag field",
       strcmp(ev_record_get(&elem, "tag", &pool).text, "h1") == 0);
    EValue fattrs = ev_record_get(&elem, "attrs", &pool);
    ok("HTML attrs is record",     fattrs.tag == EV_RECORD);
    ok("HTML class attr",
       strcmp(ev_record_get(&fattrs, "class", &pool).text, "header") == 0);
    EValue fchildren = ev_record_get(&elem, "children", &pool);
    ok("HTML children is list",    fchildren.tag == EV_LIST);

    /* ── Wire format ── */
    printf("\nWire format \u2014 serialise / deserialise every type\n");
    uint8_t buf[4096];

    EValue types[] = {
        ev_void(), ev_bool(1), ev_bool(0), ev_int(12345), ev_int(-1),
        ev_real(2.718281828), ev_text("hello"), ev_text("")
    };
    const char *tnames[] = {
        "void","bool:T","bool:F","int:12345","int:-1",
        "real:e","text:hello","text:empty"
    };
    for (int i = 0; i < 8; i++) {
        int32_t n = ev_serialise(&types[i], buf, sizeof buf, &pool);
        ok(tnames[i], n > 0);
        int32_t cons = 0;
        EValue back = ev_deserialise(buf, n, &cons, &pool);
        ok(tnames[i], ev_equal(&types[i], &back, &pool) && cons == n);
    }

    /* blob round-trip */
    int32_t nb = ev_serialise(&blob, buf, sizeof buf, &pool);
    ok("blob serialise",     nb > 0);
    int32_t cb = 0; EValue bback = ev_deserialise(buf, nb, &cb, &pool);
    ok("blob round-trip",    ev_equal(&blob, &bback, &pool) && cb == nb);

    /* list round-trip */
    int32_t nl = ev_serialise(&lst, buf, sizeof buf, &pool);
    ok("list serialise",     nl > 0);
    int32_t cl = 0; EValue lback = ev_deserialise(buf, nl, &cl, &pool);
    ok("list round-trip",    ev_equal(&lst, &lback, &pool) && cl == nl);

    /* record round-trip */
    int32_t nr = ev_serialise(&row, buf, sizeof buf, &pool);
    ok("SQL row serialise",  nr > 0);
    int32_t cr = 0; EValue rback = ev_deserialise(buf, nr, &cr, &pool);
    ok("SQL row round-trip", ev_equal(&row, &rback, &pool) && cr == nr);

    /* nested record+list round-trip */
    int32_t ne = ev_serialise(&elem, buf, sizeof buf, &pool);
    ok("HTML element serialise", ne > 0);
    int32_t ce = 0; EValue eback = ev_deserialise(buf, ne, &ce, &pool);
    ok("HTML element round-trip", ev_equal(&elem, &eback, &pool) && ce == ne);

    /* ── Description ── */
    printf("\nPlain-language descriptions\n");
    char dbuf[128];
    { EValue _dv=ev_void(),_db=ev_bool(1),_di=ev_int(42),_dt=ev_text("hi");
    ok("describe void",   strcmp(ev_describe(&_dv, &pool, dbuf, sizeof dbuf), "nothing") == 0);
    ok("describe bool",   strcmp(ev_describe(&_db, &pool, dbuf, sizeof dbuf), "true") == 0);
    ok("describe int",    strcmp(ev_describe(&_di, &pool, dbuf, sizeof dbuf), "42") == 0);
    ok("describe text",   strstr(ev_describe(&_dt, &pool, dbuf, sizeof dbuf), "hi") != NULL); }
    ev_describe(&lst,  &pool, dbuf, sizeof dbuf);
    ok("describe list",   strstr(dbuf, "list") != NULL);
    ev_describe(&row,  &pool, dbuf, sizeof dbuf);
    ok("describe record", strstr(dbuf, "id") != NULL);

    printf("\n=== EValue: %d passed, %d failed ===\n\n", passed, failed);
    return failed == 0 ? 0 : 1;
}
