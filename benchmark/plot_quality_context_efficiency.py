from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import tiktoken
from matplotlib.ticker import FixedLocator, FuncFormatter

PRIMARY_CONDITION = "flat_decomposition"
# Per-condition input-token summaries, cached next to the results so the figure can be redrawn
# from the compact released results, which do not include the full sessions.jsonl traces.
PROMPT_TOKEN_CACHE_NAME = "workflow_prompt_tokens.json"
TIE_THRESHOLD = 0.05


def _token_encoding() -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model("gpt-4o")
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


TOKEN_ENCODING = _token_encoding()

DEFAULT_CONDITIONS: tuple[str, ...] = (
    "no_elicitation",
    "no_reuse",
    "all_context",
    "random_selection",
    "full_jumpstarter",
    "flat_decomposition",
)

LABELS: dict[str, str] = {
    "adapt_recursive_decomposition": "ADaPT",
    "all_context": "No selection",
    "ask_before_plan": "Ask-before-plan",
    "chatgpt_vanilla": "ChatGPT vanilla",
    "chatgpt_with_elicited_context": "ChatGPT + elicited context",
    "chatgpt_with_structured_summary": "ChatGPT + structured summary",
    "flat_decomposition": "JumpStarter-Shallow",
    "full_jumpstarter": "JumpStarter-Recursive",
    "long_context_planner": "Long-context planner",
    "no_elicitation": "No elicitation",
    "no_reuse": "No reuse",
    "no_selection": "No selection",
    "random_selection": "Random selection",
    "unstructured_memory_rag": "Memory-RAG",
}

FAMILIES: dict[str, str] = {
    "adapt_recursive_decomposition": "Planning/memory baselines",
    "all_context": "JumpStarter ablations",
    "ask_before_plan": "Planning/memory baselines",
    "chatgpt_vanilla": "ChatGPT baselines",
    "chatgpt_with_elicited_context": "ChatGPT baselines",
    "chatgpt_with_structured_summary": "ChatGPT baselines",
    "flat_decomposition": "Primary method",
    "full_jumpstarter": "JumpStarter variants",
    "long_context_planner": "Planning/memory baselines",
    "no_elicitation": "JumpStarter ablations",
    "no_reuse": "JumpStarter ablations",
    "no_selection": "JumpStarter ablations",
    "random_selection": "JumpStarter ablations",
    "unstructured_memory_rag": "Planning/memory baselines",
}

COLORS: dict[str, str] = {
    "Primary method": "#0072B2",
    "JumpStarter variants": "#56B4E9",
    "JumpStarter ablations": "#009E73",
    "Planning/memory baselines": "#D55E00",
    "ChatGPT baselines": "#6B7280",
}

MARKERS: dict[str, str] = {
    "Primary method": "*",
    "JumpStarter variants": "D",
    "JumpStarter ablations": "o",
    "Planning/memory baselines": "s",
    "ChatGPT baselines": "^",
}

# Label offsets in points. These are hand-tuned for the default paper figure.
LABEL_OFFSETS: dict[str, tuple[float, float]] = {
    "chatgpt_vanilla": (8, 4),
    "chatgpt_with_elicited_context": (8, -13),
    "chatgpt_with_structured_summary": (8, -4),
    "adapt_recursive_decomposition": (-72, -25),
    "ask_before_plan": (8, -2),
    "unstructured_memory_rag": (8, 3),
    "all_context": (-10, 0),
    "no_reuse": (-10, 0),
    "random_selection": (10, 0),
    "no_elicitation": (10, 0),
    "no_selection": (10, 15),
    "full_jumpstarter": (-10, 0),
    "flat_decomposition": (-10, 0),
}


