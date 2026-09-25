from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .pipeline import DEFAULT_DATA_DIR, DEFAULT_REPORTS_DIR, REPO_ROOT
from .schemas import UserDecisionCalibrationReport


DEFAULT_USER_DECISION_CALIBRATION_PATH = DEFAULT_DATA_DIR / "user_decision_calibration.json"
DEFAULT_USER_DECISION_CALIBRATION_REPORT_PATH = DEFAULT_REPORTS_DIR / "user_decision_calibration_report.json"
DEFAULT_USER_STUDY_LOG_PATHS = (REPO_ROOT / "userstudy.log", REPO_ROOT / "userstudy2.log")


@dataclass(frozen=True)
class StudyLogRecord:
    source_log: str
    line_number: int
    task: str
    username: str
    root_node: dict[str, Any]
    user_global_context: dict[str, Any]
    user_context: dict[str, Any]


@dataclass(frozen=True)
class NodeObservation:
    node_id: str
    parent_id: str | None
    title: str
    level: int
    sibling_index: int
    sibling_count: int
    child_count: int
    need_subtasks: bool
    is_completed: bool
    has_saved_draft: bool
    has_generated_response: bool
    generated_response_count: int
    has_curated_context: bool


def build_user_decision_calibration(
    log_paths: Iterable[Path] = DEFAULT_USER_STUDY_LOG_PATHS,
    output_path: Path = DEFAULT_USER_DECISION_CALIBRATION_PATH,
    report_path: Path = DEFAULT_USER_DECISION_CALIBRATION_REPORT_PATH,
) -> UserDecisionCalibrationReport:
    paths = [Path(path) for path in log_paths]
    records, parse_warnings = read_study_log_records(paths)
    if not records:
        report = UserDecisionCalibrationReport(
            valid=False,
            source_logs=[str(path) for path in paths],
            output_path=str(output_path),
            report_path=str(report_path),
            total_log_records=0,
            final_session_count=0,
            policies={},
            errors=["No JumpStarter task records were extracted from the study logs."],
            warnings=parse_warnings,
        )
        _write_report(report, output_path, report_path)
        return report

    final_records = _latest_record_per_user_task(records)
    policies = _build_policies(final_records, records)
    report = UserDecisionCalibrationReport(
        valid=True,
        source_logs=[str(path) for path in paths],
        output_path=str(output_path),
        report_path=str(report_path),
        total_log_records=len(records),
        final_session_count=len(final_records),
        policies=policies,
        errors=[],
        warnings=parse_warnings + _calibration_warnings(policies),
    )
    _write_report(report, output_path, report_path)
    return report


def read_study_log_records(log_paths: Iterable[Path]) -> tuple[list[StudyLogRecord], list[str]]:
    records: list[StudyLogRecord] = []
    warnings: list[str] = []
    for path in log_paths:
        if not path.exists():
            warnings.append(f"Study log not found: {path}")
            continue
        for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith("{'task':") or stripped.startswith('{"task":')):
                continue
            try:
                payload = ast.literal_eval(stripped)
            except (SyntaxError, ValueError) as exc:
                warnings.append(f"{path}:{line_number}: could not parse task record: {exc}")
                continue
            root_node = payload.get("root_node")
            if not isinstance(root_node, dict):
                warnings.append(f"{path}:{line_number}: task record missing root_node")
                continue
            records.append(
                StudyLogRecord(
                    source_log=str(path),
                    line_number=line_number,
                    task=str(payload.get("task") or ""),
                    username=str(payload.get("username") or "unknown"),
                    root_node=root_node,
                    user_global_context=_dict_or_empty(payload.get("userGlobalContext") or payload.get("user_global_context")),
                    user_context=_dict_or_empty(payload.get("user_context")),
                )
            )
    return records, warnings


