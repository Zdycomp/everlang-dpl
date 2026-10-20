# Predictor evaluation

This page reports how the order-k predictor in `predict/` performs on seeded datasets, a slice of
this repository's Python source, and a throughput and heap run. The predictor is a statistical
estimator. Every number here is what it measured on the inputs named below, from one run on
2026-10-15. The run used the working tree on top of commit `9698a56`, with uncommitted changes. The
`predict/` module and these eval files are untracked in git, so checking out `9698a56` does not give
this predictor. The production predictor (`OrderKModel`, `evaluateSymbols`, `evaluateBytes`) was not
changed.

## What is measured

- **bits/base**: the total ideal code length, the sum of -log2 p(actual symbol | context) with
  the model's probability before that symbol is learned, divided by the number of bases. This is
  not the size of any compressed file. See [Limitations](#limitations).
- **top-1**: the fraction of bases equal to the most frequent symbol of their context, with the
  lowest index winning ties.
- **gain over 2.0**: 2.0 - bits/base, in bits per base. A 2-bit uniform code is the baseline. The
  percentage column is the gain divided by 2.0. A negative gain means the model costs more than
  the baseline.
- **floor** and **ceiling**: exact reference values for the data where they exist, computed in
  Python by `predict/tools/eval_reference.py`. A floor bounds the expected bits/base from below,
  and a ceiling bounds the expected top-1 from above. Both are references for interpretation.
  Neither is a target the predictor is tuned toward.

## Reproduce

Run from the `6-android-kotlin` directory. The Python step needs only the standard library.

The sandbox has no Android SDK. On a machine where Android Studio writes `sdk.dir` to
`local.properties`, `settings.gradle.kts` also includes the `:app` module and adds `google()`. Add
`-Pandroid=false` to keep the build JVM-only. The evaluation does not depend on `:app`. The
Android-enabled configuration was not tested here.

```sh
# 1. Exact references: Markov stationary law, entropy rate, Bayes top-1, tandem floors.
#    Writes predict/tools/eval_reference.tsv, which the test reads.
python3 predict/tools/eval_reference.py

# 2. The gated evaluation, under the locked Gradle form. EVAL=1 turns it on.
#    :predict:cleanTest is needed because EVAL is not a declared input of the test task, so Gradle
#    would otherwise report an earlier skipped run as up to date.
mkdir -p .gradle && EVAL=1 flock .gradle/build.lock ./gradlew --console=plain \
  :predict:cleanTest :predict:test --tests 'org.everlang.dna.predict.PredictorEvalTest'

# 3. The report. The test also writes the same text to the test output in the XML.
cat predict/build/predictor-eval/results.md
grep -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*"' \
  predict/build/test-results/test/TEST-org.everlang.dna.predict.PredictorEvalTest.xml
```

The expected XML summary is `tests="1" skipped="0" failures="0"`. On this VM the evaluation took
about 45 seconds.

Without `EVAL=1`, the same test is reported as skipped and the other predict tests still run:

```sh
mkdir -p .gradle && flock .gradle/build.lock ./gradlew --console=plain :predict:cleanTest :predict:test
```

## Datasets

| id | data | size | seed | notes |
|---|---|---|---|---|
| A | uniform random bytes | 1 MiB = 4,194,304 bases | 1001 | `evaluateBytes` |
| B | order-2 Markov DNA source | 1,000,000 bases | 2002 | 16 contexts, weights in `predict/tools/markov_order2.tsv`, started in context `AA` |
| C | period-16 tandem repeat, substitution rate 0, 0.01, 0.05, 0.10 | 1,000,000 bases each | unit 3003, substitutions 4004 to 4007 | template `GTCGGGCATAGAGGTT`; each base is replaced with probability r, by one of the other three bases uniformly; substitutions are independent and do not accumulate |
| D | this repository's Python source | first 1 MiB = 4,194,304 bases | none (fixed by repo state) | 116 files pinned in `6-android-kotlin/predict/tools/corpus_116.txt`, the list of the original run, which is the tree at commit `d0e17de`. The first 104 files, from `4-archive-sql/archive_db.py` to `ezr/tests/algebra_parity.py`, were concatenated and cut at 1,048,576 bytes. SHA-256 of the slice: `7a288d04a028b4df56c658a319e32460c0bd848d0f59921624eaeb6f68cbedcb` |

Datasets B and C are symbol streams, passed to `evaluateSymbols`. Datasets A and D are bytes, passed
to `evaluateBytes`, which splits each byte into four 2-bit symbols, most significant pair first.

## Exact references

Computed by `predict/tools/eval_reference.py`. The stationary law and the top-1 ceilings are exact
rationals. The entropies involve logarithms, so they were evaluated from those exact rationals at 60-digit
precision. The stationary law was checked exactly against pi = pi P.

| quantity | value | meaning |
|---|---:|---|
| B: entropy rate H | 1.7791 bits/base | floor for orders 2 and up |
| B: H(X_t given X_{t-1}) | 1.9140 bits/base | floor for order 1 |
| B: top-1 ceiling, one symbol of context | 0.3808 | order 1 |
| B: top-1 ceiling, two symbols of context | 0.4443 | orders 2 and up |
| C: entropy rate H_b(r) + r log2 3 | 0, 0.0966, 0.3656, 0.6275 | for r = 0, 0.01, 0.05, 0.10; a bound on any predictor, since the process is not order-limited |
| C: top-1 ceiling 1 - r | 1.0, 0.99, 0.95, 0.90 | for r = 0, 0.01, 0.05, 0.10 |
| A: floor and ceiling | 2 bits/base, top-1 0.25 | uniform symbols |

The sampler was checked against the matrix. The test scores the generated sample with the matrix
that produced it, giving 1.7803 bits/base against the exact rate 1.7791, within the 0.005 tolerance.

## Results

Each table is the output of the final run, in `predict/build/predictor-eval/results.md`.

### A. Uniform random bytes (1 MiB)

Floor 2.0 bits/base. Ceiling 0.25 top-1 in expectation.

| order | bits/base | top-1 | gain over 2.0 (bits) | gain (% of 2.0) | floor bits/base | ceiling top-1 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2.0000 | 0.2498 | -0.0000 | -0.00 | 2.0000 | 0.2500 |
| 2 | 2.0001 | 0.2503 | -0.0001 | -0.00 | 2.0000 | 0.2500 |
| 3 | 2.0003 | 0.2501 | -0.0003 | -0.02 | 2.0000 | 0.2500 |
| 4 | 2.0011 | 0.2496 | -0.0011 | -0.06 | 2.0000 | 0.2500 |
| 5 | 2.0037 | 0.2501 | -0.0037 | -0.19 | 2.0000 | 0.2500 |
| 6 | 2.0120 | 0.2495 | -0.0120 | -0.60 | 2.0000 | 0.2500 |
| 7 | 2.0359 | 0.2495 | -0.0359 | -1.79 | 2.0000 | 0.2500 |
| 8 | 2.0964 | 0.2497 | -0.0964 | -4.82 | 2.0000 | 0.2500 |

### B. Order-2 Markov DNA source (1,000,000 bases)

Known-source code length on this sample, scored with the generating matrix: 1.7803 bits/base.

| order | bits/base | top-1 | gain over 2.0 (bits) | gain (% of 2.0) | floor bits/base | ceiling top-1 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.9148 | 0.3800 | +0.0852 | +4.26 | 1.9140 | 0.3808 |
| 2 | 1.7806 | 0.4435 | +0.2194 | +10.97 | 1.7791 | 0.4443 |
| 3 | 1.7814 | 0.4437 | +0.2186 | +10.93 | 1.7791 | 0.4443 |
| 4 | 1.7839 | 0.4429 | +0.2161 | +10.81 | 1.7791 | 0.4443 |
| 5 | 1.7915 | 0.4415 | +0.2085 | +10.43 | 1.7791 | 0.4443 |
| 6 | 1.8110 | 0.4360 | +0.1890 | +9.45 | 1.7791 | 0.4443 |
| 7 | 1.8521 | 0.4225 | +0.1479 | +7.39 | 1.7791 | 0.4443 |
| 8 | 1.9130 | 0.3973 | +0.0870 | +4.35 | 1.7791 | 0.4443 |

### C. Period-16 tandem repeat, substitution rate 0 (1,000,000 bases)

Distinct cyclic k-mers among the 16 template positions: k=1: 4, k=2: 12, k=3 to 8: 16.
Realized substitution fraction 0.0000.

| order | bits/base | top-1 | gain over 2.0 (bits) | gain (% of 2.0) | floor bits/base | ceiling top-1 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.6033 | 0.3125 | +0.3967 | +19.83 | 0.0000 | 1.0000 |
| 2 | 0.5475 | 0.6250 | +1.4525 | +72.62 | 0.0000 | 1.0000 |
| 3 | 0.0004 | 1.0000 | +1.9996 | +99.98 | 0.0000 | 1.0000 |
| 4 | 0.0004 | 1.0000 | +1.9996 | +99.98 | 0.0000 | 1.0000 |
| 5 | 0.0004 | 1.0000 | +1.9996 | +99.98 | 0.0000 | 1.0000 |
| 6 | 0.0004 | 1.0000 | +1.9996 | +99.98 | 0.0000 | 1.0000 |
| 7 | 0.0004 | 1.0000 | +1.9996 | +99.98 | 0.0000 | 1.0000 |
| 8 | 0.0004 | 1.0000 | +1.9996 | +99.98 | 0.0000 | 1.0000 |

### C. Period-16 tandem repeat, substitution rate 0.01 (1,000,000 bases)

Realized substitution fraction 0.0099.

| order | bits/base | top-1 | gain over 2.0 (bits) | gain (% of 2.0) | floor bits/base | ceiling top-1 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.6366 | 0.4349 | +0.3634 | +18.17 | 0.0966 | 0.9900 |
| 2 | 0.6949 | 0.7331 | +1.3051 | +65.25 | 0.0966 | 0.9900 |
| 3 | 0.1660 | 0.9745 | +1.8340 | +91.70 | 0.0966 | 0.9900 |
| 4 | 0.1242 | 0.9799 | +1.8758 | +93.79 | 0.0966 | 0.9900 |
| 5 | 0.1054 | 0.9870 | +1.8946 | +94.73 | 0.0966 | 0.9900 |
| 6 | 0.1015 | 0.9890 | +1.8985 | +94.92 | 0.0966 | 0.9900 |
| 7 | 0.1027 | 0.9886 | +1.8973 | +94.86 | 0.0966 | 0.9900 |
| 8 | 0.1042 | 0.9882 | +1.8958 | +94.79 | 0.0966 | 0.9900 |

### C. Period-16 tandem repeat, substitution rate 0.05 (1,000,000 bases)

Realized substitution fraction 0.0499.

| order | bits/base | top-1 | gain over 2.0 (bits) | gain (% of 2.0) | floor bits/base | ceiling top-1 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.7178 | 0.4250 | +0.2822 | +14.11 | 0.3656 | 0.9500 |
| 2 | 1.0535 | 0.6755 | +0.9465 | +47.32 | 0.3656 | 0.9500 |
| 3 | 0.6160 | 0.8784 | +1.3840 | +69.20 | 0.3656 | 0.9500 |
| 4 | 0.4930 | 0.9003 | +1.5070 | +75.35 | 0.3656 | 0.9500 |
| 5 | 0.4211 | 0.9303 | +1.5789 | +78.95 | 0.3656 | 0.9500 |
| 6 | 0.3957 | 0.9416 | +1.6043 | +80.21 | 0.3656 | 0.9500 |
| 7 | 0.3933 | 0.9429 | +1.6067 | +80.34 | 0.3656 | 0.9500 |
| 8 | 0.3985 | 0.9419 | +1.6015 | +80.08 | 0.3656 | 0.9500 |

### C. Period-16 tandem repeat, substitution rate 0.10 (1,000,000 bases)

Realized substitution fraction 0.0997.

| order | bits/base | top-1 | gain over 2.0 (bits) | gain (% of 2.0) | floor bits/base | ceiling top-1 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.7852 | 0.4120 | +0.2148 | +10.74 | 0.6275 | 0.9000 |
| 2 | 1.3399 | 0.6104 | +0.6601 | +33.01 | 0.6275 | 0.9000 |
| 3 | 1.0103 | 0.7716 | +0.9897 | +49.48 | 0.6275 | 0.9000 |
| 4 | 0.8579 | 0.8060 | +1.1421 | +57.10 | 0.6275 | 0.9000 |
| 5 | 0.7547 | 0.8523 | +1.2453 | +62.26 | 0.6275 | 0.9000 |
| 6 | 0.7053 | 0.8735 | +1.2947 | +64.74 | 0.6275 | 0.9000 |
| 7 | 0.6917 | 0.8791 | +1.3083 | +65.41 | 0.6275 | 0.9000 |
| 8 | 0.6979 | 0.8770 | +1.3021 | +65.10 | 0.6275 | 0.9000 |

### D. This repository's Python source (first 1 MiB)

No floor is known for this data. Ideal code length per input byte is four times bits/base, since
each byte becomes four bases.

| order | bits/base | top-1 | gain over 2.0 (bits) | gain (% of 2.0) | floor bits/base | ceiling top-1 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.8540 | 0.3926 | +0.1460 | +7.30 | - | - |
| 2 | 1.7193 | 0.4552 | +0.2807 | +14.04 | - | - |
| 3 | 1.4141 | 0.5792 | +0.5859 | +29.30 | - | - |
| 4 | 1.1750 | 0.6483 | +0.8250 | +41.25 | - | - |
| 5 | 1.0260 | 0.6970 | +0.9740 | +48.70 | - | - |
| 6 | 0.9174 | 0.7300 | +1.0826 | +54.13 | - | - |
| 7 | 0.8374 | 0.7518 | +1.1626 | +58.13 | - | - |
| 8 | 0.7576 | 0.7779 | +1.2424 | +62.12 | - | - |

### Summary: best order per dataset

| dataset | best order | bits/base | top-1 | gain over 2.0 (bits) |
|---|---:|---:|---:|---:|
| A. Uniform random bytes (1 MiB) | 1 | 2.0000 | 0.2498 | -0.0000 |
| B. Order-2 Markov DNA source (1,000,000 bases) | 2 | 1.7806 | 0.4435 | +0.2194 |
| C. Period-16 tandem repeat, substitution rate 0 (1,000,000 bases) | 3 | 0.0004 | 1.0000 | +1.9996 |
| C. Period-16 tandem repeat, substitution rate 0.01 (1,000,000 bases) | 6 | 0.1015 | 0.9890 | +1.8985 |
| C. Period-16 tandem repeat, substitution rate 0.05 (1,000,000 bases) | 7 | 0.3933 | 0.9429 | +1.6067 |
| C. Period-16 tandem repeat, substitution rate 0.10 (1,000,000 bases) | 7 | 0.6917 | 0.8791 | +1.3083 |
| D. This repository's Python source (first 1 MiB) | 8 | 0.7576 | 0.7779 | +1.2424 |

## Throughput and heap

`evaluateBytes` at order 8 on a 64 MiB random input, single evaluating thread, on the Gradle test
worker JVM (OpenJDK 21.0.12, 64-bit server VM). The input was generated outside the timed region.
One warm-up run on 8 MiB preceded the three timed runs. MB means MiB, 2^20 bytes.

| run | seconds | MiB/s | Mbases/s |
|---:|---:|---:|---:|
| 1 | 13.072 | 4.90 | 20.54 |
| 2 | 12.403 | 5.16 | 21.64 |
| 3 | 12.329 | 5.19 | 21.77 |

Median **5.16 MiB/s** (about 21.6 Mbases/s), min 4.90, max 5.19. This is the final run. Three earlier
executions of the same measurement, made while the test was being revised, gave medians of 5.19, 5.05
and 5.14 MiB/s. Across the four executions the median ranged from 5.05 to 5.19 MiB/s, and single runs
from 4.90 to 5.34 MiB/s. Treat the figure as approximate.

Heap: the sum of the JVM heap pools' peak usage since a reset just before the timed runs was
**80.78 MiB**. That includes the 64 MiB input array. Each pool's peak was taken separately, so the
sum is an upper bound on the combined peak. The test JVM's `Runtime.maxMemory` was 512 MiB. The
model's own table at order 8 is 1 MiB, which is 16 bytes times 4^8. The earlier executions reported
between 80.73 and 80.80 MiB.

All three runs gave identical reports. On this input, order 8 gave 2.0037 bits/base and top-1 0.2500.

## Reading the results

These statements describe the tables above. They are not claims beyond the measurements.

- **Uniform bytes (A).** No order beats the 2-bit baseline, and cost rises with order because each
  context is seen fewer times. The learning cost shrinks with more data: order 8 costs 2.0964 bits/base
  on 1 MiB, and 2.0037 on the 64 MiB throughput input.
- **Markov source (B).** Order 2 gives the lowest measured cost, 1.7806, which is 0.0015 above the
  exact entropy rate of 1.7791. Order 1 is 0.0008 above its own floor of 1.9140. Orders 3 to 8 cost
  more than order 2 on 1,000,000 bases, which is learning cost in sparse contexts. Order 8 is back
  near order 1.
- **Tandem repeats (C).** With no substitutions, orders 3 and up learn the template exactly, reaching
  top-1 1.0000. The residual 0.0004 bits/base is consistent with the additive smoothing, since with
  alpha = 0.5 no probability reaches 1. That was not measured separately. Orders 1 and 2 are ambiguous on this template: only 4 distinct 1-mers and
  12 distinct 2-mers appear among its 16 positions. With substitutions, the best measured order is 6 or
  7. The gap to the process floor at the best order is 0.0049 at r = 0.01, 0.0277 at r = 0.05 and
  0.0642 at r = 0.10. The gap widens with r. A likely explanation is that substitutions corrupt the
  higher-order contexts, but that was not measured separately.
- **Repository source (D).** Cost falls at every order from 1 to 8, down to 0.7576 bits/base at order 8,
  and top-1 rises to 0.7779. This is a single 1 MiB slice of source code, so it says nothing about text
  in general. Because the cost is still falling at order 8, the best order in this range is the largest
  one tested. Orders above 8 were not measured.

## Limitations

- **This is an estimator.** The predictor is an adaptive count model with additive smoothing. The
  numbers describe what this model does on these inputs. They are not the true entropy of the data,
  except where an exact floor from a known generator is stated, and then only as a bound.
- **The numbers are ideal code length, not real compressed size.** Each cost is the sum of
  -log2 p over bases. There is no arithmetic coder, no headers, no cost for the model's state, and no
  byte alignment. A real codec would produce a different size.
- **No real genome data was used.** All DNA here is synthetic: a seeded uniform stream, a made-up order-2
  Markov chain, and a random period-16 template with substitutions. Real genomes have structure these
  inputs lack, such as repeats at many scales and regional composition. Nothing here transfers to real DNA
  without measurement on it.
- **No Android device was measured.** Throughput and heap come from the Gradle test-worker JVM on a 4-vCPU
  Linux VM (Intel Xeon, 2.80 GHz). A JVM on this machine says nothing about ART on a phone, where speed,
  memory limits and garbage collection differ. The Android app module was not built or run, because the
  Android SDK is not available in this sandbox.
- **Single run, single thread.** Single timed runs ranged from 4.90 to 5.34 MiB/s across the four
  executions, about 9 percent, as shown above. The heap figure is an upper bound from summed pool peaks.
- **Finite inputs.** Results depend on sample size. The 1,000,000-base sources and the 1 MiB inputs carry
  learning cost that longer inputs would reduce.
- **Orders 1 to 8 only.** Orders 9 and 10 are supported by the code, but they were not part of this
  evaluation.
- **Dataset D is pinned, not live.** The file list is `predict/tools/corpus_116.txt`, and the test fails unless
  the slice hashes to the pinned SHA-256. Repository changes do not change the numbers, but they do break the
  check if they touch one of the first 104 listed files. The later listed files do not affect the slice. Two
  files added after the original run, `everlang_standalone/everlang/core/algebra.py` and
  `everlang_standalone/tests/test_algebra.py`, are not in the list, which is why a live walk now finds 118 files.
- **Floors are process bounds, not order-k bounds, for the tandem source.** An order-k predictor sees only k
  symbols, so it can sit above them. For the Markov source, the floors H(X_t given X_{t-1}) and the entropy
  rate are the bounds for orders 1 and 2 and up.

## Files

- `predict/tools/eval_reference.py`: exact references, stdlib only. Writes `predict/tools/eval_reference.tsv`.
- `predict/tools/markov_order2.tsv`: the transition weights of the order-2 source. The Python tool and the test both read it.
- `predict/src/test/kotlin/org/everlang/dna/predict/PredictorEvalTest.kt`: the gated evaluation.
- `predict/build/predictor-eval/results.md`: the report from the last run. This is a build output and is not committed.
- `predict/tools/ref_predict.py` and `predict/src/test/resources/predict_reference.tsv`: the parity reference for the predictor, unchanged.