def main() -> None:
    args = _parse_args()
    summary_path = args.summary
    run_dir = summary_path.parent
    out_dir = args.out_dir or run_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = json.loads(summary_path.read_text())
    conditions = _selected_conditions(summary, args)
    rows = _plot_rows(summary, conditions)
    prompt_summaries = _workflow_prompt_token_summaries(run_dir, conditions)
    for row in rows:
        row.update(prompt_summaries.get(row["condition"], {}))
    if PRIMARY_CONDITION not in {row["condition"] for row in rows}:
        raise SystemExit(f"Primary condition {PRIMARY_CONDITION!r} is missing from plotted rows.")

    matched_stats = _matched_deltas(run_dir, PRIMARY_CONDITION)
    for row in rows:
        row.update(matched_stats.get(row["condition"], {}))

    stem = args.stem
    _write_csv(rows, out_dir / f"{stem}_stats.csv")
    _write_markdown(rows, out_dir / f"{stem}_stats.md")
    _plot(
        rows,
        out_dir / stem,
        args.title,
        show_error_bars=not args.no_error_bars,
        show_annotations=not args.no_annotations,
        y_max=args.y_max,
    )

    print(f"Wrote {out_dir / f'{stem}.pdf'}")
    print(f"Wrote {out_dir / f'{stem}.png'}")
    print(f"Wrote {out_dir / f'{stem}.svg'}")
    print(f"Wrote {out_dir / f'{stem}_stats.csv'}")
    print(f"Wrote {out_dir / f'{stem}_stats.md'}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot study quality against workflow generation input-token usage for workflow runs.",
    )
    parser.add_argument(
        "summary",
        type=Path,
        help="Path to score_summary.json produced by workflow_analysis.py.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for figure and stats outputs. Defaults to RUN_DIR/figures.",
    )
    parser.add_argument(
        "--stem",
        default="quality_context_efficiency",
        help="Output filename stem.",
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Plot every condition in the summary instead of the default paper subset.",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Figure title. Pass an empty string to omit.",
    )
    parser.add_argument(
        "--no-error-bars",
        action="store_true",
        help="Hide 95% CI error bars and show only the condition points.",
    )
    parser.add_argument(
        "--no-annotations",
        action="store_true",
        help="Hide text labels next to condition points.",
    )
    parser.add_argument(
        "--y-max",
        type=float,
        default=None,
        help="Optional upper y-axis limit.",
    )
    return parser.parse_args()


def _selected_conditions(summary: dict[str, Any], args: argparse.Namespace) -> list[str]:
    available = {item["condition"] for item in summary.get("condition_summaries", [])}
    if args.include_all:
        return sorted(available)
    return [condition for condition in DEFAULT_CONDITIONS if condition in available]


def _plot_rows(summary: dict[str, Any], conditions: list[str]) -> list[dict[str, Any]]:
    by_condition = {
        item["condition"]: item
        for item in summary.get("condition_summaries", [])
        if item.get("condition") in conditions
    }
    rows: list[dict[str, Any]] = []
    for condition in conditions:
        item = by_condition[condition]
        quality = item["study_quality_score"]
        context_tokens = item["selected_context_token_count"]
        output_words = item["output_words"]
        rows.append(
            {
                "condition": condition,
                "label": LABELS.get(condition, condition),
                "family": FAMILIES.get(condition, "Other"),
                "n": item["count"],
                "quality_mean": quality["mean"],
                "quality_stderr": quality.get("stderr"),
                "quality_ci95_low": _ci_low(quality["mean"], quality.get("stderr")),
                "quality_ci95_high": _ci_high(quality["mean"], quality.get("stderr")),
                "selected_context_tokens_mean": context_tokens["mean"],
                "selected_context_tokens_stderr": context_tokens.get("stderr"),
                "selected_context_tokens_ci95_low": _ci_low(context_tokens["mean"], context_tokens.get("stderr")),
                "selected_context_tokens_ci95_high": _ci_high(context_tokens["mean"], context_tokens.get("stderr")),
                "selected_context_items_mean": item["selected_context_item_count"]["mean"],
                "output_words_mean": output_words["mean"],
                "workflow_prompt_tokens_mean": context_tokens["mean"],
                "workflow_prompt_tokens_stderr": context_tokens.get("stderr"),
                "workflow_prompt_tokens_ci95_low": _ci_low(context_tokens["mean"], context_tokens.get("stderr")),
                "workflow_prompt_tokens_ci95_high": _ci_high(context_tokens["mean"], context_tokens.get("stderr")),
            }
        )
    return rows


