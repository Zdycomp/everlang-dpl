package org.everlang.dna.predict

import org.junit.jupiter.api.Assumptions.assumeTrue
import java.io.ByteArrayOutputStream
import java.io.File
import java.lang.management.ManagementFactory
import java.lang.management.MemoryType
import java.security.MessageDigest
import java.util.Locale
import java.util.Random
import kotlin.math.abs
import kotlin.math.log2
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Evaluation of the order-k predictor on seeded datasets, a slice of this repository's Python source,
 * and a throughput and heap run. Skipped unless the environment has EVAL=1.
 *
 * Every number is the adaptive estimator's ideal code length, the sum of -log2 p(actual | context),
 * measured on fixed inputs. None is the size of a compressed file, and no real genome is used.
 *
 * Inputs: predict/tools/markov_order2.tsv and predict/tools/eval_reference.tsv, both read relative to
 * the module directory, which is the working directory of Gradle's test task. Output:
 * predict/build/predictor-eval/results.md, also printed to the test output.
 */
class PredictorEvalTest {

    @Test
    fun predictorEvaluation() {
        assumeTrue(System.getenv(GATE) == "1", "set $GATE=1 to run the predictor evaluation")

        val ref = loadReference()
        val p = loadMatrix()
        val checks = Checks()
        val md = StringBuilder()
        val datasets = ArrayList<Dataset>()

        md.line("# Predictor evaluation")
        md.line()
        writeEnvironment(md)

        // A. Seeded uniform random bytes, through the binary, strand, predict pipeline.
        val uniform = ByteArray(MIB).also { Random(UNIFORM_SEED).nextBytes(it) }
        datasets += Dataset(
            title = "A. Uniform random bytes (1 MiB)",
            note = "Seed $UNIFORM_SEED. evaluateBytes, so $UNIFORM_BASES_TEXT bases. Floor: 2 bits/base. " +
                "Ceiling: top-1 accuracy 0.25 in expectation for any predictor.",
            expectedBases = 4L * MIB,
            rows = (1..MAX_ORDER).map { k ->
                Row(k, evaluateBytes(uniform, k), ref.value("uniform.bits"), ref.value("uniform.top1"))
            },
        )

        // B. Order-2 Markov DNA source, 1,000,000 bases, with the exact entropy rate from the Python tool.
        val markov = sampleMarkov(p, MARKOV_BASES, MARKOV_SEED)
        val known = knownSourceBitsPerBase(p, markov)
        val hRate = ref.value("markov.H_rate")
        val hOrder1 = ref.value("markov.H_order1")
        val top1Order1 = ref.value("markov.top1_order1")
        val top1Order2 = ref.value("markov.top1_order2")
        checks.that(abs(known - hRate) <= KNOWN_SOURCE_TOLERANCE) {
            "sampler check: known-source code length $known differs from H_rate $hRate by more than $KNOWN_SOURCE_TOLERANCE"
        }
        datasets += Dataset(
            title = "B. Order-2 Markov DNA source (1,000,000 bases)",
            note = "Seed $MARKOV_SEED, transition weights in predict/tools/markov_order2.tsv. Floors: H(X_t | X_t-1) = " +
                "${f4(hOrder1)} bits/base for order 1, and the entropy rate ${f4(hRate)} for orders 2 and up. " +
                "Top-1 ceilings: ${f4(top1Order1)} and ${f4(top1Order2)} on the same contexts. " +
                "Known-source code length on this sample, scored with the matrix itself: ${f4(known)} bits/base.",
            expectedBases = MARKOV_BASES.toLong(),
            rows = (1..MAX_ORDER).map { k ->
                val first = k == 1
                Row(k, evaluateSymbols(markov, k),
                    if (first) hOrder1 else hRate,
                    if (first) top1Order1 else top1Order2)
            },
        )

        // C. Period-16 tandem repeats with substitution-only noise at four rates.
        val unitRnd = Random(UNIT_SEED)
        val unit = IntArray(TANDEM_PERIOD) { unitRnd.nextInt(4) }
        val unitText = unit.joinToString("") { "ATCG"[it].toString() }
        val distinctText = (1..MAX_ORDER).joinToString(", ") { k -> "$k: ${distinctCyclicKmers(unit, k)}" }
        TANDEM_RATES.forEachIndexed { i, rateText ->
            val rate = rateText.toDouble()
            val source = tandem(unit, TANDEM_BASES, rate, MUTATION_SEED + i)
            checks.that(abs(source.realizedRate - rate) <= MUTATION_RATE_TOLERANCE) {
                "tandem $rateText: realized substitution fraction ${source.realizedRate} is far from $rate"
            }
            datasets += Dataset(
                title = "C. Period-16 tandem repeat, substitution rate $rateText (1,000,000 bases)",
                note = "Template `$unitText` (seed $UNIT_SEED). Distinct cyclic k-mers among the 16 positions, by k: " +
                    "$distinctText. " +
                    "Substitution seed ${MUTATION_SEED + i}, realized substitution fraction ${f4(source.realizedRate)}. " +
                    "Floor: entropy rate of the process, ${f4(ref.value("tandem.floor.$rateText"))} bits/base, " +
                    "a bound on any predictor. Top-1 ceiling: ${f4(ref.value("tandem.top1.$rateText"))}.",
                expectedBases = TANDEM_BASES.toLong(),
                rows = (1..MAX_ORDER).map { k ->
                    Row(k, evaluateSymbols(source.bases, k),
                        ref.value("tandem.floor.$rateText"), ref.value("tandem.top1.$rateText"))
                },
            )
        }

        // D. This repository's own Python source, as bytes, through the same pipeline.
        val corpus = pythonCorpus()
        datasets += Dataset(
            title = "D. This repository's Python source (first 1 MiB)",
            note = "${corpus.candidates} Python files outside 6-android-kotlin and hidden, cache, build and venv " +
                "directories, ${corpus.candidateBytes} bytes in total. The first ${corpus.filesUsed} files, " +
                "from `${corpus.first}` to `${corpus.last}` in sorted path order, were concatenated and cut at " +
                "1,048,576 bytes. SHA-256 of the slice: `${corpus.sha256}`. evaluateBytes, so $UNIFORM_BASES_TEXT bases. " +
                "No floor is known for this data.",
            expectedBases = 4L * MIB,
            rows = (1..MAX_ORDER).map { k -> Row(k, evaluateBytes(corpus.bytes, k), null, null) },
        )

        for (d in datasets) {
            writeDataset(md, d)
            checkDataset(d, checks)
        }

        writeSummary(md, datasets)

        // E. Throughput and heap, last so that the earlier datasets do not affect the heap peak.
        throughput(md, checks)

        md.line("## Checks")
        md.line()
        md.line("Checks run: ${checks.run}. Failed: ${checks.failed.size}.")
        checks.failed.forEach { md.line("- FAILED: $it") }
        md.line()

        val text = md.toString()
        val outDir = File("build/predictor-eval").apply { mkdirs() }
        File(outDir, "results.md").writeText(text, Charsets.UTF_8)
        println(text)

        assertTrue(checks.failed.isEmpty(), "predictor evaluation sanity checks failed:\n" + checks.failed.joinToString("\n"))
    }

