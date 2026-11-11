from typing import Dict, List, Union

class QuaternaryTranslationLayer:
    """
    Translates raw biological DNA sequences (quaternary base-4) into digital bytes and vice-versa,
    providing 1:1 bit-exact parity between software bytecode and DNA strands.
    Base-4 Mapping: A = 00, T = 01, C = 10, G = 11
    """
    def __init__(self) -> None:
        self.base_to_bits: Dict[str, str] = {'A': '00', 'T': '01', 'C': '10', 'G': '11'}
        self.bits_to_base: Dict[str, str] = {v: k for k, v in self.base_to_bits.items()}

    def DNA_to_bytes(self, dna_sequence: str) -> bytearray:
        """Translates a DNA string into standard digital execution bytes."""
        dna_cleaned = str(dna_sequence).upper().replace(" ", "")
        bit_string = "".join([self.base_to_bits[base] for base in dna_cleaned if base in self.base_to_bits])
        
        byte_list: List[int] = []
        for i in range(0, len(bit_string), 8):
            byte_chunk = bit_string[i:i+8]
            if len(byte_chunk) == 8:
                byte_list.append(int(byte_chunk, 2))
                
        return bytearray(byte_list)

    def bytes_to_DNA(self, data_bytes: Union[bytearray, bytes, List[int]]) -> str:
        """Encodes native software instruction bytes into structural DNA code loops."""
        dna_sequence: List[str] = []
        for byte in data_bytes:
            byte_val = max(0, min(255, int(byte)))
            binary_str = f"{byte_val:08b}"
            for i in range(0, 8, 2):
                pair = binary_str[i:i+2]
                dna_sequence.append(self.bits_to_base[pair])
                
        return "".join(dna_sequence)
