"""Rebuild the paper's main results table (Table 2) and the numbers the mechanism analysis cites.

Every comparison is JumpStarter-Shallow (or JumpStarter-Recursive) minus a comparator, paired by
``simulation_profile_id`` over the 300 held-out test profiles. The paper's conditions come from
three judged runs: the main 14-condition run, the single-turn decomposition run, and the
integrated agentic planner run. W/T/L counts treat only equal scores as ties, as in the paper.
Context-precision and trace metrics are read from each run's ``score_summary.json``, which
``analyze-workflow-experiment`` computed from the full session traces.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .failure_analysis import (
    DEFAULT_BENCHMARK_PATH,
    DEFAULT_MAIN_RUN_DIR,
    DEFAULT_SINGLE_TURN_RUN_DIR,
    PAPER_TIE_THRESHOLD,
    RECURSIVE,
    RUBRIC_DIMENSIONS,
    SHALLOW,
    SINGLE_TURN,
    Session,
    dimension_deltas,
    display_path,
    load_judged_sessions,
    mean_ci95,
    paired_deltas,
    paired_summary,
)
from .pipeline import DEFAULT_REPORTS_DIR, DEFAULT_RESULTS_DIR
from .workflow_analysis import _round
from .workflow_simulator import CONDITION_DESCRIPTIONS


DEFAULT_AGENT_RUN_DIR = DEFAULT_RESULTS_DIR / "test300_integrated_agent"
DEFAULT_OUTPUT_NAME = "paper_tables"
AGENT = "react_integrated_planner"

# Table 2 comparators in paper order, with the run each one was judged in.
TABLE2_COMPARATORS: tuple[tuple[str, str], ...] = (
    ("chatgpt_vanilla", "main"),
    ("chatgpt_with_elicited_context", "main"),
    ("chatgpt_with_structured_summary", "main"),
    ("single_turn_decomposition", "single_turn"),
    ("all_context", "main"),
    ("random_selection", "main"),
    ("no_selection", "main"),
    ("no_reuse", "main"),
    ("no_elicitation", "main"),
    ("full_jumpstarter", "main"),
    ("adapt_recursive_decomposition", "main"),
    ("ask_before_plan", "main"),
    ("long_context_planner", "main"),
    ("unstructured_memory_rag", "main"),
    ("react_integrated_planner", "agent"),
)
CONTEXT_METRIC_CONDITIONS: tuple[str, ...] = (
    SHALLOW,
    RECURSIVE,
    "all_context",
    "random_selection",
    "no_selection",
    "no_reuse",
    "no_elicitation",
)
TRACE_METRICS: tuple[tuple[str, str], ...] = (
    ("elicited_context_items", "Elicited ctx items"),
    ("selected_context_items_trace", "Selected ctx items"),
    ("reused_context_items_trace", "Reused ctx items"),
    ("context_reuse_with_context_events", "Reuse events w/ ctx"),
    ("draft_context_reuse_events", "Draft reuse events"),
    ("reused_draft_context_items", "Reused draft ctx items"),
    ("saved_draft_context_events", "Saved drafts"),
    ("completed_node_count", "Completed nodes"),
)
INPUT_TOKEN_FIGURE = Path("figures") / "quality_context_efficiency_stats.csv"


def build_paper_tables(
    main_run_dir: Path = DEFAULT_MAIN_RUN_DIR,
    single_turn_run_dir: Path = DEFAULT_SINGLE_TURN_RUN_DIR,
    agent_run_dir: Path = DEFAULT_AGENT_RUN_DIR,
    benchmark_path: Path = DEFAULT_BENCHMARK_PATH,
    output_dir: Path = DEFAULT_REPORTS_DIR,
    tie_threshold: float = PAPER_TIE_THRESHOLD,
) -> dict[str, Any]:
    run_dirs = {"main": Path(main_run_dir), "single_turn": Path(single_turn_run_dir), "agent": Path(agent_run_dir)}
    complexity = {goal["goal_id"]: goal["complexity"] for goal in json.loads(Path(benchmark_path).read_text())}

    shallow = load_judged_sessions(run_dirs["main"], SHALLOW)
    recursive = load_judged_sessions(run_dirs["main"], RECURSIVE)
    single_turn = load_judged_sessions(run_dirs["single_turn"], SINGLE_TURN)
    agent = load_judged_sessions(run_dirs["agent"], AGENT)
    recursive_agent_run = load_judged_sessions(run_dirs["agent"], RECURSIVE)

    def by_complexity(primary: dict[str, Session], reference: dict[str, Session], simple_vs_complex: bool) -> dict[str, Any]:
        groups: dict[str, list[float]] = {}
        for profile_id, delta in paired_deltas(primary, reference).items():
            level = complexity[primary[profile_id]["goal_id"]]
            if simple_vs_complex:
                level = "simple" if level == "medium" else "complex"
            groups.setdefault(level, []).append(delta)
        return {level: paired_summary(deltas, tie_threshold) for level, deltas in sorted(groups.items())}

    def comparison(primary: dict[str, Session], reference: dict[str, Session]) -> dict[str, Any]:
        return paired_summary(list(paired_deltas(primary, reference).values()), tie_threshold)

    def dimensions(primary: dict[str, Session], reference: dict[str, Session]) -> dict[str, Any]:
        return dimension_deltas(primary, reference, list(paired_deltas(primary, reference)))

    table2 = [_condition_row(SHALLOW, "main", shallow, None, tie_threshold)]
    for condition, run in TABLE2_COMPARATORS:
        comparator = load_judged_sessions(run_dirs[run], condition)
        table2.append(_condition_row(condition, run, comparator, shallow, tie_threshold))

    main_summary = _score_summary(run_dirs["main"])
    agent_summary = _score_summary(run_dirs["agent"])
    single_turn_words = _mean_output_words(single_turn)

    report = {
        "inputs": {name: display_path(path) for name, path in run_dirs.items()} | {"benchmark_path": display_path(benchmark_path)},
        "tie_threshold": tie_threshold,
        "table2": table2,
        "vs_single_turn": {
            "shallow": comparison(shallow, single_turn),
            "recursive": comparison(recursive, single_turn),
            "chatgpt_with_elicited_context": comparison(
                load_judged_sessions(run_dirs["main"], "chatgpt_with_elicited_context"), single_turn
            ),
            "shallow_by_complexity": by_complexity(shallow, single_turn, simple_vs_complex=True),
            "recursive_by_complexity": by_complexity(recursive, single_turn, simple_vs_complex=True),
            "shallow_dimensions": dimensions(shallow, single_turn),
            "recursive_dimensions": dimensions(recursive, single_turn),
        },
        "integrated_agent": {
            "agent_mean": mean_ci95([s["study_quality"] for s in agent.values()])[0],
            "recursive_agent_run_mean": mean_ci95([s["study_quality"] for s in recursive_agent_run.values()])[0],
            "shallow_vs_agent": comparison(shallow, agent),
            "recursive_vs_agent": comparison(recursive_agent_run, agent),
            "single_turn_vs_agent": comparison(single_turn, agent),
            "recursive_rerun_calibration": comparison(recursive_agent_run, recursive),
            "shallow_dimensions": dimensions(shallow, agent),
            "recursive_dimensions": dimensions(recursive_agent_run, agent),
            "shallow_by_complexity": by_complexity(shallow, agent, simple_vs_complex=False),
            "recursive_by_complexity": by_complexity(recursive_agent_run, agent, simple_vs_complex=False),
            "output_words": {
                AGENT: _mean_output_words(agent),
                f"{RECURSIVE} (agent run)": _mean_output_words(recursive_agent_run),
                SINGLE_TURN: single_turn_words,
            },
            "trace_metrics": {
                AGENT: _trace_metrics(agent_summary, AGENT),
                f"{RECURSIVE} (agent run)": _trace_metrics(agent_summary, RECURSIVE),
            },
        },
        "context_metrics": {condition: _context_metrics(main_summary, condition) for condition in CONTEXT_METRIC_CONDITIONS},
        "input_context_tokens": _input_context_tokens(run_dirs["main"] / INPUT_TOKEN_FIGURE),
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{DEFAULT_OUTPUT_NAME}.json"
    markdown_path = output_dir / f"{DEFAULT_OUTPUT_NAME}.md"
    latex_path = output_dir / f"{DEFAULT_OUTPUT_NAME}_table2.tex"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(_render_markdown(report))
    latex_path.write_text(_render_table2_latex(table2))
    report["output_paths"] = [str(json_path), str(markdown_path), str(latex_path)]
    return report


def _condition_row(
    condition: str,
    run: str,
    sessions: dict[str, Session],
    shallow: dict[str, Session] | None,
    tie_threshold: float,
) -> dict[str, Any]:
    mean, mean_ci = mean_ci95([session["study_quality"] for session in sessions.values()])
    row = {
        "condition": condition,
        "paper_name": CONDITION_DESCRIPTIONS[condition][0],
        "run": run,
        "n": len(sessions),
        "mean": mean,
        "mean_ci95": mean_ci,
    }
    if shallow is not None:
        row["shallow_minus_condition"] = paired_summary(list(paired_deltas(shallow, sessions).values()), tie_threshold)
    return row


def _score_summary(run_dir: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads((run_dir / "score_summary.json").read_text())
    return {item["condition"]: item for item in payload["condition_summaries"]}


def _context_metrics(summary: dict[str, dict[str, Any]], condition: str) -> dict[str, Any]:
    item = summary[condition]
    gpt = item.get("gpt_context_relevance_metrics") or {}
    return {
        "selected_context_tokens": _mean_of(item.get("selected_context_token_count")),
        "gpt_context_precision": _mean_of(gpt.get("gpt_context_precision")),
        "context_precision_proxy": _mean_of(item.get("context_precision_proxy")),
    } | _trace_metrics(summary, condition)


def _trace_metrics(summary: dict[str, dict[str, Any]], condition: str) -> dict[str, Any]:
    traces = summary[condition].get("component_trace_metrics") or {}
    return {key: _mean_of(traces.get(key)) for key, _label in TRACE_METRICS} | {
        "selected_context_tokens": _mean_of(summary[condition].get("selected_context_token_count")),
    }


def _mean_of(value: Any) -> float | None:
    if isinstance(value, dict):
        return value.get("mean")
    return value if isinstance(value, (int, float)) else None


def _mean_output_words(sessions: dict[str, Session]) -> float | None:
    words = [session["output_words"] for session in sessions.values() if session["output_words"] is not None]
    return _round(sum(words) / len(words)) if words else None


def _input_context_tokens(stats_path: Path) -> dict[str, Any] | None:
    """Per-condition input context tokens behind the quality-vs-context-efficiency figure.

    These are counted from the rendered prompts in the full session traces, so they are read from
    the figure's saved statistics rather than recomputed from the compact results.
    """
    if not stats_path.exists():
        return None
    with stats_path.open() as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["condition"]: _round(float(row["workflow_prompt_tokens_mean"]))
        for row in rows
        if row.get("workflow_prompt_tokens_mean")
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Tables",
        "",
        "Paired over the 300 held-out test profiles. Delta = first-named condition minus comparator; "
        f"a profile is a tie when |delta| <= {report['tie_threshold']:g}.",
        "",
        "## Table 2: JumpStarter-Shallow vs. every condition",
        "",
        "| Condition | Run | n | Study quality | Delta (Shallow - condition) | 95% CI | W/T/L |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: |",
    ]
    for row in report["table2"]:
        comparison = row.get("shallow_minus_condition")
        if comparison is None:
            lines.append(f"| **{row['paper_name']}** (`{row['condition']}`) | {row['run']} | {row['n']} | {row['mean']:.4f} | -- | -- | -- |")
            continue
        lines.append(
            f"| {row['paper_name']} (`{row['condition']}`) | {row['run']} | {row['n']} | {row['mean']:.4f} | "
            f"{comparison['mean_delta']:+.4f} | {_ci(comparison['ci95'], 4)} | {_wtl(comparison)} |"
        )

    vs_single = report["vs_single_turn"]
    lines += [
        "",
        "## Single-turn decomposition baseline",
        "",
        "| Comparison | n | Delta | 95% CI | W/T/L |",
        "| --- | ---: | ---: | --- | ---: |",
        _comparison_row("JumpStarter-Shallow - single-turn", vs_single["shallow"]),
        _comparison_row("JumpStarter-Recursive - single-turn", vs_single["recursive"]),
        _comparison_row("ChatGPT + elicited context - single-turn", vs_single["chatgpt_with_elicited_context"]),
    ]
    for variant in ("shallow", "recursive"):
        for level, summary in vs_single[f"{variant}_by_complexity"].items():
            lines.append(_comparison_row(f"{variant.capitalize()} - single-turn, {level} goals", summary))
    lines += _dimension_table(
        "Per-dimension delta vs. single-turn",
        {"Shallow": vs_single["shallow_dimensions"], "Recursive": vs_single["recursive_dimensions"]},
    )

    agent = report["integrated_agent"]
    lines += [
        "",
        "## Integrated agentic planner",
        "",
        f"Agent mean {agent['agent_mean']:.4f}; JumpStarter-Recursive in the agent run {agent['recursive_agent_run_mean']:.4f}.",
        "",
        "| Comparison | n | Delta | 95% CI | W/T/L |",
        "| --- | ---: | ---: | --- | ---: |",
        _comparison_row("JumpStarter-Shallow - agent", agent["shallow_vs_agent"]),
        _comparison_row("JumpStarter-Recursive (agent run) - agent", agent["recursive_vs_agent"]),
        _comparison_row("Single-turn - agent", agent["single_turn_vs_agent"]),
        _comparison_row("Recursive (agent run) - Recursive (main run), rerun check", agent["recursive_rerun_calibration"]),
    ]
    for variant in ("shallow", "recursive"):
        for level, summary in agent[f"{variant}_by_complexity"].items():
            lines.append(_comparison_row(f"{variant.capitalize()} - agent, {level} goals", summary))
    lines += _dimension_table(
        "Per-dimension delta vs. the integrated agent",
        {"Shallow": agent["shallow_dimensions"], "Recursive (agent run)": agent["recursive_dimensions"]},
    )
    words = ", ".join(f"`{name}` {value:.0f}" for name, value in agent["output_words"].items() if value is not None)
    lines += ["", f"Mean output words: {words}.", "", "| Trace metric | " + " | ".join(f"`{name}`" for name in agent["trace_metrics"]) + " |"]
    lines.append("| --- |" + " ---: |" * len(agent["trace_metrics"]))
    for key, label in (*TRACE_METRICS, ("selected_context_tokens", "Selected ctx tokens")):
        lines.append(f"| {label} | " + " | ".join(_number(metrics.get(key)) for metrics in agent["trace_metrics"].values()) + " |")

    context = report["context_metrics"]
    lines += [
        "",
        "## Context selection and trace metrics (main run)",
        "",
        "| Condition | Selected ctx tokens | GPT ctx precision | "
        + " | ".join(label for _key, label in TRACE_METRICS)
        + " |",
        "| --- |" + " ---: |" * (2 + len(TRACE_METRICS)),
    ]
    for condition, metrics in context.items():
        cells = [_number(metrics["selected_context_tokens"]), _number(metrics["gpt_context_precision"])]
        cells += [_number(metrics.get(key)) for key, _label in TRACE_METRICS]
        lines.append(f"| `{condition}` | " + " | ".join(cells) + " |")

    tokens = report["input_context_tokens"]
    if tokens:
        lines += [
            "",
            "## Input context tokens per session (quality-vs-context-efficiency figure)",
            "",
            "Counted from rendered prompts in the full session traces; read from "
            f"`{INPUT_TOKEN_FIGURE}` in the main run.",
            "",
            "| Condition | Input context tokens |",
            "| --- | ---: |",
        ]
        lines += [f"| `{condition}` | {value:.1f} |" for condition, value in tokens.items()]
    return "\n".join(lines) + "\n"


def _dimension_table(title: str, columns: dict[str, dict[str, Any]]) -> list[str]:
    lines = ["", f"### {title}", "", "| Dimension | " + " | ".join(columns) + " |", "| --- |" + " ---: |" * len(columns)]
    for dimension in RUBRIC_DIMENSIONS:
        cells = [f"{_signed(deltas[dimension]['mean_delta'])} {_ci(deltas[dimension]['ci95'], 3)}" for deltas in columns.values()]
        lines.append(f"| `{dimension}` | " + " | ".join(cells) + " |")
    return lines


def _render_table2_latex(table2: list[dict[str, Any]]) -> str:
    lines = [
        "% Generated by `python -m benchmark.cli paper-tables`; requires \\usepackage{booktabs}.",
        "\\begin{tabular}{lrrrr}",
        "\\toprule",
        "Condition & Study quality & $\\Delta$ (Shallow $-$ cond.) & 95\\% CI & W/T/L \\\\",
        "\\midrule",
    ]
    for row in table2:
        comparison = row.get("shallow_minus_condition")
        if comparison is None:
            lines.append(f"\\textbf{{{row['paper_name']}}} & \\textbf{{{row['mean']:.3f}}} & -- & -- & -- \\\\")
            lines.append("\\midrule")
            continue
        low, high = comparison["ci95"]
        lines.append(
            f"{row['paper_name']} & {row['mean']:.3f} & {comparison['mean_delta']:+.3f} & "
            f"[{low:.3f}, {high:.3f}] & {_wtl(comparison)} \\\\"
        )
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def _comparison_row(label: str, summary: dict[str, Any]) -> str:
    return f"| {label} | {summary['n']} | {summary['mean_delta']:+.4f} | {_ci(summary['ci95'], 4)} | {_wtl(summary)} |"


def _wtl(summary: dict[str, Any]) -> str:
    return f"{summary['wins']}/{summary['ties']}/{summary['losses']}"


def _ci(bounds: list[float | None], digits: int) -> str:
    low, high = bounds
    return "n/a" if low is None or high is None else f"[{low:+.{digits}f}, {high:+.{digits}f}]"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
