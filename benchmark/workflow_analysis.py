from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from .schemas import (
    JudgeScoreRecord,
    MetricSummary,
    WorkflowSession,
    WorkflowConditionComparison,
    WorkflowConditionScoreSummary,
    WorkflowExperimentAnalysisReport,
)


CORE_RUBRIC_CRITERIA: tuple[str, ...] = (
    "plan_quality",
    "tangible_result_quality",
    "confidence_support",
    "workflow_progress_support",
    "user_burden_reduction",
)
TIE_THRESHOLD = 0.05
COMPONENT_TRACE_METRICS: tuple[tuple[str, str], ...] = (
    ("elicited_context_items", "Elicited ctx"),
    ("substantive_elicited_context_items", "Substantive elicited"),
    ("unknown_context_answer_events", "Unknown answers"),
    ("hierarchical_decomposition_events", "Hierarchical decomps"),
    ("max_node_depth", "Max node depth"),
    ("selected_context_items_trace", "Selected ctx"),
    ("reused_context_items_trace", "Reused ctx"),
    ("context_reuse_with_context_events", "Reuse events w/ ctx"),
    ("draft_context_reuse_events", "Draft reuse events"),
    ("reused_draft_context_items", "Reused draft ctx"),
    ("saved_draft_context_events", "Saved drafts"),
    ("completed_node_count", "Completed nodes"),
    ("completed_node_ratio", "Completion ratio"),
)
GPT_CONTEXT_RELEVANCE_METRICS: tuple[tuple[str, str], ...] = (
    ("gpt_context_precision", "GPT ctx precision"),
    ("gpt_context_recall", "GPT ctx recall"),
    ("gpt_context_f1", "GPT ctx F1"),
    ("gpt_selected_relevance_score_mean", "GPT selected relevance"),
    ("gpt_reused_context_precision", "GPT reused precision"),
    ("gpt_reused_relevance_score_mean", "GPT reused relevance"),
    ("gpt_used_relevant_context_items", "GPT used relevant"),
    ("gpt_used_relevant_context_rate", "GPT used relevant rate"),
    ("gpt_available_relevance_score_mean", "GPT available relevance"),
    ("gpt_available_relevant_context_items", "GPT available relevant"),
    ("gpt_relevant_selected_context_items", "GPT relevant selected"),
)


