from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from .openai_generation import DEFAULT_USER_SIMULATOR_MODEL
from .pipeline import DEFAULT_DATA_DIR
from .progress import progress
from .schemas import ExperimentRunReport, WorkflowSession
from .workflow_prompts import PROMPT_DIR, PROMPT_VERSION, prompt_ids, validate_prompt_files
from .workflow_simulator import (
    DEFAULT_RUNS_DIR,
    EXPERIMENT_CONDITION_PRESETS,
    PRIMARY_EXPERIMENT_CONDITIONS,
    WORKFLOW_CONDITIONS,
    CONTEXT_RELEVANCE_THRESHOLD,
    LiveStageMode,
    _context_relevance_score,
    _context_token_count,
    _is_substantive_context,
    read_simulation_profiles,
    simulate_workflow_session,
    workflow_fidelity_report,
)


DEFAULT_EXPERIMENT_RUNS_DIR = DEFAULT_RUNS_DIR


def parse_condition_list(value: str | None) -> list[str]:
    if not value:
        return list(PRIMARY_EXPERIMENT_CONDITIONS)
    conditions: list[str] = []
    for item in [item.strip() for item in value.split(",") if item.strip()]:
        preset = EXPERIMENT_CONDITION_PRESETS.get(item.lower())
        if preset is not None:
            conditions.extend(preset)
        else:
            conditions.append(item)
    conditions = list(dict.fromkeys(conditions))
    unknown = sorted(set(conditions) - set(WORKFLOW_CONDITIONS))
    if unknown:
        presets = ", ".join(sorted(EXPERIMENT_CONDITION_PRESETS))
        raise ValueError(f"Unknown workflow conditions: {', '.join(unknown)}. Presets: {presets}")
    return conditions