    // Sections and tables

    private class Row(val order: Int, val r: PredictionReport, val floor: Double?, val ceiling: Double?)

    private class Dataset(val title: String, val note: String, val expectedBases: Long, val rows: List<Row>)

    private fun writeDataset(md: StringBuilder, d: Dataset) {
        md.line("## ${d.title}")
        md.line()
        md.line(d.note)
        md.line()
        md.line("| order | bits/base | top-1 | gain over 2.0 (bits) | gain (% of 2.0) | floor bits/base | ceiling top-1 |")
        md.line("|---:|---:|---:|---:|---:|---:|---:|")
        for (row in d.rows) {
            val bpb = row.r.bitsPerBase
            val gain = BASELINE - bpb
            md.line(
                "| ${row.order} | ${f4(bpb)} | ${f4(row.r.top1Accuracy)} | ${signed4(gain)} | " +
                    "${signed2(100.0 * gain / BASELINE)} | ${row.floor?.let { f4(it) } ?: "-"} | " +
                    "${row.ceiling?.let { f4(it) } ?: "-"} |"
            )
        }
        md.line()
    }

    private fun checkDataset(d: Dataset, checks: Checks) {
        for (row in d.rows) {
            val tag = "${d.title}, order ${row.order}"
            checks.that(row.r.bases == d.expectedBases) { "$tag: bases ${row.r.bases} != ${d.expectedBases}" }
            checks.that(row.r.bitsPerBase.isFinite() && row.r.bitsPerBase > 0.0) { "$tag: bits/base ${row.r.bitsPerBase}" }
            checks.that(row.r.top1Accuracy in 0.0..1.0) { "$tag: top-1 ${row.r.top1Accuracy}" }
            row.floor?.let { floor ->
                checks.that(row.r.bitsPerBase >= floor - FLOOR_TOLERANCE) {
                    "$tag: bits/base ${row.r.bitsPerBase} is below the floor $floor by more than $FLOOR_TOLERANCE"
                }
            }
            row.ceiling?.let { ceiling ->
                checks.that(row.r.top1Accuracy <= ceiling + CEILING_TOLERANCE) {
                    "$tag: top-1 ${row.r.top1Accuracy} is above the ceiling $ceiling by more than $CEILING_TOLERANCE"
                }
            }
        }
    }

