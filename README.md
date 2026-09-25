# JumpStarter: Human-AI Planning with Task-Structured Context Curation

Code and data for the AACL 2026 paper by Xuanming Zhang, Sitong Wang, Jenny Ma, Alyssa Hwang, Zhou Yu, and Lydia Chilton ([arXiv:2410.03882](https://arxiv.org/abs/2410.03882)).

JumpStarter helps a person plan a complex personal goal with an LLM. It breaks the goal into subtasks and attaches the right context to each one. It asks the user for missing context (elicitation), picks the context that matters for the current subtask (selection), and carries saved drafts into later subtasks (reuse).

This repository contains two things:

| Folder | What it is | Paper |
| --- | --- | --- |
| [`app/`](app/) | The interactive JumpStarter web app used in the user study | System; user study |
| [`benchmark/`](benchmark/) | The simulation benchmark: goals, personas, simulated users, the workflow simulator with all 16 conditions, the LLM judge, and the scripts that produce the paper's tables | Simulation study; appendices |

## Setup

Python 3.12:

```bash
pip install -r requirements.txt
```

The app and live benchmark runs call the OpenAI API. Set your key as an environment variable:

```bash
export OPENAI_API_KEY="<your-openai-api-key>"
export OPENAI_ORG_ID="<your-openai-org-id>"  # optional
```

## Reproduce the paper's numbers

These commands read the judged results in [`benchmark/results/`](benchmark/results/) and need no API key:

```bash
# Table 2 and the mechanism numbers -> benchmark/reports/paper_tables.{md,json}, paper_tables_table2.tex
python -m benchmark.cli paper-tables

# Failure-case analysis -> benchmark/reports/failure_analysis.{md,json}
python -m benchmark.cli analyze-failure-cases

# Quality vs. context-efficiency figure
python benchmark/plot_quality_context_efficiency.py \
  benchmark/results/test300_main/score_summary.json --out-dir figures
```

## Run the app

```bash
python app/server.py
```

Then open http://127.0.0.1:55113, log in with any new username and password (accounts are created on first login and stored in plain text in `app/database/`, so don't reuse a real password), and enter a goal. See [`app/README.md`](app/README.md) for how the app's routes map to the paper's mechanisms.

## Run the simulation benchmark

A deterministic run exercises all 16 conditions without calling the API:

```bash
python -m benchmark.cli run-workflow-experiment --conditions all,single_turn_decomposition --limit 5
```

The paper's runs used live GPT-4o workflow stages and simulated users, and the GPT-5.5 judge. See [`benchmark/README.md`](benchmark/README.md) for the full pipeline and the command behind each result.

## Paper to code

| In the paper | In the code |
| --- | --- |
| Elicitation, selection, reuse, decomposition, subtask detection, task forking | [`app/server.py`](app/server.py) routes, with the decomposition and drafting prompts in [`app/static/task.js`](app/static/task.js); the same prompts as text files in [`benchmark/prompts/paper_workflow_v1/`](benchmark/prompts/paper_workflow_v1/) |
| Benchmark construction: 60 goals, 20 personas, 1,200 simulation profiles | [`benchmark/pipeline.py`](benchmark/pipeline.py), [`personas.py`](benchmark/personas.py), [`simulation_profiles.py`](benchmark/simulation_profiles.py); outputs in [`benchmark/data/`](benchmark/data/) |
| Simulated users and their calibrated decision policies | [`benchmark/workflow_simulator.py`](benchmark/workflow_simulator.py), [`user_decision_calibration.py`](benchmark/user_decision_calibration.py) |
| JumpStarter variants, ablations, and baselines | `CONDITION_DESCRIPTIONS` in [`benchmark/workflow_simulator.py`](benchmark/workflow_simulator.py) (table below) |
| LLM judge and the study-quality composite | [`benchmark/judge.py`](benchmark/judge.py), prompts `benchmark/prompts/judge_*.txt` |
| Context-relevance labeler (context precision) | [`benchmark/context_relevance.py`](benchmark/context_relevance.py) |
| Table 2 and the mechanism numbers | [`benchmark/paper_tables.py`](benchmark/paper_tables.py) (`paper-tables`) |
| Failure-case analysis | [`benchmark/failure_analysis.py`](benchmark/failure_analysis.py) (`analyze-failure-cases`) |
| Quality vs. context-efficiency figure | [`benchmark/plot_quality_context_efficiency.py`](benchmark/plot_quality_context_efficiency.py) |

## Conditions

Condition keys in the code and results, and their names in the paper:

| Key | Paper name | What it tests |
| --- | --- | --- |
| `flat_decomposition` | JumpStarter-Shallow | The primary system: one level of subtasks, elicitation, task-local context selection, saved drafts, and reuse |
| `full_jumpstarter` | JumpStarter-Recursive | The same workflow with recursive decomposition |
| `all_context` | All-context prompting | Every context item goes to every subtask |
| `random_selection` | Random context selection | A random subset of context per subtask |
| `no_selection` | No context selection | Subtask drafts without selected context |
| `no_reuse` | No context reuse | Drafts are saved but not reused |
| `no_elicitation` | No elicitation | No proactive context questions |
| `chatgpt_vanilla` | ChatGPT vanilla | One-shot GPT-4o answer |
| `chatgpt_with_elicited_context` | ChatGPT + elicited context | One-shot answer with the same elicited context |
| `chatgpt_with_structured_summary` | ChatGPT + structured summary | One-shot answer with a structured summary of that context |
| `single_turn_decomposition` | Single-turn decomposition | One turn asked to decompose and draft every subtask, with the same elicited context |
| `adapt_recursive_decomposition` | ADaPT-style recursive decomposition | Recursive decompose-and-execute planner |
| `ask_before_plan` | Ask-before-plan | Clarification loop, then planning |
| `unstructured_memory_rag` | Unstructured memory-RAG | Retrieval over an unstructured memory of context snippets |
| `long_context_planner` | Long-context planner | All context in one long prompt |
| `react_integrated_planner` | Integrated agentic planner | Elicitation, retrieval, a simulated browse tool, and per-subtask selection, without draft reuse |

The component ablations (`all_context` through `no_elicitation`) modify the recursive workflow.

## Data and privacy

**Released:**
- the 60 benchmark goals, 20 personas, and 1,200 simulation profiles with their splits;
- all prompts;
- the simulated-user calibration rates;
- the judge-calibration reports;
- the judged results of the three runs reported in the paper.

**Not released:** the raw user-study logs, participant documents, and the human-study judge-calibration packages, which contain participant data. Commands that rebuild data from those files will not run from this repository: `build-anchors`, `build-all`, `build-personas`, `build-judge-calibration`, `build-study-judge-inputs`, and `build-user-decision-calibration`. The outputs they produced are included in `benchmark/data/` and `benchmark/reports/`.

Personas are derived from study participants. Names are removed and institutions are replaced with a fictional one. The full simulation traces (about 2.3 GB) are also not included; `benchmark/results/` keeps what the tables and figures need.

## License

Code is released under the [MIT License](LICENSE). The benchmark data and results (`benchmark/data/`, `benchmark/results/`, `benchmark/reports/`) are released under [CC BY 4.0](DATA_LICENSE).

## Citation

```bibtex
@article{zhang2024jumpstarter,
  title   = {JumpStarter: Human-AI Planning with Task-Structured Context Curation},
  author  = {Zhang, Xuanming and Wang, Sitong and Ma, Jenny and Hwang, Alyssa and Yu, Zhou and Chilton, Lydia},
  journal = {arXiv preprint arXiv:2410.03882},
  year    = {2024}
}
```
