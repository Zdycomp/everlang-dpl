// archive.js — Failure/Fixture archive. Zero-dep JSONL, one line per
// repair, append-only. Nothing is deleted. Same shape as repair table
// in 4-archive-sql/repair.sql.
//
// The JSONL choice is deliberate: git-diffable, greppable, and
// reviewable without a database. When ReFix Pro adds a hosted archive
// this file's schema is the API contract.

'use strict';

const fs   = require('fs');
const path = require('path');
const { E, KIND_COST, STATUS } = require('./constants');

const REPAIRS_FILE = 'repairs.jsonl';
const RULES_FILE   = 'rules.jsonl';

// ─────────────────────────────────────────────
// A repair is a pair. Empty halves are rejected — same rule as the
// SQL CHECK constraint. Cost is derived from kind, never passed in.
// ─────────────────────────────────────────────

function makeRepair({
  runId, lang, signatureId, kind, sourceIdent, lineNo,
  failureText, fixtureText, fixtureForm, reason, confBefore,
}) {
  if (!failureText || !failureText.length)
    throw new Error('archive: empty failure_text is not a repair');
  if (!fixtureText || !fixtureText.length)
    throw new Error('archive: empty fixture_text is not a repair');
  if (kind !== 0 && kind !== 1)
    throw new Error(`archive: kind must be 0 (plain) or 1 (inferred), got ${kind}`);
  if (confBefore < E.E_ZERO || confBefore > E.E_CERTAIN)
    throw new Error(`archive: conf_before out of range: ${confBefore}`);

  const cost      = KIND_COST[kind];
  const confAfter = Math.max(E.E_ZERO, confBefore - cost);

  // The one invariant that must hold across every implementation:
  // confidence never rises through a repair.
  if (confAfter > confBefore)
    throw new Error('archive: confidence cannot rise through a repair');

  return {
    v: 1,
    archived_ms: Date.now(),
    run_id: runId,
    lang, signature_id: signatureId, kind,
    source_ident: sourceIdent, line_no: lineNo | 0,
    failure_text: failureText,
    fixture_text: fixtureText,
    fixture_form: fixtureForm || null,   // null means: does not count toward recurrence
    reason: reason || '',
    cost, conf_before: confBefore, conf_after: confAfter,
  };
}

class Archive {
  constructor(dir) {
    this.dir = dir;
    fs.mkdirSync(dir, { recursive: true });
    this.repairsPath = path.join(dir, REPAIRS_FILE);
    this.rulesPath   = path.join(dir, RULES_FILE);
  }

  append(record)  { fs.appendFileSync(this.repairsPath, JSON.stringify(record) + '\n'); }
  appendRule(r)   { fs.appendFileSync(this.rulesPath,   JSON.stringify(r)      + '\n'); }

  readAll(file) {
    if (!fs.existsSync(file)) return [];
    return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(JSON.parse);
  }
  repairs() { return this.readAll(this.repairsPath); }
  rules()   { return this.readAll(this.rulesPath);   }

  // ─────────────────────────────────────────────
  // Recurrence: same shape as the repair_candidate SQL view.
  // Only repairs with a non-null fixture_form count. Distinct
  // sources — not distinct rows — clear the threshold. Ten repairs
  // in one repo is one habit, not a rule.
  // ─────────────────────────────────────────────
  candidates() {
    const byKey = new Map();
    for (const r of this.repairs()) {
      if (!r.fixture_form) continue;
      const key = `${r.signature_id}\u241f${r.fixture_form}`;
      let g = byKey.get(key);
      if (!g) {
        g = { signature_id: r.signature_id, fixture_form: r.fixture_form,
              seen: 0, sources: new Set(), langs: new Set(),
              first_ms: r.archived_ms, last_ms: r.archived_ms };
        byKey.set(key, g);
      }
      g.seen++;
      g.sources.add(r.source_ident);
      g.langs.add(r.lang);
      if (r.archived_ms < g.first_ms) g.first_ms = r.archived_ms;
      if (r.archived_ms > g.last_ms)  g.last_ms  = r.archived_ms;
    }
    const out = [];
    for (const g of byKey.values()) {
      if (g.sources.size >= E.E_ASCEND_POINTS) {
        out.push({ signature_id: g.signature_id, fixture_form: g.fixture_form,
                   seen: g.seen, distinct_sources: g.sources.size,
                   distinct_langs: g.langs.size,
                   first_ms: g.first_ms, last_ms: g.last_ms });
      }
    }
    return out;
  }

  // ─────────────────────────────────────────────
  // Rule admission. Two gates, both from SEMANTICS.md §9.6:
  //   1. cannot admit below E_EXECUTE_FLOOR
  //   2. cannot admit if replay changes any prior outcome
  // A rejected rule is kept forever with its reason, same as an
  // EError. This function returns the rule object; the caller
  // decides whether to persist it.
  // ─────────────────────────────────────────────
  proposeRule(candidate) {
    const rule = {
      v: 1,
      proposed_ms: Date.now(),
      signature_id: candidate.signature_id,
      fixture_form: candidate.fixture_form,
      derived_from: candidate.seen,
      status: STATUS.PROPOSED,
      confidence: E.E_INTAKE,          // born below the floor
      replay_total: 0,
      replay_agreed: 0,
      rejected_why: '',
      decided_ms: null,
    };
    return this._replay(rule);
  }

  _replay(rule) {
    const priors = this.repairs().filter(
      r => r.signature_id === rule.signature_id && r.fixture_form);

    rule.replay_total  = priors.length;
    rule.replay_agreed = priors.filter(r => r.fixture_form === rule.fixture_form).length;
    rule.status        = STATUS.REPLAYED;

    if (rule.replay_agreed !== rule.replay_total) {
      rule.status       = STATUS.REJECTED;
      rule.rejected_why = `replay disagreed: ${rule.replay_total - rule.replay_agreed} of ${rule.replay_total} prior repairs would change`;
      rule.decided_ms   = Date.now();
      return rule;
    }
    // Unanimous replay. Rule may rise from E_INTAKE (120) to
    // E_EXECUTE_FLOOR (128). It does not rise further from replay
    // alone; further evidence is real usage.
    rule.confidence = E.E_EXECUTE_FLOOR;
    rule.status     = STATUS.ADMITTED;
    rule.decided_ms = Date.now();
    return rule;
  }
}

module.exports = { Archive, makeRepair };