    private fun writeSummary(md: StringBuilder, datasets: List<Dataset>) {
        md.line("## Summary: best order per dataset")
        md.line()
        md.line("| dataset | best order | bits/base | top-1 | gain over 2.0 (bits) |")
        md.line("|---|---:|---:|---:|---:|")
        for (d in datasets) {
            val best = d.rows.minBy { it.r.bitsPerBase }
            md.line(
                "| ${d.title} | ${best.order} | ${f4(best.r.bitsPerBase)} | ${f4(best.r.top1Accuracy)} | " +
                    "${signed4(BASELINE - best.r.bitsPerBase)} |"
            )
        }
        md.line()
    }

    // Throughput and heap

    private fun throughput(md: StringBuilder, checks: Checks) {
        md.line("## E. Throughput and heap: evaluateBytes, order $THROUGHPUT_ORDER, ${THROUGHPUT_BYTES / MIB} MiB input")
        md.line()
        val input = ByteArray(THROUGHPUT_BYTES).also { Random(THROUGHPUT_SEED).nextBytes(it) }
        evaluateBytes(input.copyOf(WARMUP_BYTES), THROUGHPUT_ORDER) // JIT warm-up on 8 MiB, result discarded
        System.gc()
        resetHeapPeaks()

        val reports = ArrayList<PredictionReport>()
        val seconds = DoubleArray(RUNS)
        for (i in 0 until RUNS) {
            val t0 = System.nanoTime()
            reports += evaluateBytes(input, THROUGHPUT_ORDER)
            seconds[i] = (System.nanoTime() - t0) / 1e9
        }
        val peakHeap = heapPeakBytes()
        checks.that(reports.all { it == reports[0] }) { "throughput: repeated runs gave different reports" }

        val bases = 4.0 * THROUGHPUT_BYTES
        md.line("| run | seconds | MiB/s | Mbases/s |")
        md.line("|---:|---:|---:|---:|")
        for (i in 0 until RUNS) {
            md.line("| ${i + 1} | ${f3(seconds[i])} | ${f2(THROUGHPUT_BYTES.toDouble() / MIB / seconds[i])} | " +
                "${f2(bases / seconds[i] / 1e6)} |")
        }
        val sorted = seconds.sorted()
        md.line()
        md.line(
            "Median ${f2(THROUGHPUT_BYTES.toDouble() / MIB / sorted[RUNS / 2])} MiB/s " +
                "(min ${f2(THROUGHPUT_BYTES.toDouble() / MIB / sorted.last())}, max ${f2(THROUGHPUT_BYTES.toDouble() / MIB / sorted.first())}). " +
                "MB here means MiB, 2^20 bytes. Single evaluating thread."
        )
        md.line()
        md.line(
            "Heap: sum of the JVM heap pools' peak usage since the reset just before the timed runs: " +
                "${f2(peakHeap / MIB.toDouble())} MiB. That includes the ${THROUGHPUT_BYTES / MIB} MiB input array, " +
                "and each pool's peak is taken separately, so the sum is an upper bound on the combined peak. " +
                "Runtime.maxMemory of the test JVM: ${f2(Runtime.getRuntime().maxMemory() / MIB.toDouble())} MiB. " +
                "The model's own table at order $THROUGHPUT_ORDER is ${f2(16.0 * (1 shl (2 * THROUGHPUT_ORDER)) / MIB)} MiB."
        )
        md.line()
        md.line(
            "Output on this input: ${reports[0].bases} bases, ${f4(reports[0].bitsPerBase)} bits/base, " +
                "top-1 ${f4(reports[0].top1Accuracy)}. Every run gave an identical report: ${reports.all { it == reports[0] }}."
        )
        md.line()
    }

    private fun heapPools() = ManagementFactory.getMemoryPoolMXBeans().filter { it.type == MemoryType.HEAP }

    private fun resetHeapPeaks() = heapPools().forEach { it.resetPeakUsage() }

    private fun heapPeakBytes(): Long = heapPools().sumOf { it.peakUsage.used }

