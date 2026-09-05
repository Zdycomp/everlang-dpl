// test_all.js — zero-dep tests. Run: node tests/test_all.js
'use strict';

const fs   = require('fs');
const os   = require('os');
const path = require('path');
const assert = require('assert');

const { Archive, makeRepair }  = require('../src/archive');
const { loadSignatures, scan } = require('../src/match');
const { E, KIND, STATUS }      = require('../src/constants');

let pass = 0, fail = 0;
function t(name, fn) { try { fn(); pass++; console.log('  ok ' + name); }
  catch (e) { fail++; console.log('FAIL ' + name + ': ' + e.message); } }

function tmpArchive() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'refix-test-'));
  return new Archive(dir);
}

// ─── archive invariants ────────────────────────────────────────────

t('empty failure_text is rejected', () => {
  assert.throws(() => makeRepair({ lang: 'gradle', signatureId: 'x', kind: 0,
    sourceIdent: 's', failureText: '', fixtureText: 'y', confBefore: 256 }));
});

t('empty fixture_text is rejected', () => {
  assert.throws(() => makeRepair({ lang: 'gradle', signatureId: 'x', kind: 0,
    sourceIdent: 's', failureText: 'y', fixtureText: '', confBefore: 256 }));
});

t('plain repair costs E_REPAIR_PLAIN (8)', () => {
  const r = makeRepair({ lang: 'gradle', signatureId: 'x', kind: KIND.PLAIN,
    sourceIdent: 's', failureText: 'a', fixtureText: 'b', confBefore: 256 });
  assert.strictEqual(r.conf_after, 256 - E.E_REPAIR_PLAIN);
});

t('inferred repair costs E_REPAIR_INFERRED (32)', () => {
  const r = makeRepair({ lang: 'gradle', signatureId: 'x', kind: KIND.INFERRED,
    sourceIdent: 's', failureText: 'a', fixtureText: 'b', confBefore: 256 });
  assert.strictEqual(r.conf_after, 256 - E.E_REPAIR_INFERRED);
});

t('four inferred repairs land exactly on E_EXECUTE_FLOOR (128)', () => {
  // SEMANTICS.md §9.2: the consequence falls out rather than being tuned.
  // 256 - 4*32 = 128. The fifth would put it beneath the floor.
  assert.strictEqual(E.E_CERTAIN - 4 * E.E_REPAIR_INFERRED, E.E_EXECUTE_FLOOR);
  assert.ok       (E.E_CERTAIN - 5 * E.E_REPAIR_INFERRED  <  E.E_EXECUTE_FLOOR);
});

t('confidence never rises through a repair', () => {
  const r = makeRepair({ lang: 'gradle', signatureId: 'x', kind: KIND.PLAIN,
    sourceIdent: 's', failureText: 'a', fixtureText: 'b', confBefore: 100 });
  assert.ok(r.conf_after <= r.conf_before);
});

// ─── recurrence & admission ────────────────────────────────────────

function seed(arch, sig, form, sources, kind = KIND.INFERRED) {
  for (const s of sources) {
    arch.append(makeRepair({ lang: 'gradle', signatureId: sig, kind,
      sourceIdent: s, failureText: 'fail-' + s, fixtureText: 'fix', fixtureForm: form,
      reason: '', confBefore: 256 }));
  }
}

t('recurrence needs distinct sources, not distinct rows', () => {
  const a = tmpArchive();
  seed(a, 'sig.x', 'FORM_A', ['same/repo', 'same/repo', 'same/repo']);
  assert.strictEqual(a.candidates().length, 0);   // one source, threshold not met
});

t('recurrence fires at E_ASCEND_POINTS distinct sources', () => {
  const a = tmpArchive();
  seed(a, 'sig.x', 'FORM_A', ['a/x', 'b/x', 'c/x']);
  const cs = a.candidates();
  assert.strictEqual(cs.length, 1);
  assert.strictEqual(cs[0].distinct_sources, E.E_ASCEND_POINTS);
});