def _build_policies(final_records: list[StudyLogRecord], snapshots: list[StudyLogRecord]) -> dict[str, Any]:
    final_nodes_by_record = {record_key(record): _node_observations(record.root_node) for record in final_records}
    final_nodes = [node for nodes in final_nodes_by_record.values() for node in nodes]
    non_root_nodes = [node for node in final_nodes if node.parent_id]
    roots = [nodes[0] for nodes in final_nodes_by_record.values() if nodes]
    parent_nodes = [node for node in final_nodes if node.child_count > 0]
    generated_or_drafted_nodes = [
        node
        for node in non_root_nodes
        if node.has_generated_response or node.has_saved_draft or node.is_completed
    ]
    leaf_nodes = [node for node in non_root_nodes if node.child_count == 0]

    completion_ratios = [
        _safe_ratio(sum(1 for node in nodes if node.is_completed), len(nodes))
        for nodes in final_nodes_by_record.values()
        if nodes
    ]
    draft_ratios = [
        _safe_ratio(sum(1 for node in nodes if node.has_saved_draft), len(nodes))
        for nodes in final_nodes_by_record.values()
        if nodes
    ]
    saved_context_counts = [len(record.user_context) for record in final_records]
    global_context_counts = [len(record.user_global_context) for record in final_records]
    snapshot_counts_by_session = Counter(record_key(record) for record in snapshots)

    policies = {
        "source_summary": {
            "record_snapshots": len(snapshots),
            "final_sessions": len(final_records),
            "unique_users": len({record.username for record in final_records}),
            "unique_tasks": len({record.task for record in final_records}),
            "records_by_log": dict(Counter(record.source_log for record in snapshots)),
            "mean_snapshots_per_session": _rounded_mean(snapshot_counts_by_session.values()),
        },
        "task_tree_review": {
            "observations": len(roots),
            "accept_proxy_definition": "Root task has at least one saved child node in the final JumpStarter task tree.",
            "accept_rate": _rate(sum(1 for node in roots if node.child_count > 0), len(roots)),
            "mean_top_level_children": _rounded_mean(node.child_count for node in roots),
            "child_count_distribution": _distribution(node.child_count for node in roots),
            "recommended_simulator_action": "Sample accept/revise using accept_rate; if revising, request a regenerated decomposition rather than silently accepting.",
        },
        "subtask_detection_decision": {
            "observations": len(non_root_nodes),
            "proxy_definition": "Saved node fields need_subtasks and children indicate whether the real workflow proceeded by decomposition or direct drafting.",
            "decompose_further_rate": _rate(sum(1 for node in non_root_nodes if node.need_subtasks or node.child_count > 0), len(non_root_nodes)),
            "draft_answer_rate": _rate(sum(1 for node in non_root_nodes if not node.need_subtasks and node.child_count == 0), len(non_root_nodes)),
            "realized_child_decomposition_rate": _rate(sum(1 for node in non_root_nodes if node.child_count > 0), len(non_root_nodes)),
            "saved_draft_without_children_rate": _rate(sum(1 for node in leaf_nodes if node.has_saved_draft), len(leaf_nodes)),
            "recommended_simulator_action": "Do not always apply the assistant suggestion; sample decompose_further versus draft_answer from these rates conditioned on node level and specificity.",
        },
        "nested_task_review": {
            "observations": len(parent_nodes),
            "proxy_definition": "For nodes that ended with children, child completion/draft position approximates which children the user pursued after accepting the nested tree.",
            "accept_children_proxy_rate": _rate(sum(1 for node in parent_nodes if node.child_count > 0), len(parent_nodes)),
            "mean_children_per_parent": _rounded_mean(node.child_count for node in parent_nodes),
            "selected_child_position_distribution": _selected_child_position_distribution(final_nodes_by_record),
            "recommended_simulator_action": "Pick child work targets according to observed pursued-child positions rather than always choosing the last child.",
        },
        "context_answer_behavior": {
            "observations": len(final_records),
            "proxy_definition": "Saved global context and per-node user_context entries approximate how much context real users provided and preserved.",
            "mean_global_context_items": _rounded_mean(global_context_counts),
            "mean_local_context_items": _rounded_mean(saved_context_counts),
            "sessions_with_global_context_rate": _rate(sum(1 for count in global_context_counts if count > 0), len(global_context_counts)),
            "sessions_with_local_context_rate": _rate(sum(1 for count in saved_context_counts if count > 0), len(saved_context_counts)),
            "local_context_per_saved_draft": _safe_round(
                sum(saved_context_counts) / max(1, sum(1 for node in final_nodes if node.has_saved_draft))
            ),
            "recommended_simulator_action": "Calibrate how often the simulated user gives local context or says unknown from observed saved context density.",
        },
        "draft_review": {
            "observations": len(generated_or_drafted_nodes),
            "proxy_definition": "Saving answer_draft_input and marking a node completed approximate accepting a working draft; multiple generations before saving approximate revision/pushback.",
            "saved_draft_rate": _rate(sum(1 for node in generated_or_drafted_nodes if node.has_saved_draft), len(generated_or_drafted_nodes)),
            "completed_node_rate": _rate(sum(1 for node in generated_or_drafted_nodes if node.is_completed), len(generated_or_drafted_nodes)),
            "revision_proxy_rate": _rate(
                sum(1 for node in generated_or_drafted_nodes if node.generated_response_count > 1),
                len(generated_or_drafted_nodes),
            ),
            "curated_context_present_rate": _rate(
                sum(1 for node in generated_or_drafted_nodes if node.has_curated_context),
                len(generated_or_drafted_nodes),
            ),
            "recommended_simulator_action": "Accept, push back, or save partially based on saved_draft_rate, completion_rate, and revision_proxy_rate instead of only selected-context presence.",
        },
        "final_artifact_review": {
            "observations": len(final_records),
            "proxy_definition": "The logs do not contain an explicit final approval click; completion and saved-draft ratios are conservative final-readiness proxies.",
            "mean_completion_ratio": _rounded_mean(completion_ratios),
            "mean_saved_draft_ratio": _rounded_mean(draft_ratios),
            "completion_bucket_distribution": _bucket_distribution(completion_ratios),
            "saved_draft_bucket_distribution": _bucket_distribution(draft_ratios),
            "recommended_simulator_action": "Use completion/saved-draft buckets plus human DOCX ratings when available; do not approve solely because every simulated node was visited.",
        },
        "example_sessions": [_example_session(record, final_nodes_by_record[record_key(record)]) for record in final_records[:5]],
    }
    policies["agreement_metrics"] = _agreement_metrics(final_records, final_nodes_by_record)
    return policies


