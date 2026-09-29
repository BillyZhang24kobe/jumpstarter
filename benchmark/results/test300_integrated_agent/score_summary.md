# Workflow Experiment Score Summary

- Run directory: `benchmark/runs/react_full_test300_limit300`
- Baseline: `full_jumpstarter`
- Scores: 600
- Conditions: `full_jumpstarter`, `react_integrated_planner`

## Condition Summary

| Condition | n | Study quality mean | Study quality stderr | Overall mean | Output words mean | Selected ctx mean | Selected ctx tokens | Context precision | Relevance mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_jumpstarter` | 300 | 4.1925 | 0.0246 | 3.9900 | 1071.0200 | 2.3700 | 270.0133 | 0.5258 | 0.2696 |
| `react_integrated_planner` | 300 | 3.9375 | 0.0196 | 3.8000 | 1099.5567 | 5.4033 | 79.5833 | 0.5168 | 0.2307 |

## Baseline Comparisons

| Comparator | Mode | Matched n | Mean delta | 95% CI | W/T/L |
| --- | --- | ---: | ---: | ---: | ---: |
| `react_integrated_planner` | matched | 300 | 0.2550 | [0.2033, 0.3067] | 196/32/72 |

## Component Trace Metrics

| Condition | Elicited ctx | Substantive elicited | Unknown answers | Hierarchical decomps | Max node depth | Selected ctx | Reused ctx | Reuse events w/ ctx | Draft reuse events | Reused draft ctx | Saved drafts | Completed nodes | Completion ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_jumpstarter` | 6.9567 | 1.2100 | 5.7467 | 2.9067 | 1.9967 | 2.3700 | 2.3700 | 3.7667 | 1.4833 | 1.4067 | 3.9567 | 2.8500 | 0.7206 |
| `react_integrated_planner` | 3.0000 | 0.9367 | 2.0633 | 0.0000 | 1.0000 | 5.4033 | 5.4033 | 3.9533 | 0.0000 | 0.0000 | 0.0000 | 3.9533 | 1.0000 |
