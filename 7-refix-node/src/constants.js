// constants.js — one source, same values as ever_constant.
//
// If a number is not here it does not exist in ReFix. Drift is the only
// bug this file is designed to prevent.

'use strict';

const E = Object.freeze({
  E_ZERO:               0,
  E_CERTAIN:          256,   // 4^4
  E_EXECUTE_FLOOR:    128,   // 256 / 2
  E_INTAKE:           120,   // pre-evidence
  E_ASCEND_POINTS:      3,   // distinct sources required to rise
  E_REPAIR_PLAIN:       8,   // 256 / 32
  E_REPAIR_INFERRED:   32,   // 256 / 8
});

// Two kinds. Same partition as SEMANTICS.md §9.2.
const KIND = Object.freeze({ PLAIN: 0, INFERRED: 1 });
const KIND_COST = Object.freeze({ 0: E.E_REPAIR_PLAIN, 1: E.E_REPAIR_INFERRED });

// Rule lifecycle. Same states as repair_rule.status.
const STATUS = Object.freeze({
  PROPOSED:  'proposed',
  REPLAYED:  'replayed',
  ADMITTED:  'admitted',
  REJECTED:  'rejected',
});

module.exports = { E, KIND, KIND_COST, STATUS };