def _latest_record_per_user_task(records: list[StudyLogRecord]) -> list[StudyLogRecord]:
    latest: dict[tuple[str, str], StudyLogRecord] = {}
    for record in records:
        latest[record_key(record)] = record
    return sorted(latest.values(), key=lambda record: (record.source_log, record.line_number))


def record_key(record: StudyLogRecord) -> tuple[str, str]:
    return (record.username, record.task)


def _node_observations(root_node: dict[str, Any]) -> list[NodeObservation]:
    observations: list[NodeObservation] = []

    def visit(node: dict[str, Any], parent_id: str | None, sibling_index: int, sibling_count: int) -> None:
        children = [child for child in node.get("children") or [] if isinstance(child, dict)]
        node_id = str(node.get("id") or "")
        draft = _answer_draft_text(node)
        generated_response_count = _generated_response_count(node)
        observations.append(
            NodeObservation(
                node_id=node_id,
                parent_id=parent_id,
                title=str(node.get("text") or ""),
                level=_int_or_default(node.get("level"), 1),
                sibling_index=sibling_index,
                sibling_count=sibling_count,
                child_count=len(children),
                need_subtasks=bool(node.get("need_subtasks")),
                is_completed=bool(node.get("is_completed")),
                has_saved_draft=_substantive_text(draft),
                has_generated_response=generated_response_count > 0,
                generated_response_count=generated_response_count,
                has_curated_context=_substantive_text(str(node.get("curated_context_draft") or "")),
            )
        )
        for index, child in enumerate(children, start=1):
            visit(child, node_id, index, len(children))

    visit(root_node, None, 1, 1)
    return observations


def _selected_child_position_distribution(final_nodes_by_record: dict[tuple[str, str], list[NodeObservation]]) -> dict[str, float]:
    counts: Counter[str] = Counter()
    total = 0
    children_by_parent_by_record: dict[tuple[str, str], dict[str | None, list[NodeObservation]]] = {}
    for key, nodes in final_nodes_by_record.items():
        by_parent: dict[str | None, list[NodeObservation]] = defaultdict(list)
        for node in nodes:
            by_parent[node.parent_id].append(node)
        children_by_parent_by_record[key] = by_parent

    for by_parent in children_by_parent_by_record.values():
        for parent_id, children in by_parent.items():
            if parent_id is None or not children:
                continue
            pursued = [child for child in children if child.is_completed or child.has_saved_draft]
            if not pursued:
                continue
            total += 1
            pursued_indexes = {child.sibling_index for child in pursued}
            if len(pursued) == len(children):
                counts["all_children"] += 1
            elif min(pursued_indexes) == 1:
                counts["first_child"] += 1
            elif max(pursued_indexes) == len(children):
                counts["last_child"] += 1
            else:
                counts["middle_child"] += 1
    return {key: _safe_round(value / total) for key, value in sorted(counts.items())} if total else {}