def analyze_workflow_experiment(
    run_dir: Path,
    baseline_condition: str = "full_jumpstarter",
) -> WorkflowExperimentAnalysisReport:
    run_dir = Path(run_dir)
    output_json_path = run_dir / "score_summary.json"
    output_markdown_path = run_dir / "score_summary.md"
    errors: list[str] = []
    warnings: list[str] = []

    scores_path = run_dir / "judge_scores.jsonl"
    condition_key_path = run_dir / "condition_key.jsonl"
    artifacts_path = run_dir / "artifacts.jsonl"
    mechanism_metrics_path = run_dir / "mechanism_metrics.json"
    sessions_path = run_dir / "sessions.jsonl"
    context_relevance_metrics_path = run_dir / "context_relevance_metrics.json"
    context_relevance_labels_path = run_dir / "context_relevance_labels.jsonl"
    for path in (scores_path, condition_key_path, artifacts_path, mechanism_metrics_path):
        if not path.exists():
            errors.append(f"Missing required experiment analysis input: {path}")

    scores: list[JudgeScoreRecord] = []
    condition_key: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    mechanism_metrics: list[dict[str, Any]] = []
    if not errors:
        scores = [JudgeScoreRecord.model_validate(record) for record in _read_jsonl(scores_path)]
        condition_key = _read_jsonl(condition_key_path)
        artifacts = _read_jsonl(artifacts_path)
        mechanism_payload = json.loads(mechanism_metrics_path.read_text())
        if not isinstance(mechanism_payload, list):
            errors.append(f"{mechanism_metrics_path} must contain a JSON list")
        else:
            mechanism_metrics = [dict(item) for item in mechanism_payload]
        if sessions_path.exists():
            mechanism_metrics = _enrich_mechanism_metrics_from_sessions(mechanism_metrics, sessions_path)
        if context_relevance_metrics_path.exists():
            mechanism_metrics = _enrich_mechanism_metrics_from_context_relevance(
                mechanism_metrics,
                context_relevance_metrics_path,
            )
        if context_relevance_labels_path.exists():
            mechanism_metrics = _enrich_mechanism_metrics_from_context_relevance_labels(
                mechanism_metrics,
                context_relevance_labels_path,
            )

    joined_rows: list[dict[str, Any]] = []
    if not errors:
        key_by_blind_id = _unique_by(condition_key, "blind_id", errors, "condition_key")
        artifact_by_blind_id = _unique_by(artifacts, "blind_id", errors, "artifacts")
        metric_by_session_id = _unique_by(mechanism_metrics, "session_id", errors, "mechanism_metrics")
        score_counter = Counter(score.blind_id for score in scores)
        duplicate_score_ids = sorted(blind_id for blind_id, count in score_counter.items() if count > 1)
        if duplicate_score_ids:
            errors.append(f"Duplicate blind_id values in judge_scores: {', '.join(duplicate_score_ids[:10])}")

        score_blind_ids = set(score_counter)
        key_blind_ids = set(key_by_blind_id)
        missing_scores = sorted(key_blind_ids - score_blind_ids)
        missing_keys = sorted(score_blind_ids - key_blind_ids)
        if missing_scores:
            errors.append(f"Missing judge scores for blind IDs: {', '.join(missing_scores[:10])}")
        if missing_keys:
            errors.append(f"Judge scores without condition-key rows: {', '.join(missing_keys[:10])}")

        for score in scores:
            key = key_by_blind_id.get(score.blind_id)
            if key is None:
                continue
            artifact = artifact_by_blind_id.get(score.blind_id)
            if artifact is None:
                errors.append(f"Missing artifact row for blind_id {score.blind_id}")
                continue
            session_id = str(key.get("session_id", ""))
            mechanism = metric_by_session_id.get(session_id)
            if mechanism is None:
                errors.append(f"Missing mechanism metrics for session_id {session_id}")
                continue
            joined_rows.append(
                {
                    "blind_id": score.blind_id,
                    "condition": str(key.get("condition", "")),
                    "simulation_profile_id": str(key.get("simulation_profile_id", "")),
                    "session_id": session_id,
                    "score": score,
                    "artifact": artifact,
                    "mechanism": mechanism,
                }
            )

    conditions = sorted({row["condition"] for row in joined_rows})
    condition_summaries = _condition_summaries(joined_rows)
    comparisons = _comparisons(joined_rows, baseline_condition, warnings)
    if joined_rows and baseline_condition not in conditions:
        errors.append(f"Baseline condition {baseline_condition!r} was not found in scored experiment rows")

    report = WorkflowExperimentAnalysisReport(
        valid=not errors,
        run_dir=str(run_dir),
        baseline_condition=baseline_condition,
        score_count=len(scores),
        condition_count=len(conditions),
        conditions=conditions,
        condition_summaries=condition_summaries,
        comparisons=comparisons,
        output_json_path=str(output_json_path),
        output_markdown_path=str(output_markdown_path),
        errors=errors,
        warnings=warnings,
    )

    if not errors:
        output_json_path.write_text(report.model_dump_json(indent=2))
        output_markdown_path.write_text(_render_markdown(report))
    return report


def _condition_summaries(rows: list[dict[str, Any]]) -> list[WorkflowConditionScoreSummary]:
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_condition[row["condition"]].append(row)

    summaries: list[WorkflowConditionScoreSummary] = []
    for condition in sorted(by_condition):
        condition_rows = by_condition[condition]
        rubric_means = {
            criterion: _mean(_rubric_scores(condition_rows, criterion))
            for criterion in CORE_RUBRIC_CRITERIA
            if _rubric_scores(condition_rows, criterion)
        }
        summaries.append(
            WorkflowConditionScoreSummary(
                condition=condition,
                count=len(condition_rows),
                study_quality_score=_metric_summary(
                    _score_values(condition_rows, lambda score: score.study_quality_score)
                ),
                overall_score=_metric_summary(_score_values(condition_rows, lambda score: score.score.overall.score)),
                rubric_means=rubric_means,
                output_words=_metric_summary(_score_values(condition_rows, lambda score: score.output_words)),
                selected_context_item_count=_metric_summary(
                    _artifact_values(condition_rows, "selected_context_item_count")
                ),
                reused_context_item_count=_metric_summary(_artifact_values(condition_rows, "reused_context_item_count")),
                selected_context_token_count=_metric_summary(
                    _artifact_values(condition_rows, "selected_context_token_count")
                ),
                reused_context_token_count=_metric_summary(_artifact_values(condition_rows, "reused_context_token_count")),
                context_precision_proxy=_metric_summary(_mechanism_values(condition_rows, "context_precision_proxy")),
                context_recall_proxy=_metric_summary(_mechanism_values(condition_rows, "context_recall_proxy")),
                selected_relevance_score_mean=_metric_summary(
                    _mechanism_values(condition_rows, "selected_relevance_score_mean")
                ),
                component_trace_metrics={
                    metric_key: _metric_summary(_mechanism_values(condition_rows, metric_key))
                    for metric_key, _label in COMPONENT_TRACE_METRICS
                    if _mechanism_values(condition_rows, metric_key)
                },
                gpt_context_relevance_metrics={
                    metric_key: _metric_summary(_mechanism_values(condition_rows, metric_key))
                    for metric_key, _label in GPT_CONTEXT_RELEVANCE_METRICS
                    if _mechanism_values(condition_rows, metric_key)
                },
            )
        )
    return summaries


