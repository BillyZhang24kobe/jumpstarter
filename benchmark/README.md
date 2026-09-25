# JumpStarter simulation benchmark

This benchmark runs simulated planning sessions. JumpStarter and every baseline work with persona-grounded simulated users on the same goals, and a blinded LLM judge scores the final plans. It produces the paper's simulation results: Table 2, the mechanism analysis, the failure-case analysis, and the quality-vs.-context-efficiency figure.

Run all commands from the repository root. Commands that call OpenAI need `OPENAI_API_KEY` (see the [top-level README](../README.md)); everything else runs offline.

## Reproduce the paper's numbers

No API key needed. These read the judged results in [`results/`](results/):

```bash
python -m benchmark.cli paper-tables            # Table 2, single-turn and integrated-agent comparisons, context metrics
python -m benchmark.cli analyze-failure-cases   # failure-case analysis
python benchmark/plot_quality_context_efficiency.py \
  benchmark/results/test300_main/score_summary.json --out-dir figures
```

| Output | Paper |
| --- | --- |
| `reports/paper_tables.md` / `.json`, `reports/paper_tables_table2.tex` | Table 2; single-turn decomposition baseline; integrated agentic planner; context precision and trace metrics |
| `reports/failure_analysis.md` / `.json` | Failure-case analysis: loss rates, breakdowns by goal and persona, per-dimension deltas on losses, depth failure mode, largest losses |
| `figures/quality_context_efficiency.pdf` and `_stats.csv` | Quality vs. context-efficiency figure |

All comparisons pair conditions on the same 300 held-out simulation profiles by `simulation_profile_id`. Deltas are the first-named condition minus the comparator, with normal-approximation 95% confidence intervals. Win/tie/loss counts treat only equal scores as ties.

## Results

`results/` holds the judged results of the three runs reported in the paper, all on `data/simulation_profiles_test_300.json`:

| Directory | Conditions | Original run name |
| --- | --- | --- |
| `test300_main/` | The 14 conditions of the main experiment | `workflow_experiment_test-300_all_live_all_limit300_20260507_183507` |
| `test300_single_turn/` | Single-turn decomposition | `single_turn_decomposition_test300` |
| `test300_integrated_agent/` | Integrated agentic planner, plus a rerun of JumpStarter-Recursive | `react_full_test300_limit300` |

Each directory contains:

| File | Contents |
| --- | --- |
| `condition_key.jsonl` | Maps each blinded `blind_id` to its condition, simulation profile, persona, and goal |
| `judge_scores.jsonl` | GPT-5.5 judge scores for each blinded artifact: 12 rubric criteria with evidence, the extracted evidence record, and the `study_quality_score` composite |
| `artifacts.jsonl` | The final plan each session produced, as shown to the judge |
| `score_summary.json` / `.md` | Per-condition summary from `analyze-workflow-experiment`, including context and trace metrics (its W/T/L uses a ±0.05 tie band, unlike the paper) |
| `mechanism_metrics.json` | Per-session context selection and reuse metrics |
| `context_relevance_metrics.json` | Per-session GPT context-relevance labels, main run only |
| `workflow_prompt_tokens.json`, `figures/` | Input-token counts and the figure, main run only |
| `run_config.json`, `experiment_report.json`, `workflow_fidelity_report.json`, `judge_run_report.json` | Run settings and checks |

The full session traces, about 2.3 GB, are not included. The trace metrics in `score_summary.json` and the token counts in `workflow_prompt_tokens.json` were computed from them.

## Layout

| Path | What it does |
| --- | --- |
| `cli.py` | Entry point for every command: `python -m benchmark.cli <command> --help` |
| `pipeline.py`, `similarity.py` | Build and validate the 60-goal benchmark |
| `personas.py` | Extract the 9 base personas and 11 controlled variants |
| `simulation_profiles.py` | Cross personas and goals into 1,200 simulation profiles; build the validation, test, and test-300 splits |
| `user_decision_calibration.py` | Estimate the simulated user's decision rates from the study logs |
| `workflow_simulator.py` | Simulate a session for each condition (`CONDITION_DESCRIPTIONS`, `WORKFLOW_CONDITIONS`) |
| `workflow_prompts.py`, `prompts/paper_workflow_v1/` | The JumpStarter prompts from the paper's appendix |
| `experiment_runner.py` | Run many profiles × conditions and write blinded judge inputs |
| `openai_generation.py` | OpenAI calls: structured outputs, retries, model defaults |
| `judge.py`, `prompts/judge_*.txt` | Blinded LLM judge, study-quality composite, judge calibration |
| `context_relevance.py`, `prompts/context_relevance_label_v1.txt` | GPT context-relevance labeler |
| `workflow_analysis.py` | Per-condition summaries (`analyze-workflow-experiment`) |
| `paper_tables.py`, `failure_analysis.py`, `plot_quality_context_efficiency.py` | The paper's tables, failure analysis, and figure |
| `schemas.py` | Pydantic models for every record |
| `data/`, `reports/`, `results/` | Frozen benchmark data, build and calibration reports, paper results |
| `run_live_workflow_benchmark.sh` | Runs a live experiment end to end: simulate, judge, label, analyze |

## Data