def _agreement_metrics(
    final_records: list[StudyLogRecord],
    final_nodes_by_record: dict[tuple[str, str], list[NodeObservation]],
) -> dict[str, Any]:
    grouped_labels: dict[str, dict[tuple[str, str], list[int]]] = defaultdict(dict)
    for record in final_records:
        key = record_key(record)
        nodes = final_nodes_by_record.get(key, [])
        if not nodes:
            continue
        root = nodes[0]
        non_root_nodes = [node for node in nodes if node.parent_id]
        generated_or_drafted_nodes = [
            node
            for node in non_root_nodes
            if node.has_generated_response or node.has_saved_draft or node.is_completed
        ]
        completion_ratio = _safe_ratio(sum(1 for node in nodes if node.is_completed), len(nodes))
        saved_draft_ratio = _safe_ratio(sum(1 for node in nodes if node.has_saved_draft), len(nodes))

        grouped_labels["task_tree_acceptance"][key] = [int(root.child_count > 0)]
        grouped_labels["subtask_decompose_further"][key] = [
            int(node.need_subtasks or node.child_count > 0) for node in non_root_nodes
        ]
        grouped_labels["realized_child_decomposition"][key] = [int(node.child_count > 0) for node in non_root_nodes]
        grouped_labels["draft_saved"][key] = [int(node.has_saved_draft) for node in generated_or_drafted_nodes]
        grouped_labels["node_completed"][key] = [int(node.is_completed) for node in generated_or_drafted_nodes]
        grouped_labels["revision_proxy"][key] = [
            int(node.generated_response_count > 1) for node in generated_or_drafted_nodes
        ]
        grouped_labels["global_context_provided"][key] = [int(len(record.user_global_context) > 0)]
        grouped_labels["local_context_provided"][key] = [int(len(record.user_context) > 0)]
        grouped_labels["completion_ratio_ge_0_75"][key] = [int(completion_ratio >= 0.75)]
        grouped_labels["saved_draft_ratio_ge_0_75"][key] = [int(saved_draft_ratio >= 0.75)]

    metrics = {
        name: _leave_one_session_out_binary_metrics(labels_by_session)
        for name, labels_by_session in grouped_labels.items()
    }
    metric_values = [metric for metric in metrics.values() if metric.get("observations")]
    summary = {
        "metric_families": len(metric_values),
        "mean_loo_brier": _rounded_mean(
            metric["loo_brier"] for metric in metric_values if metric.get("loo_brier") is not None
        ),
        "mean_loo_ece_5_bin": _rounded_mean(
            metric["loo_ece_5_bin"] for metric in metric_values if metric.get("loo_ece_5_bin") is not None
        ),
        "mean_loo_session_rate_mae": _rounded_mean(
            metric["loo_session_rate_mae"]
            for metric in metric_values
            if metric.get("loo_session_rate_mae") is not None
        ),
        "mean_threshold_accuracy": _rounded_mean(
            metric["threshold_accuracy"]
            for metric in metric_values
            if metric.get("threshold_accuracy") is not None
        ),
        "mean_threshold_balanced_accuracy": _rounded_mean(
            metric["threshold_balanced_accuracy"]
            for metric in metric_values
            if metric.get("threshold_balanced_accuracy") is not None
        ),
        "mean_threshold_f1": _rounded_mean(
            metric["threshold_f1"] for metric in metric_values if metric.get("threshold_f1") is not None
        ),
        "mean_cohens_kappa": _rounded_mean(
            metric["cohens_kappa"] for metric in metric_values if metric.get("cohens_kappa") is not None
        ),
        "validation_protocol": (
            "Leave-one-session-out: estimate each binary behavior's base rate from all other "
            "final sessions, score held-out observations with that probability, and threshold "
            "at 0.5 only for chance-corrected agreement diagnostics."
        ),
    }
    return {"summary": summary, "binary_decisions": metrics}


