from __future__ import annotations

import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .openai_generation import DEFAULT_CONTEXT_RELEVANCE_MODEL, label_context_relevance_live
from .progress import progress
from .schemas import ContextRelevanceLabel, WorkflowSession
from .workflow_simulator import CONTEXT_RELEVANCE_THRESHOLD, _answer_status, _context_relevance_score, _is_substantive_context


DEFAULT_CONTEXT_RELEVANCE_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "context_relevance_label_v1.txt"
DEFAULT_CONTEXT_RELEVANCE_LABELS_NAME = "context_relevance_labels.jsonl"
DEFAULT_CONTEXT_RELEVANCE_METRICS_NAME = "context_relevance_metrics.json"
DEFAULT_CONTEXT_RELEVANCE_REPORT_NAME = "context_relevance_report.json"


@dataclass(frozen=True)
class ContextRelevanceLabelInput:
    label_id: str
    session_id: str
    condition: str
    simulation_profile_id: str
    goal_id: str
    seed: int
    event_id: int
    node_id: str | None
    task_name: str
    task_description: str
    context_id: str
    context_scope: str
    context_label: str
    context_value: str
    selected: bool
    reused: bool
    lexical_relevance_score: float

    def payload(self) -> str:
        return json.dumps(
            {
                "goal_id": self.goal_id,
                "condition": self.condition,
                "task": {
                    "node_id": self.node_id,
                    "name": self.task_name,
                    "description": self.task_description,
                },
                "context_item": {
                    "context_id": self.context_id,
                    "scope": self.context_scope,
                    "label": self.context_label,
                    "value": self.context_value,
                },
                "selected_by_condition": self.selected,
                "reused_in_draft": self.reused,
                "lexical_proxy_relevance_score": self.lexical_relevance_score,
                "instruction": (
                    "Label whether this context item is relevant and concretely usable for the specific task. "
                    "Do not label unknown or undecided answers as usable evidence."
                ),
            },
            ensure_ascii=True,
            indent=2,
        )


def run_context_relevance_labeler(
    run_dir: Path,
    output_path: Path | None = None,
    metrics_path: Path | None = None,
    report_path: Path | None = None,
    model: str = DEFAULT_CONTEXT_RELEVANCE_MODEL,
    live: bool = True,
    max_workers: int = 4,
    prompt_path: Path = DEFAULT_CONTEXT_RELEVANCE_PROMPT_PATH,
) -> dict[str, Any]:
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")
    run_dir = Path(run_dir)
    output_path = output_path or run_dir / DEFAULT_CONTEXT_RELEVANCE_LABELS_NAME
    metrics_path = metrics_path or run_dir / DEFAULT_CONTEXT_RELEVANCE_METRICS_NAME
    report_path = report_path or run_dir / DEFAULT_CONTEXT_RELEVANCE_REPORT_NAME
    sessions_path = run_dir / "sessions.jsonl"
    if not sessions_path.exists():
        raise FileNotFoundError(f"Missing sessions.jsonl: {sessions_path}")
    if live and not prompt_path.exists():
        raise FileNotFoundError(f"Missing prompt file: {prompt_path}")

    sessions = _read_sessions(sessions_path)
    label_inputs = build_context_relevance_label_inputs(sessions)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    expected_label_ids = {label_input.label_id for label_input in label_inputs}
    existing_labels = [
        label
        for label in _read_checkpointed_labels(output_path)
        if str(label.get("label_id", "")) in expected_label_ids
    ]
    existing_by_id = {str(label.get("label_id", "")): label for label in existing_labels if label.get("label_id")}
    pending_inputs = [label_input for label_input in label_inputs if label_input.label_id not in existing_by_id]
    labels = list(existing_by_id.values())
    if labels:
        _write_label_records(output_path, _sort_label_records(labels))
    else:
        output_path.write_text("")

    def checkpoint_label(label: dict[str, Any]) -> None:
        _append_label_record(output_path, label)

    labels.extend(
        _label_inputs(
            pending_inputs,
            model=model,
            live=live,
            max_workers=max_workers,
            prompt_path=prompt_path,
            on_result=checkpoint_label,
        )
    )
    labels = _sort_label_records(labels)
    metrics = _session_context_relevance_metrics(labels)

    _write_label_records(output_path, labels)
    metrics_path.write_text(json.dumps(metrics, indent=2))
    report = {
        "valid": True,
        "run_dir": str(run_dir),
        "sessions_path": str(sessions_path),
        "output_path": str(output_path),
        "metrics_path": str(metrics_path),
        "model": model,
        "live": live,
        "max_workers": max_workers,
        "session_count": len(sessions),
        "label_count": len(labels),
        "condition_counts": dict(Counter(label["condition"] for label in labels)),
        "selected_label_count": sum(1 for label in labels if label["selected"]),
        "reused_label_count": sum(1 for label in labels if label["reused"]),
        "relevant_label_count": sum(1 for label in labels if label["gpt_relevant"]),
    }
    report_path.write_text(json.dumps(report, indent=2))
    return report


