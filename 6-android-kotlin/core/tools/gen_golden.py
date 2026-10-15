#!/usr/bin/env python3
"""Generate core/src/test/resources/golden.tsv from the Python reference (stdlib only).

Run from the 6-android-kotlin project root:

    python3 core/tools/gen_golden.py

Every expected value is produced by calling the Python reference in
everlang_standalone/everlang/biocomputing (the parity spec). Nothing is
re-derived here. The inputs are seeded, so regeneration is deterministic.

Line format (always four tab-separated fields; arg2 is empty when unused):

    op <TAB> arg1 <TAB> arg2 <TAB> expected

Encodings:
  String argument   UTF-16BE hex of the exact code units. Lone surrogates survive.
                    A Python str whose adjacent surrogate code points would merge
                    into one Kotlin code point is not generated (checked here).
  bytes argument    lowercase hex.
  Text output       lowercase hex of its ASCII bytes (the generator asserts ASCII).
  bytes output      lowercase hex.
  Raised exception  the plain text ERR:<ExceptionClass>, which is never hex.

Ops:
  quat.dna_to_bytes  arg1=dna                 expected=bytes          Quaternary.DNA_to_bytes
  quat.bytes_to_dna  arg1=bytes               expected=dna text       QuaternaryTranslationLayer.bytes_to_DNA
  seq.run            arg1=raw                 expected=canonical      DnaSequencer().run; ERR:DnaSyntaxError
  bin.sequence       arg1=bytes               expected=canonical      BinarySequencer().sequence
  bin.decode         arg1=dna                 expected=bytes          BinarySequencer().decode; ERR:ValueError
  bin.affinity       arg1=dna  arg2=gate      expected=decimal        BinarySequencer().affinity(dna, gate)
  engine.affinity    arg1=gate arg2=input     expected=decimal        BioPhaseEngine(gate).calculate_hybridization_affinity(input)

Canonical text (ASCII, compared exactly by the Kotlin test):
  SequenceResult  T[..];P[..];C[..];R[..];LE[..];PE[..];GC=<f64 bits hex or ->;V=<0|1>
  StrandReport    DNA=<dna>;N=<byte_count>;C[..];R[..];GC=<f64 bits hex or ->;RT=<0|1>
  token           t<base>:<index>:<valid>
  pair            p<index>:<base>:<complement or ->:<valid>
  codon           c<start_index>:<pair>|<pair>|<pair>
  <base>, <complement> are lowercase hex code points. GC is the big-endian IEEE-754
  bit pattern of the float, 16 hex digits, so the comparison is bit-exact.

Projection (documented in BaseToken): the Kotlin base is a Char, so a code point above
U+FFFF cannot be stored. The reference's base for such a token is written as U+FFFD
here, and the Kotlin port does the same. Index, validity, complement and counts are
not projected.
"""

import random
import struct
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
PROJECT = CORE.parent
STANDALONE = PROJECT.parent / "everlang_standalone"
OUT = CORE / "src" / "test" / "resources" / "golden.tsv"
MIN_CASES = 3000
SEED = 20260615

sys.path.insert(0, str(STANDALONE))
from everlang.biocomputing.binary_sequencer import BinarySequencer  # noqa: E402
from everlang.biocomputing.dna_engine import BioPhaseEngine  # noqa: E402
from everlang.biocomputing.quaternary import QuaternaryTranslationLayer  # noqa: E402
from everlang.biocomputing.sequencer import DnaSequencer, DnaSyntaxError  # noqa: E402


def require(condition, message):
    if not condition:
        raise SystemExit(f"gen_golden: {message}")


def code_points_from_units(units):
    """Combine UTF-16 code units into code points the way java.lang.String.codePointAt does."""
    out = []
    i = 0
    while i < len(units):
        u = units[i]
        if 0xD800 <= u <= 0xDBFF and i + 1 < len(units) and 0xDC00 <= units[i + 1] <= 0xDFFF:
            out.append(0x10000 + ((u - 0xD800) << 10) + (units[i + 1] - 0xDC00))
            i += 2
        else:
            out.append(u)
            i += 1
    return out


