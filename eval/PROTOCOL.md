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
