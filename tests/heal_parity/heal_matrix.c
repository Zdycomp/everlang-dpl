/*
 * heal_matrix.c — the C layer's side of the heal parity matrix.
 *
 * Reads tests/heal_parity/cases.tsv and, for every heal case, runs the same
 * program the Python and Java layers run: the TAC interpreter, lowered and
 * executed for real, against the archive directory given on the command
 * line. Prints one row per case:
 *
 *     name <TAB> value <TAB> confidence <TAB> action
 *
 * learn cases are C-layer-inapplicable (the C layer has no learn node) and
 * are skipped. Built by tests/heal_parity_test.py together with 0-atom-c.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tac.c"

static const char *ACTION[] = { "KEEP", "SUBSTITUTE", "FALLBACK", "FAILED" };

static EvNode *div_node(EvArena *a, int64_t x, int64_t y) {
    return ev_node_binop(a, EV_NODE_DIV, ev_node_int(a, x, 1), ev_node_int(a, y, 1), 1);
}

/* the callee every call case names: f(x) = 10 / x */
static EvNode *callee_def(EvArena *a) {
    const char *params[] = {"x"};
    EvNode *body = ev_node_binop(a, EV_NODE_DIV, ev_node_int(a, 10, 1),
                                 ev_node_var(a, "x", 1), 1);
    return ev_node_def(a, "f", params, 1, body, 1);
}

/* builds the primary for an expr token: int:N, div:A:B, nested:A:B, call:B, zvar */
static EvNode *primary(EvArena *a, const char *expr) {
    int64_t x = 0, y = 0;
    if (sscanf(expr, "int:%lld", (long long *)&x) == 1) return ev_node_int(a, x, 1);
    if (sscanf(expr, "div:%lld:%lld", (long long *)&x, (long long *)&y) == 2)
        return div_node(a, x, y);
    if (sscanf(expr, "nested:%lld:%lld", (long long *)&x, (long long *)&y) == 2)
        return ev_node_binop(a, EV_NODE_ADD, div_node(a, x, y), ev_node_int(a, 1, 1), 1);
    if (sscanf(expr, "call:%lld", (long long *)&x) == 1) {
        EvNode *args[] = { ev_node_int(a, x, 1) };
        return ev_node_call(a, "f", args, 1, 1);
    }
    if (strcmp(expr, "zvar") == 0) return ev_node_var(a, "x_undef", 1);
    return NULL;
}

static void run_case(const char *name, const char *expr, const char *strat,
                     int64_t fallback, EvArena *a) {
    EvNode *p = primary(a, expr);
    if (!p) { printf("%s\tERROR\texpr %s\t-\n", name, expr); return; }
    EvNode *h = ev_node_new(a, EV_NODE_HEAL, 1);
    ev_node_add_child(h, p);
    ev_node_add_child(h, ev_node_text(a, strat, 1));
    EvNode *fb = ev_node_int(a, fallback, 1);
    /* a call's callee must be in the module. Lowering registers it from this
       branch, which never runs: the condition is false. */
    if (strncmp(expr, "call:", 5) == 0)
        fb = ev_node_if(a, ev_node_bool(a, 0, 1), callee_def(a), fb, 1);
    ev_node_add_child(h, fb);
    EvModule *m = ev_lower_module("heal_matrix", h);
    if (!m) { printf("%s\tERROR\tlowering\t-\n", name); return; }
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    EvHealTrace t = ev_interp_heal_trace(ip);
    int conf = (int)ip->ret_conf;
    const char *action = (t.action >= 0 && t.action <= 3) ? ACTION[t.action] : "?";
    printf("%s\t", name);
    switch (r.tag) {
        case EV_INT:  printf("%lld", (long long)r.body.as_int); break;
        case EV_REAL: printf("%g", r.body.as_real); break;
        case EV_BOOL: printf("%s", r.body.as_bool ? "true" : "false"); break;
        case EV_TEXT: printf("%s", r.text); break;
        default:      printf("z"); conf = 0; break;
    }
    printf("\t%d\t%s\n", conf, action);
    ev_interp_free(ip);
    ev_module_free(m);
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: heal_matrix <prepared-archives> <cases.tsv>\n");
        return 2;
    }
    FILE *cases = fopen(argv[2], "r");
    if (!cases) { perror(argv[2]); return 2; }

    char line[2048];
    int first = 1;
    while (fgets(line, sizeof line, cases)) {
        if (first) { first = 0; continue; }          /* header */
        line[strcspn(line, "\r\n")] = '\0';
        if (!line[0]) continue;

        char *fields[6] = {0};
        int nf = 0;
        for (char *tok = strtok(line, "\t"); tok && nf < 6; tok = strtok(NULL, "\t"))
            fields[nf++] = tok;
        if (nf < 6) { printf("ERROR\tshort row\t-\t-\n"); continue; }
        if (strcmp(fields[1], "heal") != 0) continue;   /* learn: not in the C layer */

        char path[1024];
        snprintf(path, sizeof path, "%s/%s/repairs.jsonl", argv[1], fields[5]);
        g_repair_registry = ev_repair_registry_new(path);
        EvArena *a = ev_arena_new("heal_matrix");
        run_case(fields[0], fields[2], fields[3], atoll(fields[4]), a);
        ev_arena_free(a);
        ev_repair_registry_free(g_repair_registry);
        g_repair_registry = NULL;
    }
    fclose(cases);
    return 0;
}