def _comparisons(
    rows: list[dict[str, Any]],
    baseline_condition: str,
    warnings: list[str],
) -> list[WorkflowConditionComparison]:
    by_condition = {summary.condition: summary for summary in _condition_summaries(rows)}
    conditions = sorted(by_condition)
    if baseline_condition not in by_condition:
        return []

    pair_counter = Counter((row["simulation_profile_id"], row["condition"]) for row in rows)
    duplicate_pairs = sorted(pair for pair, count in pair_counter.items() if count > 1)
    aggregate_only = bool(duplicate_pairs)
    if aggregate_only:
        warnings.append(
            "Duplicate simulation_profile_id/condition rows detected; comparisons use aggregate condition means instead of matched deltas."
        )

    comparisons: list[WorkflowConditionComparison] = []
    for condition in conditions:
        if condition == baseline_condition:
            continue
        if aggregate_only:
            comparisons.append(_aggregate_comparison(by_condition[baseline_condition], by_condition[condition]))
        else:
            comparisons.append(_matched_comparison(rows, baseline_condition, condition))
    return comparisons


def _matched_comparison(
    rows: list[dict[str, Any]],
    baseline_condition: str,
    comparator_condition: str,
) -> WorkflowConditionComparison:
    by_profile_condition = {
        (row["simulation_profile_id"], row["condition"]): row
        for row in rows
        if row["condition"] in {baseline_condition, comparator_condition}
    }
    profile_ids = sorted(
        {
            row["simulation_profile_id"]
            for row in rows
            if row["condition"] in {baseline_condition, comparator_condition}
        }
    )
    deltas: list[float] = []
    wins = ties = losses = 0
    for profile_id in profile_ids:
        baseline_row = by_profile_condition.get((profile_id, baseline_condition))
        comparator_row = by_profile_condition.get((profile_id, comparator_condition))
        if baseline_row is None or comparator_row is None:
            continue
        baseline_score = baseline_row["score"].study_quality_score
        comparator_score = comparator_row["score"].study_quality_score
        if baseline_score is None or comparator_score is None:
            continue
        delta = float(baseline_score) - float(comparator_score)
        deltas.append(delta)
        if delta > TIE_THRESHOLD:
            wins += 1
        elif delta < -TIE_THRESHOLD:
            losses += 1
        else:
            ties += 1

    summary = _metric_summary(deltas)
    ci_low, ci_high = _ci95(summary.mean, summary.stderr)
    return WorkflowConditionComparison(
        baseline_condition=baseline_condition,
        comparator_condition=comparator_condition,
        aggregate_only=False,
        matched_profile_count=len(deltas),
        mean_delta=summary.mean,
        stderr_delta=summary.stderr,
        ci95_low=ci_low,
        ci95_high=ci_high,
        wins=wins,
        ties=ties,
        losses=losses,
    )


def _aggregate_comparison(
    baseline: WorkflowConditionScoreSummary,
    comparator: WorkflowConditionScoreSummary,
) -> WorkflowConditionComparison:
    baseline_mean = baseline.study_quality_score.mean
    comparator_mean = comparator.study_quality_score.mean
    mean_delta = None if baseline_mean is None or comparator_mean is None else _round(baseline_mean - comparator_mean)
    baseline_stderr = baseline.study_quality_score.stderr or 0.0
    comparator_stderr = comparator.study_quality_score.stderr or 0.0
    stderr_delta = _round(math.sqrt(baseline_stderr**2 + comparator_stderr**2)) if mean_delta is not None else None
    ci_low, ci_high = _ci95(mean_delta, stderr_delta)
    return WorkflowConditionComparison(
        baseline_condition=baseline.condition,
        comparator_condition=comparator.condition,
        aggregate_only=True,
        matched_profile_count=0,
        mean_delta=mean_delta,
        stderr_delta=stderr_delta,
        ci95_low=ci_low,
        ci95_high=ci_high,
        wins=0,
        ties=0,
        losses=0,
    )


