// everconf-wrap.mjs — the Express side of the everconf adapter.
//
// Zero dependencies (Node 18+ for global fetch). The scoring is done by the
// Python service in everconf/adapter.py; this file only calls it. Every
// failure path returns an Unknown in the same envelope shape, so the phone
// never receives a null, an empty body or a made-up score.
//
//   import { wrapRead } from './everconf-wrap.mjs';
//   const ever = await wrapRead({ kind: 'clause', document: text, answer: geminiJson });
//   res.json({ ...geminiJson, ever });

export const DEFAULT_BASE_URL = process.env.EVERCONF_URL || 'http://127.0.0.1:8787';
export const DEFAULT_TIMEOUT_MS = 3000;

const KINDS = ['clause', 'tone', 'motive'];

// The result shape for one unknown value (see everconf/docs/JSON.md).
export function unknownResult(code, reason) {
  return {
    value: { unknown: true },
    state: 'unknown',
    score: 0,
    percent: 0,
    label: "can't tell",
    reasons: [{ code, reason }],
    chain: [],
    evidence: [],
    provenance: [],
  };
}

// The envelope for a whole read that could not be scored.
export function unknownEnvelope(kind, code, reason) {
  return { kind, overall: unknownResult(code, reason), reads: [], unchecked: [] };
}

function isEnvelope(body) {
  return (
    body !== null &&
    typeof body === 'object' &&
    !Array.isArray(body) &&
    typeof body.kind === 'string' &&
    body.overall !== null &&
    typeof body.overall === 'object' &&
    Array.isArray(body.reads) &&
    Array.isArray(body.unchecked)
  );
}

/**
 * Score one Gemini answer.
 *
 * @param {object} args
 * @param {'clause'|'tone'|'motive'} args.kind
 * @param {string} args.document      the text that was read
 * @param {object} args.answer        the Gemini JSON, unchanged
 * @param {string} [args.at]          a timestamp from the caller (never read from the clock here)
 * @param {string} [args.baseUrl]
 * @param {number} [args.timeoutMs]
 * @param {Function} [args.fetchImpl] injectable for tests
 * @returns {Promise<object>} the scored envelope; never throws
 */
export async function wrapRead({
  kind,
  document,
  answer,
  at,
  baseUrl = DEFAULT_BASE_URL,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  fetchImpl = globalThis.fetch,
} = {}) {
  if (!KINDS.includes(kind)) {
    return unknownEnvelope(String(kind), 'MALFORMED', `kind must be one of ${KINDS.join(', ')}`);
  }
  if (typeof document !== 'string' || document.trim() === '') {
    return unknownEnvelope(kind, 'MISSING_INPUT', 'the document text is empty');
  }
  if (answer === null || typeof answer !== 'object' || Array.isArray(answer)) {
    return unknownEnvelope(kind, 'MALFORMED', "the model's answer must be an object");
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchImpl(`${baseUrl}/wrap`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ kind, document, answer, at }),
      signal: controller.signal,
    });
    let body;
    try {
      body = await res.json();
    } catch {
      return unknownEnvelope(kind, 'UNVERIFIED_SOURCE',
        'the confidence service replied with something other than JSON, so the answer is unverified');
    }
    if (!isEnvelope(body)) {
      return unknownEnvelope(kind, 'UNVERIFIED_SOURCE',
        'the confidence service replied in an unexpected shape, so the answer is unverified');
    }
    return body;
  } catch (err) {
    if (err && err.name === 'AbortError') {
      return unknownEnvelope(kind, 'TIMEOUT',
        `the confidence service did not answer within ${timeoutMs} ms`);
    }
    return unknownEnvelope(kind, 'UNVERIFIED_SOURCE',
      'the confidence service could not be reached, so the answer is unverified');
  } finally {
    clearTimeout(timer);
  }
}