def run_workflow_experiment(
    profiles_path: Path = DEFAULT_DATA_DIR / "simulation_profiles.json",
    output_dir: Path | None = None,
    conditions: list[str] | None = None,
    limit: int = 10,
    runs_per_profile: int = 1,
    seed: int = 42,
    model: str = "deterministic",
    live_stages: LiveStageMode = "deterministic",
    simulated_user_model: str = DEFAULT_USER_SIMULATOR_MODEL,
    live_simulated_user: bool = False,
    max_workers: int = 1,
) -> ExperimentRunReport:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if runs_per_profile <= 0:
        raise ValueError("runs_per_profile must be positive")
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")
    prompt_errors = validate_prompt_files()
    if prompt_errors:
        raise RuntimeError("Paper workflow prompt files are incomplete: " + "; ".join(prompt_errors))

    selected_conditions = conditions or list(PRIMARY_EXPERIMENT_CONDITIONS)
    unknown = sorted(set(selected_conditions) - set(WORKFLOW_CONDITIONS))
    if unknown:
        raise ValueError(f"Unknown workflow conditions: {', '.join(unknown)}")

    profiles = read_simulation_profiles(profiles_path)[:limit]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"workflow_experiment_{timestamp}"
    if output_dir is None:
        output_dir = DEFAULT_EXPERIMENT_RUNS_DIR / experiment_id
    traces_dir = output_dir / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    jobs = [
        (run_index, profile, condition)
        for run_index in range(runs_per_profile)
        for profile in profiles
        for condition in selected_conditions
    ]
    expected_sessions = len(profiles) * len(selected_conditions) * runs_per_profile
    _write_run_config(
        output_dir=output_dir,
        experiment_id=experiment_id,
        profiles_path=profiles_path,
        conditions=selected_conditions,
        limit=limit,
        runs_per_profile=runs_per_profile,
        seed=seed,
        model=model,
        live_stages=live_stages,
        simulated_user_model=simulated_user_model,
        live_simulated_user=live_simulated_user,
        max_workers=max_workers,
    )
    sessions = _simulate_jobs(
        jobs=jobs,
        seed=seed,
        model=model,
        live_stages=live_stages,
        simulated_user_model=simulated_user_model,
        live_simulated_user=live_simulated_user,
        max_workers=max_workers,
        total=expected_sessions,
        output_dir=output_dir,
        traces_dir=traces_dir,
    )

    _write_sessions(output_dir, traces_dir, sessions)
    artifacts, judge_inputs, condition_key, mechanism_metrics = _build_experiment_records(sessions)
    _write_jsonl(output_dir / "artifacts.jsonl", artifacts)
    _write_jsonl(output_dir / "judge_inputs_blinded.jsonl", judge_inputs)
    _write_jsonl(output_dir / "condition_key.jsonl", condition_key)
    (output_dir / "mechanism_metrics.json").write_text(json.dumps(mechanism_metrics, indent=2))

    workflow_report = workflow_fidelity_report(sessions)
    (output_dir / "workflow_fidelity_report.json").write_text(workflow_report.model_dump_json(indent=2))

    errors: list[str] = []
    warnings: list[str] = []
    if len(sessions) != expected_sessions:
        errors.append(f"Expected {expected_sessions} sessions, generated {len(sessions)}")
    if not workflow_report.valid:
        errors.extend(workflow_report.errors)
    if model != "deterministic":
        if live_stages == "deterministic":
            warnings.append("Workflow model was recorded for provenance only because live_stages=deterministic.")

    report = ExperimentRunReport(
        valid=not errors,
        experiment_id=experiment_id,
        total_sessions=len(sessions),
        total_profiles=len(profiles),
        conditions=selected_conditions,
        runs_per_profile=runs_per_profile,
        max_workers=max_workers,
        workflow_model=model,
        simulated_user_model=simulated_user_model,
        live_stages=live_stages,
        live_simulated_user=live_simulated_user,
        condition_counts=dict(Counter(session.condition for session in sessions)),
        expected_sessions=expected_sessions,
        grid_complete=len(sessions) == expected_sessions,
        artifact_count=len(artifacts),
        judge_input_count=len(judge_inputs),
        average_output_words=_mean([record["output_words"] for record in artifacts]),
        average_selected_context_items=_mean([record["selected_context_item_count"] for record in artifacts]),
        average_reused_context_items=_mean([record["reused_context_item_count"] for record in artifacts]),
        workflow_fidelity=workflow_report,
        output_dir=str(output_dir),
        errors=errors,
        warnings=warnings,
    )
    (output_dir / "experiment_report.json").write_text(report.model_dump_json(indent=2))
    if not report.valid:
        raise RuntimeError(f"Workflow experiment validation failed: {report.errors}")
    return report


def _simulate_jobs(
    jobs: list[tuple[int, Any, str]],
    seed: int,
    model: str,
    live_stages: LiveStageMode,
    simulated_user_model: str,
    live_simulated_user: bool,
    max_workers: int,
    total: int,
    output_dir: Path,
    traces_dir: Path,
) -> list[WorkflowSession]:
    job_order: dict[str, int] = {}
    for index, (run_index, profile, condition) in enumerate(jobs):
        session_seed = _stable_session_seed(seed, run_index, profile.simulation_profile_id, condition)
        session_id = _expected_session_id(profile.simulation_profile_id, condition, session_seed)
        job_order[session_id] = index
    expected_session_ids = set(job_order)

    sessions_path = output_dir / "sessions.jsonl"
    existing_sessions = _read_checkpointed_sessions(sessions_path, expected_session_ids)
    sessions_by_id = {session.session_id: session for session in existing_sessions}

    def run_job(job: tuple[int, Any, str]) -> WorkflowSession:
        run_index, profile, condition = job
        session_seed = _stable_session_seed(seed, run_index, profile.simulation_profile_id, condition)
        return simulate_workflow_session(
            profile,
            condition=condition,  # type: ignore[arg-type]
            seed=session_seed,
            rng=random.Random(session_seed),
            model=model,
            live_stages=live_stages,
            simulated_user_model=simulated_user_model,
            live_simulated_user=live_simulated_user,
        )

    pending_jobs = []
    for job in jobs:
        run_index, profile, condition = job
        session_seed = _stable_session_seed(seed, run_index, profile.simulation_profile_id, condition)
        session_id = _expected_session_id(profile.simulation_profile_id, condition, session_seed)
        if session_id not in sessions_by_id:
            pending_jobs.append(job)

    output_dir.mkdir(parents=True, exist_ok=True)
    if existing_sessions:
        _write_sessions(output_dir, traces_dir, _sort_sessions(existing_sessions, job_order))
    elif not sessions_path.exists():
        sessions_path.write_text("")

    def checkpoint_session(session: WorkflowSession) -> None:
        sessions_by_id[session.session_id] = session
        _append_session_checkpoint(output_dir, traces_dir, session)

    if max_workers == 1:
        for job in progress(pending_jobs, total=len(pending_jobs), desc="Simulating workflows", unit="session"):
            checkpoint_session(run_job(job))
        return _sort_sessions(list(sessions_by_id.values()), job_order)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {executor.submit(run_job, job): job for job in pending_jobs}
        for future in progress(
            as_completed(future_to_job),
            total=len(future_to_job),
            desc=f"Simulating workflows ({max_workers} workers)",
            unit="session",
        ):
            checkpoint_session(future.result())
    return _sort_sessions(list(sessions_by_id.values()), job_order)


