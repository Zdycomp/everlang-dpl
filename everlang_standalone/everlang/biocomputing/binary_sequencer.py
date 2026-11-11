"""
Binary-backed DNA sequencer.

Composes the existing biocomputing stages instead of defining new ones:
- ``QuaternaryTranslationLayer``: 2 bits per base (A=00, T=01, C=10, G=11),
  most significant bits first, so one byte is always four bases.
- ``DnaSequencer``: the lexer/parser pass over the resulting strand, giving
  codon triplets, GC content and validity.
- ``BioPhaseEngine``: Watson-Crick affinity of a strand against a gate.

The only new mapping here is the byte-to-strand framing, which is the
existing translator's own output. Nothing else about DNA is modeled.
"""

from typing import Any, Dict, Union

from .quaternary import QuaternaryTranslationLayer
from .dna_engine import BioPhaseEngine
from .sequencer import DnaSequencer

BASES_PER_BYTE = 4


class BinarySequencer:
    """Encodes binary data as a DNA strand and sequences the result."""

    def __init__(self) -> None:
        self.translator: QuaternaryTranslationLayer = QuaternaryTranslationLayer()
        self.sequencer: DnaSequencer = DnaSequencer()

    def sequence(self, data: Union[bytes, bytearray]) -> Dict[str, Any]:
        """Encode ``data`` as a strand and return the sequencing result.

        Keys: dna, byte_count, codons, trailing_partial, gc_content,
        round_trip (decoding the strand gives back ``data`` exactly).
        """
        data = bytes(data)
        if not data:
            return {
                "dna": "",
                "byte_count": 0,
                "codons": [],
                "trailing_partial": (),
                "gc_content": None,
                "round_trip": True,
            }

        dna = self.translator.bytes_to_DNA(data)
        result = self.sequencer.run(dna)
        return {
            "dna": dna,
            "byte_count": len(data),
            "codons": result["codons"],
            "trailing_partial": result["trailing_partial"],
            "gc_content": result["gc_content"],
            "round_trip": self.decode(dna) == data,
        }

    def decode(self, dna: str) -> bytes:
        """Decode a strand produced by ``sequence`` back into bytes.

        Raises ValueError if the strand contains non-ATCG characters or does
        not hold a whole number of bytes. The translator alone would drop
        both silently, so they are checked here.
        """
        if not "".join(dna.split()):
            # sequence(b"") yields an empty strand, so the empty strand must decode to b"".
            return b""
        result = self.sequencer.run(dna)
        if result["lexer_errors"]:
            bad = "".join(tok.base for tok in result["lexer_errors"])
            raise ValueError(f"strand contains non-ATCG characters: {bad!r}")
        if len(result["pairs"]) % BASES_PER_BYTE != 0:
            raise ValueError(
                f"strand length {len(result['pairs'])} is not a multiple of {BASES_PER_BYTE}"
            )
        return bytes(self.translator.DNA_to_bytes(dna))

    def affinity(self, dna: str, gate: str) -> int:
        """Return the 0-256 hybridization affinity of ``dna`` against ``gate``."""
        return BioPhaseEngine(gate).calculate_hybridization_affinity(dna)
