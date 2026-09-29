# Workflow Experiment Score Summary

- Run directory: `benchmark/runs/workflow_experiment_test-300_all_live_all_limit300_20260507_183507`
- Baseline: `full_jumpstarter`
- Scores: 4200
- Conditions: `adapt_recursive_decomposition`, `all_context`, `ask_before_plan`, `chatgpt_vanilla`, `chatgpt_with_elicited_context`, `chatgpt_with_structured_summary`, `flat_decomposition`, `full_jumpstarter`, `long_context_planner`, `no_elicitation`, `no_reuse`, `no_selection`, `random_selection`, `unstructured_memory_rag`

## Condition Summary

| Condition | n | Study quality mean | Study quality stderr | Overall mean | Output words mean | Selected ctx mean | Selected ctx tokens | Context precision | Relevance mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `adapt_recursive_decomposition` | 300 | 4.0538 | 0.0189 | 3.7500 | 2631.7633 | 7.7333 | 161.2333 | 0.7378 | 0.3279 |
| `all_context` | 300 | 4.0817 | 0.0262 | 3.8433 | 1117.3367 | 8.8867 | 436.7267 | 0.1424 | 0.0840 |
| `ask_before_plan` | 300 | 3.2208 | 0.0292 | 3.1433 | 570.5600 | 5.1200 | 170.5667 | 0.2386 | 0.1392 |
| `chatgpt_vanilla` | 300 | 3.7507 | 0.0228 | 3.8333 | 275.4833 | 0.0000 | 0.0000 | n/a | n/a |
| `chatgpt_with_elicited_context` | 300 | 3.6992 | 0.0245 | 3.7267 | 267.7167 | 0.0000 | 0.0000 | n/a | n/a |
| `chatgpt_with_structured_summary` | 300 | 3.7215 | 0.0241 | 3.7433 | 270.0167 | 0.0000 | 0.0000 | n/a | n/a |
| `flat_decomposition` | 300 | 4.2698 | 0.0237 | 4.0833 | 1086.6167 | 2.3433 | 268.4933 | 0.5639 | 0.2919 |
| `full_jumpstarter` | 300 | 4.1967 | 0.0243 | 3.9667 | 1077.7633 | 2.3367 | 266.8700 | 0.5381 | 0.2748 |
| `long_context_planner` | 300 | 3.2423 | 0.0218 | 3.1600 | 399.8067 | 4.0367 | 38.7767 | 0.1185 | 0.0884 |
| `no_elicitation` | 300 | 4.1903 | 0.0203 | 3.9433 | 917.8933 | 0.0000 | 0.0000 | n/a | n/a |
| `no_reuse` | 300 | 4.0880 | 0.0247 | 3.8700 | 954.7733 | 2.3300 | 238.8067 | 0.5502 | 0.2793 |
| `no_selection` | 300 | 4.2067 | 0.0241 | 3.9700 | 1061.2367 | 0.0000 | 0.0000 | n/a | n/a |
| `random_selection` | 300 | 4.1418 | 0.0241 | 3.8967 | 1091.6800 | 2.5633 | 296.6700 | 0.5240 | 0.2688 |
| `unstructured_memory_rag` | 300 | 3.2898 | 0.0211 | 3.1867 | 393.2567 | 3.3600 | 31.8067 | 0.2833 | 0.2068 |

## Baseline Comparisons

| Comparator | Mode | Matched n | Mean delta | 95% CI | W/T/L |
| --- | --- | ---: | ---: | ---: | ---: |
| `adapt_recursive_decomposition` | matched | 300 | 0.1428 | [0.0901, 0.1955] | 181/22/97 |
| `all_context` | matched | 300 | 0.1150 | [0.0537, 0.1763] | 162/36/102 |
| `ask_before_plan` | matched | 300 | 0.9758 | [0.9031, 1.0485] | 278/8/14 |
| `chatgpt_vanilla` | matched | 300 | 0.4460 | [0.3868, 0.5052] | 227/22/51 |
| `chatgpt_with_elicited_context` | matched | 300 | 0.4975 | [0.4395, 0.5555] | 243/16/41 |
| `chatgpt_with_structured_summary` | matched | 300 | 0.4752 | [0.4158, 0.5346] | 236/24/40 |
| `flat_decomposition` | matched | 300 | -0.0732 | [-0.1296, -0.0168] | 124/29/147 |
| `long_context_planner` | matched | 300 | 0.9543 | [0.8980, 1.0106] | 286/8/6 |
| `no_elicitation` | matched | 300 | 0.0063 | [-0.0482, 0.0608] | 136/28/136 |
| `no_reuse` | matched | 300 | 0.1087 | [0.0532, 0.1642] | 154/37/109 |
| `no_selection` | matched | 300 | -0.0100 | [-0.0688, 0.0488] | 131/35/134 |
| `random_selection` | matched | 300 | 0.0548 | [-0.0073, 0.1169] | 155/26/119 |
| `unstructured_memory_rag` | matched | 300 | 0.9068 | [0.8511, 0.9625] | 286/8/6 |

## Component Trace Metrics