def _write_run_config(
    output_dir: Path,
    experiment_id: str,
    profiles_path: Path,
    conditions: list[str],
    limit: int,
    runs_per_profile: int,
    seed: int,
    model: str,
    live_stages: LiveStageMode,
    simulated_user_model: str,
    live_simulated_user: bool,
    max_workers: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "profiles_path": str(profiles_path),
                "conditions": conditions,
                "limit": limit,
                "runs_per_profile": runs_per_profile,
                "seed": seed,
                "model": model,
                "workflow_model": model,
                "simulated_user_model": simulated_user_model,
                "live_stages": live_stages,
                "live_simulated_user": live_simulated_user,
                "max_workers": max_workers,
                "runner": "live_workflow_experiment" if live_stages != "deterministic" else "deterministic_workflow_experiment",
                "prompt_version": PROMPT_VERSION,
                "prompt_dir": str(PROMPT_DIR),
                "prompt_ids": prompt_ids(),
            },
            indent=2,
        )
    )


def _write_sessions(output_dir: Path, traces_dir: Path, sessions: list[WorkflowSession]) -> None:
    with (output_dir / "sessions.jsonl").open("w") as handle:
        for session in sessions:
            handle.write(session.model_dump_json() + "\n")
            condition_dir = traces_dir / session.condition
            condition_dir.mkdir(parents=True, exist_ok=True)
            (condition_dir / f"{session.session_id}.json").write_text(session.model_dump_json(indent=2))


def _append_session_checkpoint(output_dir: Path, traces_dir: Path, session: WorkflowSession) -> None:
    with (output_dir / "sessions.jsonl").open("a") as handle:
        handle.write(session.model_dump_json() + "\n")
        handle.flush()
    condition_dir = traces_dir / session.condition
    condition_dir.mkdir(parents=True, exist_ok=True)
    (condition_dir / f"{session.session_id}.json").write_text(session.model_dump_json(indent=2))


def _read_checkpointed_sessions(path: Path, expected_session_ids: set[str]) -> list[WorkflowSession]:
    if not path.exists():
        return []
    sessions_by_id: dict[str, WorkflowSession] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            session = WorkflowSession.model_validate_json(line)
        except ValueError:
            continue
        if session.session_id in expected_session_ids:
            sessions_by_id[session.session_id] = session
    return list(sessions_by_id.values())


def _sort_sessions(sessions: list[WorkflowSession], job_order: dict[str, int]) -> list[WorkflowSession]:
    return sorted(sessions, key=lambda session: job_order.get(session.session_id, 10**12))


