"""The adapter the Express server calls: pure handler, and real loopback HTTP."""

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from everconf.adapter import handle, make_server, MAX_BODY_BYTES  # noqa: E402
from everconf import __version__  # noqa: E402

DOC = "Tenant shall indemnify Landlord for any and all claims regardless of fault."
GEMINI = {
    "overall_risk_score": 88,
    "risk_tier": "CRITICAL",
    "summary": "One unilateral indemnity.",
    "findings": [{"verbatim_text": "indemnify Landlord for any and all claims regardless of fault",
                  "category": "Unilateral Indemnification", "risk_level": "CRITICAL",
                  "recommendation": "Strike the indemnity or cap it."}],
}


class Handler(unittest.TestCase):
    def test_gemini_schema_is_mapped_and_scored(self):
        status, reply = handle({"kind": "clause", "document": DOC, "answer": GEMINI,
                                "at": "2026-11-13T03:00:00Z"})
        self.assertEqual(status, 200)
        read = reply["reads"][0]
        self.assertEqual(read["quote"], GEMINI["findings"][0]["verbatim_text"])
        self.assertEqual(read["ever"]["label"], "pretty sure")
        self.assertEqual(read["model"]["recommendation"], "Strike the indemnity or cap it.")

    def test_whole_document_fields_are_scored_too(self):
        _, reply = handle({"kind": "clause", "document": DOC, "answer": GEMINI})
        self.assertEqual(reply["tier"]["value"], "CRITICAL")
        self.assertEqual(reply["tier"]["label"], "not sure")
        self.assertEqual(reply["model_risk_score"]["value"], 88)
        self.assertEqual(reply["summary"]["value"], "One unilateral indemnity.")

    def test_bad_bodies_are_400_with_an_unknown_not_null(self):
        for body in (None, [], "x", {"kind": "mood"}, {"kind": "clause", "answer": []},
                     {"kind": "clause", "answer": {}, "at": ""}):
            status, reply = handle(body)
            self.assertEqual(status, 400, repr(body))
            self.assertEqual(reply["overall"]["state"], "unknown")

    def test_missing_document_is_an_unknown_read(self):
        status, reply = handle({"kind": "clause", "answer": GEMINI})
        self.assertEqual(status, 200)
        self.assertEqual(reply["overall"]["reasons"][0]["code"], "MISSING_INPUT")


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, data: bytes, path="/wrap"):
        req = urllib.request.Request(self.base + path, data=data, method="POST",
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            finally:
                e.close()

    def test_health(self):
        with urllib.request.urlopen(self.base + "/health", timeout=5) as r:
            body = json.loads(r.read())
        self.assertEqual(body, {"status": "online", "service": "everconf", "version": __version__})

    def test_wrap_round_trip(self):
        status, reply = self._post(json.dumps({"kind": "clause", "document": DOC,
                                               "answer": GEMINI}).encode())
        self.assertEqual(status, 200)
        self.assertEqual(reply["reads"][0]["ever"]["score"], 180)

    def test_not_json_is_400_unknown(self):
        status, reply = self._post(b"<html>")
        self.assertEqual(status, 400)
        self.assertEqual(reply["overall"]["reasons"][0]["code"], "MALFORMED")

    def test_empty_body_is_400_unknown(self):
        status, reply = self._post(b"")
        self.assertEqual(status, 400)
        self.assertEqual(reply["overall"]["reasons"][0]["code"], "MISSING_INPUT")

    def test_unknown_route_is_404_unknown(self):
        status, reply = self._post(b"{}", path="/nope")
        self.assertEqual(status, 404)
        self.assertEqual(reply["overall"]["state"], "unknown")

    def test_oversize_body_is_refused_before_it_is_read(self):
        import http.client
        host, port = self.server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.putrequest("POST", "/wrap")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
        conn.endheaders()                       # headers only: the body is never sent
        resp = conn.getresponse()
        self.assertEqual(resp.status, 413)
        resp.read()
        conn.close()

    def test_only_loopback_is_allowed(self):
        with self.assertRaises(ValueError):
            make_server("0.0.0.0", 0)
        with self.assertRaises(ValueError):
            make_server("::1", 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
