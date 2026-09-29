# JumpStarter: Human-AI Planning with Task-Structured Context Curation

Code and data for the AACL 2026 paper by Xuanming Zhang, Sitong Wang, Jenny Ma, Alyssa Hwang, Zhou Yu, and Lydia Chilton ([arXiv:2410.03882](https://arxiv.org/abs/2410.03882)).

JumpStarter helps a person plan a complex personal goal with an LLM. It breaks the goal into subtasks and attaches the right context to each one. It asks the user for missing context (elicitation), picks the context that matters for the current subtask (selection), and carries saved drafts into later subtasks (reuse).

This repository contains two things:

| Folder | What it is | Paper |
| --- | --- | --- |
| [`app/`](app/) | The interactive JumpStarter web app used in the user study | System; user study |
| [`benchmark/`](benchmark/) | The simulation benchmark: goals, personas, simulated users, the workflow simulator with all 16 conditions, the LLM judge, and the scripts that produce the paper's tables | Simulation study; appendices |

## Setup

Python 3.11–3.14; the paper's experiments ran on 3.12. Check with `python3 --version`: some systems, including macOS, ship an older `python3`. Create an environment and install the dependencies from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

With conda, use `conda create -n jumpstarter python=3.12 && conda activate jumpstarter` in place of the first two lines. If `venv` reports that `ensurepip` is not available (some Ubuntu systems), install `python3-venv` or use conda.

The app and live benchmark runs call the OpenAI API. Set your key as an environment variable:

```bash
export OPENAI_API_KEY="<your-openai-api-key>"
export OPENAI_ORG_ID="<your-openai-org-id>"  # optional
```

## Reproduce the paper's numbers

The paper's simulation study evaluates a balanced subset of 300 of the 1,200 simulation profiles: five per goal and fifteen per persona. These commands read the judged results of those runs in [`benchmark/results/`](benchmark/results/), need no API key, and take a few seconds each:

```bash
# Table 2 and the mechanism numbers -> benchmark/reports/paper_tables.{md,json}, paper_tables_table2.tex
python -m benchmark.cli paper-tables

# Failure-case analysis -> benchmark/reports/failure_analysis.{md,json}
python -m benchmark.cli analyze-failure-cases

# Quality vs. context-efficiency figure -> figures/quality_context_efficiency.{pdf,png,svg}
python benchmark/plot_quality_context_efficiency.py \
  benchmark/results/test300_main/score_summary.json --out-dir figures
```

## Run the app

With `OPENAI_API_KEY` set:

```bash
python app/server.py
```

Then open http://127.0.0.1:55113, log in with any new username and password (accounts are created on first login and stored in plain text in `app/database/`, so don't reuse a real password), and enter a goal. Stop the server with Ctrl+C. The app calls `gpt-4o`; see [`app/README.md`](app/README.md) to change the model and for how its routes map to the paper's mechanisms.

## Run the simulation benchmark

A deterministic run exercises all 16 conditions on 5 profiles without calling the API and writes the sessions, traces, and blinded judge inputs to `benchmark/runs/smoke/`:

```bash
python -m benchmark.cli run-workflow-experiment --conditions all,single_turn_decomposition --limit 5 --output-dir benchmark/runs/smoke
```

The paper's runs used live GPT-4o workflow stages and simulated users, and the GPT-5.5 judge. [`benchmark/README.md`](benchmark/README.md) shows how to judge and summarize a run, start with a small live run, estimate cost, and recreate each of the paper's runs.

### Larger-scale evaluation

The paper uses 300 profiles for budget reasons, but the release includes all 1,200. See [Larger-scale evaluation](benchmark/README.md#larger-scale-evaluation) in the benchmark README for commands that run on all 1,200 profiles.

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
