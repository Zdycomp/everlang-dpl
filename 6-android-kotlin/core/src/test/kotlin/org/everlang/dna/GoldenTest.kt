package org.everlang.dna

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Exact equality against core/src/test/resources/golden.tsv, which core/tools/gen_golden.py
 * generates from the Python reference. Every case is checked; a failure lists the mismatches.
 *
 * Error mapping: a Python ValueError from decode is the Kotlin IllegalArgumentException, and a
 * Python DnaSyntaxError is DnaSyntaxError. Other exceptions are not caught, so they fail the test.
 */
class GoldenTest {
    private data class Case(val line: Int, val op: String, val arg1: String, val arg2: String, val expected: String)

    private val cases: List<Case> by lazy {
        Canon.resourceLines("/golden.tsv").mapIndexedNotNull { i, line ->
            if (line.isEmpty()) {
                null
            } else {
                val f = line.split('\t')
                assertEquals(4, f.size, "golden.tsv line ${i + 1} must have four fields")
                Case(i + 1, f[0], f[1], f[2], f[3])
            }
        }
    }

    private fun actual(c: Case): String = when (c.op) {
        "quat.dna_to_bytes" -> Canon.bytesToHex(Quaternary.dnaToBytes(Canon.decodeUtf16Hex(c.arg1)))
        "quat.bytes_to_dna" -> Canon.asciiHex(Quaternary.bytesToDna(Canon.hexToBytes(c.arg1)))
        "seq.run" -> try {
            Canon.asciiHex(Canon.sequence(DnaSequencer.run(Canon.decodeUtf16Hex(c.arg1))))
        } catch (e: DnaSyntaxError) {
            "ERR:DnaSyntaxError"
        }
        "bin.sequence" -> Canon.asciiHex(Canon.strand(BinarySequencer().sequence(Canon.hexToBytes(c.arg1))))
        "bin.decode" -> try {
            Canon.bytesToHex(BinarySequencer().decode(Canon.decodeUtf16Hex(c.arg1)))
        } catch (e: IllegalArgumentException) {
            "ERR:ValueError"
        }
        "bin.affinity" -> Canon.asciiHex(
            BinarySequencer().affinity(Canon.decodeUtf16Hex(c.arg1), Canon.decodeUtf16Hex(c.arg2)).toString(),
        )
        "engine.affinity" -> Canon.asciiHex(
            BioPhaseEngine(Canon.decodeUtf16Hex(c.arg1))
                .calculateHybridizationAffinity(Canon.decodeUtf16Hex(c.arg2))
                .toString(),
        )
        else -> error("unknown golden op ${c.op} on line ${c.line}")
    }

    private fun checkOp(op: String) {
        val selected = cases.filter { it.op == op }
        assertTrue(selected.isNotEmpty(), "golden.tsv has no $op cases")
        val mismatches = selected.mapNotNull { c ->
            val got = actual(c)
            if (got == c.expected) {
                null
            } else {
                "line ${c.line}: arg1=${c.arg1} arg2=${c.arg2} expected=${c.expected} got=$got"
            }
        }
        assertTrue(
            mismatches.isEmpty(),
            "${mismatches.size} of ${selected.size} $op cases differ from golden.tsv:\n" +
                mismatches.take(25).joinToString("\n"),
        )
    }

    @Test
    fun quatDnaToBytesMatchesPythonForEveryCase() = checkOp("quat.dna_to_bytes")

    @Test
    fun quatBytesToDnaMatchesPythonForEveryCase() = checkOp("quat.bytes_to_dna")

    @Test
    fun seqRunMatchesPythonForEveryCase() = checkOp("seq.run")

    @Test
    fun binSequenceMatchesPythonForEveryCase() = checkOp("bin.sequence")

    @Test
    fun binDecodeMatchesPythonForEveryCase() = checkOp("bin.decode")

    @Test
    fun binAffinityMatchesPythonForEveryCase() = checkOp("bin.affinity")

    @Test
    fun engineAffinityMatchesPythonForEveryCase() = checkOp("engine.affinity")

    @Test
    fun goldenFileIsWellFormedAndCoversEveryPath() {
        assertTrue(cases.size >= 3000, "need at least 3000 cases, found ${cases.size}")
        val opCounts = cases.groupingBy { it.op }.eachCount()
        assertEquals(
            setOf("quat.dna_to_bytes", "quat.bytes_to_dna", "seq.run", "bin.sequence", "bin.decode",
                "bin.affinity", "engine.affinity"),
            opCounts.keys,
        )
        for (c in cases) {
            assertTrue(c.arg1.length % 2 == 0 && c.arg2.length % 2 == 0, "odd-length hex on line ${c.line}")
            assertTrue(
                c.expected.startsWith("ERR:") || c.expected.all { it in '0'..'9' || it in 'a'..'f' },
                "expected field is neither ERR: nor hex on line ${c.line}",
            )
        }
        for (op in listOf("seq.run", "bin.decode")) {
            val errors = cases.count { it.op == op && it.expected.startsWith("ERR:") }
            val successes = cases.count { it.op == op && !it.expected.startsWith("ERR:") }
            assertTrue(errors > 0 && successes > 0, "$op must cover both success and error paths")
        }
    }

    @Test
    fun goldenCoversEveryBmpWhitespaceCodePoint() {
        // Only String-typed arguments are UTF-16BE. bytes arguments (quat.bytes_to_dna, bin.sequence) are not.
        val stringArgs = cases.flatMap { c ->
            when (c.op) {
                "quat.dna_to_bytes", "seq.run", "bin.decode" -> listOf(c.arg1)
                "bin.affinity", "engine.affinity" -> listOf(c.arg1, c.arg2)
                else -> emptyList()
            }
        }
        val seen = HashSet<Char>()
        for (arg in stringArgs) seen += Canon.decodeUtf16Hex(arg).toSet()
        val missing = PyUnicodeTables.SPACE.filter { cp -> cp.toChar() !in seen }
        assertTrue(missing.isEmpty(), "whitespace code points absent from golden arguments: " +
            missing.joinToString(" ") { "U+%04X".format(it) })
    }
}