def utf16_units(text):
    raw = text.encode("utf-16-be", "surrogatepass")
    return raw, [int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw), 2)]


def unambiguous(text):
    _, units = utf16_units(text)
    return code_points_from_units(units) == [ord(c) for c in text]


def enc_str(text):
    require(unambiguous(text), f"ambiguous surrogates in {text!r}")
    raw, _ = utf16_units(text)
    return raw.hex()


def ascii_hex(text):
    require(text.isascii(), f"text output is not ASCII: {text!r}")
    return text.encode("ascii").hex()


def proj(cp):
    return cp if cp <= 0xFFFF else 0xFFFD


def gc_field(gc):
    return "-" if gc is None else struct.pack(">d", gc).hex()


def token_field(t):
    return f"t{proj(ord(t.base)):x}:{t.index}:{int(t.valid)}"


def pair_field(p):
    comp = "-" if p.complement is None else f"{ord(p.complement):x}"
    return f"p{p.index}:{proj(ord(p.base)):x}:{comp}:{int(p.valid)}"


def codon_field(c):
    return f"c{c.start_index}:" + "|".join(pair_field(p) for p in c.pairs)


def sequence_canon(res):
    return (
        f"T[{','.join(token_field(t) for t in res['tokens'])}];"
        f"P[{','.join(pair_field(p) for p in res['pairs'])}];"
        f"C[{','.join(codon_field(c) for c in res['codons'])}];"
        f"R[{','.join(pair_field(p) for p in res['trailing_partial'])}];"
        f"LE[{','.join(token_field(t) for t in res['lexer_errors'])}];"
        f"PE[{','.join(token_field(t) for t in res['parser_errors'])}];"
        f"GC={gc_field(res['gc_content'])};V={int(res['valid'])}"
    )


def strand_canon(res):
    return (
        f"DNA={res['dna']};N={res['byte_count']};"
        f"C[{','.join(codon_field(c) for c in res['codons'])}];"
        f"R[{','.join(pair_field(p) for p in res['trailing_partial'])}];"
        f"GC={gc_field(res['gc_content'])};RT={int(res['round_trip'])}"
    )


# Pools. WS is every BMP code point CPython's str.isspace() accepts, taken from the
# reference runtime rather than typed by hand.
WS = [chr(cp) for cp in range(0x10000) if chr(cp).isspace()]
BASES = "ATCGatcg"
JUNK = ["X", "N", "-", "*", "#", "1", "0", "%", ".", "/", "é"]
HOSTILE = [
    "​", "﻿", "́", "ͅ", "ι", "Ａ", "ａ", "А", "а",
    "Α", "ı", "ſ", "İ", "ŉ", "ǰ", "ß", "ẞ", "ẚ",
    "ẗ", "ﬅ", "ﬁ", "ÿ", "µ", "\x00", "\x7f", "�", "Ⅰ",
    "Ā", "ǅ", "\ud800", "\udfff", "\U0001f9ec", "\U00010428",
]
SPECIALS = [
    "ß", "ßAAA", "AßT", "ﬅAAA", "AAAﬅ", "ẚAAA", "ẗAAA",
    "AAAẗ", "ıAAA", "ſAAAA", "ͅAAA", "ﬁAAA", "ǰAAA", "ŉAAA",
    "ιAAA", "aßt", "\U0001f9ecATCG", "ATCG\U0001f9ec", "A\U0001f9ecT", "\U00010428ACG",
    "\ud800", "\udfff", "A\ud800T", "\udfffACGT", "ACG\ud800", "\ud800\U0001f9ec", "\U0001f9ec\udfff",
    "ATCG ", " ATCG", " ATCG ", "\u001cATCG\u001f", "\u0085ATCG",
    "A\tT\nC\rG", "A\x0bT\x0cC", " ATCG ", "　ATCG ",
]


def insert_ws(rng, text, count):
    s = text
    for _ in range(count):
        pos = rng.randrange(len(s) + 1)
        s = s[:pos] + rng.choice(WS) + s[pos:]
    return s


def random_strings(rng, count, alphabet, lo, hi):
    out = []
    while len(out) < count:
        n = rng.randint(lo, hi)
        s = "".join(rng.choice(alphabet) for _ in range(n))
        if unambiguous(s):
            out.append(s)
    return out


