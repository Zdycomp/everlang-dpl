import unittest
from everlang.core.particle import EParticle
from everlang.biocomputing.quaternary import QuaternaryTranslationLayer
from everlang.biocomputing.dna_engine import BioPhaseEngine
from everlang.biocomputing.vibe_compiler import VibeDnaCompiler

COMP = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}


def complement(seq):
    return "".join(COMP[b] for b in seq)


class TestQuaternaryTranslationLayer(unittest.TestCase):
    def setUp(self):
        self.q = QuaternaryTranslationLayer()

    def test_round_trip_all_byte_values(self):
        data = bytes(range(256))
        dna = self.q.bytes_to_DNA(data)
        self.assertEqual(self.q.DNA_to_bytes(dna), bytearray(data))
        for b in range(256):
            self.assertEqual(self.q.DNA_to_bytes(self.q.bytes_to_DNA([b])), bytearray([b]))

    def test_base_mapping(self):
        self.assertEqual(self.q.bytes_to_DNA([0b00011011]), "ATCG")
        self.assertEqual(self.q.bytes_to_DNA([0x00]), "AAAA")
        self.assertEqual(self.q.bytes_to_DNA([0xFF]), "GGGG")
        self.assertEqual(self.q.bytes_to_DNA([0b01010101]), "TTTT")
        self.assertEqual(self.q.bytes_to_DNA([0b10101010]), "CCCC")

    def test_four_bases_per_byte(self):
        for n in (0, 1, 5, 32):
            self.assertEqual(len(self.q.bytes_to_DNA(bytes(n))), 4 * n)

    def test_bytes_to_dna_clamps_out_of_range(self):
        self.assertEqual(self.q.bytes_to_DNA([-5, 300, 1000]), self.q.bytes_to_DNA([0, 255, 255]))
        self.assertEqual(self.q.bytes_to_DNA([256]), "GGGG")
        self.assertEqual(self.q.bytes_to_DNA([-1]), "AAAA")

    def test_dna_to_bytes_ignores_spaces_and_case(self):
        self.assertEqual(self.q.DNA_to_bytes("atcg"), bytearray([0b00011011]))
        self.assertEqual(self.q.DNA_to_bytes("AT CG AA AA"), bytearray([0b00011011, 0]))

    def test_dna_to_bytes_drops_trailing_incomplete_byte(self):
        self.assertEqual(self.q.DNA_to_bytes("ATCGA"), bytearray([0b00011011]))
        self.assertEqual(self.q.DNA_to_bytes("ATC"), bytearray())
        self.assertEqual(self.q.DNA_to_bytes(""), bytearray())


class TestBioPhaseEngine(unittest.TestCase):
    def test_affinity_zero_on_empty_gate(self):
        self.assertEqual(BioPhaseEngine("").calculate_hybridization_affinity(""), 0)
        self.assertEqual(BioPhaseEngine("   ").calculate_hybridization_affinity("ATCG"), 0)

    def test_affinity_zero_on_length_mismatch(self):
        e = BioPhaseEngine("ATCGATCG")
        self.assertEqual(e.calculate_hybridization_affinity("TAGCTAG"), 0)
        self.assertEqual(e.calculate_hybridization_affinity("TAGCTAGCT"), 0)

    def test_perfect_complement_is_256(self):
        gate = "ATCGGCTAATCGGCTA"
        self.assertEqual(BioPhaseEngine(gate).calculate_hybridization_affinity(complement(gate)), 256)

    def test_no_match_is_zero(self):
        # identical strand is never complementary
        self.assertEqual(BioPhaseEngine("ATCG").calculate_hybridization_affinity("ATCG"), 0)

    def test_partial_affinity_values(self):
        e = BioPhaseEngine("A" * 16)
        self.assertEqual(e.calculate_hybridization_affinity("T" * 12 + "A" * 4), 192)
        self.assertEqual(e.calculate_hybridization_affinity("T" * 11 + "A" * 5), 176)

    def test_normalisation_lowercase_and_whitespace(self):
        e = BioPhaseEngine("  atcg \n")
        self.assertEqual(e.gate_sequence, "ATCG")
        self.assertEqual(e.calculate_hybridization_affinity(" tagc\t"), 256)

    def _displace(self, gate, strand, conf):
        return BioPhaseEngine(gate).process_displacement(EParticle(strand, conf))

    def test_threshold_affinity_boundary(self):
        # 20-base gate: 15 matches -> 192 (>=180), 14 matches -> 179 (<180)
        gate = "A" * 20
        ok = "T" * 15 + "A" * 5
        bad = "T" * 14 + "A" * 6
        r_ok = self._displace(gate, ok, 200)
        r_bad = self._displace(gate, bad, 200)
        self.assertEqual(r_ok["calculated_affinity"], 192)
        self.assertTrue(r_ok["gate_displaced"])
        self.assertEqual(r_bad["calculated_affinity"], 179)
        self.assertFalse(r_bad["gate_displaced"])

    def test_threshold_8_base_gate(self):
        gate = "A" * 8
        self.assertTrue(self._displace(gate, "T" * 6 + "AA", 200)["gate_displaced"])   # 192
        self.assertFalse(self._displace(gate, "T" * 5 + "AAA", 200)["gate_displaced"])  # 160

    def test_confidence_boundary(self):
        gate = "ATCGATCG"
        strand = complement(gate)
        self.assertFalse(self._displace(gate, strand, 128)["gate_displaced"])
        self.assertTrue(self._displace(gate, strand, 129)["gate_displaced"])

    def test_result_shape_and_status(self):
        p = EParticle("TAGC", 200)
        r = BioPhaseEngine("ATCG").process_displacement(p)
        self.assertIs(r["input_evaluated"], p)
        self.assertTrue(r["gate_displaced"])
        self.assertIn("SUCCESS", r["status"])
        r2 = BioPhaseEngine("ATCG").process_displacement(EParticle("TAGC", 10))
        self.assertFalse(r2["gate_displaced"])
        self.assertIn("Locked", r2["status"])


