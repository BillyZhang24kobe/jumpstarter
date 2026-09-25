# Paper Tables

Paired over the 300 held-out test profiles. Delta = first-named condition minus comparator; a profile is a tie when |delta| <= 1e-09.

## Table 2: JumpStarter-Shallow vs. every condition

| Condition | Run | n | Study quality | Delta (Shallow - condition) | 95% CI | W/T/L |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| **JumpStarter-Shallow** (`flat_decomposition`) | main | 300 | 4.2698 | -- | -- | -- |
| ChatGPT vanilla (`chatgpt_vanilla`) | main | 300 | 3.7507 | +0.5192 | [+0.4602, +0.5782] | 255/8/37 |
| ChatGPT + elicited context (`chatgpt_with_elicited_context`) | main | 300 | 3.6992 | +0.5707 | [+0.5092, +0.6322] | 257/6/37 |
| ChatGPT + structured summary (`chatgpt_with_structured_summary`) | main | 300 | 3.7215 | +0.5483 | [+0.4897, +0.6070] | 260/6/34 |
| Single-turn decomposition (`single_turn_decomposition`) | single_turn | 300 | 4.0503 | +0.2195 | [+0.1637, +0.2753] | 197/11/92 |
| All-context prompting (`all_context`) | main | 300 | 4.0817 | +0.1882 | [+0.1275, +0.2488] | 178/9/113 |
| Random context selection (`random_selection`) | main | 300 | 4.1418 | +0.1280 | [+0.0690, +0.1870] | 171/17/112 |
| No context selection (`no_selection`) | main | 300 | 4.2067 | +0.0632 | [+0.0041, +0.1222] | 156/12/132 |
| No context reuse (`no_reuse`) | main | 300 | 4.0880 | +0.1818 | [+0.1251, +0.2385] | 180/17/103 |
| No elicitation (`no_elicitation`) | main | 300 | 4.1903 | +0.0795 | [+0.0270, +0.1320] | 163/15/122 |
| JumpStarter-Recursive (`full_jumpstarter`) | main | 300 | 4.1967 | +0.0732 | [+0.0167, +0.1296] | 158/12/130 |
| ADaPT-style recursive decomposition (`adapt_recursive_decomposition`) | main | 300 | 4.0538 | +0.2160 | [+0.1649, +0.2671] | 200/20/80 |
| Ask-before-plan (`ask_before_plan`) | main | 300 | 3.2208 | +1.0490 | [+0.9791, +1.1189] | 287/4/9 |
| Long-context planner (`long_context_planner`) | main | 300 | 3.2423 | +1.0275 | [+0.9712, +1.0838] | 292/3/5 |
| Unstructured memory-RAG (`unstructured_memory_rag`) | main | 300 | 3.2898 | +0.9800 | [+0.9234, +1.0366] | 291/2/7 |
| Integrated agentic planner (`react_integrated_planner`) | agent | 300 | 3.9375 | +0.3323 | [+0.2813, +0.3833] | 227/14/59 |

## Single-turn decomposition baseline

| Comparison | n | Delta | 95% CI | W/T/L |
| --- | ---: | ---: | --- | ---: |
| JumpStarter-Shallow - single-turn | 300 | +0.2195 | [+0.1637, +0.2753] | 197/11/92 |
| JumpStarter-Recursive - single-turn | 300 | +0.1463 | [+0.0874, +0.2053] | 186/9/105 |
| ChatGPT + elicited context - single-turn | 300 | -0.3512 | [-0.4081, -0.2943] | 52/13/235 |
| Shallow - single-turn, complex goals | 150 | +0.2510 | [+0.1657, +0.3363] | 100/4/46 |
| Shallow - single-turn, simple goals | 150 | +0.1880 | [+0.1160, +0.2600] | 97/7/46 |
| Recursive - single-turn, complex goals | 150 | +0.2383 | [+0.1485, +0.3281] | 106/4/40 |
| Recursive - single-turn, simple goals | 150 | +0.0543 | [-0.0195, +0.1281] | 80/5/65 |

### Per-dimension delta vs. single-turn

| Dimension | Shallow | Recursive |
| --- | ---: | ---: |
| `context_curation_reuse` | +1.357 [+1.256, +1.457] | +1.540 [+1.445, +1.635] |
| `personalization_context_grounding` | +0.660 [+0.562, +0.758] | +0.557 [+0.455, +0.658] |
| `workflow_progress_support` | +0.190 [+0.111, +0.269] | +0.360 [+0.284, +0.435] |
| `no_contradiction_hallucination` | +0.277 [+0.145, +0.408] | -0.867 [-1.015, -0.718] |
| `specificity` | +0.060 [-0.019, +0.139] | +0.107 [+0.026, +0.188] |
| `completeness_coverage` | +0.257 [+0.174, +0.340] | +0.003 [-0.081, +0.088] |
| `decomposition_quality` | +0.120 [+0.043, +0.197] | +0.013 [-0.067, +0.094] |
| `plan_quality` | -0.113 [-0.189, -0.037] | -0.170 [-0.247, -0.092] |
| `user_burden_reduction` | -0.067 [-0.145, +0.012] | -0.050 [-0.129, +0.029] |
| `tangible_result_quality` | -0.017 [-0.102, +0.068] | -0.373 [-0.471, -0.275] |
| `confidence_support` | -0.107 [-0.178, -0.035] | -0.113 [-0.188, -0.039] |
| `overall` | -0.010 [-0.084, +0.064] | -0.127 [-0.199, -0.055] |

## Integrated agentic planner

Agent mean 3.9375; JumpStarter-Recursive in the agent run 4.1925.

