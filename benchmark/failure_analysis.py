"""Failure-case analysis: where does JumpStarter-Shallow lose to single-turn decomposition?

Pairs judged sessions from separate run directories by ``simulation_profile_id`` and reports
the overall loss rate, breakdowns by goal and persona attributes, per-dimension deltas on
loss vs. win profiles, the hierarchy-depth failure mode (Recursive - Shallow), and the
largest-margin loss cases. Deltas are always ``primary - reference``: positive means the
first-named condition scores higher.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Callable

from .personas import DEFAULT_PERSONAS_PATH
from .pipeline import DEFAULT_DATA_DIR, DEFAULT_REPORTS_DIR, DEFAULT_RESULTS_DIR, REPO_ROOT
from .workflow_analysis import _read_jsonl, _round
from .workflow_simulator import CONDITION_DESCRIPTIONS


DEFAULT_MAIN_RUN_DIR = DEFAULT_RESULTS_DIR / "test300_main"
DEFAULT_SINGLE_TURN_RUN_DIR = DEFAULT_RESULTS_DIR / "test300_single_turn"
DEFAULT_BENCHMARK_PATH = DEFAULT_DATA_DIR / "benchmark.json"
DEFAULT_OUTPUT_NAME = "failure_analysis"
# The paper and rebuttal W/T/L counts treat only equal scores as ties (study-quality deltas are
# multiples of 0.05). Pass 0.05 to match the tie band used by analyze-workflow-experiment instead.
PAPER_TIE_THRESHOLD = 1e-9

SHALLOW = "flat_decomposition"
RECURSIVE = "full_jumpstarter"
SINGLE_TURN = "single_turn_decomposition"
PAPER_NAMES = {condition: CONDITION_DESCRIPTIONS[condition][0] for condition in (SHALLOW, RECURSIVE, SINGLE_TURN)}
RUBRIC_DIMENSIONS: tuple[str, ...] = (
    "context_curation_reuse",
    "personalization_context_grounding",
    "workflow_progress_support",
    "no_contradiction_hallucination",
    "specificity",
    "completeness_coverage",
    "decomposition_quality",
    "plan_quality",
    "user_burden_reduction",
    "tangible_result_quality",
    "confidence_support",
    "overall",
)

Session = dict[str, Any]


def analyze_failure_cases(
    main_run_dir: Path = DEFAULT_MAIN_RUN_DIR,
    single_turn_run_dir: Path = DEFAULT_SINGLE_TURN_RUN_DIR,
    benchmark_path: Path = DEFAULT_BENCHMARK_PATH,
    personas_path: Path = DEFAULT_PERSONAS_PATH,
    output_dir: Path = DEFAULT_REPORTS_DIR,
    top_k: int = 10,
    tie_threshold: float = PAPER_TIE_THRESHOLD,
) -> dict[str, Any]:
    goals = {goal["goal_id"]: goal for goal in json.loads(Path(benchmark_path).read_text())}
    personas_payload = json.loads(Path(personas_path).read_text())
    personas = {
        persona["persona_id"]: persona
        for persona in (personas_payload["personas"] if isinstance(personas_payload, dict) else personas_payload)
    }

    shallow = load_judged_sessions(Path(main_run_dir), SHALLOW)
    recursive = load_judged_sessions(Path(main_run_dir), RECURSIVE)
    single_turn = load_judged_sessions(Path(single_turn_run_dir), SINGLE_TURN)

    def attributes(profile_id: str) -> dict[str, str]:
        session = shallow[profile_id]
        goal = goals[session["goal_id"]]
        persona = personas[session["persona_id"]]
        complexity = "simple" if goal["complexity"] == "medium" else "complex"
        return {
            "complexity": complexity,
            "time_horizon": "weeks" if "week" in goal["time_horizon"] else "months+",
            "domain": goal["domain"],
            "complexity_x_domain": f"{complexity} x {goal['domain']}",
            "persona": session["persona_id"],
            "persona_context_richness": persona["context_richness"],
        }

    shallow_vs_single = paired_deltas(shallow, single_turn)
    recursive_vs_single = paired_deltas(recursive, single_turn)
    recursive_vs_shallow = paired_deltas(recursive, shallow)
    losses = [pid for pid, delta in shallow_vs_single.items() if delta < -tie_threshold]
    wins = [pid for pid, delta in shallow_vs_single.items() if delta > tie_threshold]

    breakdowns = {
        name: _grouped_summary(shallow_vs_single, lambda pid, name=name: attributes(pid)[name], tie_threshold)
        for name in ("complexity", "time_horizon", "domain", "complexity_x_domain", "persona", "persona_context_richness")
    }

    report = {
        "conditions": {
            "primary": SHALLOW,
            "reference": SINGLE_TURN,
            "recursive": RECURSIVE,
            "paper_names": PAPER_NAMES,
        },
        "inputs": {
            "main_run_dir": display_path(main_run_dir),
            "single_turn_run_dir": display_path(single_turn_run_dir),
            "benchmark_path": display_path(benchmark_path),
            "personas_path": display_path(personas_path),
        },
        "tie_threshold": tie_threshold,
        "shallow_vs_single_turn": paired_summary(list(shallow_vs_single.values()), tie_threshold),
        "margin_sizes": _margin_sizes([shallow_vs_single[pid] for pid in wins], [shallow_vs_single[pid] for pid in losses]),
        "breakdowns": breakdowns,
        "dimensions_shallow_vs_single_turn": {
            "all": dimension_deltas(shallow, single_turn, list(shallow_vs_single)),
            "loss_profiles": dimension_deltas(shallow, single_turn, losses),
            "win_profiles": dimension_deltas(shallow, single_turn, wins),
        },
        "output_words": {
            "all": {
                SHALLOW: _mean_words(shallow, list(shallow_vs_single)),
                SINGLE_TURN: _mean_words(single_turn, list(shallow_vs_single)),
            },
            "loss_profiles": {
                SHALLOW: _mean_words(shallow, losses),
                SINGLE_TURN: _mean_words(single_turn, losses),
            },
        },
        "recursive_vs_single_turn": {
            "all": paired_summary(list(recursive_vs_single.values()), tie_threshold),
            "by_complexity": _grouped_summary(
                recursive_vs_single, lambda pid: attributes(pid)["complexity"], tie_threshold
            ),
        },
        "depth_failure_mode": {
            "recursive_vs_shallow": paired_summary(list(recursive_vs_shallow.values()), tie_threshold),
            "by_complexity": _grouped_summary(
                recursive_vs_shallow, lambda pid: attributes(pid)["complexity"], tie_threshold
            ),
            "dimensions": dimension_deltas(recursive, shallow, list(recursive_vs_shallow)),
        },
        "largest_losses": [
            _loss_case(pid, shallow_vs_single[pid], shallow, single_turn, goals, attributes(pid))
            for pid in sorted(losses, key=lambda pid: (shallow_vs_single[pid], pid))[:top_k]
        ],
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{DEFAULT_OUTPUT_NAME}.json"
    markdown_path = output_dir / f"{DEFAULT_OUTPUT_NAME}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(_render_markdown(report))
    report["output_json_path"] = str(json_path)
    report["output_markdown_path"] = str(markdown_path)
    return report


def display_path(path: Path) -> str:
    """Repository-relative path for reports, so they read the same on every machine."""
    resolved = Path(path).resolve()
    return str(resolved.relative_to(REPO_ROOT)) if resolved.is_relative_to(REPO_ROOT) else str(resolved)


def load_judged_sessions(run_dir: Path, condition: str) -> dict[str, Session]:
    """Join judge scores to the condition key and index one condition's sessions by profile."""
    key_by_blind_id = {
        row["blind_id"]: row
        for row in _read_jsonl(run_dir / "condition_key.jsonl")
        if row["condition"] == condition
    }
    sessions: dict[str, Session] = {}
    for score in _read_jsonl(run_dir / "judge_scores.jsonl"):
        key = key_by_blind_id.get(score["blind_id"])
        if key is None or key["simulation_profile_id"] in sessions:
            continue
        sessions[key["simulation_profile_id"]] = {
            "simulation_profile_id": key["simulation_profile_id"],
            "goal_id": key["goal_id"],
            "persona_id": key["persona_id"],
            "study_quality": float(score["study_quality_score"]),
            "subscores": {name: item["score"] for name, item in score["score"].items()},
            "output_words": score.get("output_words"),
        }
    if not sessions:
        raise ValueError(f"No judged sessions for condition {condition!r} in {run_dir}")
    return sessions


