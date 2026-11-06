# CSV generalisation benchmark (exploratory)

**How to read this.** This is a small, exploratory benchmark (80 hand-written questions, 8 public CSV files) reported separately from the
143-question Chinook benchmark and its held-out test split. Questions were written after looking at each file's schema and value profile, and
before any model output. Prompts were frozen before the files were chosen and were not tuned on these results. Questions within a file are not
independent, so the intervals below are optimistic. One more public file (`bad-drivers.csv`) was left out because its long headers collapse to
near-identical column names; see the manifest.

## Execution accuracy

| Model | Approach | Correct | Accuracy | 95% CI | p50 latency |
|---|---|---|---|---|---|
| qwen2.5-coder:3b | plain | 63/80 | 78.8% | 68.6 to 86.3% | 2.5 s |
| qwen2.5-coder:3b | profiled | 70/80 | 87.5% | 78.5 to 93.1% | 2.5 s |
| qwen2.5-coder:3b | profiled_retry | 70/80 | 87.5% | 78.5 to 93.1% | 2.5 s |
| qwen2.5-coder:7b | plain | 64/80 | 80.0% | 70.0 to 87.3% | 2.7 s |
| qwen2.5-coder:7b | profiled | 75/80 | 93.8% | 86.2 to 97.3% | 2.7 s |
| qwen2.5-coder:7b | profiled_retry | 75/80 | 93.8% | 86.2 to 97.3% | 2.7 s |

## Paired comparisons (exact McNemar; each row compares the same questions)

| Model | A vs B | A only right | B only right | p |
|---|---|---|---|---|
| qwen2.5-coder:3b | profiled vs plain | 9 | 2 | 0.0654 |
| qwen2.5-coder:3b | profiled_retry vs profiled | 0 | 0 | 1.0 |
| qwen2.5-coder:3b | profiled_retry vs plain | 9 | 2 | 0.0654 |
| qwen2.5-coder:7b | profiled vs plain | 12 | 1 | 0.0034 |
| qwen2.5-coder:7b | profiled_retry vs profiled | 0 | 0 | 1.0 |
| qwen2.5-coder:7b | profiled_retry vs plain | 12 | 1 | 0.0034 |
| both models pooled | profiled vs plain | 21 | 3 | 0.0003 |
| both models pooled | profiled_retry vs profiled | 0 | 0 | 1.0 |
| both models pooled | profiled_retry vs plain | 21 | 3 | 0.0003 |

## Model size, H8 (paired: qwen2.5-coder:7b vs qwen2.5-coder:3b)

| Approach | A only right | B only right | p |
|---|---|---|---|
| plain | 3 (7b) | 2 (3b) | 1.0 |
| profiled | 5 (7b) | 0 (3b) | 0.0625 |
| profiled_retry | 5 (7b) | 0 (3b) | 0.0625 |

## By question category (correct/total)

| category | 3b plain | 3b profiled | 3b profiled_retry | 7b plain | 7b profiled | 7b profiled_retry |
|---|---|---|---|---|---|---|
| aggregate | 10/14 | 12/14 | 12/14 | 12/14 | 14/14 | 14/14 |
| count | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |
| filter | 13/16 | 14/16 | 14/16 | 13/16 | 14/16 | 14/16 |
| group | 5/7 | 6/7 | 6/7 | 5/7 | 6/7 | 6/7 |
| null | 5/5 | 5/5 | 5/5 | 4/5 | 5/5 | 5/5 |
| ranking | 18/20 | 17/20 | 17/20 | 18/20 | 19/20 | 19/20 |
| subquery | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| text_values | 2/8 | 6/8 | 6/8 | 2/8 | 7/8 | 7/8 |

## By dataset (correct/total)

| dataset | 3b plain | 3b profiled | 3b profiled_retry | 7b plain | 7b profiled | 7b profiled_retry |
|---|---|---|---|---|---|---|
| airline_safety | 8/10 | 8/10 | 8/10 | 9/10 | 10/10 | 10/10 |
| candy_data | 8/10 | 8/10 | 8/10 | 7/10 | 8/10 | 8/10 |
| coffee_ratings | 8/10 | 9/10 | 9/10 | 9/10 | 10/10 | 10/10 |
| dc_wikia_data | 5/10 | 6/10 | 6/10 | 4/10 | 7/10 | 7/10 |
| penguins | 8/10 | 10/10 | 10/10 | 8/10 | 10/10 | 10/10 |
| recent_grads | 9/10 | 10/10 | 10/10 | 9/10 | 10/10 | 10/10 |
| seattle_weather | 7/10 | 9/10 | 9/10 | 8/10 | 10/10 | 10/10 |
| titanic | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |

## By difficulty (correct/total)

| difficulty | 3b plain | 3b profiled | 3b profiled_retry | 7b plain | 7b profiled | 7b profiled_retry |
|---|---|---|---|---|---|---|
| easy | 15/18 | 18/18 | 18/18 | 14/18 | 18/18 | 18/18 |
| hard | 24/29 | 24/29 | 24/29 | 24/29 | 25/29 | 25/29 |
| medium | 24/33 | 28/33 | 28/33 | 26/33 | 32/33 | 32/33 |

## Failure types (wrong answers)

- **qwen2.5-coder:3b / plain**: wrong_filter 7, other_wrong_result 5, wrong_aggregation 2, wrong_output_columns 2, hallucinated_column 1
- **qwen2.5-coder:3b / profiled**: wrong_filter 5, wrong_output_columns 2, wrong_aggregation 1, db_error_other 1, other_wrong_result 1
- **qwen2.5-coder:3b / profiled_retry**: wrong_filter 5, wrong_aggregation 2, wrong_output_columns 2, other_wrong_result 1
- **qwen2.5-coder:7b / plain**: wrong_filter 8, other_wrong_result 4, wrong_aggregation 2, wrong_output_columns 2
- **qwen2.5-coder:7b / profiled**: wrong_filter 3, wrong_aggregation 1, wrong_output_columns 1
- **qwen2.5-coder:7b / profiled_retry**: wrong_filter 3, wrong_aggregation 1, wrong_output_columns 1
