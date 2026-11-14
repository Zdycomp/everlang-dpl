"""HTTP adapter: the Express server posts each Gemini answer here before it
reaches the phone.

    POST /wrap    body: {"kind": "clause"|"tone"|"motive", "document": "...",
                         "answer": {...Gemini JSON...}, "at": "<optional stamp>"}
                  reply: the scored envelope (see reads.py)
    GET  /health  reply: {"status": "online", "service": "everconf", "version": ...}

The service listens on 127.0.0.1 only. A bad request is answered with an
Unknown (MALFORMED) in the same shape, never with an empty body or null.

Run it:  python3 -m everconf.adapter --port 8787
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from . import C, INTAKE, MALFORMED, MISSING_INPUT, NOT_RECORDED, Unknown, __version__
from .reads import KINDS, wrap_read
from .result import to_result

MAX_BODY_BYTES = 30 * 1024 * 1024   # matches the Express server's 30 mb JSON limit


def _envelope_unknown(kind: str, code: str, reason: str) -> dict:
    return {"kind": kind, "overall": to_result(Unknown(code, reason)),
            "reads": [], "unchecked": []}


def _model_fields(answer: Dict[str, Any], at: str) -> Dict[str, Any]:
    """Score the model's own whole-document fields: tier, score and summary.

    None of these can be checked against the text, so each is a third-party
    read at INTAKE with that stated.
    """
    out: Dict[str, Any] = {}
    note_src = ("INTAKE_SOURCE", "the model's own judgement; a third-party source is at most 120")
    note_unc = ("UNCORROBORATED", "no local rule scores the whole document")

    tier = answer.get("risk_tier")
    if isinstance(tier, str) and tier.strip():
        out["tier"] = to_result(C(tier.strip(), INTAKE, source="model answer", at=at),
                                notes=[note_src, note_unc])
    else:
        out["tier"] = to_result(Unknown(MISSING_INPUT, "the model gave no risk tier"))

    score = answer.get("overall_risk_score")
    if isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100:
        out["model_risk_score"] = to_result(C(score, INTAKE, source="model answer", at=at),
                                 notes=[note_src, note_unc])
    else:
        out["model_risk_score"] = to_result(Unknown(MALFORMED,
                                         "the model's risk score is missing or not 0 to 100"))

    summary = answer.get("summary")
    if isinstance(summary, str) and summary.strip():
        out["summary"] = to_result(C(summary.strip(), INTAKE, source="model answer", at=at),
                                   notes=[note_src])
    else:
        out["summary"] = to_result(Unknown(MISSING_INPUT, "the model gave no summary"))
    return out


def _as_read_answer(answer: Dict[str, Any]) -> Dict[str, Any]:
    """Map the Gemini schema (verbatim_text) onto the read shape (quote)."""
    findings = answer.get("findings", [])
    if not isinstance(findings, list):
        return {"findings": findings}
    mapped = []
    for f in findings:
        if isinstance(f, dict) and "quote" not in f and "verbatim_text" in f:
            f = dict(f)
            f["quote"] = f.pop("verbatim_text")
        mapped.append(f)
    return {"findings": mapped}


def handle(payload: Any) -> Tuple[int, dict]:
    """Pure request handler: a parsed JSON body in, (status, reply) out."""
    if not isinstance(payload, dict):
        return 400, _envelope_unknown("clause", MALFORMED, "the body must be a JSON object")
    kind = payload.get("kind")
    if kind not in KINDS:
        return 400, _envelope_unknown(str(kind), MALFORMED, f"kind must be one of {KINDS}")
    at = payload.get("at", NOT_RECORDED)
    if not isinstance(at, str) or not at.strip():
        return 400, _envelope_unknown(kind, MALFORMED, "'at' must be a non-empty string")
    answer = payload.get("answer")
    if not isinstance(answer, dict):
        return 400, _envelope_unknown(kind, MALFORMED, "'answer' must be a JSON object")

    reply = wrap_read(kind, payload.get("document"), _as_read_answer(answer), at=at)
    reply.update(_model_fields(answer, at))
    return 200, reply


def make_server(host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    # IPv4 loopback only: the server is an AF_INET ThreadingHTTPServer, which cannot bind ::1.
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("the adapter listens on loopback only")

    class Handler(BaseHTTPRequestHandler):
        server_version = f"everconf/{__version__}"

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 (http.server naming)
            if self.path == "/health":
                self._send(200, {"status": "online", "service": "everconf",
                                 "version": __version__})
            else:
                self._send(404, _envelope_unknown("clause", MALFORMED, "no such route"))

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/wrap":
                self._send(404, _envelope_unknown("clause", MALFORMED, "no such route"))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400, _envelope_unknown("clause", MALFORMED, "bad Content-Length"))
                return
            if length <= 0:
                self._send(400, _envelope_unknown("clause", MISSING_INPUT, "the body is empty"))
                return
            if length > MAX_BODY_BYTES:
                self._send(413, _envelope_unknown("clause", MALFORMED,
                                                  "the body is larger than 30 mb"))
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, _envelope_unknown("clause", MALFORMED, "the body is not JSON"))
                return
            status, reply = handle(payload)
            self._send(status, reply)

        def log_message(self, fmt: str, *args) -> None:  # keep the phone's data out of logs
            return

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="everconf adapter for the Express server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    server = make_server(args.host, args.port)
    print(f"everconf adapter listening on {args.host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