| File | Contents |
| --- | --- |
| `data/benchmark.json` | 60 planning goals across 5 domains, with complexity, time horizon, expected outputs, and context needs |
| `data/personas.json` | 20 personas: 9 derived from study participants, 11 controlled variants that change one behavioral axis |
| `data/simulation_profiles.json` | 1,200 persona × goal profiles: private facts, what the user reveals when asked, approval and pushback rules |
| `data/simulation_profiles_test_300.json` | The 300 held-out profiles used in the paper (5 per goal, 15 per persona) |
| `data/simulation_profiles_validation_limit10.json`, `data/simulation_profiles_test_excluding_validation.json`, `data/simulation_profile_split.json` | The validation split, the full test split, and split metadata |
| `data/user_decision_calibration.json` | Decision rates the simulated user samples from (accepting a task tree, decomposing, saving drafts, completing nodes) |
| `data/generated_candidates.json`, `data/filter_decisions.json`, `fixtures/generated_goals.json` | Goal candidates generated with GPT-5.5 and the filter decisions that produced the 48 synthesized goals |

The goals, personas, and decision rates were built from the user-study logs, which are not released. The commands that read those logs (`build-anchors`, `build-all`, `build-personas`, `build-user-decision-calibration`, and the judge-calibration builders) will not run from the public repository. Their outputs are frozen in `data/` and `reports/`.

## Run experiments

The simulator is deterministic by default: it renders every prompt and records every stage but calls no model. This runs all 16 conditions on 5 profiles in a few seconds:

```bash
python -m benchmark.cli run-workflow-experiment --conditions all,single_turn_decomposition --limit 5 --output-dir benchmark/runs/smoke
python -m benchmark.cli run-judge benchmark/runs/smoke/judge_inputs_blinded.jsonl --output benchmark/runs/smoke/judge_scores.jsonl
python -m benchmark.cli analyze-workflow-experiment benchmark/runs/smoke
```

Without `--live`, `run-judge` gives heuristic dry-run scores, which are useful only for checking the pipeline.

The paper's runs used live GPT-4o workflow stages and GPT-4o simulated users, the GPT-5.5 judge, and the GPT-5.4-mini relevance labeler. `run_live_workflow_benchmark.sh` runs all four steps. These commands recreate the three runs; they make many API calls, and LLM outputs vary, so the scores will not match `results/` exactly:

```bash
# Main experiment: 14 conditions
PROFILE_SET=test-300 CONDITION_SET=all LIMIT=300 BUILD_PROFILE_SPLIT=0 RUN_CONTEXT_RELEVANCE_LABELER=1 \
  bash benchmark/run_live_workflow_benchmark.sh

# Single-turn decomposition baseline
PROFILE_SET=test-300 CONDITIONS=single_turn_decomposition LIMIT=300 BUILD_PROFILE_SPLIT=0 \
  bash benchmark/run_live_workflow_benchmark.sh

# Integrated agentic planner, with JumpStarter-Recursive rerun for pairing
PROFILE_SET=test-300 CONDITIONS=full_jumpstarter,react_integrated_planner LIMIT=300 BUILD_PROFILE_SPLIT=0 \
  bash benchmark/run_live_workflow_benchmark.sh
```

Then point `paper-tables` and `analyze-failure-cases` at the new run directories with `--main-run`, `--single-turn-run`, and `--agent-run`. Run a new condition in its own run directory. Adding conditions to an existing directory re-blinds its artifacts and forces everything to be judged again.

Useful runner variables: `CONDITIONS` or `CONDITION_SET` (`primary`, `component_ablation`, `agent_baselines`, `all`), `PROFILE_SET` (`validation`, `test`, `test-300`), `LIMIT`, `LIVE_STAGES` (`drafts`, `planning`, `all`), `MAX_WORKERS`, `JUDGE_MAX_WORKERS`, `RUN_DIR`, and the model variables `WORKFLOW_MODEL`, `SIMULATED_USER_MODEL`, `JUDGE_MODEL`, `CONTEXT_RELEVANCE_MODEL`. Keep `BUILD_PROFILE_SPLIT=0` to use the released splits.

## Judge

The judge scores each blinded artifact on 12 criteria on the 1–7 scale of the user study. It first extracts an evidence record, then scores. The headline `study_quality_score` is a weighted average of nine criteria:

| Criterion | Weight |
| --- | ---: |
| plan quality, tangible-result quality, confidence support | 0.15 each |
| personalization and context grounding, completeness, decomposition quality, context curation and reuse, workflow-progress support | 0.10 each |
| user-burden reduction | 0.05 |

Specificity, contradiction/hallucination avoidance, and the overall score are reported as diagnostics and are not part of the composite.

The judge was validated against the user study's human ratings before scoring the benchmark. The results are in `reports/study_pointwise_judge_calibration_report.json` (Spearman 0.779 and study-quality directional accuracy 1.0 on 12 study artifacts) and `reports/study_judge_calibration_report.json` (paired study-quality directional accuracy 0.917). The calibration inputs contain participant material and are not released.

## Tests

```bash
python -m unittest benchmark.tests.test_pipeline
```

Tests that need the private study logs and documents are skipped when those files are absent.