def _render_markdown(report: WorkflowExperimentAnalysisReport) -> str:
    lines = [
        "# Workflow Experiment Score Summary",
        "",
        f"- Run directory: `{report.run_dir}`",
        f"- Baseline: `{report.baseline_condition}`",
        f"- Scores: {report.score_count}",
        f"- Conditions: {', '.join(f'`{condition}`' for condition in report.conditions)}",
        "",
        "## Condition Summary",
        "",
        "| Condition | n | Study quality mean | Study quality stderr | Overall mean | Output words mean | Selected ctx mean | Selected ctx tokens | Context precision | Relevance mean |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in report.condition_summaries:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{summary.condition}`",
                    str(summary.count),
                    _display(summary.study_quality_score.mean),
                    _display(summary.study_quality_score.stderr),
                    _display(summary.overall_score.mean),
                    _display(summary.output_words.mean),
                    _display(summary.selected_context_item_count.mean),
                    _display(summary.selected_context_token_count.mean),
                    _display(summary.context_precision_proxy.mean),
                    _display(summary.selected_relevance_score_mean.mean),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Baseline Comparisons",
            "",
            "| Comparator | Mode | Matched n | Mean delta | 95% CI | W/T/L |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for comparison in report.comparisons:
        mode = "aggregate" if comparison.aggregate_only else "matched"
        ci = f"[{_display(comparison.ci95_low)}, {_display(comparison.ci95_high)}]"
        wtl = f"{comparison.wins}/{comparison.ties}/{comparison.losses}"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{comparison.comparator_condition}`",
                    mode,
                    str(comparison.matched_profile_count),
                    _display(comparison.mean_delta),
                    ci,
                    wtl,
                ]
            )
            + " |"
        )
    component_metric_keys = [
        metric_key
        for metric_key, _label in COMPONENT_TRACE_METRICS
        if any(metric_key in summary.component_trace_metrics for summary in report.condition_summaries)
    ]
    if component_metric_keys:
        lines.extend(
            [
                "",
                "## Component Trace Metrics",
                "",
                "| Condition | " + " | ".join(label for key in component_metric_keys for metric_key, label in COMPONENT_TRACE_METRICS if metric_key == key) + " |",
                "| --- | " + " | ".join("---:" for _key in component_metric_keys) + " |",
            ]
        )
        for summary in report.condition_summaries:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{summary.condition}`",
                        *[
                            _display(summary.component_trace_metrics.get(metric_key, MetricSummary(count=0)).mean)
                            for metric_key in component_metric_keys
                        ],
                    ]
                )
                + " |"
            )
    gpt_metric_keys = [
        metric_key
        for metric_key, _label in GPT_CONTEXT_RELEVANCE_METRICS
        if any(metric_key in summary.gpt_context_relevance_metrics for summary in report.condition_summaries)
    ]
    if gpt_metric_keys:
        lines.extend(
            [
                "",
                "## GPT Context Relevance Metrics",
                "",
                "| Condition | " + " | ".join(label for key in gpt_metric_keys for metric_key, label in GPT_CONTEXT_RELEVANCE_METRICS if metric_key == key) + " |",
                "| --- | " + " | ".join("---:" for _key in gpt_metric_keys) + " |",
            ]
        )
        for summary in report.condition_summaries:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{summary.condition}`",
                        *[
                            _display(summary.gpt_context_relevance_metrics.get(metric_key, MetricSummary(count=0)).mean)
                            for metric_key in gpt_metric_keys
                        ],
                    ]
                )
                + " |"
            )
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines) + "\n"


def _enrich_mechanism_metrics_from_sessions(
    mechanism_metrics: list[dict[str, Any]],
    sessions_path: Path,
) -> list[dict[str, Any]]:
    from .experiment_runner import _trace_component_metrics, _unique_context_ids

    records_by_session_id = {str(record.get("session_id", "")): dict(record) for record in mechanism_metrics}
    with sessions_path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            session = WorkflowSession.model_validate(json.loads(line))
            record = records_by_session_id.get(session.session_id)
            if record is None:
                continue
            context_bank = session.final_state.get("context_bank", {})
            selected_context_ids = _unique_context_ids(
                event.payload.get("selected_context_ids", [])
                for event in session.events
                if event.event_type in {"context_selection", "subtask_draft"}
            )
            reused_context_ids = _unique_context_ids(
                event.payload.get("reused_context_ids", [])
                for event in session.events
                if event.event_type in {"context_reuse", "subtask_draft"}
            )
            for key, value in _trace_component_metrics(session, selected_context_ids, reused_context_ids, context_bank).items():
                record.setdefault(key, value)
    return list(records_by_session_id.values())


def _enrich_mechanism_metrics_from_context_relevance(
    mechanism_metrics: list[dict[str, Any]],
    context_relevance_metrics_path: Path,
) -> list[dict[str, Any]]:
    records_by_session_id = {str(record.get("session_id", "")): dict(record) for record in mechanism_metrics}
    payload = json.loads(context_relevance_metrics_path.read_text())
    if not isinstance(payload, list):
        return mechanism_metrics
    for metric_record in payload:
        if not isinstance(metric_record, dict):
            continue
        session_id = str(metric_record.get("session_id", ""))
        record = records_by_session_id.get(session_id)
        if record is None:
            continue
        for key, value in metric_record.items():
            if key.startswith("gpt_") and isinstance(value, (int, float)):
                record[key] = value
    return list(records_by_session_id.values())


def _enrich_mechanism_metrics_from_context_relevance_labels(
    mechanism_metrics: list[dict[str, Any]],
    context_relevance_labels_path: Path,
) -> list[dict[str, Any]]:
    from .context_relevance import _session_context_relevance_metrics

    records_by_session_id = {str(record.get("session_id", "")): dict(record) for record in mechanism_metrics}
    label_rows = _read_jsonl(context_relevance_labels_path)
    for metric_record in _session_context_relevance_metrics(label_rows):
        session_id = str(metric_record.get("session_id", ""))
        record = records_by_session_id.get(session_id)
        if record is None:
            continue
        for key, value in metric_record.items():
            if key.startswith("gpt_") and isinstance(value, (int, float)):
                record[key] = value
    return list(records_by_session_id.values())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _unique_by(
    records: list[dict[str, Any]],
    key: str,
    errors: list[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    counts = Counter(str(record.get(key, "")) for record in records)
    duplicates = sorted(item_key for item_key, count in counts.items() if count > 1)
    if duplicates:
        errors.append(f"Duplicate {key} values in {label}: {', '.join(duplicates[:10])}")
    for record in records:
        item_key = str(record.get(key, ""))
        if item_key and item_key not in result:
            result[item_key] = record
    return result


def _metric_summary(values: list[int | float]) -> MetricSummary:
    numeric = [float(value) for value in values if value is not None]
    count = len(numeric)
    if not numeric:
        return MetricSummary(count=0)
    mean = sum(numeric) / count
    if count > 1:
        variance = sum((value - mean) ** 2 for value in numeric) / (count - 1)
        std = math.sqrt(variance)
    else:
        std = 0.0
    stderr = std / math.sqrt(count) if count else None
    return MetricSummary(
        count=count,
        mean=_round(mean),
        median=_round(float(median(numeric))),
        std=_round(std),
        stderr=_round(stderr) if stderr is not None else None,
    )


def _score_values(rows: list[dict[str, Any]], getter: Any) -> list[int | float]:
    values: list[int | float] = []
    for row in rows:
        value = getter(row["score"])
        if value is not None:
            values.append(value)
    return values


def _artifact_values(rows: list[dict[str, Any]], key: str) -> list[int | float]:
    return _record_values(rows, "artifact", key)


def _mechanism_values(rows: list[dict[str, Any]], key: str) -> list[int | float]:
    return _record_values(rows, "mechanism", key)


def _record_values(rows: list[dict[str, Any]], record_key: str, value_key: str) -> list[int | float]:
    values: list[int | float] = []
    for row in rows:
        value = row[record_key].get(value_key)
        if isinstance(value, (int, float)):
            values.append(value)
    return values


def _rubric_scores(rows: list[dict[str, Any]], criterion: str) -> list[int]:
    values: list[int] = []
    for row in rows:
        score = getattr(row["score"].score, criterion, None)
        if score is not None:
            values.append(score.score)
    return values


def _mean(values: list[int | float]) -> float:
    return _round(sum(float(value) for value in values) / len(values))


def _ci95(mean: float | None, stderr: float | None) -> tuple[float | None, float | None]:
    if mean is None or stderr is None:
        return None, None
    return _round(mean - 1.96 * stderr), _round(mean + 1.96 * stderr)


def _round(value: float) -> float:
    return round(float(value), 4)


def _display(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