def _workflow_prompt_token_summaries(run_dir: Path, conditions: list[str]) -> dict[str, dict[str, Any]]:
    sessions_path = run_dir / "sessions.jsonl"
    cache_path = run_dir / PROMPT_TOKEN_CACHE_NAME
    if not sessions_path.exists():
        if not cache_path.exists():
            raise SystemExit(
                f"Input-token counts need {sessions_path} or the cached {cache_path}; neither exists."
            )
        cached = json.loads(cache_path.read_text())
        return {condition: cached[condition] for condition in conditions if condition in cached}
    values_by_condition: dict[str, list[float]] = {}
    for record in _read_jsonl(sessions_path):
        condition = str(record.get("condition", ""))
        values_by_condition.setdefault(condition, [])
        prompt_tokens = 0
        for event in record.get("events", []):
            if isinstance(event, dict):
                prompt_tokens += _rendered_prompt_token_count(event.get("payload"))
        values_by_condition[condition].append(float(prompt_tokens))

    summaries: dict[str, dict[str, Any]] = {}
    for condition, values in values_by_condition.items():
        if not values:
            continue
        mean, stderr = _mean_stderr(values)
        summaries[condition] = {
            "workflow_prompt_tokens_mean": mean,
            "workflow_prompt_tokens_stderr": stderr,
            "workflow_prompt_tokens_ci95_low": _ci_low(mean, stderr),
            "workflow_prompt_tokens_ci95_high": _ci_high(mean, stderr),
        }
    cache_path.write_text(json.dumps(summaries, indent=2, sort_keys=True) + "\n")
    return {condition: summaries[condition] for condition in conditions if condition in summaries}


def _rendered_prompt_token_count(value: Any) -> int:
    if isinstance(value, dict):
        total = 0
        rendered_prompt = value.get("rendered_prompt")
        if isinstance(rendered_prompt, str):
            total += len(TOKEN_ENCODING.encode(rendered_prompt))
        for key, child in value.items():
            if key != "rendered_prompt":
                total += _rendered_prompt_token_count(child)
        return total
    if isinstance(value, list):
        return sum(_rendered_prompt_token_count(child) for child in value)
    return 0


def _matched_deltas(run_dir: Path, baseline_condition: str) -> dict[str, dict[str, Any]]:
    scores_path = run_dir / "judge_scores.jsonl"
    condition_key_path = run_dir / "condition_key.jsonl"
    if not scores_path.exists() or not condition_key_path.exists():
        return {}

    score_by_blind_id: dict[str, float] = {}
    for record in _read_jsonl(scores_path):
        score = record.get("study_quality_score")
        if isinstance(score, (int, float)):
            score_by_blind_id[str(record["blind_id"])] = float(score)

    key_rows = _read_jsonl(condition_key_path)
    condition_by_profile: dict[tuple[str, str], float] = {}
    duplicate_counter = Counter(
        (str(row.get("simulation_profile_id", "")), str(row.get("condition", "")))
        for row in key_rows
    )
    if any(count > 1 for count in duplicate_counter.values()):
        return {}

    for row in key_rows:
        blind_id = str(row.get("blind_id", ""))
        score = score_by_blind_id.get(blind_id)
        if score is None:
            continue
        profile_id = str(row.get("simulation_profile_id", ""))
        condition = str(row.get("condition", ""))
        condition_by_profile[(profile_id, condition)] = score

    conditions = sorted({condition for _profile_id, condition in condition_by_profile})
    profile_ids = sorted({profile_id for profile_id, _condition in condition_by_profile})
    results: dict[str, dict[str, Any]] = {
        baseline_condition: {
            "matched_delta_vs_shallow": 0.0,
            "matched_delta_stderr": 0.0,
            "matched_delta_ci95_low": 0.0,
            "matched_delta_ci95_high": 0.0,
            "matched_wins": 0,
            "matched_ties": 0,
            "matched_losses": 0,
            "matched_n": len(
                [
                    profile_id
                    for profile_id in profile_ids
                    if (profile_id, baseline_condition) in condition_by_profile
                ]
            ),
        }
    }
    for condition in conditions:
        if condition == baseline_condition:
            continue
        deltas: list[float] = []
        wins = ties = losses = 0
        for profile_id in profile_ids:
            baseline_score = condition_by_profile.get((profile_id, baseline_condition))
            comparator_score = condition_by_profile.get((profile_id, condition))
            if baseline_score is None or comparator_score is None:
                continue
            delta = baseline_score - comparator_score
            deltas.append(delta)
            if delta > TIE_THRESHOLD:
                wins += 1
            elif delta < -TIE_THRESHOLD:
                losses += 1
            else:
                ties += 1
        if not deltas:
            continue
        mean, stderr = _mean_stderr(deltas)
        results[condition] = {
            "matched_delta_vs_shallow": mean,
            "matched_delta_stderr": stderr,
            "matched_delta_ci95_low": _ci_low(mean, stderr),
            "matched_delta_ci95_high": _ci_high(mean, stderr),
            "matched_wins": wins,
            "matched_ties": ties,
            "matched_losses": losses,
            "matched_n": len(deltas),
        }
    return results