t('repair with null fixture_form counts toward nothing', () => {
  const a = tmpArchive();
  a.append(makeRepair({ lang: 'gradle', signatureId: 'sig.y', kind: KIND.PLAIN,
    sourceIdent: 'a/x', failureText: 'a', fixtureText: 'b', fixtureForm: null,
    confBefore: 256 }));
  a.append(makeRepair({ lang: 'gradle', signatureId: 'sig.y', kind: KIND.PLAIN,
    sourceIdent: 'b/x', failureText: 'a', fixtureText: 'b', fixtureForm: null,
    confBefore: 256 }));
  a.append(makeRepair({ lang: 'gradle', signatureId: 'sig.y', kind: KIND.PLAIN,
    sourceIdent: 'c/x', failureText: 'a', fixtureText: 'b', fixtureForm: null,
    confBefore: 256 }));
  assert.strictEqual(a.candidates().length, 0);
});

t('unanimous replay admits at E_EXECUTE_FLOOR', () => {
  const a = tmpArchive();
  seed(a, 'sig.z', 'FORM_Z', ['a/x', 'b/x', 'c/x']);
  const rule = a.proposeRule(a.candidates()[0]);
  assert.strictEqual(rule.status, STATUS.ADMITTED);
  assert.strictEqual(rule.confidence, E.E_EXECUTE_FLOOR);
});

t('disagreeing replay rejects and preserves the reason', () => {
  const a = tmpArchive();
  seed(a, 'sig.z', 'FORM_Z', ['a/x', 'b/x', 'c/x']);
  seed(a, 'sig.z', 'FORM_DIFFERENT', ['dissent/x']);
  // candidate is still FORM_Z (3 sources). Rule proposal replays
  // against ALL repairs on that signature — one disagrees.
  const rule = a.proposeRule({ signature_id: 'sig.z',
    fixture_form: 'FORM_Z', seen: 3, distinct_sources: 3, distinct_langs: 1,
    first_ms: 0, last_ms: 0 });
  assert.strictEqual(rule.status, STATUS.REJECTED);
  assert.ok(rule.rejected_why.includes('disagreed'));
  assert.strictEqual(rule.confidence, E.E_INTAKE);   // never rose
});

// ─── signature engine ──────────────────────────────────────────────

t('signature file loads and every entry has both halves', () => {
  const sigs = loadSignatures(path.join(__dirname, '..', 'signatures', 'gradle.json'));
  assert.ok(sigs.length >= 10);
  for (const s of sigs) {
    assert.ok(s.fixture_form, `${s.id} missing fixture_form`);
    assert.ok(s.fixture_text, `${s.id} missing fixture_text`);
    assert.ok(s._re,          `${s.id} regex failed to compile`);
    assert.ok(s.kind === 0 || s.kind === 1, `${s.id} bad kind`);
  }
});

t('unresolved_dependency captures the real coordinate', () => {
  const sigs = loadSignatures(path.join(__dirname, '..', 'signatures', 'gradle.json'));
  const hits = scan('> Could not find com.squareup.okhttp3:okhttp:4.12.0.', sigs);
  const dep  = hits.find(h => h.signature_id === 'gradle.unresolved_dependency');
  assert.ok(dep, 'signature did not match');
  assert.strictEqual(dep.fixture_form, 'SEARCH_MAVEN_CENTRAL:com.squareup.okhttp3:okhttp');
});

t('agp_too_old captures both versions', () => {
  const sigs = loadSignatures(path.join(__dirname, '..', 'signatures', 'gradle.json'));
  const hits = scan('The project is using an incompatible version (AGP 7.0.4) of the Android Gradle plugin. Latest supported version is AGP 8.5.2.', sigs);
  const h = hits.find(x => x.signature_id === 'gradle.agp_too_old');
  assert.ok(h);
  assert.strictEqual(h.fixture_form, 'SET_AGP_VERSION:8.5.2');
});

t('sdk_not_found matches without captures', () => {
  const sigs = loadSignatures(path.join(__dirname, '..', 'signatures', 'gradle.json'));
  const hits = scan('SDK location not found. Define a valid SDK location with an ANDROID_HOME environment variable or by setting the sdk.dir path in your project.', sigs);
  assert.ok(hits.some(h => h.signature_id === 'gradle.sdk_not_found'));
});

// ─────────────────────────────────────────────
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
