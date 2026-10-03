// match.js — signature matching against captured Gradle stderr.
// Zero-dep. Returns every distinct match; caller decides.

'use strict';

const fs   = require('fs');
const path = require('path');

function loadSignatures(file) {
  const j = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!j || !Array.isArray(j.signatures))
    throw new Error('signature corpus must contain a signatures array');
  return j.signatures.map((s, index) => {
    if (!s.id || !s.match || !s.fixture_form || !s.fixture_text)
      throw new Error(`signature ${index} is missing required fields`);
    if (s.kind !== 0 && s.kind !== 1)
      throw new Error(`signature ${s.id} has invalid kind`);
    let re;
    try {
      re = new RegExp(s.match, s.flags || 'mg');
    } catch (error) {
      throw new Error(`signature ${s.id} has invalid regex: ${error.message}`);
    }
    return { ...s, _re: re };
  });
}

function _interp(tpl, caps) {
  return tpl.replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_, k) =>
    k in caps ? String(caps[k]) : `{${k}}`);
}

// One match = one repair proposal. The caller sees the raw failure
// text (the exact matched substring) alongside the interpolated
// fixture. Both halves are always present.
function scan(stderr, signatures) {
  const out = [];
  const seen = new Set();
  for (const sig of signatures) {
    sig._re.lastIndex = 0;
    let m;
    while ((m = sig._re.exec(stderr)) !== null) {
      const caps = {};
      (sig.capture || []).forEach((name, i) => { caps[name] = m[i + 1]; });
      const hit = {
        signature_id: sig.id,
        kind: sig.kind,
        family: sig.family,
        failure_text: m[0],
        fixture_form: _interp(sig.fixture_form, caps),
        fixture_text: _interp(sig.fixture_text, caps),
        captures: caps,
      };
      const key = `${hit.signature_id}\u241f${hit.fixture_form}`;
      if (!seen.has(key)) {
        seen.add(key);
        out.push(hit);
      }
      // Guard against a malformed zero-width signature looping forever.
      if (m[0] === '') sig._re.lastIndex++;
    }
  }
  return out;
}

module.exports = { loadSignatures, scan };
