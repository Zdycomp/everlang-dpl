import unittest
import threading
import importlib

from everlang.core.particle import EParticle, EquivalenceRange, PhiEqualizer
from everlang.core.phase_engine import PhaseEngine
from everlang.core.expect import ExpectGate
from everlang.core.archive import EArchive
from everlang.pipeline import EZPipeline
from everlang.quantum.entanglement import EntanglementSwapSystem

class TestEverlangCore(unittest.TestCase):
    def test_particle_confidence_bounds(self):
        p = EParticle("Test", 300)
        self.assertEqual(p.confidence, 256)
        p_z = EParticle("Zero", 0)
        self.assertTrue(p_z.is_z())

    def test_particle_numerical_guards(self):
        # NaN and Inf guards
        p_nan = EParticle("NanTest", float('nan'))
        self.assertEqual(p_nan.confidence, 0)
        self.assertTrue(p_nan.is_z())

        p_inf = EParticle("InfTest", float('inf'))
        self.assertEqual(p_inf.confidence, 0)

        p_str = EParticle("StringBad", "invalid_num")
        self.assertEqual(p_str.confidence, 0)

    def test_excel_phase_arithmetic(self):
        p_a = EParticle("A", 180)
        p_b = EParticle("B", 120)
        res = PhaseEngine.collide(p_a, p_b)
        self.assertEqual(res["outcome"], "EXCEL")
        self.assertEqual(res["particle"].confidence, 215)

    def test_z_contagion(self):
        p_a = EParticle("A", 200)
        p_z = EParticle("Z", 0)
        res = PhaseEngine.collide(p_a, p_z)
        self.assertEqual(res["outcome"], "Z_CONTAGION")
        self.assertEqual(res["particle"].confidence, 0)

    def test_pi_governor(self):
        eq_ok = EquivalenceRange(10.0, 30.0)
        self.assertEqual(eq_ok.evaluate_pi_governor(), "ACCEPTABLE")
        eq_wide = EquivalenceRange(0.0, 100.0)
        self.assertEqual(eq_wide.evaluate_pi_governor(), "APPROACHING_Z")

    def test_expect_gate_fallbacks(self):
        gate = ExpectGate("minConfidence", threshold=200)
        p_low = EParticle("LowConf", 100)
        eval_res = gate.evaluate(p_low)
        self.assertFalse(eval_res["passed"])

        p_fallback_z = gate.enforce_fallback(eval_res, "orZ")
        self.assertTrue(p_fallback_z.is_z())

        with self.assertRaises(ValueError):
            gate.enforce_fallback(eval_res, "orThrow")

    def test_multithreaded_race_conditions(self):
        """Stress test: 100 concurrent threads mutating EArchive & colliding particles."""
        archive = EArchive()
        errors = []

        def worker(thread_id):
            try:
                p = EParticle(f"Thread_{thread_id}", 150 + (thread_id % 50))
                archive.log_boundary_marker(f"Context_{thread_id}", p, "Concurrent_Test")
                archive.emulate_repair(f"Sig_{thread_id}", (thread_id % 3) + 1)
                archive.calculate_evolve_vector(200.0, 1.0, 1.618)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Encountered thread errors: {errors}")
        self.assertEqual(len(archive.boundary_markers), 100)
        self.assertEqual(len(archive.evolved_vectors), 100)

    def test_full_pipeline_execution(self):
        pipeline = EZPipeline()
        rule = EParticle("Rule", 200)
        res = pipeline.run("BUILD_101", "val x = 10", "Kotlin", rule)
        self.assertTrue(res["evolved"])
        self.assertGreater(res["final_particle"].confidence, 0)

    def test_pipeline_quarantines_memory_hazard(self):
        """A BAD_POINTER construct must be quarantined at Z and never evolved."""
        pipeline = EZPipeline()
        rule = EParticle("Rule", 220)
        res = pipeline.run("SNIP_Z", "void* p = BAD_POINTER;", "Clang_C", rule)
        self.assertEqual(res["examine_status"], "QUARANTINED_Z")
        self.assertTrue(res["final_particle"].is_z())
        self.assertFalse(res["evolved"])

    def test_equivalence_range_numerical_guard(self):
        # NaN / Inf bounds must degrade to APPROACHING_Z rather than propagate.
        eq_nan = EquivalenceRange(float("nan"), 10.0)
        self.assertEqual(eq_nan.width, 999.0)
        self.assertEqual(eq_nan.evaluate_pi_governor(), "APPROACHING_Z")

        eq_inf = EquivalenceRange(0.0, float("inf"))
        self.assertEqual(eq_inf.evaluate_pi_governor(), "APPROACHING_Z")

        eq_bad = EquivalenceRange("not_a_number", 10.0)
        self.assertEqual(eq_bad.evaluate_pi_governor(), "APPROACHING_Z")

    def test_phi_equalizer_balance(self):
        self.assertTrue(PhiEqualizer.is_balanced(5.0, 5.0))
        self.assertTrue(PhiEqualizer.is_balanced(5.0, 5.4))
        self.assertFalse(PhiEqualizer.is_balanced(5.0, 9.0))
        self.assertFalse(PhiEqualizer.is_balanced(float("nan"), 5.0))
        self.assertFalse(PhiEqualizer.is_balanced("bad", 5.0))

    def test_entanglement_swap_restores_z_particle(self):
        archive = EArchive()
        swap = EntanglementSwapSystem(archive)
        z_particle = EParticle("Alpha_Z", 0)
        anchor = EParticle("Beta_Anchor", 200)
        res = swap.execute_entanglement_swap(z_particle, anchor, velocity_c=0.95)
        self.assertEqual(res["outcome"], "NON_LOCAL_SWAP_RESTORED")
        # Confidence is recovered exactly from the non-local anchor particle.
        self.assertEqual(res["particle"].confidence, 200)
        self.assertGreater(res["gamma_factor"], 3.0)

    def test_benchmarks_are_importable(self):
        """Regression: benchmark scripts must import regardless of CWD.

        Previously several scripts hard-coded '/workspace/scratch/...' paths,
        so importing/running them raised ModuleNotFoundError.
        """
        benchmark_modules = [
            "ez_300_code_healing_benchmark",
            "ez_autonomous_agent_loop",
            "ez_container_ci_service",
            "ez_cpu_stress_test",
            "ez_financial_feed_simulation",
            "ez_llm_agent_loop",
            "ez_micro_containers",
        ]
        for name in benchmark_modules:
            with self.subTest(module=name):
                importlib.import_module(f"benchmarks.{name}")

if __name__ == "__main__":
    unittest.main()
