// test_all.js — zero-dep tests. Run: node tests/test_all.js
'use strict';

const fs   = require('fs');
const os   = require('os');
const path = require('path');
const assert = require('assert');
const { spawnSync } = require('child_process');

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

t('error catch is append-only', () => {
  const a = tmpArchive();
  const record = a.appendError({ runId: 1, lang: 'gradle', sourceIdent: 'repo-a',
    stage: 'compile', message: 'SDK location not found',
    context: 'stderr', fingerprint: 'deadbeef' });
  assert.strictEqual(record.status, 'unresolved');
  assert.strictEqual(a.errors().length, 1);
  assert.strictEqual(a.errors()[0].fingerprint, 'deadbeef');
});

t('matched error catch starts the repair path', () => {
  const a = tmpArchive();
  const record = a.appendError({ runId: 1, lang: 'gradle', sourceIdent: 'repo-a',
    message: 'known failure', fingerprint: 'known', signatureId: 'sig.x' });
  assert.strictEqual(record.status, 'matched');
});


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

// ─── constants and the CLI ─────────────────────────────────────────

const BIN = path.join(__dirname, '..', 'bin', 'refix');

function cli(home, args) {
  return spawnSync(process.execPath, [BIN, ...args],
    { env: Object.assign({}, process.env, { REFIX_HOME: home }), encoding: 'utf8' });
}

function writeLog(home, name, text) {
  const file = path.join(home, name);
  fs.writeFileSync(file, text);
  return file;
}

t('constants hold the values the SQL archive records', () => {
  assert.deepStrictEqual({ ...E }, { E_ZERO: 0, E_CERTAIN: 256, E_EXECUTE_FLOOR: 128,
    E_INTAKE: 120, E_ASCEND_POINTS: 3, E_REPAIR_PLAIN: 8, E_REPAIR_INFERRED: 32 });
  assert.deepStrictEqual({ ...KIND }, { PLAIN: 0, INFERRED: 1 });
});

t('propose does not repeat a rule already on record', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'refix-cli-'));
  const log = writeLog(home, 'build.log', '> Could not find com.squareup.okhttp3:okhttp:4.12.0.\n');
  for (const src of ['repo/a', 'repo/b', 'repo/c']) {
    assert.strictEqual(cli(home, ['accept', log, src]).status, 0);
  }
  assert.strictEqual(cli(home, ['propose']).status, 0);
  assert.strictEqual(cli(home, ['propose']).status, 0);
  const rules = cli(home, ['rules']).stdout.trim().split('\n');
  assert.strictEqual(rules.length, 1, rules.join('\n'));
  assert.ok(rules[0].startsWith('admitted'), rules[0]);
});

t('an empty build log is a no-match, not a crash', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'refix-cli-'));
  const r = cli(home, ['scan', writeLog(home, 'empty.log', '')]);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.ok(r.stdout.includes('nothing to match'), r.stdout);
});

t('refix errors shows only the first line of a multi-line message', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'refix-cli-'));
  const log = writeLog(home, 'novel.log', 'FAILURE: Build failed\n* What went wrong:\nSomething odd\n');
  assert.strictEqual(cli(home, ['scan', log]).status, 0);
  const out = cli(home, ['errors']).stdout;
  assert.ok(out.includes('FAILURE: Build failed …'), out);
  assert.ok(!out.includes('Something odd'), out);
});

// ─────────────────────────────────────────────
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