def hostile_mix(rng, count, lo, hi):
    return random_strings(rng, count, BASES + "".join(HOSTILE) if False else BASES, lo, hi) and [
        _mix_hostile(rng, lo, hi) for _ in range(count)
    ]


def _mix_hostile(rng, lo, hi):
    while True:
        n = rng.randint(lo, hi)
        s = "".join(rng.choice(HOSTILE) if rng.random() < 0.3 else rng.choice(BASES) for _ in range(n))
        if unambiguous(s):
            return s


def random_bytes(rng, count, lo, hi):
    return [bytes(rng.getrandbits(8) for _ in range(rng.randint(lo, hi))) for _ in range(count)]


def build_quat_dna_to_bytes(rng):
    cases = [""] + list(BASES) + random_strings(rng, 1, BASES, 0, 0)
    for n in range(0, 41):
        cases += random_strings(rng, 2, BASES, n, n)
    cases += [insert_ws(rng, s, rng.randint(1, 4)) for s in random_strings(rng, 60, BASES, 1, 24)]
    cases += random_strings(rng, 120, BASES + "".join(JUNK), 1, 30)
    cases += _mix_hostile_list(rng, 120, 1, 20)
    cases += list(WS)
    cases += ["A" + w + "TCG" for w in WS]
    cases += SPECIALS
    return [("quat.dna_to_bytes", enc_str(s), "", bytes(_quat_dna_to_bytes(s)).hex()) for s in cases]


def _mix_hostile_list(rng, count, lo, hi):
    return [_mix_hostile(rng, lo, hi) for _ in range(count)]


def _quat_dna_to_bytes(text):
    from everlang.biocomputing.quaternary import QuaternaryTranslationLayer as Q

    return Q().DNA_to_bytes(text)


def build_quat_bytes_to_dna(rng):
    q = QuaternaryTranslationLayer()
    cases = [bytes([b]) for b in range(256)] + [b"", bytes(range(256))]
    cases += [bytes([v]) * n for v in (0x00, 0xFF, 0x80, 0x1B, 0x6C) for n in range(1, 9)]
    cases += random_bytes(rng, 200, 0, 48)
    return [("quat.bytes_to_dna", data.hex(), "", ascii_hex(q.bytes_to_DNA(data))) for data in cases]


def build_seq_run(rng):
    seq = DnaSequencer()
    cases = [""] + list(WS)
    cases += ["".join(rng.choice(WS) for _ in range(rng.randint(2, 6))) for _ in range(60)]
    cases += list(BASES)
    cases += random_strings(rng, 150, BASES, 1, 30)
    cases += [insert_ws(rng, s, rng.randint(1, 3)) for s in random_strings(rng, 120, BASES, 1, 30)]
    cases += random_strings(rng, 150, BASES + "".join(JUNK), 1, 30)
    cases += _mix_hostile_list(rng, 120, 1, 30)
    cases += SPECIALS
    cases += ["".join(HOSTILE[i:i + 1] + BASES[i % 8] for i in range(len(HOSTILE)))]
    rows = []
    for raw in cases:
        try:
            canon = sequence_canon(seq.run(raw))
        except DnaSyntaxError:
            canon = "ERR:DnaSyntaxError"
        rows.append(("seq.run", enc_str(raw), "", ascii_hex(canon) if not canon.startswith("ERR:") else canon))
    return rows


def build_bin_sequence(rng):
    seqr = BinarySequencer()
    cases = [bytes([b]) for b in range(256)] + [b"", bytes(range(256)), bytes([0x1B]), bytes([0xFF]) * 3]
    cases += random_bytes(rng, 200, 0, 48)
    return [("bin.sequence", data.hex(), "", ascii_hex(strand_canon(seqr.sequence(data)))) for data in cases]


