// Tests for everconf-wrap.mjs. Run: node --test everconf/adapters/express/
// Exit 0 pass, non-zero fail. Needs Node 18+ and python3 (for the end-to-end case).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { wrapRead, unknownResult } from './everconf-wrap.mjs';

const EVERCONF_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

const DOC = 'Tenant shall indemnify Landlord for any and all claims regardless of fault.';
const ANSWER = {
  overall_risk_score: 88,
  risk_tier: 'CRITICAL',
  summary: 'one trap',
  findings: [{ verbatim_text: 'indemnify Landlord for any and all claims regardless of fault',
               category: 'Unilateral Indemnification', risk_level: 'CRITICAL' }],
};

// Walk a value and fail if any null appears anywhere in it.
function assertNoNull(value, where = '$') {
  assert.notEqual(value, null, `null at ${where}`);
  if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) assertNoNull(v, `${where}.${k}`);
  }
}

function listen(handler) {
  return new Promise((resolve) => {
    const server = http.createServer(handler);
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

test('unknown results are never null and always carry a reason', () => {
  const r = unknownResult('TIMEOUT', 'did not answer');
  assertNoNull(r);
  assert.equal(r.state, 'unknown');
  assert.equal(r.score, 0);
  assert.equal(r.label, "can't tell");
  assert.ok(r.reasons.length >= 1 && r.reasons[0].reason.length > 0);
});

test('a bad kind is an Unknown, not an exception', async () => {
  const env = await wrapRead({ kind: 'mood', document: DOC, answer: ANSWER, fetchImpl: () => assert.fail('no call') });
  assert.equal(env.overall.reasons[0].code, 'MALFORMED');
  assertNoNull(env);
});

test('an empty document is MISSING_INPUT and makes no call', async () => {
  const env = await wrapRead({ kind: 'clause', document: '   ', answer: ANSWER, fetchImpl: () => assert.fail('no call') });
  assert.equal(env.overall.reasons[0].code, 'MISSING_INPUT');
});

test('a reply from the service is passed through unchanged', async () => {
  const canned = { kind: 'clause', overall: unknownResult('CONFLICTING_SOURCES', 'x'), reads: [], unchecked: [] };
  const server = await listen((req, res) => {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify(canned));
  });
  try {
    const env = await wrapRead({ kind: 'clause', document: DOC, answer: ANSWER,
                                 baseUrl: `http://127.0.0.1:${server.address().port}` });
    assert.deepEqual(env, canned);
  } finally {
    server.close();
  }
});

test('a service that never answers is TIMEOUT, not a score', async () => {
  const server = await listen(() => { /* never respond */ });
  try {
    const env = await wrapRead({ kind: 'clause', document: DOC, answer: ANSWER, timeoutMs: 200,
                                 baseUrl: `http://127.0.0.1:${server.address().port}` });
    assert.equal(env.overall.reasons[0].code, 'TIMEOUT');
    assert.equal(env.overall.state, 'unknown');
    assertNoNull(env);
  } finally {
    server.closeAllConnections?.();
    server.close();
  }
});

test('a service that cannot be reached is UNVERIFIED_SOURCE', async () => {
  const server = await listen((req, res) => res.end());
  const port = server.address().port;
  await new Promise((r) => server.close(r));
  const env = await wrapRead({ kind: 'clause', document: DOC, answer: ANSWER,
                               baseUrl: `http://127.0.0.1:${port}`, timeoutMs: 2000 });
  assert.equal(env.overall.reasons[0].code, 'UNVERIFIED_SOURCE');
  assertNoNull(env);
});

test('a reply that is not JSON is UNVERIFIED_SOURCE', async () => {
  const server = await listen((req, res) => res.end('<html>oops</html>'));
  try {
    const env = await wrapRead({ kind: 'clause', document: DOC, answer: ANSWER,
                                 baseUrl: `http://127.0.0.1:${server.address().port}` });
    assert.equal(env.overall.reasons[0].code, 'UNVERIFIED_SOURCE');
  } finally {
    server.close();
  }
});

test('end to end: the Python adapter scores a Gemini answer', async (t) => {
  const port = 18000 + Math.floor(Math.random() * 20000);
  const proc = spawn('python3', ['-m', 'everconf.adapter', '--port', String(port)],
                     { cwd: EVERCONF_DIR, stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  proc.stderr.on('data', (d) => { stderr += d; });
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('adapter did not start: ' + stderr)), 10000);
      proc.stdout.on('data', (d) => { if (String(d).includes('listening')) { clearTimeout(timer); resolve(); } });
      proc.on('exit', (code) => { clearTimeout(timer); reject(new Error(`adapter exited ${code}: ${stderr}`)); });
    });
    const env = await wrapRead({ kind: 'clause', document: DOC, answer: ANSWER,
                                 baseUrl: `http://127.0.0.1:${port}`, at: '2026-11-13T03:00:00Z' });
    assert.equal(env.kind, 'clause');
    assert.equal(env.reads.length, 1);
    assert.equal(env.reads[0].ever.state, 'known');
    assert.equal(env.reads[0].ever.label, 'pretty sure');
    assert.equal(env.reads[0].ever.score, 180);
    assert.equal(env.reads[0].ever.evidence[0].phrase.includes('indemnify'), true);
    assertNoNull(env);
  } finally {
    proc.kill();
  }
});