def build_context_relevance_label_inputs(sessions: list[WorkflowSession]) -> list[ContextRelevanceLabelInput]:
    inputs: list[ContextRelevanceLabelInput] = []
    seen: set[tuple[str, int, str]] = set()
    for session in sessions:
        context_bank = session.final_state.get("context_bank", {})
        if not isinstance(context_bank, dict):
            continue
        reused_by_node: dict[str | None, set[str]] = defaultdict(set)
        for event in session.events:
            if event.event_type != "context_reuse":
                continue
            reused_by_node[event.node_id].update(str(context_id) for context_id in event.payload.get("reused_context_ids", []))
        for event in session.events:
            if event.event_type != "context_selection":
                continue
            task_name = str(event.payload.get("task_name", ""))
            task_description = str(event.payload.get("task_description", ""))
            task_text = f"{task_name} {task_description}"
            selected_ids = {str(context_id) for context_id in event.payload.get("selected_context_ids", [])}
            available_ids = [str(context_id) for context_id in event.payload.get("available_context_ids", [])]
            for context_id in available_ids:
                dedupe_key = (session.session_id, event.event_id, context_id)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                context = context_bank.get(context_id, {})
                if not isinstance(context, dict):
                    continue
                value = str(context.get("value", "")).strip()
                if not value:
                    continue
                label_id = f"CR{len(inputs) + 1:06d}"
                inputs.append(
                    ContextRelevanceLabelInput(
                        label_id=label_id,
                        session_id=session.session_id,
                        condition=session.condition,
                        simulation_profile_id=session.simulation_profile_id,
                        goal_id=session.goal_id,
                        seed=session.seed,
                        event_id=event.event_id,
                        node_id=event.node_id,
                        task_name=task_name,
                        task_description=task_description,
                        context_id=context_id,
                        context_scope=str(context.get("scope", "")),
                        context_label=str(context.get("label", context_id)),
                        context_value=value,
                        selected=context_id in selected_ids,
                        reused=context_id in reused_by_node.get(event.node_id, set()),
                        lexical_relevance_score=round(_context_relevance_score(task_text, context), 4),
                    )
                )
    return inputs


def _label_inputs(
    label_inputs: list[ContextRelevanceLabelInput],
    model: str,
    live: bool,
    max_workers: int,
    prompt_path: Path,
    on_result: Any | None = None,
) -> list[dict[str, Any]]:
    executor_cls = ProcessPoolExecutor if live else ThreadPoolExecutor
    worker_args = [
        {
            "label_input": label_input,
            "model": model,
            "live": live,
            "prompt_path": prompt_path,
        }
        for label_input in label_inputs
    ]

    if not worker_args:
        return []

    with executor_cls(max_workers=max_workers) as executor:
        future_to_label_id = {
            executor.submit(_label_one_worker, worker_arg): worker_arg["label_input"].label_id
            for worker_arg in worker_args
        }
        labels: list[dict[str, Any]] = []
        for future in progress(
            as_completed(future_to_label_id),
            total=len(worker_args),
            desc=f"Labeling context relevance ({max_workers} workers)",
            unit="label",
        ):
            label = future.result()
            labels.append(label)
            if on_result is not None:
                on_result(label)
        return _sort_label_records(labels)


def _read_checkpointed_labels(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    labels_by_id: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            label = json.loads(line)
        except json.JSONDecodeError:
            continue
        label_id = str(label.get("label_id", ""))
        if label_id:
            labels_by_id[label_id] = label
    return list(labels_by_id.values())


def _write_label_records(path: Path, labels: list[dict[str, Any]]) -> None:
    with path.open("w") as handle:
        for label in labels:
            handle.write(json.dumps(label, ensure_ascii=True) + "\n")


def _append_label_record(path: Path, label: dict[str, Any]) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(label, ensure_ascii=True) + "\n")
        handle.flush()


