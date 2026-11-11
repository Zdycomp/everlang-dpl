import unittest
from everlang.core.particle import EParticle, EquivalenceRange, PhiEqualizer
from everlang.core.phase_engine import PhaseEngine
from everlang.core.archive import EArchive
from everlang.quantum.entanglement import EntanglementSwapSystem
from everlang.biocomputing.quaternary import QuaternaryTranslationLayer
from everlang.biocomputing.dna_engine import BioPhaseEngine
from everlang.biocomputing.vibe_compiler import VibeDnaCompiler

class TestEverlangCoreSuite(unittest.TestCase):
    def setUp(self):
        self.archive = EArchive()

    def test_01_eparticle_bounding_and_quarantine(self):
        p_valid = EParticle("Alpha", 220)
        self.assertEqual(p_valid.confidence, 220)
        self.assertFalse(p_valid.is_z())

        p_over = EParticle("Over", 300)
        self.assertEqual(p_over.confidence, 256)

        p_neg = EParticle("Under", -50)
        self.assertEqual(p_neg.confidence, 0)
        self.assertTrue(p_neg.is_z())

        p_nan = EParticle("Invalid", "NOT_A_NUMBER")
        self.assertEqual(p_nan.confidence, 0)
        self.assertTrue(p_nan.is_z())

    def test_02_pauli_collision_trigger_order(self):
        # 1. Z-Contagion check
        p_z = EParticle("Z_Particle", 0)
        p_high = EParticle("High_Particle", 250)
        res_z = PhaseEngine.collide(p_z, p_high)
        self.assertEqual(res_z["outcome"], "Z_CONTAGION")
        self.assertTrue(res_z["particle"].is_z())

        # 2. Expel check (ratio > 2*phi = ~3.236 and max_conf >= 81)
        p_strong = EParticle("Strong", 220)
        p_weak = EParticle("Weak", 50)
        res_expel = PhaseEngine.collide(p_strong, p_weak)
        self.assertEqual(res_expel["outcome"], "EXPEL")
        self.assertEqual(res_expel["particle"].value, "Strong")

        # 3. Excel check (gap < 81)
        p1 = EParticle("CodeA", 200)
        p2 = EParticle("CodeB", 180)
        res_excel = PhaseEngine.collide(p1, p2)
        self.assertEqual(res_excel["outcome"], "EXCEL")
        self.assertGreater(res_excel["particle"].confidence, 200)

        # 4. Repel check
        p_dom1 = EParticle("Domain1", 200)
        p_dom2 = EParticle("Domain2", 110)
        res_repel = PhaseEngine.collide(p_dom1, p_dom2)
        self.assertEqual(res_repel["outcome"], "REPEL")

    def test_03_emulate_repair_and_archive(self):
        repair_1 = self.archive.emulate_repair("ParseError_01", 1)
        self.assertEqual(repair_1.confidence, 220)

        repair_3 = self.archive.emulate_repair("ParseError_03", 3)
        self.assertEqual(repair_3.confidence, 160)

        repair_fail = self.archive.emulate_repair("ParseError_05", 5)
        self.assertTrue(repair_fail.is_z())

    def test_04_pi_governor_and_phi_equalizer(self):
        range_acceptable = EquivalenceRange(10.0, 30.0)
        self.assertEqual(range_acceptable.evaluate_pi_governor(), "ACCEPTABLE")

        range_wide = EquivalenceRange(10.0, 80.0)
        self.assertEqual(range_wide.evaluate_pi_governor(), "WIDE_ENUMERATE")

        range_z = EquivalenceRange(10.0, 150.0)
        self.assertEqual(range_z.evaluate_pi_governor(), "APPROACHING_Z")

        self.assertTrue(PhiEqualizer.is_balanced(5.0, 5.2, tolerance=0.5))
        self.assertFalse(PhiEqualizer.is_balanced(5.0, 8.0, tolerance=0.5))

    def test_05_entanglement_swap_restoration(self):
        swap_sys = EntanglementSwapSystem(self.archive)
        cell_alpha_z = EParticle("CellAlpha_Z", 0)
        cell_beta = EParticle("CellBeta_Anchor", 256)
        res = swap_sys.execute_entanglement_swap(cell_alpha_z, cell_beta, velocity_c=0.95)
        self.assertEqual(res["outcome"], "NON_LOCAL_SWAP_RESTORED")
        self.assertEqual(res["particle"].confidence, 256)

    def test_06_quaternary_translation_lossless_parity(self):
        translator = QuaternaryTranslationLayer()
        original_bytes = bytearray([0, 42, 128, 185, 255])
        dna_str = translator.bytes_to_DNA(original_bytes)
        self.assertEqual(len(dna_str), 20)  # 5 bytes * 4 bases/byte = 20 bases
        decoded_bytes = translator.DNA_to_bytes(dna_str)
        self.assertEqual(list(original_bytes), list(decoded_bytes))

    def test_07_biophase_dna_strand_displacement(self):
        gate = BioPhaseEngine("ATCGATCG")
        # Perfect complement
        p_perf = EParticle("TAGCTAGC", 250)
        res_perf = gate.process_displacement(p_perf)
        self.assertEqual(res_perf["calculated_affinity"], 256)
        self.assertTrue(res_perf["gate_displaced"])

        # Mutated strand within 70% healing threshold (6/8 matches = 192/256)
        p_mut = EParticle("TAGCTAAA", 200)
        res_mut = gate.process_displacement(p_mut)
        self.assertEqual(res_mut["calculated_affinity"], 192)
        self.assertTrue(res_mut["gate_displaced"])

        # Severe mutation (2/8 matches = 64/256) -> Gate Lock
        p_bad = EParticle("TTTTTTTT", 150)
        res_bad = gate.process_displacement(p_bad)
        self.assertEqual(res_bad["calculated_affinity"], 64)
        self.assertFalse(res_bad["gate_displaced"])

    def test_08_vibe_dna_compiler_execution(self):
        compiler = VibeDnaCompiler()
        cycle_1_results = compiler.execute_vibe_pulse_cycle(cycle=1)
        self.assertEqual(len(cycle_1_results), 3)
        for res in cycle_1_results:
            self.assertTrue(res["parity_match"])
            self.assertEqual(res["status"], "STATE_SHIFT_SUCCESS")

if __name__ == "__main__":
    unittest.main()