def _leave_one_session_out_binary_metrics(labels_by_session: dict[tuple[str, str], list[int]]) -> dict[str, Any]:
    labels_by_session = {key: labels for key, labels in labels_by_session.items() if labels}
    all_labels = [label for labels in labels_by_session.values() for label in labels]
    observations = len(all_labels)
    if not observations:
        return {
            "observations": 0,
            "sessions": 0,
            "empirical_rate": None,
            "loo_brier": None,
            "loo_ece_5_bin": None,
            "loo_session_rate_mae": None,
            "threshold_accuracy": None,
            "threshold_balanced_accuracy": None,
            "threshold_precision": None,
            "threshold_recall": None,
            "threshold_f1": None,
            "cohens_kappa": None,
        }

    predictions: list[float] = []
    truths: list[int] = []
    session_rate_errors: list[float] = []
    total_positive = sum(all_labels)
    for key, heldout_labels in labels_by_session.items():
        heldout_positive = sum(heldout_labels)
        train_n = observations - len(heldout_labels)
        train_positive = total_positive - heldout_positive
        if train_n <= 0:
            continue
        predicted_rate = train_positive / train_n
        predictions.extend([predicted_rate] * len(heldout_labels))
        truths.extend(heldout_labels)
        session_rate_errors.append(abs(predicted_rate - (heldout_positive / len(heldout_labels))))

    thresholded = [int(probability >= 0.5) for probability in predictions]
    threshold_metrics = _threshold_binary_metrics(truths, thresholded)
    return {
        "observations": observations,
        "sessions": len(labels_by_session),
        "empirical_rate": _safe_round(total_positive / observations),
        "loo_brier": _safe_round(mean((probability - truth) ** 2 for probability, truth in zip(predictions, truths)))
        if predictions
        else None,
        "loo_ece_5_bin": _expected_calibration_error(predictions, truths, bins=5) if predictions else None,
        "loo_session_rate_mae": _rounded_mean(session_rate_errors),
        **threshold_metrics,
    }


def _threshold_binary_metrics(truths: list[int], predictions: list[int]) -> dict[str, float | None]:
    if not truths:
        return {
            "threshold_accuracy": None,
            "threshold_balanced_accuracy": None,
            "threshold_precision": None,
            "threshold_recall": None,
            "threshold_f1": None,
            "cohens_kappa": None,
        }
    tp = sum(1 for truth, prediction in zip(truths, predictions) if truth == 1 and prediction == 1)
    tn = sum(1 for truth, prediction in zip(truths, predictions) if truth == 0 and prediction == 0)
    fp = sum(1 for truth, prediction in zip(truths, predictions) if truth == 0 and prediction == 1)
    fn = sum(1 for truth, prediction in zip(truths, predictions) if truth == 1 and prediction == 0)
    total = len(truths)
    positive_count = tp + fn
    negative_count = tn + fp
    predicted_positive = tp + fp
    precision = tp / predicted_positive if predicted_positive else None
    recall = tp / positive_count if positive_count else None
    f1 = (2 * precision * recall / (precision + recall)) if precision is not None and recall is not None and precision + recall else None
    balanced_accuracy = (
        ((tp / positive_count) + (tn / negative_count)) / 2 if positive_count and negative_count else None
    )
    return {
        "threshold_accuracy": _safe_round((tp + tn) / total),
        "threshold_balanced_accuracy": _safe_round(balanced_accuracy) if balanced_accuracy is not None else None,
        "threshold_precision": _safe_round(precision) if precision is not None else None,
        "threshold_recall": _safe_round(recall) if recall is not None else None,
        "threshold_f1": _safe_round(f1) if f1 is not None else None,
        "cohens_kappa": _cohens_kappa(tp=tp, tn=tn, fp=fp, fn=fn),
    }


