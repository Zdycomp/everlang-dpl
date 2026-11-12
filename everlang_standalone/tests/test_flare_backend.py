"""Smoke tests for the Flare backend (everlang.flare_backend).

Runs Python-shaped snippets through EZPipeline.run_python() -> Flare and
checks the result comes back with DPL confidence metadata. Flare is a
subset language (lowercase true/false, no break/continue); tests use
Flare-shaped source only.
"""

import unittest

from everlang.core.particle import EParticle
from everlang.flare_backend.executor import FlareExecutor
from everlang.pipeline import EZPipeline

RULE = EParticle("Rule<Math>", 200)


class TestFlareExecutor(unittest.TestCase):
    def test_print_expression(self):
        res = FlareExecutor().run("print(2 + 3)")
        self.assertTrue(res.ok)
        self.assertEqual(res.stdout.strip(), "5")
        self.assertEqual(res.particle.confidence, 256)

    def test_fib(self):
        src = (
            "def fib(n):\n"
            "    if n < 2:\n"
            "        return n\n"
            "    return fib(n - 1) + fib(n - 2)\n"
            "print(fib(20))\n"
        )
        res = FlareExecutor().run(src)
        self.assertTrue(res.ok)
        self.assertEqual(res.stdout.strip(), "6765")
        self.assertEqual(res.particle.confidence, 256)

    def test_division_by_zero_is_z(self):
        res = FlareExecutor().run("print(1 / 0)")
        self.assertFalse(res.ok)
        self.assertEqual(res.particle.confidence, 0)
        self.assertTrue(res.particle.is_z())
        self.assertIn("division by zero", (res.error or "").lower())

    def test_compile_error_is_z(self):
        res = FlareExecutor().run("def broken(:\n    print(1)\n")
        self.assertFalse(res.ok)
        self.assertEqual(res.particle.confidence, 0)
        self.assertTrue(res.error)

    def test_multifile_import_via_extra_files(self):
        # Flare imports are namespace-less AST merges: imported names are
        # called bare, not qualified (import mylib -> twice(), not mylib.twice()).
        # (Function must not be named `double` — that collides with C's
        # `double` keyword in the generated code; standalone Flare fails
        # identically, so this is a Flare limit, not an adapter bug.)
        lib = "def twice(x):\n    return x * 2\n"
        res = FlareExecutor().run(
            "import mylib\nprint(twice(21))\n",
            extra_files={"mylib.fl": lib})
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.stdout.strip(), "42")
        self.assertEqual(res.particle.confidence, 256)


class TestPipelineRunPython(unittest.TestCase):
    def test_sum_loop_through_pipeline(self):
        src = (
            "total = 0\n"
            "i = 0\n"
            "while i < 1000:\n"
            "    total = total + i\n"
            "    i = i + 1\n"
            "print(total)\n"
        )
        res = EZPipeline().run_python("SNIP_FLARE_001", src, RULE)
        self.assertTrue(res["executed"])
        self.assertEqual(res["flare_stdout"].strip(), "499500")
        self.assertEqual(res["final_particle"].confidence, 256)
        self.assertEqual(res["examine_status"], "NORMALIZED")

    def test_runtime_failure_quarantined_by_pipeline(self):
        res = EZPipeline().run_python("SNIP_FLARE_002", "print(1 / 0)", RULE)
        self.assertTrue(res["executed"])
        self.assertEqual(res["final_particle"].confidence, 0)
        self.assertTrue(res["final_particle"].is_z())

    def test_quarantined_snippet_skips_execution(self):
        res = EZPipeline().run_python(
            "SNIP_FLARE_003", "char *ptr = BAD_POINTER_NULL", RULE)
        self.assertFalse(res["executed"])
        self.assertEqual(res["final_particle"].confidence, 0)


if __name__ == "__main__":
    unittest.main()