def paired_deltas(primary: dict[str, Session], reference: dict[str, Session]) -> dict[str, float]:
    return {
        profile_id: primary[profile_id]["study_quality"] - reference[profile_id]["study_quality"]
        for profile_id in sorted(primary.keys() & reference.keys())
    }


def mean_ci95(values: list[float]) -> tuple[float | None, list[float | None]]:
    """Mean and normal-approximation 95% CI (sample SD), rounded only after computing the interval."""
    count = len(values)
    if not count:
        return None, [None, None]
    mean = sum(values) / count
    stderr = math.sqrt(sum((value - mean) ** 2 for value in values) / (count - 1) / count) if count > 1 else 0.0
    return _round(mean), [_round(mean - 1.96 * stderr), _round(mean + 1.96 * stderr)]


def paired_summary(deltas: list[float], tie_threshold: float = PAPER_TIE_THRESHOLD) -> dict[str, Any]:
    mean, ci95 = mean_ci95(deltas)
    wins = sum(delta > tie_threshold for delta in deltas)
    losses = sum(delta < -tie_threshold for delta in deltas)
    ties = len(deltas) - wins - losses
    count = len(deltas)
    return {
        "n": count,
        "mean_delta": mean,
        "ci95": ci95,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "loss_rate": _round(losses / count) if count else None,
        "loss_or_tie_rate": _round((losses + ties) / count) if count else None,
    }