def _cohens_kappa(*, tp: int, tn: int, fp: int, fn: int) -> float | None:
    total = tp + tn + fp + fn
    if not total:
        return None
    observed_agreement = (tp + tn) / total
    predicted_positive_rate = (tp + fp) / total
    predicted_negative_rate = (tn + fn) / total
    true_positive_rate = (tp + fn) / total
    true_negative_rate = (tn + fp) / total
    expected_agreement = (
        predicted_positive_rate * true_positive_rate + predicted_negative_rate * true_negative_rate
    )
    if expected_agreement >= 1.0:
        return None
    return _safe_round((observed_agreement - expected_agreement) / (1.0 - expected_agreement))


def _expected_calibration_error(predictions: list[float], truths: list[int], bins: int = 5) -> float | None:
    if not predictions:
        return None
    total = len(predictions)
    weighted_error = 0.0
    for bin_index in range(bins):
        lower = bin_index / bins
        upper = (bin_index + 1) / bins
        indexes = [
            index
            for index, probability in enumerate(predictions)
            if (lower <= probability <= upper if bin_index == bins - 1 else lower <= probability < upper)
        ]
        if not indexes:
            continue
        mean_prediction = mean(predictions[index] for index in indexes)
        empirical_rate = mean(truths[index] for index in indexes)
        weighted_error += (len(indexes) / total) * abs(mean_prediction - empirical_rate)
    return _safe_round(weighted_error)


def _example_session(record: StudyLogRecord, nodes: list[NodeObservation]) -> dict[str, Any]:
    return {
        "source_log": record.source_log,
        "line_number": record.line_number,
        "username": record.username,
        "task": record.task,
        "global_context_items": len(record.user_global_context),
        "local_context_items": len(record.user_context),
        "node_count": len(nodes),
        "completed_nodes": sum(1 for node in nodes if node.is_completed),
        "saved_draft_nodes": sum(1 for node in nodes if node.has_saved_draft),
    }


def _calibration_warnings(policies: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    final_observations = int(policies.get("final_artifact_review", {}).get("observations", 0))
    if final_observations < 8:
        warnings.append("Fewer than 8 final JumpStarter sessions available; user decision calibration will be noisy.")
    if not policies.get("nested_task_review", {}).get("selected_child_position_distribution"):
        warnings.append("No pursued-child position distribution could be estimated from saved task trees.")
    warnings.append("Final approval is not directly logged; final_artifact_review uses completion and saved-draft proxies.")
    return warnings


def _write_report(report: UserDecisionCalibrationReport, output_path: Path, report_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.policies, indent=2, sort_keys=True))
    report_path.write_text(report.model_dump_json(indent=2))


def _answer_draft_text(node: dict[str, Any]) -> str:
    answer_draft = node.get("answer_draft")
    if not isinstance(answer_draft, dict):
        return ""
    return str(answer_draft.get("answer_draft_input") or "")


def _generated_response_count(node: dict[str, Any]) -> int:
    count = 0
    for key in ("gpt_response", "gpt_response_brainstorm", "gpt_response_steps"):
        value = node.get(key)
        if isinstance(value, list):
            count += len([item for item in value if _substantive_text(str(item))])
        elif _substantive_text(str(value or "")):
            count += 1
    return count


def _substantive_text(text: str) -> bool:
    cleaned = str(text).strip()
    lowered = cleaned.lower()
    return bool(cleaned) and lowered not in {"undefined", "undefined: undefined", "none", "null", "[]", "{}"}


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return _safe_round(numerator / denominator)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _safe_round(value: float) -> float:
    return round(float(value), 4)


def _rounded_mean(values: Iterable[float | int]) -> float | None:
    materialized = [float(value) for value in values]
    return _safe_round(mean(materialized)) if materialized else None


def _distribution(values: Iterable[Any]) -> dict[str, int]:
    return {str(key): value for key, value in sorted(Counter(values).items(), key=lambda item: str(item[0]))}


def _bucket_distribution(values: Iterable[float]) -> dict[str, float]:
    counts: Counter[str] = Counter()
    materialized = list(values)
    for value in materialized:
        if value <= 0.25:
            counts["0.00-0.25"] += 1
        elif value <= 0.50:
            counts["0.25-0.50"] += 1
        elif value <= 0.75:
            counts["0.50-0.75"] += 1
        else:
            counts["0.75-1.00"] += 1
    total = len(materialized)
    return {bucket: _safe_round(count / total) for bucket, count in sorted(counts.items())} if total else {}
