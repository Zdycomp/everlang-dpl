/*
 * repair.h — Ever / Tapestry, the self-healing registry
 *
 * This registry stores "repairs" (fixtures) that can be used to recover
 * from a failure (Z-value) given a specific failure reason and strategy.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */

#ifndef EVER_REPAIR_H
#define EVER_REPAIR_H

#include "tapestry.h"
#include "evalue.h"

typedef struct {
    char *failure_text;
    char *fixture_text;
    int32_t kind;
    char *strategy;     /* NULL: a wildcard, matches any strategy */
} EvRepair;

typedef struct {
    EvRepair **repairs;
    int32_t count;
    int32_t cap;
    char *archive_path;
} EvRepairRegistry;

EvRepairRegistry *ev_repair_registry_new(const char *path);
void ev_repair_registry_free(EvRepairRegistry *reg);
const char *ev_repair_find(EvRepairRegistry *reg, const char *reason,
                           const char *strategy, int32_t *kind_out);
EValue ev_parse_constant(const char *s);

#endif /* EVER_REPAIR_H */