| Condition | Elicited ctx | Substantive elicited | Unknown answers | Hierarchical decomps | Max node depth | Selected ctx | Reused ctx | Reuse events w/ ctx | Draft reuse events | Reused draft ctx | Saved drafts | Completed nodes | Completion ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `adapt_recursive_decomposition` | 0.0000 | 0.0000 | 0.0000 | 3.8800 | 3.1633 | 7.7333 | 7.7333 | 11.2233 | 0.0000 | 0.0000 | 0.0000 | 7.3433 | 0.6496 |
| `all_context` | 6.9433 | 1.1233 | 5.8200 | 2.8667 | 2.0000 | 8.8867 | 3.4133 | 3.7500 | 2.4367 | 2.3233 | 3.9433 | 2.9533 | 0.7486 |
| `ask_before_plan` | 3.0000 | 1.4833 | 1.5167 | 0.0000 | 1.0000 | 5.1200 | 5.1200 | 0.9600 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
| `chatgpt_vanilla` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `chatgpt_with_elicited_context` | 3.0000 | 1.0400 | 1.9600 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `chatgpt_with_structured_summary` | 3.0000 | 0.9867 | 2.0133 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `flat_decomposition` | 6.9467 | 1.0833 | 5.8633 | 0.0000 | 1.0000 | 2.3433 | 2.3433 | 3.7000 | 1.5633 | 1.4333 | 3.9467 | 2.9200 | 0.7397 |
| `full_jumpstarter` | 6.9667 | 1.1633 | 5.8033 | 2.9167 | 1.9933 | 2.3367 | 2.3367 | 3.7733 | 1.5933 | 1.4000 | 3.9667 | 2.8767 | 0.7247 |
| `long_context_planner` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 4.0367 | 4.0367 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
| `no_elicitation` | 0.0000 | 0.0000 | 0.0000 | 2.8933 | 1.9900 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3.9600 | 1.0667 | 0.2697 |
| `no_reuse` | 6.9533 | 1.2500 | 5.7033 | 2.9067 | 1.9867 | 2.3300 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3.9533 | 1.0133 | 0.2561 |
| `no_selection` | 6.9467 | 1.2967 | 5.6500 | 2.8333 | 1.9867 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3.9467 | 0.9833 | 0.2492 |
| `random_selection` | 6.9767 | 1.2033 | 5.7733 | 2.8733 | 1.9967 | 2.5633 | 2.5633 | 3.7500 | 1.5900 | 1.5967 | 3.9767 | 2.8767 | 0.7236 |
| `unstructured_memory_rag` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 3.3600 | 3.3600 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |

## GPT Context Relevance Metrics

| Condition | GPT ctx precision | GPT ctx recall | GPT ctx F1 | GPT selected relevance | GPT reused precision | GPT reused relevance | GPT used relevant | GPT used relevant rate | GPT available relevance | GPT available relevant | GPT relevant selected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `adapt_recursive_decomposition` | 0.7549 | 0.7104 | 0.7268 | 0.6865 | 0.7549 | 0.6865 | 26.3933 | 0.7104 | 0.3173 | 37.6800 | 26.3933 |
| `all_context` | 0.2186 | 1.0000 | 0.3521 | 0.2530 | 0.4958 | 0.4743 | 4.1300 | 0.8125 | 0.2530 | 5.1300 | 5.1300 |
| `ask_before_plan` | 0.9840 | 0.8921 | 0.9454 | 0.8879 | 0.9840 | 0.8879 | 5.0367 | 0.8921 | 0.6682 | 5.5867 | 5.0367 |
| `chatgpt_vanilla` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `chatgpt_with_elicited_context` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `chatgpt_with_structured_summary` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `flat_decomposition` | 0.7205 | 0.5956 | 0.6413 | 0.6208 | 0.7205 | 0.6208 | 3.6667 | 0.5956 | 0.2836 | 6.2867 | 3.6667 |
| `full_jumpstarter` | 0.5536 | 0.5981 | 0.5988 | 0.5196 | 0.5536 | 0.5196 | 2.8733 | 0.5981 | 0.2380 | 4.7533 | 2.8733 |
| `long_context_planner` | 0.8650 | 0.9980 | 0.9168 | 0.7865 | 0.8650 | 0.7865 | 3.4900 | 0.9980 | 0.3928 | 3.5000 | 3.4900 |
| `no_elicitation` | n/a | 0.0000 | n/a | n/a | n/a | n/a | 0.0000 | 0.0000 | 0.4865 | 2.9367 | 0.0000 |
| `no_reuse` | 0.4484 | 0.5551 | 0.5350 | 0.4508 | n/a | n/a | 0.0000 | 0.0000 | 0.2173 | 4.0367 | 2.2667 |
| `no_selection` | n/a | 0.0000 | n/a | n/a | n/a | n/a | 0.0000 | 0.0000 | 0.2152 | 3.7600 | 0.0000 |
| `random_selection` | 0.5572 | 0.5732 | 0.5739 | 0.5160 | 0.5572 | 0.5160 | 2.8433 | 0.5732 | 0.2455 | 5.0433 | 2.8433 |
| `unstructured_memory_rag` | 0.9375 | 0.8633 | 0.8657 | 0.8620 | 0.9375 | 0.8620 | 3.1100 | 0.8633 | 0.4063 | 3.6100 | 3.1100 |