def _sort_label_records(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(label: dict[str, Any]) -> int:
        label_id = str(label.get("label_id", ""))
        if label_id.startswith("CR") and label_id[2:].isdigit():
            return int(label_id[2:])
        return 10**12

    return sorted(labels, key=sort_key)


def _label_one_worker(args: dict[str, Any]) -> dict[str, Any]:
    label_input = args["label_input"]
    model = str(args["model"])
    live = bool(args["live"])
    prompt_path = Path(args["prompt_path"])
    if live:
        label = _live_label_one(label_input, prompt_path, model)
        dry_run = False
    else:
        label = _dry_run_label(label_input)
        dry_run = True
    return _label_record(label_input, label, model=model, dry_run=dry_run)


def _live_label_one(label_input: ContextRelevanceLabelInput, prompt_path: Path, model: str) -> ContextRelevanceLabel:
    return label_context_relevance_live(prompt_path, label_input.payload(), model=model)


def _dry_run_label(label_input: ContextRelevanceLabelInput) -> ContextRelevanceLabel:
    if _answer_status(label_input.context_value) == "unknown" or not _is_substantive_context(
        {"label": label_input.context_label, "value": label_input.context_value}
    ):
        return ContextRelevanceLabel(
            relevance_score=0.0,
            relevant=False,
            relevance_rationale="Context is unknown or non-substantive.",
            relevance_type="unknown_or_unusable",
        )
    score = max(0.0, min(1.0, label_input.lexical_relevance_score))
    relevant = score > CONTEXT_RELEVANCE_THRESHOLD
    if score >= 0.71:
        relevance_type = "direct"
    elif score >= 0.5:
        relevance_type = "supporting"
    elif score >= 0.21:
        relevance_type = "background"
    else:
        relevance_type = "irrelevant"
    return ContextRelevanceLabel(
        relevance_score=score,
        relevant=relevant,
        relevance_rationale="Dry-run lexical overlap proxy.",
        relevance_type=relevance_type,
    )


def _label_record(
    label_input: ContextRelevanceLabelInput,
    label: ContextRelevanceLabel,
    model: str,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "label_id": label_input.label_id,
        "session_id": label_input.session_id,
        "condition": label_input.condition,
        "simulation_profile_id": label_input.simulation_profile_id,
        "goal_id": label_input.goal_id,
        "seed": label_input.seed,
        "event_id": label_input.event_id,
        "node_id": label_input.node_id,
        "task_name": label_input.task_name,
        "task_description": label_input.task_description,
        "context_id": label_input.context_id,
        "context_scope": label_input.context_scope,
        "context_label": label_input.context_label,
        "context_value": label_input.context_value,
        "selected": label_input.selected,
        "reused": label_input.reused,
        "lexical_relevance_score": label_input.lexical_relevance_score,
        "gpt_relevance_score": round(label.relevance_score, 4),
        "gpt_relevant": bool(label.relevant),
        "gpt_relevance_type": label.relevance_type,
        "gpt_relevance_rationale": label.relevance_rationale,
        "model": model,
        "dry_run": dry_run,
    }


def _session_context_relevance_metrics(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for label in labels:
        by_session[str(label["session_id"])].append(label)
    records: list[dict[str, Any]] = []
    for session_id, session_labels in sorted(by_session.items()):
        selected = [label for label in session_labels if label["selected"]]
        reused = [label for label in session_labels if label["reused"]]
        available_relevant = [label for label in session_labels if label["gpt_relevant"]]
        selected_relevant = [label for label in selected if label["gpt_relevant"]]
        reused_relevant = [label for label in reused if label["gpt_relevant"]]
        precision = _ratio(len(selected_relevant), len(selected))
        recall = _ratio(len(selected_relevant), len(available_relevant))
        reused_precision = _ratio(len(reused_relevant), len(reused))
        used_relevant_rate = _ratio(len(reused_relevant), len(available_relevant))
        first = session_labels[0]
        records.append(
            {
                "session_id": session_id,
                "condition": first["condition"],
                "simulation_profile_id": first["simulation_profile_id"],
                "goal_id": first["goal_id"],
                "seed": first["seed"],
                "gpt_context_label_count": len(session_labels),
                "gpt_available_relevant_context_items": len(available_relevant),
                "gpt_selected_context_items": len(selected),
                "gpt_reused_context_items": len(reused),
                "gpt_relevant_selected_context_items": len(selected_relevant),
                "gpt_relevant_reused_context_items": len(reused_relevant),
                "gpt_used_relevant_context_items": len(reused_relevant),
                "gpt_context_precision": precision,
                "gpt_context_recall": recall,
                "gpt_context_f1": _f1(precision, recall),
                "gpt_reused_context_precision": reused_precision,
                "gpt_used_relevant_context_rate": used_relevant_rate,
                "gpt_selected_relevance_score_mean": _mean([label["gpt_relevance_score"] for label in selected]),
                "gpt_reused_relevance_score_mean": _mean([label["gpt_relevance_score"] for label in reused]),
                "gpt_available_relevance_score_mean": _mean([label["gpt_relevance_score"] for label in session_labels]),
            }
        )
    return records


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 4)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(float(value) for value in values) / len(values), 4)


def _read_sessions(path: Path) -> list[WorkflowSession]:
    sessions: list[WorkflowSession] = []
    with path.open() as handle:
        for line in handle:
            if line.strip():
                sessions.append(WorkflowSession.model_validate(json.loads(line)))
    return sessions