def build_bin_decode(rng):
    seqr = BinarySequencer()
    cases = [""] + list(WS) + ["".join(rng.choice(WS) for _ in range(rng.randint(2, 6))) for _ in range(40)]
    for k in range(0, 13):
        cases += [insert_ws(rng, s, rng.randint(0, 3)) for s in random_strings(rng, 4, BASES, 4 * k, 4 * k)]
    cases += random_strings(rng, 80, BASES, 4, 64)
    for n in range(1, 20):
        if n % 4:
            cases += random_strings(rng, 4, BASES, n, n)
    cases += [insert_ws(rng, s, 1) for s in random_strings(rng, 40, BASES, 4, 32)]
    cases += random_strings(rng, 120, BASES + "".join(JUNK), 4, 40)
    cases += _mix_hostile_list(rng, 120, 4, 40)
    cases += SPECIALS
    rows = []
    for dna in cases:
        try:
            out = seqr.decode(dna).hex()
        except ValueError:
            out = "ERR:IllegalArgumentException"
        rows.append(("bin.decode", enc_str(dna), "", out if not out.startswith("ERR:") else out))
    return rows


def _affinity_pairs(rng, count):
    pairs = []
    while len(pairs) < count:
        n = rng.randint(0, 24)
        dna = "".join(rng.choice(BASES) for _ in range(n))
        mode = rng.random()
        comp = "".join({"A": "T", "T": "A", "C": "G", "G": "C"}[b] for b in dna.upper())
        if mode < 0.25:
            dna_in, gate = dna, comp
        elif mode < 0.40:
            dna_in = dna
            gate = comp[:-1] + ("A" if comp[-1:] != "A" else "C") if comp else ""
        elif mode < 0.50:
            dna_in, gate = dna, comp + "A"
        elif mode < 0.58:
            dna_in, gate = dna, ""
        elif mode < 0.66:
            dna_in, gate = dna, "".join(rng.choice(BASES) for _ in range(n))
        elif mode < 0.76:
            dna_in, gate = " " + dna + "\t", comp + "\n"
        elif mode < 0.84:
            dna_in, gate = insert_ws(rng, dna, 1), comp
        elif mode < 0.92:
            dna_in, gate = dna, rng.choice(WS) * rng.randint(1, 3) + comp
        else:
            dna_in, gate = dna + rng.choice(HOSTILE), comp + rng.choice(HOSTILE)
        if unambiguous(dna_in) and unambiguous(gate):
            pairs.append((dna_in, gate))
    return pairs


def build_bin_affinity(rng):
    seqr = BinarySequencer()
    rows = []
    for dna_in, gate in _affinity_pairs(rng, 300):
        rows.append(("bin.affinity", enc_str(dna_in), enc_str(gate), ascii_hex(str(seqr.affinity(dna_in, gate)))))
    rows.append(("bin.affinity", enc_str("ATCG"), enc_str("TAGC"), ascii_hex("256")))
    return rows


def build_engine_affinity(rng):
    rows = []
    for dna_in, gate in _affinity_pairs(rng, 300):
        value = BioPhaseEngine(gate).calculate_hybridization_affinity(dna_in)
        rows.append(("engine.affinity", enc_str(gate), enc_str(dna_in), ascii_hex(str(value))))
    rows.append(("engine.affinity", enc_str("  atcg \n"), enc_str(" tagc\t"), ascii_hex("256")))
    return rows


def main():
    require(STANDALONE.is_dir(), f"reference not found at {STANDALONE}")
    rng = random.Random(SEED)
    builders = [
        build_quat_dna_to_bytes,
        build_quat_bytes_to_dna,
        build_seq_run,
        build_bin_sequence,
        build_bin_decode,
        build_bin_affinity,
        build_engine_affinity,
    ]
    rows = []
    seen = set()
    for build in builders:
        for row in build(rng):
            line = "\t".join(row)
            if line not in seen:
                seen.add(line)
                rows.append(line)
    require(len(rows) >= MIN_CASES, f"only {len(rows)} cases, need {MIN_CASES}")
    for line in rows:
        require(line.count("\t") == 3, f"malformed line: {line!r}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
    counts = {}
    for line in rows:
        op = line.split("\t", 1)[0]
        counts[op] = counts.get(op, 0) + 1
    print(f"wrote {OUT} cases={len(rows)}")
    for op in sorted(counts):
        print(f"  {op}: {counts[op]}")


if __name__ == "__main__":
    main()