def _build_experiment_records(
    sessions: list[WorkflowSession],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    artifacts: list[dict[str, Any]] = []
    judge_inputs: list[dict[str, Any]] = []
    condition_key: list[dict[str, Any]] = []
    mechanism_metrics: list[dict[str, Any]] = []
    for index, session in enumerate(sessions, start=1):
        blind_id = f"B{index:05d}"
        artifact_text = _final_artifact_text(session)
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
        context_bank = session.final_state.get("context_bank", {})
        selected_context = {context_id: context_bank.get(context_id) for context_id in selected_context_ids if context_id in context_bank}
        reused_context = {context_id: context_bank.get(context_id) for context_id in reused_context_ids if context_id in context_bank}
        artifact = {
            "artifact_id": f"A{index:05d}",
            "blind_id": blind_id,
            "session_id": session.session_id,
            "condition": session.condition,
            "simulation_profile_id": session.simulation_profile_id,
            "persona_id": session.persona_id,
            "goal_id": session.goal_id,
            "goal_text": session.goal_text,
            "seed": session.seed,
            "final_artifact": artifact_text,
            "output_words": len(_words(artifact_text)),
            "selected_context_ids": selected_context_ids,
            "reused_context_ids": reused_context_ids,
            "selected_context_item_count": len(selected_context_ids),
            "reused_context_item_count": len(reused_context_ids),
            "selected_context_token_count": _context_word_count(selected_context),
            "reused_context_token_count": _context_word_count(reused_context),
            "context_bank_size": len(context_bank),
            "event_count": len(session.events),
            "stage_counts": dict(Counter(event.stage for event in session.events)),
        }
        artifacts.append(artifact)
        judge_inputs.append(
            {
                "blind_id": blind_id,
                "goal_id": session.goal_id,
                "goal_text": session.goal_text,
                "user_context": _judge_context(context_bank),
                "system_output": artifact_text,
            }
        )
        condition_key.append(
            {
                "blind_id": blind_id,
                "session_id": session.session_id,
                "condition": session.condition,
                "simulation_profile_id": session.simulation_profile_id,
                "persona_id": session.persona_id,
                "goal_id": session.goal_id,
                "seed": session.seed,
            }
        )
        mechanism_metrics.append(_mechanism_record(session, selected_context_ids, reused_context_ids, context_bank))
    return artifacts, judge_inputs, condition_key, mechanism_metrics


def _mechanism_record(
    session: WorkflowSession,
    selected_context_ids: list[str],
    reused_context_ids: list[str],
    context_bank: dict[str, Any],
) -> dict[str, Any]:
    selection_events = [event for event in session.events if event.event_type == "context_selection"]
    relevant_selected = 0
    relevant_available = 0
    selected_total = 0
    selected_relevance_score = 0
    available_relevance_score = 0
    available_relevant_seen: set[tuple[str, str]] = set()
    final_artifact_text = _final_artifact_text(session)
    context_mentions = sum(
        1
        for context_id in reused_context_ids
        if _context_is_mentioned(final_artifact_text, context_bank.get(context_id, {}))
    )
    open_decisions_seen = 0
    open_decisions_rendered = 0
    for event in selection_events:
        selected = event.payload.get("selected_context_ids", [])
        available = event.payload.get("available_context_ids", [])
        selected_total += len(selected)
        task_text = f"{event.payload.get('task_name', '')} {event.payload.get('task_description', '')}"
        scored_available = [
            (context_id, _context_relevance_score(task_text, context_bank.get(context_id, {})))
            for context_id in available
        ]
        relevant_for_event = [
            context_id
            for context_id, score in scored_available
            if score > CONTEXT_RELEVANCE_THRESHOLD
        ]
        relevant_available += len(relevant_for_event)
        available_relevance_score += sum(score for _context_id, score in scored_available)
        for context_id in relevant_for_event:
            available_relevant_seen.add((str(event.node_id), context_id))
        relevant_selected += sum(1 for context_id in selected if context_id in relevant_for_event)
        selected_relevance_score += sum(
            _context_relevance_score(task_text, context_bank.get(context_id, {}))
            for context_id in selected
        )
    for event in session.events:
        if event.event_type != "subtask_draft":
            continue
        digest = event.payload.get("context_digest", {})
        draft_text = str(event.payload.get("draft", ""))
        if not isinstance(digest, dict):
            continue
        for decision in digest.get("open_decisions", []) or []:
            decision_text = str(decision)
            if not decision_text.strip():
                continue
            open_decisions_seen += 1
            if _text_is_mentioned(draft_text, decision_text):
                open_decisions_rendered += 1

    record = {
        "session_id": session.session_id,
        "condition": session.condition,
        "simulation_profile_id": session.simulation_profile_id,
        "goal_id": session.goal_id,
        "seed": session.seed,
        "context_selection_events": len(selection_events),
        "selected_context_items": len(selected_context_ids),
        "reused_context_items": len(reused_context_ids),
        "available_relevant_context_mentions": relevant_available,
        "unique_available_relevant_context_items": len({context_id for _, context_id in available_relevant_seen}),
        "context_precision_proxy": round(relevant_selected / selected_total, 4) if selected_total else None,
        "context_recall_proxy": round(relevant_selected / relevant_available, 4) if relevant_available else None,
        "selected_relevance_score": selected_relevance_score,
        "available_relevance_score": available_relevance_score,
        "selected_relevance_score_mean": round(selected_relevance_score / selected_total, 4) if selected_total else None,
        "reused_context_mention_rate": round(context_mentions / len(reused_context_ids), 4) if reused_context_ids else None,
        "open_decision_field_rate": round(open_decisions_rendered / open_decisions_seen, 4) if open_decisions_seen else None,
    }
    record.update(_trace_component_metrics(session, selected_context_ids, reused_context_ids, context_bank))
    return record


def _trace_component_metrics(
    session: WorkflowSession,
    selected_context_ids: list[str],
    reused_context_ids: list[str],
    context_bank: dict[str, Any],
) -> dict[str, Any]:
    event_counts = Counter(event.event_type for event in session.events)
    elicitation_events = [
        event
        for event in session.events
        if event.event_type in {"global_context_answer", "local_context_answer"}
    ]
    substantive_elicitation_events = [
        event
        for event in elicitation_events
        if event.payload.get("answer_status") != "unknown"
    ]
    context_reuse_events = [event for event in session.events if event.event_type == "context_reuse"]
    context_reuse_with_context_events = [
        event
        for event in context_reuse_events
        if event.payload.get("reused_context_ids")
    ]
    draft_context_reuse_events = [
        event
        for event in context_reuse_events
        if any(str(context_id).startswith("draft_") for context_id in event.payload.get("reused_context_ids", []))
    ]
    reused_draft_context_ids = [
        context_id
        for context_id in reused_context_ids
        if str(context_id).startswith("draft_")
    ]
    node_ids = [
        str(event.node_id)
        for event in session.events
        if event.node_id is not None
    ]
    completed_nodes = session.final_state.get("completed_nodes", [])
    node_drafts = session.final_state.get("node_drafts", {})
    context_bank_items = context_bank.values() if isinstance(context_bank, dict) else []
    draft_context_count = sum(
        1
        for context in context_bank_items
        if isinstance(context, dict) and context.get("scope") == "draft"
    )
    return {
        "global_context_answer_events": event_counts.get("global_context_answer", 0),
        "local_context_answer_events": event_counts.get("local_context_answer", 0),
        "elicited_context_items": len(elicitation_events),
        "substantive_elicited_context_items": len(substantive_elicitation_events),
        "unknown_context_answer_events": len(elicitation_events) - len(substantive_elicitation_events),
        "task_decomposition_events": event_counts.get("task_decomposition", 0),
        "nested_task_decomposition_events": event_counts.get("nested_task_decomposition", 0),
        "task_forking_decomposition_events": event_counts.get("task_forking_decomposition", 0),
        "hierarchical_decomposition_events": event_counts.get("nested_task_decomposition", 0)
        + event_counts.get("task_forking_decomposition", 0),
        "subtask_detection_events": event_counts.get("subtask_detection", 0),
        "subtask_decompose_further_decisions": sum(
            1
            for event in session.events
            if event.event_type == "subtask_detection_decision"
            and event.payload.get("chosen_next_step") == "decompose_further"
        ),
        "max_node_depth": max((str(node_id).count(".") + 1 for node_id in node_ids), default=0),
        "context_selection_events": len([event for event in session.events if event.event_type == "context_selection"]),
        "selected_context_items_trace": len(selected_context_ids),
        "reused_context_items_trace": len(reused_context_ids),
        "context_reuse_events": len(context_reuse_events),
        "context_reuse_with_context_events": len(context_reuse_with_context_events),
        "draft_context_reuse_events": len(draft_context_reuse_events),
        "reused_draft_context_items": len(reused_draft_context_ids),
        "saved_draft_context_events": event_counts.get("saved_draft_context", 0),
        "draft_context_count": draft_context_count,
        "node_draft_count": len(node_drafts) if isinstance(node_drafts, dict) else 0,
        "completed_node_count": len(completed_nodes) if isinstance(completed_nodes, list) else 0,
        "completed_node_ratio": (
            round(len(completed_nodes) / len(node_drafts), 4)
            if isinstance(completed_nodes, list) and isinstance(node_drafts, dict) and node_drafts
            else None
        ),
        "final_artifact_compilation_events": event_counts.get("final_artifact_compilation", 0),
    }


def _final_artifact_text(session: WorkflowSession) -> str:
    compiled_artifact = session.final_state.get("final_artifact")
    if isinstance(compiled_artifact, str) and compiled_artifact.strip():
        return compiled_artifact.strip()
    node_drafts = session.final_state.get("node_drafts", {})
    if not node_drafts:
        return ""
    return "\n\n".join(f"{node_id}: {draft}" for node_id, draft in node_drafts.items())


def _judge_context(context_bank: dict[str, Any]) -> str:
    if not context_bank:
        return ""
    lines = []
    for context_id, context in context_bank.items():
        if isinstance(context, dict) and not _is_substantive_context(context):
            continue
        label = str(context.get("label", context_id))
        value = str(context.get("value", ""))
        lines.append(f"{context_id} | {label}: {value}")
    return "\n".join(lines)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _stable_session_seed(seed: int, run_index: int, profile_id: str, condition: str) -> int:
    digest = hashlib.sha256(f"{seed}:{run_index}:{profile_id}:{condition}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _expected_session_id(profile_id: str, condition: str, seed: int) -> str:
    return f"{profile_id}_{condition}_seed{seed}"


def _unique_context_ids(groups: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for context_id in group or []:
            context_id = str(context_id)
            if context_id not in seen:
                seen.add(context_id)
                ordered.append(context_id)
    return ordered


def _context_word_count(contexts: dict[str, Any]) -> int:
    return sum(_context_token_count(context) for context in contexts.values() if isinstance(context, dict))


def _is_relevant_context(task_text: str, context: dict[str, Any]) -> bool:
    return _context_relevance_score(task_text, context) > CONTEXT_RELEVANCE_THRESHOLD


def _context_is_mentioned(text: str, context: Any) -> bool:
    if not isinstance(context, dict) or not _is_substantive_context(context):
        return False
    label = str(context.get("label", ""))
    value = str(context.get("value", ""))
    return _text_is_mentioned(text, f"{label} {value}")


def _text_is_mentioned(text: str, needle: str) -> bool:
    haystack_tokens = set(_key_tokens(text))
    needle_tokens = set(_key_tokens(needle))
    if not haystack_tokens or not needle_tokens:
        return False
    return len(haystack_tokens & needle_tokens) / max(1, min(len(haystack_tokens), len(needle_tokens))) >= 0.35


def _mean(values: list[int | float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _words(text: str) -> list[str]:
    return [token.strip(".,;:!?()[]{}\"'").lower() for token in text.split() if token.strip(".,;:!?()[]{}\"'")]


def _key_tokens(text: str) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "for",
        "in",
        "is",
        "of",
        "or",
        "the",
        "to",
        "use",
        "with",
    }
    return [word for word in _words(text) if len(word) > 2 and word not in stopwords]
