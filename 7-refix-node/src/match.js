// match.js — signature matching against captured Gradle stderr.
// Zero-dep. Returns every distinct match; caller decides.

'use strict';

const fs   = require('fs');
const path = require('path');

function loadSignatures(file) {
  const j = JSON.parse(fs.readFileSync(file, 'utf8'));
  return j.signatures.map(s => ({ ...s, _re: new RegExp(s.match, 'm') }));
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
  for (const sig of signatures) {
    const m = sig._re.exec(stderr);
    if (!m) continue;
    const caps = {};
    (sig.capture || []).forEach((name, i) => { caps[name] = m[i + 1]; });
    out.push({
      signature_id: sig.id,
      kind: sig.kind,
      family: sig.family,
      failure_text: m[0],
      fixture_form: _interp(sig.fixture_form, caps),
      fixture_text: _interp(sig.fixture_text, caps),
      captures: caps,
    });
  }
  return out;
}

module.exports = { loadSignatures, scan };