def dimension_deltas(
    primary: dict[str, Session],
    reference: dict[str, Session],
    profile_ids: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for dimension in RUBRIC_DIMENSIONS:
        deltas = [
            float(primary[pid]["subscores"][dimension] - reference[pid]["subscores"][dimension])
            for pid in profile_ids
            if dimension in primary[pid]["subscores"] and dimension in reference[pid]["subscores"]
        ]
        mean, ci95 = mean_ci95(deltas)
        result[dimension] = {"n": len(deltas), "mean_delta": mean, "ci95": ci95}
    return result


def _grouped_summary(
    deltas: dict[str, float],
    group_of: Callable[[str], str],
    tie_threshold: float,
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[float]] = {}
    for profile_id, delta in deltas.items():
        groups.setdefault(group_of(profile_id), []).append(delta)
    return {group: paired_summary(values, tie_threshold) for group, values in sorted(groups.items())}


def _margin_sizes(win_deltas: list[float], loss_deltas: list[float]) -> dict[str, Any]:
    """How large the wins and losses are, to separate frequent-but-small losses from large ones."""
    return {
        "median_win": _round(median(win_deltas)) if win_deltas else None,
        "median_loss": _round(median(loss_deltas)) if loss_deltas else None,
        "losses_within_0_25": _round(sum(abs(d) <= 0.25 + 1e-9 for d in loss_deltas) / len(loss_deltas)) if loss_deltas else None,
        "losses_within_0_50": _round(sum(abs(d) <= 0.50 + 1e-9 for d in loss_deltas) / len(loss_deltas)) if loss_deltas else None,
    }


def _mean_words(sessions: dict[str, Session], profile_ids: list[str]) -> float | None:
    words = [sessions[pid]["output_words"] for pid in profile_ids if sessions[pid]["output_words"] is not None]
    return _round(sum(words) / len(words)) if words else None


def _loss_case(
    profile_id: str,
    delta: float,
    primary: dict[str, Session],
    reference: dict[str, Session],
    goals: dict[str, dict[str, Any]],
    attributes: dict[str, str],
) -> dict[str, Any]:
    session = primary[profile_id]
    dimension_gaps = {
        dimension: primary[profile_id]["subscores"][dimension] - reference[profile_id]["subscores"][dimension]
        for dimension in RUBRIC_DIMENSIONS
        if dimension in primary[profile_id]["subscores"] and dimension in reference[profile_id]["subscores"]
    }
    worst = sorted((gap, dimension) for dimension, gap in dimension_gaps.items() if gap < 0)[:3]
    return {
        "simulation_profile_id": profile_id,
        "delta": _round(delta),
        "goal_id": session["goal_id"],
        "goal_text": goals[session["goal_id"]]["goal_text"],
        "complexity": attributes["complexity"],
        "domain": attributes["domain"],
        "persona_id": session["persona_id"],
        "worst_dimensions": {dimension: gap for gap, dimension in worst},
        "output_words": {SHALLOW: session["output_words"], SINGLE_TURN: reference[profile_id]["output_words"]},
    }


def _render_markdown(report: dict[str, Any]) -> str:
    shallow, single, recursive = (PAPER_NAMES[c] for c in (SHALLOW, SINGLE_TURN, RECURSIVE))
    lines = [
        "# Failure-Case Analysis",
        "",
        f"Paired over matched simulation profiles. Delta = first-named condition minus second; "
        f"a profile is a tie when |delta| <= {report['tie_threshold']:g} on the study-quality score. "
        f"Loss rate = losses / n.",
        "",
        f"## 1. {shallow} vs. {single}",
        "",
        "| n | Mean delta | 95% CI | W/T/L | Loss rate | Loss-or-tie rate |",
        "| ---: | ---: | --- | ---: | ---: | ---: |",
        _summary_row(report["shallow_vs_single_turn"], label=None),
        "",
        f"Median win {_signed(report['margin_sizes']['median_win'])}, median loss "
        f"{_signed(report['margin_sizes']['median_loss'])}; "
        f"{_percent(report['margin_sizes']['losses_within_0_25'])} of losses are within 0.25 and "
        f"{_percent(report['margin_sizes']['losses_within_0_50'])} within 0.50.",
        "",
        f"## 2. Where the gains thin out ({shallow} - {single})",
        "",
    ]
    for name, groups in report["breakdowns"].items():
        lines += [f"### By {name.replace('_', ' ')}", "", "| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |", "| --- | ---: | ---: | --- | ---: | ---: |"]
        lines += [_summary_row(summary, label=group, rates=False) for group, summary in groups.items()]
        lines.append("")

    dims = report["dimensions_shallow_vs_single_turn"]
    lines += [
        f"## 3. Per-dimension delta ({shallow} - {single})",
        "",
        f"| Dimension | All (n={dims['all']['overall']['n']}) | Loss profiles (n={dims['loss_profiles']['overall']['n']}) "
        f"| Win profiles (n={dims['win_profiles']['overall']['n']}) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for dimension in RUBRIC_DIMENSIONS:
        cells = [_signed(dims[subset][dimension]["mean_delta"]) for subset in ("all", "loss_profiles", "win_profiles")]
        lines.append(f"| `{dimension}` | " + " | ".join(cells) + " |")
    words = report["output_words"]
    lines += [
        "",
        f"Mean output words, all profiles: {shallow} {_fixed(words['all'][SHALLOW], 0)} vs. "
        f"{single} {_fixed(words['all'][SINGLE_TURN], 0)}; loss profiles: "
        f"{_fixed(words['loss_profiles'][SHALLOW], 0)} vs. {_fixed(words['loss_profiles'][SINGLE_TURN], 0)}.",
        "",
        f"## 4. {recursive} vs. {single}",
        "",
        "| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |",
        "| --- | ---: | ---: | --- | ---: | ---: |",
        _summary_row(report["recursive_vs_single_turn"]["all"], label="all", rates=False),
    ]
    lines += [
        _summary_row(summary, label=group, rates=False)
        for group, summary in report["recursive_vs_single_turn"]["by_complexity"].items()
    ]
    depth = report["depth_failure_mode"]
    lines += [
        "",
        f"## 5. Depth failure mode ({recursive} - {shallow})",
        "",
        "| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |",
        "| --- | ---: | ---: | --- | ---: | ---: |",
        _summary_row(depth["recursive_vs_shallow"], label="all", rates=False),
    ]
    lines += [_summary_row(summary, label=group, rates=False) for group, summary in depth["by_complexity"].items()]
    lines += ["", "| Dimension | Mean delta | 95% CI |", "| --- | ---: | --- |"]
    lines += [
        f"| `{dimension}` | {_signed(item['mean_delta'])} | {_ci(item['ci95'])} |"
        for dimension, item in depth["dimensions"].items()
    ]
    lines += [
        "",
        f"## 6. Largest-margin losses ({shallow} - {single})",
        "",
        "| Delta | Goal | Complexity / domain | Persona | Worst dimensions |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for case in report["largest_losses"]:
        worst = ", ".join(f"{dimension} {gap:+d}" for dimension, gap in case["worst_dimensions"].items())
        lines.append(
            f"| {_signed(case['delta'])} | {case['goal_id']}: {case['goal_text']} | "
            f"{case['complexity']} / {case['domain']} | `{case['persona_id']}` | {worst} |"
        )
    return "\n".join(lines) + "\n"


def _summary_row(summary: dict[str, Any], label: str | None, rates: bool = True) -> str:
    cells = [
        str(summary["n"]),
        _signed(summary["mean_delta"]),
        _ci(summary["ci95"]),
        f"{summary['wins']}/{summary['ties']}/{summary['losses']}",
        _percent(summary["loss_rate"]),
    ]
    if rates:
        cells.append(_percent(summary["loss_or_tie_rate"]))
    if label is not None:
        cells.insert(0, f"`{label}`")
    return "| " + " | ".join(cells) + " |"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _fixed(value: float | None, digits: int) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _ci(bounds: list[float | None]) -> str:
    low, high = bounds
    return "n/a" if low is None or high is None else f"[{low:+.3f}, {high:+.3f}]"


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"