class TestVibeDnaCompiler(unittest.TestCase):
    # Note: vibe payload bytes depend on hash() of str (PYTHONHASHSEED), so
    # nothing here asserts specific DNA strings.
    # Note: in cycle 3 Child_Beta2 currently receives a gate shorter than its
    # strand (10 + 3 = 13 vs 16 bases), so affinity is 0 and the gate locks.
    # That is current behaviour, deliberately NOT asserted here.

    def test_each_cycle_returns_three_results(self):
        c = VibeDnaCompiler()
        for cycle in (1, 2, 3):
            res = c.execute_vibe_pulse_cycle(cycle)
            self.assertEqual(len(res), 3)
            self.assertEqual([r["cell_name"] for r in res],
                             ["Child_Alpha1", "Child_Beta2", "Child_Omega3"])

    def test_parity_match_cycles_1_to_3(self):
        c = VibeDnaCompiler()
        for cycle in (1, 2, 3):
            for r in c.execute_vibe_pulse_cycle(cycle):
                self.assertTrue(r["parity_match"])
                self.assertEqual(r["raw_bytes"], r["decoded_bytes"])
                self.assertEqual(len(r["compiled_dna"]), 16)

    def test_evolved_confidence_bounded(self):
        c = VibeDnaCompiler()
        for cycle in (1, 2, 3, 4, 5, 6):
            for r in c.execute_vibe_pulse_cycle(cycle):
                self.assertGreaterEqual(r["evolved_confidence"], 0)
                self.assertLessEqual(r["evolved_confidence"], 256)

    def test_confidence_rises_10_on_displacement_falls_30_on_lock(self):
        c = VibeDnaCompiler()
        for cycle in (1, 2, 3, 4):
            before = {ch.name: ch.current_particle.confidence for ch in c.child_cells}
            results = c.execute_vibe_pulse_cycle(cycle)
            for r in results:
                prev = before[r["cell_name"]]
                if r["gate_displaced"]:
                    self.assertEqual(r["evolved_confidence"], min(256, prev + 10))
                    self.assertEqual(r["status"], "STATE_SHIFT_SUCCESS")
                else:
                    self.assertEqual(r["evolved_confidence"], max(0, prev - 30))
                    self.assertEqual(r["status"], "GATE_LOCKED_Z")
            after = {ch.name: ch.current_particle.confidence for ch in c.child_cells}
            self.assertEqual(after, {r["cell_name"]: r["evolved_confidence"] for r in results})

    def test_cycle1_all_cells_displace(self):
        # Gates are exact complements in cycle 1 and initial confidences > 128.
        res = VibeDnaCompiler().execute_vibe_pulse_cycle(1)
        for r in res:
            self.assertEqual(r["affinity_score"], 256)
            self.assertTrue(r["gate_displaced"])


if __name__ == "__main__":
    unittest.main()
