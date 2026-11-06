# Experiment protocol (written before the test-split run)

**Data.** 143 hand-written questions over Chinook. Dev (51) was used for exploration and prompt design;
test (92) is held out and run **once** per (model, approach). The runner refuses to overwrite a test run.
Few-shot examples come from a separate pool that is checked (by a test) to be disjoint from both splits.

**Models.** qwen2.5-coder 3B and 7B (Ollama, temperature 0, fixed seed); voting samples at T=0.6.

**Metric.** Execution accuracy (result-set equivalence). Exact match, latency and failure categories are secondary.
Uncertainty: 95% Wilson intervals; paired comparisons with an exact McNemar test against the zero-shot run of the
same model. Dev results are exploratory (11 comparisons, no multiplicity correction).

**Hypotheses fixed before looking at test**
- H1: retrieved examples (`shots_only`, `fewshot`) improve the 3B model over zero-shot.
- H2: no approach improves the 7B model over zero-shot (it is near ceiling on easy/medium).
- H3: execution voting and error-feedback self-correction add nothing beyond their base prompt,
  because failures are mostly systematic, wrong-but-executable queries.
- H4 (exploratory): schema documentation (`docs`) hurts the 3B model by increasing hallucinated columns.

Anything not listed above is exploratory and will be labelled as such in the write-up.

---

# Addendum: CSV generalisation benchmark (written 6 Nov 2026, before any model was run on it)

This is a separate, **exploratory** benchmark for the upload feature. It is not the held-out Chinook test and is never pooled with it.

**Data.** Eight public CSV files, fetched from the original GitHub repositories at pinned commits and verified by SHA-256
(`eval/csvbench/manifest.json`): penguins, titanic, seattle-weather, recent-grads, airline-safety, candy-data, dc-wikia-data and
coffee_ratings. They were chosen for variety of mess (missing cells, ALL-CAPS and footnote-marked text, label values such as
`Male Characters`, text dates, 43 columns), not for how the models would score. A ninth file (`bad-drivers.csv`) was **excluded after
ingestion** because its long headers collapse to near-identical column names, so questions on them cannot be answered by any model.
That is a limitation of `normalize_name`, not a model result, and it is reported as such.

**Questions.** 80 hand-written questions (10 per file) with gold SQL on the ingested schema. They were written after looking at each file's
schema and value profile and **before any model output**. The builder applies the Chinook checks (valid, non-empty, deterministic, no tie at a
LIMIT boundary) and additionally rejects gold answers of 0, 1 or NULL, so `SELECT 0` and `SELECT 1` cannot score by luck. Self-tests on the real
data: an oracle that returns the gold SQL scores 100% for all three approaches, and a constant `SELECT 1` scores 0%.

**What is frozen.** The three prompt variants (`plain`, `profiled`, `profiled_retry`), the sanitiser, the ingestion rules, the questions and the
scoring. They were all written before these files were chosen. **No change to any of them after the first model run on this benchmark.** If
something must change, it becomes a new, labelled version and the old results stay in the report.

**Models and runs.** qwen2.5-coder 3B and 7B, temperature 0, seed 0. Each (model, approach) is run once (the runner refuses to overwrite).
Execution accuracy uses the same comparison as the main benchmark (`results_match`). Execution is hardened as in the product.

**Hypotheses (fixed now).**
- H5: `profiled` beats `plain` on execution accuracy, for each model. This is the primary comparison.
- H6: Any gain from `profiled` is concentrated in questions that depend on knowing the stored values or the NULL convention (categories
  `null` and `text_values`, 13 questions). Descriptive only: far too few questions for inference.
- H7: `profiled_retry` adds little over `profiled` (the same pattern as finding 4 on Chinook).
- H8: 7B beats 3B within every approach (the same direction as finding 1).

**Analysis rules.** 95% Wilson intervals and exact McNemar tests on paired questions, reported for both models and pooled. Uncorrected p-values
are labelled exploratory. Questions within a file are correlated, so intervals are optimistic. Pooling both models counts the same question twice
and is only illustrative. Results will be reported whichever way they come out, including no difference, and small-n category results will
not be presented as findings.

**What this can and cannot show.** It can show whether the profiled schema helps on a small sample of public messy files, with these two small
models. It cannot show generalisation to arbitrary uploads, to bigger models, or to files whose columns are described in other languages.
The questions and prompts were written by the same author (and Claude), so some unconscious fit between them is possible.