def _plot(
    rows: list[dict[str, Any]],
    output_stem: Path,
    title: str,
    show_error_bars: bool = True,
    show_annotations: bool = True,
    y_max: float | None = None,
) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 7.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    fig, ax = plt.subplots(figsize=(6.8, 4.0), constrained_layout=True)

    for row in rows:
        family = row["family"]
        is_primary = row["condition"] == PRIMARY_CONDITION
        is_recursive = row["condition"] == "full_jumpstarter"
        marker_size = 260 if (is_primary or is_recursive) else 92
        color = COLORS.get(family, "#111827")
        marker = "*" if is_recursive else MARKERS.get(family, "o")
        x = float(row["workflow_prompt_tokens_mean"])
        y = float(row["quality_mean"])
        xerr = 1.96 * float(row.get("workflow_prompt_tokens_stderr") or 0.0)
        yerr = 1.96 * float(row.get("quality_stderr") or 0.0)

        if show_error_bars:
            ax.errorbar(
                x,
                y,
                xerr=xerr,
                yerr=yerr,
                fmt="none",
                ecolor="#9CA3AF",
                elinewidth=0.8,
                capsize=2,
                zorder=1,
            )
        ax.scatter(
            [x],
            [y],
            s=marker_size,
            marker=marker,
            color=color,
            edgecolor="#111827" if is_primary else "white",
            linewidth=1.0 if is_primary else 0.6,
            alpha=0.96 if is_primary else 0.86,
            zorder=3 if is_primary else 2,
        )
        if show_annotations:
            label_x, label_y = LABEL_OFFSETS.get(row["condition"], (6, 5))
            weight = "bold" if is_primary else "normal"
            ax.annotate(
                row["label"],
                (x, y),
                xytext=(label_x, label_y),
                textcoords="offset points",
                ha="left" if label_x >= 0 else "right",
                va="center",
                fontsize=8.3 if is_primary else 7.1,
                fontweight=weight,
                color="#111827",
                zorder=4,
            )

    ax.set_xlabel("Average input context tokens per task")
    ax.set_ylabel("Study quality score")
    if title:
        ax.set_title(title)
    ax.grid(True, axis="both", color="#E5E7EB", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#9CA3AF")
    ax.spines["bottom"].set_color("#9CA3AF")

    x_values = [float(row["workflow_prompt_tokens_mean"]) for row in rows]
    y_values = [float(row["quality_mean"]) for row in rows]
    x_padding = max((max(x_values) - min(x_values)) * 0.08, 300.0)
    x_min = min(x_values) - x_padding
    x_max = max(x_values) + x_padding
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(min(y_values) - 0.12, y_max if y_max is not None else max(y_values) + 0.15)
    tick_start = 12_000
    tick_step = 2_000
    tick_stop = int(math.ceil(x_max / tick_step) * tick_step)
    ax.xaxis.set_major_locator(FixedLocator(range(tick_start, tick_stop + tick_step, tick_step)))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{int(value / 1000)}k"))

    for extension in ("pdf", "png", "svg"):
        save_kwargs: dict[str, Any] = {"bbox_inches": "tight"}
        if extension == "png":
            save_kwargs["dpi"] = 300
        fig.savefig(output_stem.with_suffix(f".{extension}"), **save_kwargs)
    plt.close(fig)


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "condition",
        "label",
        "family",
        "n",
        "quality_mean",
        "quality_stderr",
        "quality_ci95_low",
        "quality_ci95_high",
        "workflow_prompt_tokens_mean",
        "workflow_prompt_tokens_stderr",
        "workflow_prompt_tokens_ci95_low",
        "workflow_prompt_tokens_ci95_high",
        "selected_context_tokens_mean",
        "selected_context_tokens_stderr",
        "selected_context_tokens_ci95_low",
        "selected_context_tokens_ci95_high",
        "selected_context_items_mean",
        "output_words_mean",
        "matched_delta_vs_shallow",
        "matched_delta_stderr",
        "matched_delta_ci95_low",
        "matched_delta_ci95_high",
        "matched_wins",
        "matched_ties",
        "matched_losses",
        "matched_n",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _write_markdown(rows: list[dict[str, Any]], path: Path) -> None:
    sorted_rows = sorted(rows, key=lambda row: float(row["quality_mean"]), reverse=True)
    primary = next(row for row in rows if row["condition"] == PRIMARY_CONDITION)
    all_context = next((row for row in rows if row["condition"] == "all_context"), None)
    recursive = next((row for row in rows if row["condition"] == "full_jumpstarter"), None)
    random_selection = next((row for row in rows if row["condition"] == "random_selection"), None)

    lines = [
        "# Quality vs. Context Efficiency Stats",
        "",
        f"- Primary method: {primary['label']}",
        (
            f"- Primary study quality: {_fmt(primary['quality_mean'])} "
            f"[{_fmt(primary['quality_ci95_low'])}, {_fmt(primary['quality_ci95_high'])}]"
        ),
        f"- Primary input context tokens: {_fmt(primary['workflow_prompt_tokens_mean'])}",
        f"- Primary selected context tokens: {_fmt(primary['selected_context_tokens_mean'])}",
    ]
    if all_context is not None:
        token_reduction = 1.0 - (
            float(primary["workflow_prompt_tokens_mean"])
            / float(all_context["workflow_prompt_tokens_mean"])
        )
        quality_gain = float(primary["quality_mean"]) - float(all_context["quality_mean"])
        lines.append(
            f"- Versus no-selection baseline: +{quality_gain:.3f} quality with {token_reduction:.1%} fewer input context tokens."
        )
    if recursive is not None:
        rec_delta = recursive.get("matched_delta_vs_shallow")
        rec_low = recursive.get("matched_delta_ci95_low")
        rec_high = recursive.get("matched_delta_ci95_high")
        if rec_delta is not None:
            lines.append(
                (
                    f"- Versus JumpStarter-Recursive: matched delta "
                    f"+{float(rec_delta):.3f} [{float(rec_low):.3f}, {float(rec_high):.3f}] "
                    f"for Shallow over Recursive."
                )
            )
    if random_selection is not None:
        random_delta = random_selection.get("matched_delta_vs_shallow")
        random_low = random_selection.get("matched_delta_ci95_low")
        random_high = random_selection.get("matched_delta_ci95_high")
        if random_delta is not None:
            lines.append(
                (
                    f"- Versus random context selection: matched delta "
                    f"+{float(random_delta):.3f} [{float(random_low):.3f}, {float(random_high):.3f}] "
                    f"for Shallow over random selection."
                )
            )
    lines.extend(
        [
            "",
            "| Method | Family | n | Study quality | 95% CI | Input context tokens | Selected ctx tokens | Output words | Matched delta vs Shallow | 95% CI | W/T/L |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in sorted_rows:
        delta = row.get("matched_delta_vs_shallow")
        ci_low = row.get("matched_delta_ci95_low")
        ci_high = row.get("matched_delta_ci95_high")
        lines.append(
            "| "
            + " | ".join(
                [
                    row["label"],
                    row["family"],
                    str(row["n"]),
                    _fmt(row["quality_mean"]),
                    f"[{_fmt(row['quality_ci95_low'])}, {_fmt(row['quality_ci95_high'])}]",
                    _fmt(row["workflow_prompt_tokens_mean"]),
                    _fmt(row["selected_context_tokens_mean"]),
                    _fmt(row["output_words_mean"]),
                    "--" if row["condition"] == PRIMARY_CONDITION else _signed(delta),
                    "--" if row["condition"] == PRIMARY_CONDITION else f"[{_fmt(ci_low)}, {_fmt(ci_high)}]",
                    "--"
                    if row["condition"] == PRIMARY_CONDITION
                    else f"{row.get('matched_wins', '')}/{row.get('matched_ties', '')}/{row.get('matched_losses', '')}",
                ]
            )
            + " |"
        )
    lines.append("")
    path.write_text("\n".join(lines))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _mean_stderr(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(variance) / math.sqrt(len(values))


def _ci_low(mean: float | None, stderr: float | None) -> float | None:
    if mean is None or stderr is None:
        return None
    return mean - 1.96 * stderr


def _ci_high(mean: float | None, stderr: float | None) -> float | None:
    if mean is None or stderr is None:
        return None
    return mean + 1.96 * stderr


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    return f"{float(value):.3f}"


def _signed(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    number = float(value)
    return f"{number:+.3f}"


def _csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return f"{value:.6f}"
    return "" if value is None else value


if __name__ == "__main__":
    main()
