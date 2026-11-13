"""The documentation cannot drift from the code.

Every ```json example=<name>``` block in docs/JSON.md must equal what the
named function in json_examples.py returns today, and must contain no null.
"""

import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from json_examples import EXAMPLES  # noqa: E402

DOC = os.path.join(HERE, "..", "docs", "JSON.md")
BLOCK = re.compile(r"```json example=([a-z_]+)\n(.*?)\n```", re.S)


def _has_null(v):
    if v is None:
        return True
    if isinstance(v, dict):
        return any(_has_null(x) for x in v.values())
    if isinstance(v, list):
        return any(_has_null(x) for x in v)
    return False


class JsonDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(DOC, encoding="utf-8") as f:
            cls.text = f.read()
        cls.blocks = {name: body for name, body in BLOCK.findall(cls.text)}

    def test_every_example_is_documented(self):
        self.assertEqual(set(self.blocks), set(EXAMPLES))

    def test_every_documented_example_matches_the_code(self):
        for name, fn in EXAMPLES.items():
            with self.subTest(example=name):
                documented = json.loads(self.blocks[name])
                self.assertEqual(documented, json.loads(json.dumps(fn())))

    def test_no_documented_example_contains_null(self):
        for name, body in self.blocks.items():
            self.assertNotIn("null", body.lower(), name)
            self.assertFalse(_has_null(json.loads(body)), name)

    def test_label_table_matches_the_code(self):
        from everconf.result import label_for
        self.assertIn("224 to 256", self.text)
        self.assertEqual(label_for(224), "very sure")
        self.assertEqual(label_for(160), "pretty sure")
        self.assertEqual(label_for(159), "not sure")
        self.assertEqual(label_for(0), "can't tell")


if __name__ == "__main__":
    unittest.main(verbosity=1)