| Comparison | n | Delta | 95% CI | W/T/L |
| --- | ---: | ---: | --- | ---: |
| JumpStarter-Shallow - agent | 300 | +0.3323 | [+0.2813, +0.3833] | 227/14/59 |
| JumpStarter-Recursive (agent run) - agent | 300 | +0.2550 | [+0.2033, +0.3067] | 205/18/77 |
| Single-turn - agent | 300 | +0.1128 | [+0.0607, +0.1649] | 175/12/113 |
| Recursive (agent run) - Recursive (main run), rerun check | 300 | -0.0042 | [-0.0592, +0.0509] | 147/15/138 |
| Shallow - agent, high goals | 85 | +0.3000 | [+0.1919, +0.4081] | 60/3/22 |
| Shallow - agent, medium goals | 150 | +0.3470 | [+0.2773, +0.4167] | 118/8/24 |
| Shallow - agent, moderate to high goals | 5 | +0.4900 | [-0.0569, +1.0369] | 4/0/1 |
| Shallow - agent, multi-track goals | 60 | +0.3283 | [+0.2295, +0.4272] | 45/3/12 |
| Recursive - agent, high goals | 85 | +0.2335 | [+0.1364, +0.3307] | 56/4/25 |
| Recursive - agent, medium goals | 150 | +0.2410 | [+0.1671, +0.3149] | 100/10/40 |
| Recursive - agent, moderate to high goals | 5 | +0.2700 | [+0.0474, +0.4926] | 4/0/1 |
| Recursive - agent, multi-track goals | 60 | +0.3192 | [+0.2025, +0.4359] | 45/4/11 |

### Per-dimension delta vs. the integrated agent

| Dimension | Shallow | Recursive (agent run) |
| --- | ---: | ---: |
| `context_curation_reuse` | +0.577 [+0.492, +0.661] | +0.733 [+0.652, +0.814] |
| `personalization_context_grounding` | +0.630 [+0.531, +0.729] | +0.570 [+0.479, +0.661] |
| `workflow_progress_support` | +0.337 [+0.267, +0.407] | +0.463 [+0.392, +0.535] |
| `no_contradiction_hallucination` | +1.217 [+1.081, +1.352] | +0.097 [-0.033, +0.226] |
| `specificity` | +0.063 [-0.007, +0.134] | +0.080 [+0.006, +0.154] |
| `completeness_coverage` | +0.193 [+0.116, +0.271] | -0.073 [-0.159, +0.012] |
| `decomposition_quality` | +0.240 [+0.169, +0.311] | +0.097 [+0.020, +0.173] |
| `plan_quality` | +0.263 [+0.200, +0.327] | +0.213 [+0.146, +0.280] |
| `user_burden_reduction` | +0.223 [+0.154, +0.293] | +0.250 [+0.181, +0.319] |
| `tangible_result_quality` | +0.310 [+0.232, +0.388] | -0.013 [-0.101, +0.074] |
| `confidence_support` | +0.250 [+0.178, +0.322] | +0.223 [+0.151, +0.296] |
| `overall` | +0.283 [+0.218, +0.349] | +0.190 [+0.122, +0.258] |

Mean output words: `react_integrated_planner` 1100, `full_jumpstarter (agent run)` 1071, `single_turn_decomposition` 357.

| Trace metric | `react_integrated_planner` | `full_jumpstarter (agent run)` |
| --- | ---: | ---: |
| Elicited ctx items | 3.0000 | 6.9567 |
| Selected ctx items | 5.4033 | 2.3700 |
| Reused ctx items | 5.4033 | 2.3700 |
| Reuse events w/ ctx | 3.9533 | 3.7667 |
| Draft reuse events | 0.0000 | 1.4833 |
| Reused draft ctx items | 0.0000 | 1.4067 |
| Saved drafts | 0.0000 | 3.9567 |
| Completed nodes | 3.9533 | 2.8500 |
| Selected ctx tokens | 79.5833 | 270.0133 |

## Context selection and trace metrics (main run)

| Condition | Selected ctx tokens | GPT ctx precision | Elicited ctx items | Selected ctx items | Reused ctx items | Reuse events w/ ctx | Draft reuse events | Reused draft ctx items | Saved drafts | Completed nodes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `flat_decomposition` | 268.4933 | 0.7205 | 6.9467 | 2.3433 | 2.3433 | 3.7000 | 1.5633 | 1.4333 | 3.9467 | 2.9200 |
| `full_jumpstarter` | 266.8700 | 0.5536 | 6.9667 | 2.3367 | 2.3367 | 3.7733 | 1.5933 | 1.4000 | 3.9667 | 2.8767 |
| `all_context` | 436.7267 | 0.2186 | 6.9433 | 8.8867 | 3.4133 | 3.7500 | 2.4367 | 2.3233 | 3.9433 | 2.9533 |
| `random_selection` | 296.6700 | 0.5572 | 6.9767 | 2.5633 | 2.5633 | 3.7500 | 1.5900 | 1.5967 | 3.9767 | 2.8767 |
| `no_selection` | 0.0000 | n/a | 6.9467 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3.9467 | 0.9833 |
| `no_reuse` | 238.8067 | 0.4484 | 6.9533 | 2.3300 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3.9533 | 1.0133 |
| `no_elicitation` | 0.0000 | n/a | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3.9600 | 1.0667 |

## Input context tokens per session (quality-vs-context-efficiency figure)

Counted from rendered prompts in the full session traces; read from `figures/quality_context_efficiency_stats.csv` in the main run.

| Condition | Input context tokens |
| --- | ---: |
| `no_elicitation` | 11723.6 |
| `no_reuse` | 19779.8 |
| `all_context` | 26955.2 |
| `random_selection` | 24145.5 |
| `full_jumpstarter` | 24345.4 |
| `flat_decomposition` | 19158.1 |