    private fun writeEnvironment(md: StringBuilder) {
        md.line("## Environment")
        md.line()
        md.line("- JVM: ${System.getProperty("java.vm.name")} ${System.getProperty("java.vm.version")}, java.version ${System.getProperty("java.version")}")
        md.line("- OS: ${System.getProperty("os.name")} ${System.getProperty("os.version")} (${System.getProperty("os.arch")})")
        md.line("- CPU: ${cpuModel()}, ${Runtime.getRuntime().availableProcessors()} logical processors visible to the JVM")
        md.line("- Run inside the Gradle test worker, which is the JVM whose heap is reported in section E")
        md.line()
    }

    private fun cpuModel(): String = runCatching {
        File("/proc/cpuinfo").readLines().first { it.startsWith("model name") }.substringAfter(':').trim()
    }.getOrDefault("unknown")

    // Inputs

    private fun loadReference(): Reference {
        val f = File(REFERENCE)
        check(f.isFile) { "${f.path} is missing; run: python3 predict/tools/eval_reference.py from the 6-android-kotlin root" }
        val map = f.readLines().drop(1).filter { it.isNotBlank() }.associate { line ->
            val parts = line.split('\t')
            parts[0] to parts[1].toDouble()
        }
        return Reference(map)
    }

    private class Reference(private val map: Map<String, Double>) {
        fun value(key: String): Double = checkNotNull(map[key]) { "no value named $key in $REFERENCE" }
    }

    /** P[i][c] for context i = 4*x[t-2] + x[t-1], codes A=0 T=1 C=2 G=3, rows normalised from the weights. */
    private fun loadMatrix(): Array<DoubleArray> {
        val f = File(MATRIX)
        check(f.isFile) { "${f.path} is missing" }
        val lines = f.readLines().filter { it.isNotBlank() && !it.startsWith("#") }
        check(lines.first() == "context\tA\tT\tC\tG") { "unexpected header in ${f.path}" }
        val rows = arrayOfNulls<DoubleArray>(16)
        for (line in lines.drop(1)) {
            val parts = line.split('\t')
            val w = IntArray(4) { parts[it + 1].toInt() }
            val idx = 4 * baseCode(parts[0][0]) + baseCode(parts[0][1])
            rows[idx] = DoubleArray(4) { w[it].toDouble() / w.sum() }
        }
        check(rows.all { it != null }) { "${f.path} must define all 16 two-symbol contexts" }
        return Array(16) { rows[it]!! }
    }

    private fun baseCode(ch: Char): Int = "ATCG".indexOf(ch).also { check(it >= 0) { "not a base: $ch" } }

    /** Samples n symbols from the order-2 chain, starting in context AA. */
    private fun sampleMarkov(p: Array<DoubleArray>, n: Int, seed: Long): ByteArray {
        val rnd = Random(seed)
        val out = ByteArray(n)
        var ctx = 0
        for (t in 0 until n) {
            val u = rnd.nextDouble()
            val row = p[ctx]
            var s = 0
            var acc = row[0]
            while (s < 3 && u >= acc) {
                s++
                acc += row[s]
            }
            out[t] = s.toByte()
            ctx = ((ctx shl 2) or s) and 15
        }
        return out
    }

    /**
     * Mean -log2 p_true(x_t | x_{t-2}, x_{t-1}) over the sample, from the first two symbols onward,
     * scored with the matrix that generated it. Matches the Python entropy rate only if the sampler
     * agrees with the matrix.
     */
    private fun knownSourceBitsPerBase(p: Array<DoubleArray>, x: ByteArray): Double {
        var bits = 0.0
        var ctx = 4 * x[0] + x[1]
        for (t in 2 until x.size) {
            val s = x[t].toInt()
            bits += -log2(p[ctx][s])
            ctx = 4 * (ctx and 3) + s
        }
        return bits / (x.size - 2)
    }

    private class Tandem(val bases: ByteArray, val realizedRate: Double)

    /**
     * The period-16 template repeated to n bases. Each base is replaced, independently and with
     * probability rate, by one of the other three bases uniformly. Substitutions do not accumulate.
     */
    private fun tandem(unit: IntArray, n: Int, rate: Double, seed: Long): Tandem {
        val rnd = Random(seed)
        var mutated = 0
        val out = ByteArray(n) { t ->
            val base = unit[t % unit.size]
            if (rnd.nextDouble() < rate) {
                mutated++
                ((base + 1 + rnd.nextInt(3)) % 4).toByte()
            } else {
                base.toByte()
            }
        }
        return Tandem(out, mutated.toDouble() / n)
    }

    /** Distinct k-mers among the period positions of the cyclic template. */
    private fun distinctCyclicKmers(unit: IntArray, k: Int): Int {
        val seen = HashSet<Int>()
        for (i in unit.indices) {
            var code = 0
            for (j in 0 until k) code = code * 4 + unit[(i + j) % unit.size]
            seen += code
        }
        return seen.size
    }

    private class Corpus(
        val bytes: ByteArray,
        val candidates: Int,
        val candidateBytes: Long,
        val filesUsed: Int,
        val first: String,
        val last: String,
        val sha256: String,
    )

    /**
     * The Python source of this repository, as bytes. The repository root is the nearest ancestor
     * containing run_all.py. 6-android-kotlin is excluded, so edits to this module's own tools do not change
     * the dataset. Files are taken in sorted path order and the slice is cut at exactly 1 MiB.
     */
    private fun pythonCorpus(): Corpus {
        val start = File(".").canonicalFile
        val root = generateSequence(start) { it.parentFile }
            .firstOrNull { File(it, "run_all.py").isFile }
            ?: error("no run_all.py found above ${start.path}, so the repository root is unknown")
        val files = root.walkTopDown()
            .onEnter { dir ->
                dir == root ||
                    (!dir.name.startsWith(".") && dir.name !in SKIP_DIRS &&
                        !(dir.parentFile == root && dir.name == MODULE_DIR_NAME))
            }
            .filter { it.isFile && it.name.endsWith(".py") }
            .sortedBy { it.relativeTo(root).invariantSeparatorsPath }
            .toList()
        val total = files.sumOf { it.length() }
        check(total >= CORPUS_BYTES) { "Python corpus is $total bytes, below the $CORPUS_BYTES required" }

        val buf = ByteArrayOutputStream()
        var used = 0
        for (f in files) {
            if (buf.size() >= CORPUS_BYTES) break
            buf.write(f.readBytes())
            used++
        }
        val bytes = buf.toByteArray().copyOf(CORPUS_BYTES)
        val sha = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        return Corpus(
            bytes = bytes,
            candidates = files.size,
            candidateBytes = total,
            filesUsed = used,
            first = files.first().relativeTo(root).invariantSeparatorsPath,
            last = files[used - 1].relativeTo(root).invariantSeparatorsPath,
            sha256 = sha,
        )
    }

    private companion object {
        const val GATE = "EVAL"
        const val MIB = 1 shl 20
        const val UNIFORM_SEED = 1001L
        const val MARKOV_SEED = 2002L
        const val UNIT_SEED = 3003L
        const val MUTATION_SEED = 4004L // the rate index is added
        const val THROUGHPUT_SEED = 5005L
        const val MARKOV_BASES = 1_000_000
        const val TANDEM_BASES = 1_000_000
        const val TANDEM_PERIOD = 16
        const val THROUGHPUT_ORDER = 8
        const val THROUGHPUT_BYTES = 64 * MIB
        const val WARMUP_BYTES = 8 * MIB
        const val RUNS = 3
        const val CORPUS_BYTES = MIB
        const val MAX_ORDER = 8
        const val BASELINE = 2.0
        const val KNOWN_SOURCE_TOLERANCE = 0.005
        const val FLOOR_TOLERANCE = 0.01
        const val CEILING_TOLERANCE = 0.01
        const val MUTATION_RATE_TOLERANCE = 0.002
        const val MODULE_DIR_NAME = "6-android-kotlin"
        const val MATRIX = "tools/markov_order2.tsv"
        const val REFERENCE = "tools/eval_reference.tsv"
        const val UNIFORM_BASES_TEXT = "4,194,304"
        val TANDEM_RATES = listOf("0", "0.01", "0.05", "0.10")
        val SKIP_DIRS = setOf("__pycache__", "build", "node_modules", "venv")
    }
}

private fun StringBuilder.line(s: String = "") {
    append(s).append('\n')
}

/** Named sanity checks. Each one counts as run, and a failed one is listed in the report. */
private class Checks {
    var run = 0
        private set
    val failed = ArrayList<String>()

    fun that(condition: Boolean, message: () -> String) {
        run++
        if (!condition) failed += message()
    }
}

private fun f2(x: Double) = String.format(Locale.ROOT, "%.2f", x)

private fun f3(x: Double) = String.format(Locale.ROOT, "%.3f", x)

private fun f4(x: Double) = String.format(Locale.ROOT, "%.4f", x)

private fun signed2(x: Double) = String.format(Locale.ROOT, "%+.2f", x)

private fun signed4(x: Double) = String.format(Locale.ROOT, "%+.4f", x)
