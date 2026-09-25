from __future__ import annotations

import json
import hashlib
import random
import re
from collections import Counter
from datetime import datetime
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Literal

from .openai_generation import (
    DEFAULT_USER_SIMULATOR_MODEL,
    generate_simulated_user_answer_live,
    parse_workflow_stage_live,
)
from .pipeline import DEFAULT_DATA_DIR
from .progress import progress
from .schemas import (
    SimulationProfile,
    WorkflowEvent,
    WorkflowFidelityReport,
    WorkflowLiveContextSelectionResponse,
    WorkflowLiveDraftResponse,
    WorkflowLiveQuestionResponse,
    WorkflowLiveSubtaskDetectionResponse,
    WorkflowLiveTaskDecompositionResponse,
    WorkflowLiveTaskForkingResponse,
    WorkflowSession,
)
from .workflow_prompts import PROMPT_DIR, PROMPT_VERSION, prompt_ids, render_prompt, validate_prompt_files


Condition = Literal[
    "full_jumpstarter",
    "all_context",
    "random_selection",
    "no_selection",
    "chatgpt_vanilla",
    "chatgpt_with_elicited_context",
    "chatgpt_with_structured_summary",
    "no_elicitation",
    "flat_decomposition",
    "no_reuse",
    "adapt_recursive_decomposition",
    "ask_before_plan",
    "unstructured_memory_rag",
    "long_context_planner",
    "single_turn_decomposition",
    "react_integrated_planner",
]
# Paper name and mechanism for every condition. The component ablations (all_context through
# no_reuse) modify the recursive workflow (full_jumpstarter); flat_decomposition is the only
# shallow JumpStarter condition and is the primary system in the paper.
CONDITION_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "flat_decomposition": (
        "JumpStarter-Shallow",
        "Primary system: one level of subtasks with global and local elicitation, task-local context selection, saved drafts, and cross-subtask reuse.",
    ),
    "full_jumpstarter": (
        "JumpStarter-Recursive",
        "The same workflow, but the simulated user may decompose subtasks further into a recursive task tree.",
    ),
    "all_context": ("All-context prompting", "Recursive workflow that passes every available context item to every subtask."),
    "random_selection": ("Random context selection", "Recursive workflow that selects a random subset of context for each subtask."),
    "no_selection": ("No context selection", "Recursive workflow that drafts subtasks without selected context."),
    "no_reuse": ("No context reuse", "Recursive workflow that saves drafts but blocks their reuse in later subtasks."),
    "no_elicitation": ("No elicitation", "Recursive workflow without proactive global or local context elicitation."),
    "chatgpt_vanilla": ("ChatGPT vanilla", "One-shot GPT-4o answer to the goal, without the workflow or elicited context."),
    "chatgpt_with_elicited_context": (
        "ChatGPT + elicited context",
        "One-shot GPT-4o answer given the same elicited global context as JumpStarter.",
    ),
    "chatgpt_with_structured_summary": (
        "ChatGPT + structured summary",
        "One-shot GPT-4o answer given a structured summary of the elicited context.",
    ),
    "single_turn_decomposition": (
        "Single-turn decomposition",
        "One GPT-4o turn with the same elicited context, prompted to decompose the goal and draft every subtask; no external task tree, selection, or reuse.",
    ),
    "adapt_recursive_decomposition": (
        "ADaPT-style recursive decomposition",
        "Recursive decompose-and-execute planner with a replanner (Prasad et al., 2024).",
    ),
    "ask_before_plan": ("Ask-before-plan", "Clarification loop with the simulated user before a single planning step (Zhang et al., 2024)."),
    "unstructured_memory_rag": ("Unstructured memory-RAG", "Planner that retrieves from an unstructured memory of context snippets."),
    "long_context_planner": ("Long-context planner", "Planner given all available context snippets in one long prompt, up to a cap."),
    "react_integrated_planner": (
        "Integrated agentic planner",
        "Global elicitation, retrieval over the user's materials, a simulated browse tool of generic guidance, and per-subtask top-k selection; no cross-subtask draft reuse.",
    ),
}
WORKFLOW_CONDITIONS: tuple[str, ...] = (
    "full_jumpstarter",
    "all_context",
    "random_selection",
    "no_selection",
    "chatgpt_vanilla",
    "chatgpt_with_elicited_context",
    "chatgpt_with_structured_summary",
    "no_elicitation",
    "flat_decomposition",
    "no_reuse",
    "adapt_recursive_decomposition",
    "ask_before_plan",
    "unstructured_memory_rag",
    "long_context_planner",
    "single_turn_decomposition",
    "react_integrated_planner",
)
PRIMARY_EXPERIMENT_CONDITIONS: tuple[str, ...] = (
    "full_jumpstarter",
    "all_context",
    "random_selection",
    "no_selection",
    "chatgpt_with_elicited_context",
    "chatgpt_with_structured_summary",
    "chatgpt_vanilla",
)
COMPONENT_ABLATION_CONDITIONS: tuple[str, ...] = (
    "full_jumpstarter",
    "all_context",
    "random_selection",
    "no_selection",
    "no_elicitation",
    "flat_decomposition",
    "no_reuse",
)
AGENT_BASELINE_CONDITIONS: tuple[str, ...] = (
    "full_jumpstarter",
    "adapt_recursive_decomposition",
    "ask_before_plan",
    "unstructured_memory_rag",
    "long_context_planner",
    "react_integrated_planner",
)
ALL_EXPERIMENT_CONDITIONS: tuple[str, ...] = tuple(
    dict.fromkeys([*PRIMARY_EXPERIMENT_CONDITIONS, *COMPONENT_ABLATION_CONDITIONS, *AGENT_BASELINE_CONDITIONS])
)
EXPERIMENT_CONDITION_PRESETS: dict[str, tuple[str, ...]] = {
    "primary": PRIMARY_EXPERIMENT_CONDITIONS,
    "component": COMPONENT_ABLATION_CONDITIONS,
    "component_ablation": COMPONENT_ABLATION_CONDITIONS,
    "ablations": COMPONENT_ABLATION_CONDITIONS,
    "agent": AGENT_BASELINE_CONDITIONS,
    "agent_baselines": AGENT_BASELINE_CONDITIONS,
    "planning_memory": AGENT_BASELINE_CONDITIONS,
    "planning_memory_agents": AGENT_BASELINE_CONDITIONS,
    "reviewer": (
        "full_jumpstarter",
        "flat_decomposition",
        "single_turn_decomposition",
        "chatgpt_with_elicited_context",
    ),
    "integrated_pilot": (
        "full_jumpstarter",
        "react_integrated_planner",
        "single_turn_decomposition",
    ),
    "all": ALL_EXPERIMENT_CONDITIONS,
}
DEFAULT_RUNS_DIR = Path(__file__).resolve().parent / "runs"
LiveStageMode = Literal["deterministic", "drafts", "planning", "all"]
WORKFLOW_LIVE_STAGE_MODES: tuple[str, ...] = ("deterministic", "drafts", "planning", "all")
CONTEXT_RELEVANCE_THRESHOLD = 0.3
DEFAULT_USER_DECISION_CALIBRATION_PATH = DEFAULT_DATA_DIR / "user_decision_calibration.json"


def run_workflow_pilot(
    profiles_path: Path = DEFAULT_DATA_DIR / "simulation_profiles.json",
    output_dir: Path | None = None,
    condition: Condition = "full_jumpstarter",
    limit: int = 10,
    seed: int = 42,
    model: str = "deterministic",
    live_stages: LiveStageMode = "deterministic",
    simulated_user_model: str = DEFAULT_USER_SIMULATOR_MODEL,
    live_simulated_user: bool = False,
    max_workers: int = 1,
) -> WorkflowFidelityReport:
    if condition not in WORKFLOW_CONDITIONS:
        raise ValueError(f"Unknown workflow condition: {condition}")
    if live_stages not in WORKFLOW_LIVE_STAGE_MODES:
        raise ValueError(f"Unknown workflow live stage mode: {live_stages}")
    if limit <= 0:
        raise ValueError("limit must be positive")
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")
    prompt_errors = validate_prompt_files()
    if prompt_errors:
        raise RuntimeError("Paper workflow prompt files are incomplete: " + "; ".join(prompt_errors))

    profiles = read_simulation_profiles(profiles_path)[:limit]
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = DEFAULT_RUNS_DIR / f"workflow_pilot_{condition}_{timestamp}"
    traces_dir = output_dir / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    sessions = [
        simulate_workflow_session(
            profile,
            condition=condition,
            seed=seed,
            rng=rng,
            model=model,
            live_stages=live_stages,
            simulated_user_model=simulated_user_model,
            live_simulated_user=live_simulated_user,
        )
        for profile in progress(profiles, total=len(profiles), desc="Simulating workflow pilot", unit="session")
    ]

    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "profiles_path": str(profiles_path),
                "condition": condition,
                "limit": limit,
                "seed": seed,
                "model": model,
                "workflow_model": model,
                "simulated_user_model": simulated_user_model,
                "live_stages": live_stages,
                "live_simulated_user": live_simulated_user,
                "max_workers": max_workers,
                "runner": "live_workflow_pilot" if live_stages != "deterministic" else "deterministic_workflow_pilot",
                "prompt_version": PROMPT_VERSION,
                "prompt_dir": str(PROMPT_DIR),
                "prompt_ids": prompt_ids(),
                "workflow_stages": [
                    "goal_entry",
                    "global_context_elicitation",
                    "task_decomposition",
                    "subtask_detection",
                    "task_forking_detection",
                    "context_selection",
                    "context_reuse",
                    "local_context_elicitation",
                    "draft_refinement",
                    "final_review",
                ],
            },
            indent=2,
        )
    )
    with (output_dir / "sessions.jsonl").open("w") as handle:
        for session in sessions:
            handle.write(session.model_dump_json() + "\n")
            (traces_dir / f"{session.session_id}.json").write_text(session.model_dump_json(indent=2))

    report = workflow_fidelity_report(sessions)
    (output_dir / "workflow_fidelity_report.json").write_text(report.model_dump_json(indent=2))
    if not report.valid:
        raise RuntimeError(f"Workflow pilot validation failed: {report.errors}")
    return report


def read_simulation_profiles(path: Path) -> list[SimulationProfile]:
    return [SimulationProfile.model_validate(item) for item in json.loads(path.read_text())]


def simulate_workflow_session(
    profile: SimulationProfile,
    condition: Condition,
    seed: int = 42,
    rng: random.Random | None = None,
    model: str = "deterministic",
    live_stages: LiveStageMode = "deterministic",
    simulated_user_model: str = DEFAULT_USER_SIMULATOR_MODEL,
    live_simulated_user: bool = False,
    user_decision_calibration: dict[str, Any] | None = None,
) -> WorkflowSession:
    if live_stages not in WORKFLOW_LIVE_STAGE_MODES:
        raise ValueError(f"Unknown workflow live stage mode: {live_stages}")
    rng = rng or random.Random(seed)
    if user_decision_calibration is None:
        user_decision_calibration = _load_user_decision_calibration()
    events: list[WorkflowEvent] = []
    context_bank: dict[str, dict[str, Any]] = {}
    node_selected_contexts: dict[str, list[str]] = {}
    node_drafts: dict[str, str] = {}
    subtask_detection_decisions: dict[str, dict[str, Any]] = {}
    nested_task_nodes: dict[str, list[dict[str, str]]] = {}
    task_forking_decisions: dict[str, dict[str, Any]] = {}
    completed_nodes: list[str] = []
    final_artifact: str | None = None

    def add(
        event_type: str,
        actor: Literal["user", "system", "simulator", "evaluator"],
        stage: str,
        payload: dict[str, Any],
        node_id: str | None = None,
    ) -> None:
        events.append(
            WorkflowEvent(
                event_id=len(events) + 1,
                event_type=event_type,
                actor=actor,
                stage=stage,
                node_id=node_id,
                payload=payload,
            )
        )

    add(
        "goal_input",
        "user",
        "goal_entry",
        {
            "goal_text": profile.goal_text,
            "source": "benchmark",
            "persona_traits": profile.stable_persona_traits.model_dump(),
        },
    )

    if condition == "chatgpt_vanilla":
        return _simulate_chatgpt_baseline(profile, condition, seed, events, context_bank, add, model, live_stages)

    if condition.startswith("chatgpt_with_"):
        _collect_global_context(
            profile,
            context_bank,
            add,
            model,
            live_stages,
            simulated_user_model,
            live_simulated_user,
        )
        return _simulate_chatgpt_baseline(profile, condition, seed, events, context_bank, add, model, live_stages)

    if condition == "single_turn_decomposition":
        _collect_global_context(
            profile,
            context_bank,
            add,
            model,
            live_stages,
            simulated_user_model,
            live_simulated_user,
        )
        return _simulate_single_turn_decomposition_baseline(
            profile, condition, seed, events, context_bank, add, model, live_stages
        )

    if condition in {
        "adapt_recursive_decomposition",
        "ask_before_plan",
        "unstructured_memory_rag",
        "long_context_planner",
        "react_integrated_planner",
    }:
        return _simulate_agent_baseline(
            profile,
            condition,
            seed,
            rng,
            events,
            context_bank,
            add,
            model,
            live_stages,
            simulated_user_model,
            live_simulated_user,
        )

    if condition != "no_elicitation":
        _collect_global_context(
            profile,
            context_bank,
            add,
            model,
            live_stages,
            simulated_user_model,
            live_simulated_user,
        )

    task_prompt = render_prompt(
        "subtask_generation",
        main_purpose=profile.goal_text,
        user_context=_context_bank_json(context_bank),
        current_task=profile.goal_text,
        existing_tree_structure="[]",
        current_subtask_title=profile.goal_text,
    )
    task_nodes = _task_nodes(profile)
    generation_mode = "deterministic"
    if _live_enabled(live_stages, "task_decomposition"):
        task_nodes = _live_task_nodes(profile, task_prompt, model, fallback_nodes=task_nodes)
        generation_mode = "live"
    add(
        "task_decomposition",
        "system",
        "task_decomposition",
        {
            "root_goal": profile.goal_text,
            "nodes": task_nodes,
            "representation": "flat_task_list" if condition == "flat_decomposition" else "subtask_tree",
            "generation_mode": generation_mode,
            "prompt": task_prompt,
        },
    )
    add(
        "task_tree_review",
        "user",
        "task_decomposition",
        _calibrated_task_tree_review(task_nodes, user_decision_calibration, rng),
    )

    for node in task_nodes:
        work_node = node
        suggestion = _subtask_detection_suggestion(profile, node)
        if condition == "flat_decomposition":
            suggestion = {
                "suggested_action": "draft_answer",
                "rationale": "Flat-decomposition baseline drafts only top-level tasks without nested decomposition.",
            }
        subtask_prompt = render_prompt(
            "subtask_detection",
            task_title=node["title"],
            task_descriptions=node["description"],
            tree_level=str(_node_level(node)),
        )
        generation_mode = "deterministic"
        if _live_enabled(live_stages, "subtask_detection") and condition != "flat_decomposition":
            suggestion = _live_subtask_detection(profile, node, subtask_prompt, model, fallback=suggestion)
            generation_mode = "live"
        add(
            "subtask_detection",
            "system",
            "subtask_detection",
            {
                "available_actions": ["draft_answer", "decompose_further"],
                "suggested_action": suggestion["suggested_action"],
                "rationale": suggestion["rationale"],
                "generation_mode": generation_mode,
                "prompt": subtask_prompt,
            },
            node_id=node["node_id"],
        )
        decision = _calibrated_subtask_detection_decision(profile, node, suggestion, condition, user_decision_calibration, rng)
        subtask_detection_decisions[node["node_id"]] = decision
        add("subtask_detection_decision", "user", "subtask_detection", decision, node_id=node["node_id"])
        if decision["chosen_next_step"] == "decompose_further":
            forking = _task_forking_suggestion(profile, node, context_bank)
            forking_prompt = render_prompt("task_forking", task_description=node["description"])
            forking_generation_mode = "deterministic"
            if _live_enabled(live_stages, "task_forking"):
                forking = _live_task_forking(profile, node, context_bank, forking_prompt, model, fallback=forking)
                forking_generation_mode = "live"
            task_forking_decisions[node["node_id"]] = forking
            add(
                "task_forking_detection",
                "system",
                "task_forking_detection",
                {
                    **forking,
                    "generation_mode": forking_generation_mode,
                    "prompt": forking_prompt,
                },
                node_id=node["node_id"],
            )
            if forking["answer"] == "Yes":
                selected_fork_context = forking.get("entity_source_context_id") or _select_fork_context_id(context_bank, node)
                fork_selection_prompt = render_prompt(
                    "task_forking_context_selection",
                    main_purpose=profile.goal_text,
                    task_name=node["title"],
                    task_description=node["description"],
                    context_history=_context_bank_json(context_bank),
                )
                fork_selection_mode = "deterministic"
                if _live_enabled(live_stages, "task_forking_context_selection"):
                    selected_fork_context = _live_select_fork_context(
                        profile,
                        node,
                        context_bank,
                        fork_selection_prompt,
                        model,
                        fallback_context_id=selected_fork_context,
                    )
                    fork_selection_mode = "live"
                add(
                    "task_forking_context_selection",
                    "system",
                    "task_forking_detection",
                    {
                        "selected_context_id": selected_fork_context,
                        "available_context_ids": list(context_bank),
                        "generation_mode": fork_selection_mode,
                        "prompt": fork_selection_prompt,
                    },
                    node_id=node["node_id"],
                )
                if _fork_entities_from_context(context_bank.get(str(selected_fork_context), {})):
                    children = _forked_task_nodes(node, context_bank.get(str(selected_fork_context), {}))
                    decomposition_event_type = "task_forking_decomposition"
                    decomposition_payload = {
                        "parent_node_id": node["node_id"],
                        "decomposition_type": "task_forking",
                        "fork_context_id": selected_fork_context,
                        "children": children,
                        "generation_mode": forking_generation_mode,
                        "prompt": forking_prompt,
                    }
                else:
                    children = _nested_task_nodes(node)
                    decomposition_event_type = "nested_task_decomposition"
                    nested_prompt = render_prompt(
                        "subtask_generation",
                        main_purpose=profile.goal_text,
                        user_context=_context_bank_json(context_bank),
                        current_task=f"{node['title']}: {node['description']}",
                        existing_tree_structure=_task_tree_summary(task_nodes),
                        current_subtask_title=node["title"],
                    )
                    nested_generation_mode = "deterministic"
                    if _live_enabled(live_stages, "task_decomposition"):
                        children = _live_task_nodes(
                            profile,
                            nested_prompt,
                            model,
                            fallback_nodes=children,
                            parent_node_id=node["node_id"],
                        )
                        nested_generation_mode = "live"
                    decomposition_payload = {
                        "parent_node_id": node["node_id"],
                        "decomposition_type": "break_down",
                        "children": children,
                        "generation_mode": nested_generation_mode,
                        "prompt": nested_prompt,
                    }
            else:
                children = _nested_task_nodes(node)
                decomposition_event_type = "nested_task_decomposition"
                nested_prompt = render_prompt(
                    "subtask_generation",
                    main_purpose=profile.goal_text,
                    user_context=_context_bank_json(context_bank),
                    current_task=f"{node['title']}: {node['description']}",
                    existing_tree_structure=_task_tree_summary(task_nodes),
                    current_subtask_title=node["title"],
                )
                nested_generation_mode = "deterministic"
                if _live_enabled(live_stages, "task_decomposition"):
                    children = _live_task_nodes(profile, nested_prompt, model, fallback_nodes=children, parent_node_id=node["node_id"])
                    nested_generation_mode = "live"
                decomposition_payload = {
                    "parent_node_id": node["node_id"],
                    "decomposition_type": "break_down",
                    "children": children,
                    "generation_mode": nested_generation_mode,
                    "prompt": nested_prompt,
                }

            nested_task_nodes[node["node_id"]] = children
            add(decomposition_event_type, "system", "task_decomposition", decomposition_payload, node_id=node["node_id"])
            nested_review = _calibrated_nested_task_review(children, user_decision_calibration, rng)
            add(
                "nested_task_review",
                "user",
                "task_decomposition",
                nested_review,
                node_id=node["node_id"],
            )
            work_node = _child_node_by_id(children, nested_review.get("selected_child_node_id")) or children[-1]

        available_ids = list(context_bank)
        selected_ids = _select_context_ids(condition, context_bank, work_node, rng)
        selection_reason = _selection_reason(condition, selected_ids)
        selection_prompt = render_prompt(
            "context_selection_draft",
            main_purpose=profile.goal_text,
            task_name=work_node["title"],
            task_description=work_node["description"],
            context_history=_context_bank_json(context_bank),
        )
        selection_generation_mode = "deterministic"
        if _live_context_selection_allowed(live_stages, condition):
            selection = _live_context_selection(
                profile,
                condition,
                context_bank,
                work_node,
                selection_prompt,
                model,
                fallback_ids=selected_ids,
                fallback_reason=selection_reason,
            )
            selected_ids = selection["selected_context_ids"]
            selection_reason = selection["selection_reason"]
            selection_generation_mode = "live"
        node_selected_contexts[work_node["node_id"]] = selected_ids
        add(
            "context_selection",
            "user",
            "context_selection",
            {
                "available_context_ids": available_ids,
                "selected_context_ids": selected_ids,
                "policy": condition,
                "task_name": work_node["title"],
                "task_description": work_node["description"],
                "selection_reason": selection_reason,
                "generation_mode": selection_generation_mode,
                "prompt": selection_prompt,
            },
            node_id=work_node["node_id"],
        )

        selected_reusable_ids = [
            context_id
            for context_id in selected_ids
            if _is_substantive_context(context_bank.get(context_id, {}))
        ]
        excluded_context_ids = [context_id for context_id in selected_ids if context_id not in selected_reusable_ids]
        reused_contexts = {}
        if condition != "no_reuse":
            reused_contexts = {context_id: context_bank[context_id] for context_id in selected_reusable_ids}
        context_digest = _context_digest_for_node(profile, work_node, reused_contexts, context_bank)
        draft_prompt = render_prompt(
            "working_solution_draft_creation",
            main_purpose=profile.goal_text,
            user_context=json.dumps(context_digest, ensure_ascii=True, sort_keys=True),
            current_task=work_node["title"],
            task_description=work_node["description"],
        )
        add(
            "context_reuse",
            "system",
            "context_reuse",
            {
                "reused_context_ids": list(reused_contexts),
                "selected_but_not_reused_context_ids": selected_ids if condition == "no_reuse" else excluded_context_ids,
                "excluded_non_substantive_context_ids": excluded_context_ids,
                "reused_contexts": reused_contexts,
                "context_digest": context_digest,
                "draft_target": work_node["title"],
                "generation_mode": "live" if _live_enabled(live_stages, "working_solution_draft_creation") else "deterministic",
                "prompt": draft_prompt,
            },
            node_id=work_node["node_id"],
        )

        draft = _draft_for_node(profile, work_node, reused_contexts, context_digest=context_digest)
        draft_generation_mode = "deterministic"
        if _live_enabled(live_stages, "working_solution_draft_creation"):
            draft = _live_draft(
                profile,
                work_node,
                reused_contexts,
                draft_prompt,
                model,
                fallback_draft=draft,
                context_digest=context_digest,
            )
            draft_generation_mode = "live"
        add(
            "subtask_draft",
            "system",
            "context_reuse",
            {
                "draft": draft,
                "selected_context_ids": selected_ids,
                "reused_context_ids": list(reused_contexts),
                "context_digest": context_digest,
                "generation_mode": draft_generation_mode,
            },
            node_id=work_node["node_id"],
        )

        if condition not in {"chatgpt_vanilla", "no_elicitation"}:
            local_need = _local_need_for_node(profile, work_node)
            local_question = f"Any extra detail to refine {work_node['title']}?"
            local_prompt = render_prompt(
                "local_context_elicitation",
                main_purpose=profile.goal_text,
                task_name=work_node["title"],
                task_description=work_node["description"],
                context_history=_context_bank_json(context_bank),
            )
            local_generation_mode = "deterministic"
            if _live_enabled(live_stages, "local_context_elicitation"):
                live_question = _live_question(
                    profile,
                    local_prompt,
                    model,
                    fallback_question=local_question,
                    fallback_key=local_need,
                    question_type="local_context_elicitation",
                )
                local_question = live_question["question"]
                local_need = live_question["requested_context_key"]
                local_generation_mode = "live"
            add(
                "local_context_elicitation",
                "system",
                "local_context_elicitation",
                {
                    "question": local_question,
                    "requested_context_key": local_need,
                    "generation_mode": local_generation_mode,
                    "prompt": local_prompt,
                },
                node_id=work_node["node_id"],
            )
            local_answer = _simulated_user_answer_for_need(
                profile,
                local_need,
                local_question,
                model=simulated_user_model,
                live=live_simulated_user,
                conversation_state={
                    "stage": "local_context_elicitation",
                    "condition": condition,
                    "node": work_node,
                    "known_context": context_bank,
                },
            )
            local_context_id = f"local_{work_node['node_id']}"
            context_bank[local_context_id] = {
                "scope": "local",
                "label": local_need,
                "value": local_answer,
                "node_id": work_node["node_id"],
            }
            add(
                "local_context_answer",
                "user",
                "local_context_elicitation",
                {
                    "context_id": local_context_id,
                    "question": local_question,
                    "answer": local_answer,
                    "answer_status": _answer_status(local_answer),
                    "generation_mode": "live" if live_simulated_user else "deterministic",
                    "simulated_user_model": simulated_user_model if live_simulated_user else "deterministic",
                },
                node_id=work_node["node_id"],
            )
            add(
                "saved_local_context",
                "system",
                "local_context_elicitation",
                {"context_id": local_context_id, "scope": "local", "attached_node_id": work_node["node_id"]},
                node_id=work_node["node_id"],
            )
            if condition != "no_reuse":
                draft = _refined_draft_for_node(draft, local_answer)
                add(
                    "draft_refinement",
                    "system",
                    "draft_refinement",
                    {"draft": draft, "reused_context_id": local_context_id},
                    node_id=work_node["node_id"],
                )
            else:
                add(
                    "draft_refinement",
                    "system",
                    "draft_refinement",
                    {"draft": draft, "reused_context_id": None, "reason": "no_reuse baseline saves but does not reuse local context"},
                    node_id=work_node["node_id"],
                )

        node_drafts[work_node["node_id"]] = draft
        draft_context_id = f"draft_{work_node['node_id']}"
        context_bank[draft_context_id] = {
            "scope": "draft",
            "label": f"Draft for {work_node['title']}",
            "value": draft,
            "node_id": work_node["node_id"],
            "source_context_ids": list(reused_contexts),
        }
        add(
            "saved_draft_context",
            "system",
            "draft_refinement",
            {
                "context_id": draft_context_id,
                "scope": "draft",
                "attached_node_id": work_node["node_id"],
                "source_context_ids": list(reused_contexts),
            },
            node_id=work_node["node_id"],
        )
        review = _calibrated_draft_review(
            profile,
            draft,
            used_selected_context=bool(selected_ids) and condition != "no_reuse",
            calibration=user_decision_calibration,
            rng=rng,
        )
        add("draft_review", "user", "draft_refinement", review, node_id=work_node["node_id"])
        if review["action"] == "accept":
            completed_nodes.append(work_node["node_id"])

    if condition == "full_jumpstarter":
        compiled = _compile_full_jumpstarter_final_artifact(
            profile,
            context_bank,
            node_drafts,
            node_selected_contexts,
            completed_nodes,
            model,
            live_stages,
        )
        final_artifact = compiled["final_artifact"]
        add(
            "final_artifact_compilation",
            "system",
            "final_synthesis",
            compiled,
        )

    final_review = _calibrated_final_artifact_review(completed_nodes, node_drafts, user_decision_calibration, rng)
    add(
        "final_artifact_review",
        "user",
        "final_review",
        final_review,
    )

    return _build_session(
        profile,
        condition,
        seed,
        events,
        context_bank,
        node_selected_contexts,
        node_drafts,
        completed_nodes,
        subtask_detection_decisions,
        nested_task_nodes,
        task_forking_decisions,
        final_artifact=final_artifact,
    )


def _simulate_agent_baseline(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    rng: random.Random,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
    simulated_user_model: str,
    live_simulated_user: bool,
) -> WorkflowSession:
    if condition == "adapt_recursive_decomposition":
        return _simulate_adapt_recursive_decomposition(
            profile,
            condition,
            seed,
            rng,
            events,
            context_bank,
            add,
            model,
            live_stages,
            simulated_user_model,
            live_simulated_user,
        )
    if condition == "ask_before_plan":
        return _simulate_ask_before_plan(
            profile,
            condition,
            seed,
            events,
            context_bank,
            add,
            model,
            live_stages,
            simulated_user_model,
            live_simulated_user,
        )
    if condition == "unstructured_memory_rag":
        return _simulate_unstructured_memory_rag(
            profile,
            condition,
            seed,
            events,
            context_bank,
            add,
            model,
            live_stages,
        )
    if condition == "long_context_planner":
        return _simulate_long_context_planner(
            profile,
            condition,
            seed,
            events,
            context_bank,
            add,
            model,
            live_stages,
        )
    if condition == "react_integrated_planner":
        return _simulate_react_integrated_planner(
            profile,
            condition,
            seed,
            rng,
            events,
            context_bank,
            add,
            model,
            live_stages,
            simulated_user_model,
            live_simulated_user,
        )
    raise ValueError(f"Unknown agent baseline condition: {condition}")


def _simulate_adapt_recursive_decomposition(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    rng: random.Random,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
    simulated_user_model: str,
    live_simulated_user: bool,
) -> WorkflowSession:
    context_bank.update(_profile_memory_context_bank(profile))
    root_node = {
        "node_id": "ADAPT",
        "title": profile.goal_text,
        "description": profile.goal_text,
    }
    add(
        "adapt_environment_observation",
        "system",
        "environment_observation",
        {
            "available_context_ids": list(context_bank),
            "observation_policy": "Initial task/environment state is available to the executor; no proactive user clarification is used.",
            "repo_grounding": "archiki/ADaPT plan_and_run executes a task first, decomposes only after executor failure, and propagates salient information.",
        },
    )
    add(
        "task_decomposition",
        "system",
        "task_decomposition",
        {
            "root_goal": profile.goal_text,
            "nodes": [root_node],
            "representation": "adapt_initial_plan",
            "generation_mode": "deterministic",
            "baseline_policy": "ADaPT first asks the planner for Step n entries plus an execution order, then recursively executes each step.",
            "max_depth": 3,
            "execution_order_format": "nested AND/OR over Step n entries",
        },
    )
    node_selected_contexts: dict[str, list[str]] = {}
    node_drafts: dict[str, str] = {}
    completed_nodes: list[str] = []
    subtask_detection_decisions: dict[str, dict[str, Any]] = {}
    nested_task_nodes: dict[str, list[dict[str, str]]] = {}
    task_forking_decisions: dict[str, dict[str, Any]] = {}

    adapt_state = {
        "node_selected_contexts": node_selected_contexts,
        "node_drafts": node_drafts,
        "completed_nodes": completed_nodes,
        "subtask_detection_decisions": subtask_detection_decisions,
        "nested_task_nodes": nested_task_nodes,
        "action_checkpoint": [],
        "plan_trace": [],
    }

    initial_plan = _adapt_planner_steps(profile, root_node, depth=1, info_prop={})
    nested_task_nodes[root_node["node_id"]] = initial_plan["steps"]
    add(
        "adapt_initial_planner",
        "system",
        "task_decomposition",
        {
            "parent_node_id": root_node["node_id"],
            "children": initial_plan["steps"],
            "logic": initial_plan["logic"],
            "execution_order": initial_plan["execution_order"],
            "step_lines": initial_plan["step_lines"],
            "generation_mode": "deterministic",
            "repo_grounding": "ADaPT pipeline_run_episodes calls plan_llm/plan_to_args before entering plan_and_run.",
        },
        node_id=root_node["node_id"],
    )
    adapt_state["plan_trace"].append(
        f"{[child['title'] for child in initial_plan['steps']]} at depth 1 and logic {initial_plan['logic']}"
    )
    for child in initial_plan["steps"]:
        child_success = _adapt_plan_and_run(
            profile=profile,
            condition=condition,
            task=child,
            depth=1,
            logic=initial_plan["logic"],
            context_bank=context_bank,
            info_prop={},
            add=add,
            model=model,
            live_stages=live_stages,
            state=adapt_state,
            max_depth=3,
        )
        if initial_plan["logic"].lower() == "or" and child_success:
            add(
                "adapt_logic_short_circuit",
                "system",
                "task_decomposition",
                {"logic": "OR", "stopped_after_successful_child": child["node_id"], "scope": "initial_plan"},
                node_id=root_node["node_id"],
            )
            break
        if initial_plan["logic"].lower() == "and" and not child_success:
            add(
                "adapt_logic_short_circuit",
                "system",
                "task_decomposition",
                {"logic": "AND", "stopped_after_failed_child": child["node_id"], "scope": "initial_plan"},
                node_id=root_node["node_id"],
            )
            break

    final_artifact = _compile_agent_baseline_artifact(profile, condition, context_bank, node_drafts, node_selected_contexts)
    add(
        "final_artifact_compilation",
        "system",
        "final_synthesis",
        {
            "final_artifact": final_artifact,
            "generation_mode": "deterministic",
            "baseline_policy": "ADaPT initial planning plus executor-first recursive replanning with propagated salient failure/status information.",
            "action_checkpoint": adapt_state["action_checkpoint"],
            "plan_trace": adapt_state["plan_trace"],
        },
    )
    add(
        "final_artifact_review",
        "user",
        "final_review",
        _calibrated_final_artifact_review(completed_nodes, node_drafts, _load_user_decision_calibration(), rng),
    )
    return _build_session(
        profile,
        condition,
        seed,
        events,
        context_bank,
        node_selected_contexts,
        node_drafts,
        completed_nodes,
        subtask_detection_decisions,
        nested_task_nodes,
        task_forking_decisions,
        final_artifact=final_artifact,
    )


def _simulate_ask_before_plan(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
    simulated_user_model: str,
    live_simulated_user: bool,
) -> WorkflowSession:
    conversation: list[dict[str, str]] = [{"role": "user", "content": profile.goal_text}]
    trajectories: dict[str, str] = {}
    ask_results: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    max_clarification_rounds = 3

    for round_index in range(1, max_clarification_rounds + 1):
        tool_run = _abp_tool_agent_run(profile, context_bank, conversation, round_index)
        trajectories = tool_run["trajectories"]
        tool_results.append(tool_run)
        add(
            "abp_tool_agent_run",
            "system",
            "environment_execution",
            {
                "round": round_index,
                "conversation": conversation,
                "tool_calls": tool_run["tool_calls"],
                "trajectories": trajectories,
                "missing_or_unavailable": tool_run["missing_or_unavailable"],
                "baseline_policy": "Ask-before-Plan CEP execution agent gathers environment/tool trajectories before clarification and planning.",
            },
        )

        question_need = _abp_clarification_need(profile, context_bank, tool_run["missing_or_unavailable"])
        needs_clarification = question_need is not None
        add(
            "abp_clarification_decision",
            "system",
            "global_context_elicitation",
            {
                "round": round_index,
                "needs_clarification": needs_clarification,
                "requested_context_key": question_need,
                "conversation": conversation,
                "trajectory_keys": list(trajectories),
                "baseline_policy": "AskAgent first answers whether clarification is needed from conversation plus trajectory, then asks one question.",
            },
        )
        if not needs_clarification:
            ask_results.append({"round": round_index, "question": None, "answer": None})
            break

        need = str(question_need)
        question = _question_for_context_need(profile.goal_text, need)
        add(
            "clarification_question",
            "system",
            "global_context_elicitation",
            {
                "round": round_index,
                "question": question,
                "requested_context_key": need,
                "generation_mode": "deterministic",
                "baseline_policy": "Ask-before-Plan asks exactly one clarification question for the missing or infeasible detail detected from tool trajectories.",
            },
        )
        answer = _simulated_user_answer_for_need(
            profile,
            need,
            question,
            model=simulated_user_model,
            live=live_simulated_user,
            conversation_state={
                "stage": "ask_before_plan_clarification",
                "condition": condition,
                "known_context": context_bank,
            },
        )
        context_id = f"clarification_{round_index}"
        context_bank[context_id] = {"scope": "clarification", "label": need, "value": answer}
        conversation.append({"role": "assistant", "content": question})
        conversation.append({"role": "user", "content": answer})
        ask_results.append({"round": round_index, "question": question, "answer": answer, "context_id": context_id})
        add(
            "global_context_answer",
            "user",
            "global_context_elicitation",
            {
                "context_id": context_id,
                "question": question,
                "answer": answer,
                "answer_status": _answer_status(answer),
                "generation_mode": "live" if live_simulated_user else "deterministic",
                "simulated_user_model": simulated_user_model if live_simulated_user else "deterministic",
            },
        )

    plan_node = {"node_id": "ABP", "title": "Clarification-First Plan", "description": f"Produce a plan for {profile.goal_text} after asking clarifying questions."}
    _add_one_shot_agent_structure(profile, condition, add, [plan_node], "ask_before_plan_clarification_first")
    selected_ids = [context_id for context_id, context in context_bank.items() if _is_substantive_context(context)]
    add(
        "abp_planning_agent_run",
        "system",
        "planning_agent",
        {
            "conversation": conversation,
            "trajectory_keys": list(trajectories),
            "ask_results": ask_results,
            "tool_results": tool_results,
            "baseline_policy": "Planner receives the final user-assistant conversation and the latest execution trajectory.",
        },
        node_id=plan_node["node_id"],
    )
    node_drafts, node_selected_contexts = _draft_one_shot_agent_plan(
        profile,
        condition,
        plan_node,
        context_bank,
        selected_ids,
        add,
        model,
        live_stages,
    )
    final_artifact = _compile_agent_baseline_artifact(profile, condition, context_bank, node_drafts, node_selected_contexts)
    add(
        "final_artifact_review",
        "user",
        "final_review",
        {"action": "approve", "completed_nodes": list(node_drafts), "completion_ratio": 1.0, "approval_status": "approved"},
    )
    return _build_session(profile, condition, seed, events, context_bank, node_selected_contexts, node_drafts, list(node_drafts), {}, {}, {}, final_artifact=final_artifact)


def _simulate_unstructured_memory_rag(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
) -> WorkflowSession:
    context_bank.update(_profile_memory_context_bank(profile))
    add(
        "memory_index_build",
        "system",
        "memory_retrieval",
        {
            "memory_item_count": len(context_bank),
            "memory_scope": "unstructured_profile_and_prior_context_snippets",
            "baseline_policy": "Retrieve top generic memory snippets for the whole planning request.",
        },
    )
    plan_node = {"node_id": "RAG", "title": "Memory-RAG Plan", "description": f"Retrieve generic memories and plan {profile.goal_text}."}
    _add_one_shot_agent_structure(profile, condition, add, [plan_node], "unstructured_memory_rag")
    selected_ids = _ranked_relevant_context_ids(context_bank, plan_node, max_selected=5) or _first_n_substantive_context_ids(context_bank, 5)
    add(
        "memory_retrieval",
        "system",
        "memory_retrieval",
        {
            "query": profile.goal_text,
            "retrieved_context_ids": selected_ids,
            "available_context_ids": list(context_bank),
            "ranking_policy": "lexical_semantic_overlap_top_k",
        },
    )
    node_drafts, node_selected_contexts = _draft_one_shot_agent_plan(
        profile,
        condition,
        plan_node,
        context_bank,
        selected_ids,
        add,
        model,
        live_stages,
    )
    final_artifact = _compile_agent_baseline_artifact(profile, condition, context_bank, node_drafts, node_selected_contexts)
    add(
        "final_artifact_review",
        "user",
        "final_review",
        {"action": "approve", "completed_nodes": list(node_drafts), "completion_ratio": 1.0, "approval_status": "approved"},
    )
    return _build_session(profile, condition, seed, events, context_bank, node_selected_contexts, node_drafts, list(node_drafts), {}, {}, {}, final_artifact=final_artifact)


def _simulate_long_context_planner(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
) -> WorkflowSession:
    context_bank.update(_profile_memory_context_bank(profile))
    selected_ids = _token_capped_context_ids(context_bank, max_tokens=260)
    add(
        "long_context_assembly",
        "system",
        "long_context_assembly",
        {
            "available_context_ids": list(context_bank),
            "included_context_ids": selected_ids,
            "included_context_token_count": _context_token_count_for_ids(context_bank, selected_ids),
            "max_context_tokens": 260,
            "baseline_policy": "Place all available profile/context snippets into a single capped planning prompt.",
        },
    )
    plan_node = {"node_id": "LCP", "title": "Long-Context Plan", "description": f"Plan {profile.goal_text} using a single long-context prompt."}
    _add_one_shot_agent_structure(profile, condition, add, [plan_node], "long_context_planner")
    node_drafts, node_selected_contexts = _draft_one_shot_agent_plan(
        profile,
        condition,
        plan_node,
        context_bank,
        selected_ids,
        add,
        model,
        live_stages,
    )
    final_artifact = _compile_agent_baseline_artifact(profile, condition, context_bank, node_drafts, node_selected_contexts)
    add(
        "final_artifact_review",
        "user",
        "final_review",
        {"action": "approve", "completed_nodes": list(node_drafts), "completion_ratio": 1.0, "approval_status": "approved"},
    )
    return _build_session(profile, condition, seed, events, context_bank, node_selected_contexts, node_drafts, list(node_drafts), {}, {}, {}, final_artifact=final_artifact)


def _web_browse_context_items(profile: SimulationProfile) -> dict[str, dict[str, Any]]:
    """Model an agent's search/browse capability as a small pool of GENERIC, non-personal
    external guidance snippets derived from the goal's target deliverables. These are
    substantive and share tokens with the task (so the dynamic selector may rank them in),
    but they carry no user-specific context — reflecting that browsing surfaces external
    best-practice material, not the user's own situation."""
    outputs = [criterion.replace("includes ", "") for criterion in profile.approval_criteria if criterion.startswith("includes ")]
    if not outputs:
        outputs = ["plan", "checklist", "timeline"]
    items: dict[str, dict[str, Any]] = {}
    for index, topic in enumerate(outputs[:3], start=1):
        topic_text = topic.strip()
        items[f"web_{index}"] = {
            "scope": "web",
            "label": f"general guidance: {topic_text}",
            "value": (
                f"General best practices for a {topic_text}: keep it specific and actionable, "
                f"set clear milestones and deadlines, and validate assumptions before committing."
            ),
        }
    return items


def _simulate_react_integrated_planner(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    rng: random.Random,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
    simulated_user_model: str,
    live_simulated_user: bool,
) -> WorkflowSession:
    """Reviewer-4 requested (ARR 2026, discussion round): a STRONG, fully integrated
    agentic planner that combines the capabilities a modern agent brings to bear — it
    (a) ASKS the user (mixed-initiative elicitation, the same global context JumpStarter
    gets), (b) INSPECTS user-provided materials and RETRIEVES from a memory store,
    (c) BROWSES for generic external guidance, and (d) DYNAMICALLY selects the top-k
    relevant context per subtask during execution. It differs from JumpStarter in exactly
    one respect: it has no task-anchored reuse substrate that routes prior drafts across
    subtasks and no structured per-node curation loop. This isolates whether an integrated
    retrieve+select+browse agent, given the same elicited context, approximates
    JumpStarter's task-anchored context binding."""
    # (a) Ask: elicit the same global context from the simulated user as JumpStarter.
    _collect_global_context(
        profile,
        context_bank,
        add,
        model,
        live_stages,
        simulated_user_model,
        live_simulated_user,
    )
    # (b) Inspect user-provided materials + retrieve from a memory store.
    memory_bank = _profile_memory_context_bank(profile)
    for context_id, context in memory_bank.items():
        context_bank.setdefault(context_id, context)
    # (c) Browse: add generic external guidance into the same retrievable pool.
    browse_items = _web_browse_context_items(profile)
    context_bank.update(browse_items)
    add(
        "agentic_retrieval",
        "system",
        "agentic_retrieval",
        {
            "inspected_context_ids": list(memory_bank),
            "browsed_context_ids": list(browse_items),
            "available_context_ids": list(context_bank),
            "baseline_policy": (
                "Integrated agent asks the user, inspects user-provided materials, retrieves memory, "
                "and browses generic external guidance into a single dynamically retrievable pool; "
                "it then selects context per subtask but does NOT route prior drafts across subtasks."
            ),
        },
    )
    # (d) Plan: decompose into subtasks (same decomposition JumpStarter uses).
    task_nodes = _task_nodes(profile)
    if _live_enabled(live_stages, "task_decomposition"):
        task_prompt = render_prompt(
            "subtask_generation",
            main_purpose=profile.goal_text,
            user_context=_context_bank_json(context_bank),
            current_task=profile.goal_text,
            existing_tree_structure="[]",
            current_subtask_title=profile.goal_text,
        )
        task_nodes = _live_task_nodes(profile, task_prompt, model, fallback_nodes=task_nodes)
    _add_one_shot_agent_structure(profile, condition, add, task_nodes, "react_integrated_plan")

    # Per-subtask ReAct loop: dynamic retrieval + selection + draft, WITHOUT cross-subtask reuse.
    node_drafts: dict[str, str] = {}
    node_selected_contexts: dict[str, list[str]] = {}
    for node in task_nodes:
        selected_ids = _ranked_relevant_context_ids(context_bank, node, max_selected=5) or _first_n_substantive_context_ids(context_bank, 3)
        drafts, selected = _draft_one_shot_agent_plan(
            profile,
            condition,
            node,
            context_bank,
            selected_ids,
            add,
            model,
            live_stages,
        )
        node_drafts.update(drafts)
        node_selected_contexts.update(selected)

    final_artifact = _compile_agent_baseline_artifact(profile, condition, context_bank, node_drafts, node_selected_contexts)
    add(
        "final_artifact_compilation",
        "system",
        "final_synthesis",
        {
            "final_artifact": final_artifact,
            "generation_mode": "deterministic",
            "baseline_policy": _agent_policy_label(condition),
        },
    )
    add(
        "final_artifact_review",
        "user",
        "final_review",
        _calibrated_final_artifact_review(list(node_drafts), node_drafts, _load_user_decision_calibration(), rng),
    )
    return _build_session(
        profile,
        condition,
        seed,
        events,
        context_bank,
        node_selected_contexts,
        node_drafts,
        list(node_drafts),
        {},
        {},
        {},
        final_artifact=final_artifact,
    )


def _adapt_plan_and_run(
    profile: SimulationProfile,
    condition: Condition,
    task: dict[str, str],
    depth: int,
    logic: str,
    context_bank: dict[str, dict[str, Any]],
    info_prop: dict[str, Any],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
    state: dict[str, Any],
    max_depth: int,
) -> bool:
    add(
        "subtask_detection",
        "system",
        "subtask_detection",
        {
            "available_actions": ["draft_answer", "decompose_further"],
            "suggested_action": "draft_answer",
            "rationale": "ADaPT executor attempts the current task before invoking the planner.",
            "generation_mode": "deterministic",
            "adapt_depth": depth,
            "incoming_logic": logic,
        },
        node_id=task["node_id"],
    )
    state["subtask_detection_decisions"][task["node_id"]] = {
        "action": "apply_suggestion",
        "chosen_next_step": "draft_answer",
        "available_actions": ["draft_answer", "decompose_further"],
        "reason": "ADaPT first tries to execute the current task directly.",
        "adapt_depth": depth,
    }
    add(
        "subtask_detection_decision",
        "system",
        "subtask_detection",
        state["subtask_detection_decisions"][task["node_id"]],
        node_id=task["node_id"],
    )

    selected_ids = _adapt_executor_context_ids(context_bank, task, info_prop)
    reused_contexts = {context_id: context_bank[context_id] for context_id in selected_ids}
    state["node_selected_contexts"][task["node_id"]] = selected_ids
    add(
        "context_selection",
        "system",
        "context_selection",
        {
            "available_context_ids": list(context_bank),
            "selected_context_ids": selected_ids,
            "policy": condition,
            "task_name": task["title"],
            "task_description": task["description"],
            "selection_reason": "ADaPT executor receives available environment/context state plus propagated salient info.",
            "generation_mode": "deterministic",
            "adapt_depth": depth,
            "info_propagated": info_prop,
        },
        node_id=task["node_id"],
    )
    context_digest = _context_digest_for_node(profile, task, reused_contexts, context_bank)
    add(
        "context_reuse",
        "system",
        "context_reuse",
        {
            "reused_context_ids": list(reused_contexts),
            "selected_but_not_reused_context_ids": [],
            "reused_contexts": reused_contexts,
            "context_digest": context_digest,
            "draft_target": task["title"],
            "generation_mode": "live" if _live_enabled(live_stages, "working_solution_draft_creation") else "deterministic",
            "adapt_depth": depth,
        },
        node_id=task["node_id"],
    )
    draft = _draft_agent_leaf(profile, task, reused_contexts, context_bank, model, live_stages)
    success = _adapt_executor_success(profile, task, depth, context_bank, draft, max_depth)
    add(
        "adapt_executor_attempt",
        "system",
        "execution",
        {
            "task": task,
            "depth": depth,
            "success": success,
            "max_depth": max_depth,
            "logic_context": logic,
            "info_propagated": info_prop,
            "action_history": [f"execute[{task['title']}]"],
            "failure_observation": None if success else _adapt_failure_observation(profile, task, context_bank),
            "repo_grounding": "Mirrors ADaPT executor call before optional planner decomposition.",
        },
        node_id=task["node_id"],
    )
    add(
        "subtask_draft",
        "system",
        "context_reuse",
        {
            "draft": draft,
            "selected_context_ids": selected_ids,
            "reused_context_ids": list(reused_contexts),
            "context_digest": context_digest,
            "generation_mode": "live" if _live_enabled(live_stages, "working_solution_draft_creation") else "deterministic",
            "adapt_depth": depth,
            "executor_success": success,
        },
        node_id=task["node_id"],
    )
    state["node_drafts"][task["node_id"]] = draft
    state["plan_trace"].append(f"{task['title']} at depth {depth}, success: {success}")
    if success:
        state["completed_nodes"].append(task["node_id"])
        state["action_checkpoint"].append(f"execute[{task['title']}]")
        info_prop["prev"] = task["title"]
        return True

    if depth >= max_depth:
        add(
            "adapt_depth_limit",
            "system",
            "task_decomposition",
            {
                "task": task,
                "depth": depth,
                "max_depth": max_depth,
                "reason": "Executor failed but maximum decomposition depth was reached.",
            },
            node_id=task["node_id"],
        )
        return False

    info_prop["status"] = _adapt_failure_observation(profile, task, context_bank)
    add(
        "adapt_info_propagation",
        "system",
        "task_decomposition",
        {
            "from_task": task["node_id"],
            "status": info_prop["status"],
            "mode": "last-step-last-act",
            "repo_grounding": "ADaPT passes salient failure/status information to the planner for the next decomposition.",
        },
        node_id=task["node_id"],
    )

    plan_steps = _adapt_planner_steps(profile, task, depth + 1, info_prop)
    children = plan_steps["steps"]
    state["nested_task_nodes"][task["node_id"]] = children
    add(
        "nested_task_decomposition",
        "system",
        "task_decomposition",
        {
            "parent_node_id": task["node_id"],
            "decomposition_type": "adapt_as_needed_after_executor_failure",
            "children": children,
            "logic": plan_steps["logic"],
            "execution_order": plan_steps["execution_order"],
            "step_lines": plan_steps["step_lines"],
            "generation_mode": "deterministic",
            "planner_input_status": info_prop.get("status", ""),
            "repo_grounding": "Planner returns abstract steps and nested AND/OR execution order after executor failure.",
        },
        node_id=task["node_id"],
    )
    state["plan_trace"].append(
        f"{[child['title'] for child in children]} at depth {depth + 1} and logic {plan_steps['logic']}"
    )

    child_successes: list[bool] = []
    for child in children:
        child_info = dict(info_prop)
        child_success = _adapt_plan_and_run(
            profile=profile,
            condition=condition,
            task=child,
            depth=depth + 1,
            logic=plan_steps["logic"],
            context_bank=context_bank,
            info_prop=child_info,
            add=add,
            model=model,
            live_stages=live_stages,
            state=state,
            max_depth=max_depth,
        )
        child_successes.append(child_success)
        if plan_steps["logic"].lower() == "or" and child_success:
            add(
                "adapt_logic_short_circuit",
                "system",
                "task_decomposition",
                {"logic": "OR", "stopped_after_successful_child": child["node_id"]},
                node_id=task["node_id"],
            )
            return True
        if plan_steps["logic"].lower() == "and" and not child_success:
            add(
                "adapt_logic_short_circuit",
                "system",
                "task_decomposition",
                {"logic": "AND", "stopped_after_failed_child": child["node_id"]},
                node_id=task["node_id"],
            )
            return False
    return any(child_successes) if plan_steps["logic"].lower() == "or" else all(child_successes)


def _adapt_executor_context_ids(
    context_bank: dict[str, dict[str, Any]],
    task: dict[str, str],
    info_prop: dict[str, Any],
) -> list[str]:
    relevant = _ranked_relevant_context_ids(context_bank, task, max_selected=4)
    selected = relevant or _first_n_substantive_context_ids(context_bank, 3)
    if info_prop.get("status"):
        status_hash = hashlib.sha1(str(info_prop.get("status")).encode("utf-8")).hexdigest()[:10]
        status_id = f"adapt_status_{status_hash}"
        if status_id not in context_bank:
            context_bank[status_id] = {
                "scope": "adapt_info_prop",
                "label": "ADaPT propagated status",
                "value": str(info_prop["status"]),
            }
        selected = _unique_strings([status_id, *selected])
    return selected


def _adapt_executor_success(
    profile: SimulationProfile,
    task: dict[str, str],
    depth: int,
    context_bank: dict[str, dict[str, Any]],
    draft: str,
    max_depth: int,
) -> bool:
    if depth >= max_depth:
        return True
    title_tokens = set(_key_tokens(task["title"] + " " + task["description"]))
    artifact_terms = {"message", "email", "checklist", "calendar", "tracker", "template", "outline", "survey", "shortlist"}
    if depth >= 2 and title_tokens & artifact_terms and _is_substantive_context_bank(context_bank):
        return True
    if task["node_id"] != "ADAPT" and len(_words(draft)) >= 120 and depth >= 2:
        return True
    if task["node_id"] == "ADAPT" and len(_approval_artifact_targets(profile.approval_criteria)) <= 1:
        return True
    return False


def _adapt_failure_observation(
    profile: SimulationProfile,
    task: dict[str, str],
    context_bank: dict[str, dict[str, Any]],
) -> str:
    missing = _missing_inputs_for_node(profile, task)
    available = [
        str(context.get("label", context_id))
        for context_id, context in context_bank.items()
        if isinstance(context, dict) and _is_substantive_context(context)
    ]
    return (
        f"Executor could not complete '{task['title']}' directly. "
        f"Missing or uncertain inputs: {', '.join(missing[:3])}. "
        f"Available evidence labels: {', '.join(available[:5]) or 'none'}."
    )


def _adapt_planner_steps(
    profile: SimulationProfile,
    task: dict[str, str],
    depth: int,
    info_prop: dict[str, Any],
) -> dict[str, Any]:
    targets = _approval_artifact_targets(profile.approval_criteria)
    if task["node_id"] == "ADAPT" and targets:
        raw_steps = [
            {"title": target.title(), "description": f"Create or refine {target} for {profile.goal_text}."}
            for target in targets[:4]
        ]
    else:
        raw_steps = [
            {
                "title": f"Resolve Inputs For {task['title']}",
                "description": f"Use propagated status to identify missing inputs before completing {task['title']}.",
            },
            {
                "title": f"Execute {task['title']}",
                "description": f"Produce the concrete artifact for {task['title']} using available evidence.",
            },
        ]
    logic = "OR" if _adapt_should_use_or(task, info_prop) else "AND"
    children = [
        {
            "node_id": f"{task['node_id']}.{index}",
            "title": step["title"],
            "description": step["description"],
        }
        for index, step in enumerate(raw_steps, start=1)
    ]
    step_terms = [f"Step {index}" for index in range(1, len(children) + 1)]
    execution_order = f" {logic} ".join(step_terms)
    if len(step_terms) > 1:
        execution_order = f"({execution_order})"
    step_lines = [f"Step {index}: {child['description']}" for index, child in enumerate(children, start=1)]
    step_lines.append(f"execution order: {execution_order}")
    return {"steps": children, "logic": logic, "execution_order": execution_order, "step_lines": step_lines, "depth": depth}


def _adapt_should_use_or(task: dict[str, str], info_prop: dict[str, Any]) -> bool:
    text = f"{task['title']} {task['description']} {info_prop.get('status', '')}".lower()
    return any(term in text for term in ("option", "alternative", "shortlist", "choose", "selection"))


def _is_substantive_context_bank(context_bank: dict[str, dict[str, Any]]) -> bool:
    return any(_is_substantive_context(context) for context in context_bank.values())


def _abp_tool_agent_run(
    profile: SimulationProfile,
    context_bank: dict[str, dict[str, Any]],
    conversation: list[dict[str, str]],
    round_index: int,
) -> dict[str, Any]:
    tool_specs = _abp_tool_specs(profile)
    trajectories: dict[str, str] = {}
    tool_calls: list[dict[str, Any]] = []
    missing_or_unavailable: list[str] = []
    known_text = "\n".join(
        [
            profile.goal_text,
            *[message["content"] for message in conversation],
            *[
                str(context.get("label", "")) + ": " + str(context.get("value", ""))
                for context in context_bank.values()
                if isinstance(context, dict)
            ],
        ]
    )
    for spec in tool_specs:
        has_params = _abp_tool_has_required_params(spec, known_text)
        call = {
            "tool": spec["tool"],
            "required_detail": spec["required_detail"],
            "parameters_available": has_params,
        }
        if has_params:
            result = _abp_tool_result(profile, spec, known_text)
            trajectories[spec["call"]] = result
            call["status"] = "success"
            call["result_preview"] = _trim_words(result, 24)
            context_id = f"abp_tool_{round_index}_{spec['tool'].lower()}"
            context_bank[context_id] = {
                "scope": "tool_trajectory",
                "label": f"{spec['tool']} result",
                "value": result,
            }
        else:
            missing_or_unavailable.append(spec["required_detail"])
            call["status"] = "missing_params"
        tool_calls.append(call)
    return {
        "round": round_index,
        "tool_calls": tool_calls,
        "trajectories": trajectories,
        "missing_or_unavailable": _unique_strings(missing_or_unavailable),
    }


def _abp_tool_specs(profile: SimulationProfile) -> list[dict[str, str]]:
    goal = profile.goal_text
    return [
        {
            "tool": "RequirementSearch",
            "call": f'RequirementSearch("{goal}")',
            "required_detail": "task requirements",
            "match_terms": "requirement criteria output deliverable must include",
        },
        {
            "tool": "ResourceSearch",
            "call": f'ResourceSearch("{goal}")',
            "required_detail": "resources or materials",
            "match_terms": "resource material document venue portfolio contact account",
        },
        {
            "tool": "TimelineCheck",
            "call": f'TimelineCheck("{goal}")',
            "required_detail": "timeline or deadline",
            "match_terms": "timeline deadline date schedule week month availability",
        },
        {
            "tool": "BudgetEstimator",
            "call": f'BudgetEstimator("{goal}")',
            "required_detail": "budget or cost constraint",
            "match_terms": "budget cost price funding money fee",
        },
        {
            "tool": "ConstraintCheck",
            "call": f'ConstraintCheck("{goal}")',
            "required_detail": "constraints or feasibility limits",
            "match_terms": "constraint feasibility limit requirement preference location size",
        },
    ]


def _abp_tool_has_required_params(spec: dict[str, str], known_text: str) -> bool:
    known_tokens = set(_key_tokens(known_text))
    required_tokens = set(_key_tokens(spec["required_detail"] + " " + spec["match_terms"]))
    return bool(known_tokens & required_tokens)


def _abp_tool_result(profile: SimulationProfile, spec: dict[str, str], known_text: str) -> str:
    required_tokens = set(_key_tokens(spec["required_detail"] + " " + spec["match_terms"]))
    matching_lines = [
        line.strip()
        for line in known_text.splitlines()
        if line.strip() and set(_key_tokens(line)) & required_tokens
    ]
    if matching_lines:
        return f"{spec['tool']} found from conversation/environment trajectory: " + " | ".join(
            _unique_strings(matching_lines)[:3]
        )
    if spec["tool"] == "RequirementSearch" and profile.approval_criteria:
        return f"{spec['tool']} found approval criteria: " + "; ".join(profile.approval_criteria[:4])
    return f"{spec['tool']} found no blocking issue, but details should be verified from the conversation."


def _abp_clarification_need(
    profile: SimulationProfile,
    context_bank: dict[str, dict[str, Any]],
    missing_or_unavailable: list[str],
) -> str | None:
    candidates = []
    candidates.extend(missing_or_unavailable)
    candidates.extend(unknown.split(":", 1)[0].strip() for unknown in profile.unknown_or_undecided_facts)
    asked_labels = {
        str(context.get("label", "")).strip().lower()
        for context in context_bank.values()
        if isinstance(context, dict) and context.get("scope") == "clarification"
    }
    for candidate in _unique_strings([item for item in candidates if item]):
        if candidate.lower() in asked_labels:
            continue
        if any(_similar_context_request(candidate, label, threshold=0.5) for label in asked_labels):
            continue
        return candidate
    return None


def _adapt_child_nodes(node: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "node_id": f"{node['node_id']}.A",
            "title": f"Analyze {node['title']}",
            "description": f"Identify requirements, constraints, and success criteria for {node['title']}.",
        },
        {
            "node_id": f"{node['node_id']}.B",
            "title": f"Execute {node['title']}",
            "description": f"Produce the concrete deliverable for {node['title']} after analysis.",
        },
    ]


def _draft_agent_leaf(
    profile: SimulationProfile,
    node: dict[str, str],
    reused_contexts: dict[str, dict[str, Any]],
    context_bank: dict[str, dict[str, Any]],
    model: str,
    live_stages: LiveStageMode,
) -> str:
    context_digest = _context_digest_for_node(profile, node, reused_contexts, context_bank)
    draft_prompt = render_prompt(
        "working_solution_draft_creation",
        main_purpose=profile.goal_text,
        user_context=json.dumps(context_digest, ensure_ascii=True, sort_keys=True),
        current_task=node["title"],
        task_description=node["description"],
    )
    draft = _draft_for_node(profile, node, reused_contexts, context_digest=context_digest)
    if _live_enabled(live_stages, "working_solution_draft_creation"):
        draft = _live_draft(
            profile,
            node,
            reused_contexts,
            draft_prompt,
            model,
            fallback_draft=draft,
            context_digest=context_digest,
        )
    return draft


def _clarification_needs(profile: SimulationProfile, context_bank: dict[str, dict[str, Any]]) -> list[str]:
    already_asked = {
        str(context.get("label", "")).strip().lower()
        for context in context_bank.values()
        if isinstance(context, dict)
    }
    candidates = [item.split(":", 1)[0].strip() for item in profile.unknown_or_undecided_facts]
    candidates.extend(item.split(":", 1)[0].strip() for item in profile.must_reveal_if_asked)
    needs = []
    for candidate in candidates:
        if not candidate or candidate.lower() in already_asked:
            continue
        if any(_similar_context_request(candidate, existing, threshold=0.6) for existing in needs):
            continue
        needs.append(candidate)
    return needs[:2]


def _add_one_shot_agent_structure(
    profile: SimulationProfile,
    condition: Condition,
    add: Any,
    nodes: list[dict[str, str]],
    representation: str,
) -> None:
    add(
        "task_decomposition",
        "system",
        "task_decomposition",
        {
            "root_goal": profile.goal_text,
            "nodes": nodes,
            "representation": representation,
            "generation_mode": "deterministic",
            "baseline_policy": _agent_policy_label(condition),
        },
    )
    for node in nodes:
        add(
            "subtask_detection",
            "system",
            "subtask_detection",
            {
                "available_actions": ["draft_answer", "decompose_further"],
                "suggested_action": "draft_answer",
                "rationale": "The baseline produces one planning artifact after its setup step.",
                "generation_mode": "deterministic",
            },
            node_id=node["node_id"],
        )
        add(
            "subtask_detection_decision",
            "system",
            "subtask_detection",
            {
                "action": "apply_suggestion",
                "chosen_next_step": "draft_answer",
                "available_actions": ["draft_answer", "decompose_further"],
                "reason": "One-shot planner baseline proceeds directly to drafting.",
            },
            node_id=node["node_id"],
        )


def _draft_one_shot_agent_plan(
    profile: SimulationProfile,
    condition: Condition,
    node: dict[str, str],
    context_bank: dict[str, dict[str, Any]],
    selected_ids: list[str],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    selected_ids = [context_id for context_id in selected_ids if context_id in context_bank and _is_substantive_context(context_bank[context_id])]
    reused_contexts = {context_id: context_bank[context_id] for context_id in selected_ids}
    context_digest = _context_digest_for_node(profile, node, reused_contexts, context_bank)
    add(
        "context_selection",
        "system",
        "context_selection",
        {
            "available_context_ids": list(context_bank),
            "selected_context_ids": selected_ids,
            "policy": condition,
            "task_name": node["title"],
            "task_description": node["description"],
            "selection_reason": _selection_reason(condition, selected_ids),
            "generation_mode": "deterministic",
        },
        node_id=node["node_id"],
    )
    draft_prompt = render_prompt(
        "working_solution_draft_creation",
        main_purpose=profile.goal_text,
        user_context=json.dumps(context_digest, ensure_ascii=True, sort_keys=True),
        current_task=node["title"],
        task_description=node["description"],
    )
    draft = _vanilla_draft(profile, user_context=_context_bank_json(reused_contexts))
    if _live_enabled(live_stages, "working_solution_draft_creation"):
        draft = _live_draft(
            profile,
            node,
            reused_contexts,
            draft_prompt,
            model,
            fallback_draft=draft,
            context_digest=context_digest,
        )
    add(
        "context_reuse",
        "system",
        "context_reuse",
        {
            "reused_context_ids": list(reused_contexts),
            "selected_but_not_reused_context_ids": [],
            "reused_contexts": reused_contexts,
            "context_digest": context_digest,
            "draft_target": node["title"],
            "generation_mode": "live" if _live_enabled(live_stages, "working_solution_draft_creation") else "deterministic",
            "prompt": draft_prompt,
        },
        node_id=node["node_id"],
    )
    add(
        "subtask_draft",
        "system",
        "context_reuse",
        {
            "draft": draft,
            "selected_context_ids": selected_ids,
            "reused_context_ids": list(reused_contexts),
            "context_digest": context_digest,
            "generation_mode": "live" if _live_enabled(live_stages, "working_solution_draft_creation") else "deterministic",
        },
        node_id=node["node_id"],
    )
    return {node["node_id"]: draft}, {node["node_id"]: selected_ids}


def _profile_memory_context_bank(profile: SimulationProfile) -> dict[str, dict[str, Any]]:
    memory: dict[str, dict[str, Any]] = {}
    seen_text: set[str] = set()
    for index, fact in enumerate(profile.private_context_facts, start=1):
        text = fact.strip()
        if not text or text.lower() in seen_text:
            continue
        seen_text.add(text.lower())
        label = text.split(":", 1)[0].strip() if ":" in text else f"memory fact {index}"
        memory[f"memory_{index}"] = {"scope": "memory", "label": label, "value": text}
    unknown_start = len(memory) + 1
    for offset, unknown in enumerate(profile.unknown_or_undecided_facts, start=unknown_start):
        label = unknown.split(":", 1)[0].strip() or f"unknown memory {offset}"
        memory[f"memory_{offset}"] = {"scope": "memory", "label": label, "value": "I do not know yet."}
    return memory


def _first_n_substantive_context_ids(context_bank: dict[str, dict[str, Any]], limit: int) -> list[str]:
    return [
        context_id
        for context_id, context in context_bank.items()
        if _is_substantive_context(context)
    ][:limit]


def _token_capped_context_ids(context_bank: dict[str, dict[str, Any]], max_tokens: int) -> list[str]:
    selected: list[str] = []
    used_tokens = 0
    for context_id, context in context_bank.items():
        if not _is_substantive_context(context):
            continue
        token_count = _context_token_count(context)
        if selected and used_tokens + token_count > max_tokens:
            continue
        selected.append(context_id)
        used_tokens += token_count
        if used_tokens >= max_tokens:
            break
    return selected


def _compile_agent_baseline_artifact(
    profile: SimulationProfile,
    condition: Condition,
    context_bank: dict[str, dict[str, Any]],
    node_drafts: dict[str, str],
    node_selected_contexts: dict[str, list[str]],
) -> str:
    selected_ids = _unique_strings([context_id for ids in node_selected_contexts.values() for context_id in ids])
    selected_contexts = _prioritized_context_items(context_bank, selected_ids, include_drafts=False)
    context_lines = [item["text"] for item in selected_contexts[:8]] or [
        "No substantive user-specific context was selected; concrete details should be verified."
    ]
    method = _agent_policy_label(condition)
    draft_sections = []
    for node_id, draft in node_drafts.items():
        draft_sections.extend(["", f"### {node_id}", "", _trim_words(_clean_draft_for_final_artifact(draft), 180)])
    todos = _final_artifact_todo_items(profile, context_bank, node_drafts, _unknown_context_items(context_bank))
    sections = [
        f"# {profile.goal_text} - Agent Baseline Deliverable",
        "",
        "## Baseline Method",
        f"- {method}",
        "",
        "## Context Used",
        *_bullet_lines(context_lines),
        "",
        "## Planning Output",
        *(draft_sections or ["No draft was produced."]),
        "",
        "## TODO Before Use",
        *_bullet_lines(todos[:8] or ["Review owner, deadline, and unstated constraints before use."]),
    ]
    return _sanitize_compiled_artifact("\n".join(sections))


def _agent_policy_label(condition: Condition) -> str:
    labels = {
        "adapt_recursive_decomposition": "ADaPT baseline: initial Step n planning, executor-first recursive replanning, and AND/OR short-circuiting.",
        "ask_before_plan": "Ask-before-Plan baseline: tool trajectory, clarification decision/question loop, then one final planner call.",
        "unstructured_memory_rag": "Unstructured Memory-RAG planner: retrieve generic top-k snippets from an unstructured memory bank.",
        "long_context_planner": "Long-Context Planner: place all available snippets into one capped prompt and produce a single plan.",
        "react_integrated_planner": "Integrated agentic planner: ask + inspect + retrieve + browse, with dynamic per-subtask context selection but no task-anchored cross-subtask reuse.",
    }
    return labels.get(condition, "Agent planning baseline.")


def _collect_global_context(
    profile: SimulationProfile,
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
    simulated_user_model: str,
    live_simulated_user: bool,
) -> None:
    needs = _global_needs(profile)
    asked_questions: list[str] = []
    asked_keys: list[str] = []
    for index, need in enumerate(needs, start=1):
        question = _question_for_context_need(profile.goal_text, need)
        prompt = render_prompt(
            "global_context_elicitation",
            task_input=profile.goal_text,
            context_history=_context_bank_json(context_bank) if context_bank else "empty",
        )
        generation_mode = "deterministic"
        if _live_enabled(live_stages, "global_context_elicitation"):
            live_question = _live_question(
                profile,
                prompt,
                model,
                fallback_question=question,
                fallback_key=need,
                question_type="global_context_elicitation",
                target_context_key=need,
                previous_questions=asked_questions,
                previous_context_keys=asked_keys,
                existing_context=context_bank,
                remaining_context_keys=needs[index - 1 :],
                enforce_target=True,
            )
            question = live_question["question"]
            need = live_question["requested_context_key"]
            generation_mode = "live"
        asked_questions.append(question)
        asked_keys.append(need)
        add(
            "global_context_elicitation",
            "system",
            "global_context_elicitation",
            {
                "question": question,
                "requested_context_key": need,
                "generation_mode": generation_mode,
                "prompt": prompt,
            },
        )
        answer = _simulated_user_answer_for_need(
            profile,
            need,
            question,
            model=simulated_user_model,
            live=live_simulated_user,
            conversation_state={
                "stage": "global_context_elicitation",
                "known_context": context_bank,
            },
        )
        context_id = f"global_{index}"
        context_bank[context_id] = {"scope": "global", "label": need, "value": answer}
        add(
            "global_context_answer",
            "user",
            "global_context_elicitation",
            {
                "context_id": context_id,
                "question": question,
                "answer": answer,
                "answer_status": _answer_status(answer),
                "generation_mode": "live" if live_simulated_user else "deterministic",
                "simulated_user_model": simulated_user_model if live_simulated_user else "deterministic",
            },
        )


def _simulate_chatgpt_baseline(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
) -> WorkflowSession:
    if condition == "chatgpt_with_structured_summary":
        summary = _structured_context_summary(context_bank)
        add(
            "structured_context_summary",
            "system",
            "context_summary",
            {"summary": summary, "source_context_ids": list(context_bank)},
        )
        user_context = summary
    elif condition == "chatgpt_with_elicited_context":
        user_context = _context_bank_json(context_bank)
    else:
        user_context = ""
    draft_prompt = render_prompt(
        "working_solution_draft_creation",
        main_purpose=profile.goal_text,
        user_context=user_context,
        current_task=profile.goal_text,
        task_description=profile.goal_text,
    )
    draft = _vanilla_draft(profile, user_context=user_context)
    draft_generation_mode = "deterministic"
    if _live_enabled(live_stages, "working_solution_draft_creation"):
        draft = _live_draft(
            profile,
            {"title": profile.goal_text, "description": profile.goal_text},
            context_bank if user_context else {},
            draft_prompt,
            model,
            fallback_draft=draft,
        )
        draft_generation_mode = "live"
    add(
        "one_shot_draft",
        "system",
        "one_shot_response",
        {
            "draft": draft,
            "condition_policy": condition,
            "context_ids_used": list(context_bank) if user_context else [],
            "generation_mode": draft_generation_mode,
            "prompt": draft_prompt,
        },
    )
    review = _review_draft(profile, draft, used_selected_context=bool(user_context))
    add("final_artifact_review", "user", "final_review", {**review, "approval_status": "not_ready"})
    return _build_session(profile, condition, seed, events, context_bank, {}, {"direct": draft}, [], {}, {}, {})


def _simulate_single_turn_decomposition_baseline(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    add: Any,
    model: str,
    live_stages: LiveStageMode,
) -> WorkflowSession:
    """Reviewer-requested control (ARR 2026): a single GPT-4o turn that is explicitly
    prompted to decompose the goal into subtasks and produce a plan plus concrete drafts,
    given the SAME elicited context as JumpStarter, but WITHOUT an external task tree,
    per-subtask context selection, or cross-subtask reuse. This isolates whether the
    benefit comes from the external task-structured context curation or merely from GPT-4o
    performing decomposition internally in one shot. It is identical to
    chatgpt_with_elicited_context except the prompt explicitly requests decomposition."""
    user_context = _context_bank_json(context_bank)
    draft_prompt = render_prompt(
        "single_turn_decomposition",
        main_purpose=profile.goal_text,
        user_context=user_context,
        current_task=profile.goal_text,
        task_description=profile.goal_text,
    )
    draft = _vanilla_draft(profile, user_context=user_context)
    draft_generation_mode = "deterministic"
    if _live_enabled(live_stages, "working_solution_draft_creation"):
        draft = _live_draft(
            profile,
            {"title": profile.goal_text, "description": profile.goal_text},
            context_bank,
            draft_prompt,
            model,
            fallback_draft=draft,
        )
        draft_generation_mode = "live"
    add(
        "single_turn_decomposition_draft",
        "system",
        "one_shot_response",
        {
            "draft": draft,
            "condition_policy": condition,
            "context_ids_used": list(context_bank),
            "generation_mode": draft_generation_mode,
            "prompt": draft_prompt,
        },
    )
    review = _review_draft(profile, draft, used_selected_context=bool(user_context))
    add("final_artifact_review", "user", "final_review", {**review, "approval_status": "not_ready"})
    return _build_session(profile, condition, seed, events, context_bank, {}, {"single_turn": draft}, [], {}, {}, {})


def _live_enabled(live_stages: LiveStageMode, stage: str) -> bool:
    if live_stages == "all":
        return True
    if live_stages == "planning":
        return stage in {"working_solution_draft_creation", "task_decomposition", "subtask_detection"}
    if live_stages == "drafts":
        return stage == "working_solution_draft_creation"
    return False


def _live_context_selection_allowed(live_stages: LiveStageMode, condition: Condition) -> bool:
    if not _live_enabled(live_stages, "context_selection"):
        return False
    return condition in {"full_jumpstarter", "flat_decomposition", "no_reuse"}


def _workflow_model(model: str) -> str | None:
    return None if model == "deterministic" else model


@lru_cache(maxsize=1)
def _load_user_decision_calibration(path: str | Path = DEFAULT_USER_DECISION_CALIBRATION_PATH) -> dict[str, Any]:
    calibration_path = Path(path)
    if not calibration_path.exists():
        return {}
    try:
        payload = json.loads(calibration_path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _calibrated_task_tree_review(
    task_nodes: list[dict[str, str]],
    calibration: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    policy = _calibration_policy(calibration, "task_tree_review")
    accept_rate = _policy_float(policy, "accept_rate", 1.0)
    accepted = _sample_probability(rng, accept_rate)
    return {
        "action": "accept" if accepted else "request_revision",
        "reason": (
            "The decomposition matches the goal well enough for a first pass."
            if accepted
            else "The decomposition should be revised before I use it."
        ),
        "reviewed_node_count": len(task_nodes),
        "calibration": _calibration_metadata("task_tree_review", policy, accept_rate=accept_rate),
    }


def _calibrated_subtask_detection_decision(
    profile: SimulationProfile,
    node: dict[str, str],
    suggestion: dict[str, str],
    condition: Condition,
    calibration: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    available_actions = ["draft_answer", "decompose_further"]
    suggested_action = suggestion["suggested_action"]
    if condition == "flat_decomposition":
        chosen_next_step = "draft_answer"
        action = "apply_suggestion"
        sampled_probability = 1.0
    else:
        policy = _calibration_policy(calibration, "subtask_detection_decision")
        decompose_rate = _policy_float(policy, "decompose_further_rate", 0.5)
        draft_rate = _policy_float(policy, "draft_answer_rate", 1.0 - decompose_rate)
        chosen_next_step = _weighted_choice(
            rng,
            {"decompose_further": decompose_rate, "draft_answer": draft_rate},
            fallback=suggested_action,
        )
        action = "apply_suggestion" if chosen_next_step == suggested_action else "override_suggestion"
        sampled_probability = decompose_rate if chosen_next_step == "decompose_further" else draft_rate
    return {
        "action": action,
        "chosen_next_step": chosen_next_step,
        "available_actions": available_actions,
        "reason": _subtask_detection_decision_reason(profile, chosen_next_step),
        "calibration": {
            **_calibration_metadata("subtask_detection_decision", _calibration_policy(calibration, "subtask_detection_decision")),
            "suggested_action": suggested_action,
            "sampled_action_probability": round(sampled_probability, 4),
        },
    }


def _calibrated_nested_task_review(
    children: list[dict[str, str]],
    calibration: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    policy = _calibration_policy(calibration, "nested_task_review")
    distribution = policy.get("selected_child_position_distribution")
    if not isinstance(distribution, dict) or not distribution:
        distribution = {"last_child": 1.0}
    selected_scope = _weighted_choice(rng, distribution, fallback="last_child")
    selected_children = _children_for_scope(children, str(selected_scope))
    selected_child = selected_children[0] if selected_children else (children[-1] if children else None)
    return {
        "action": "accept",
        "selected_child_node_id": selected_child["node_id"] if selected_child else None,
        "selected_child_node_ids": [child["node_id"] for child in selected_children],
        "selected_child_policy": selected_scope,
        "reason": _nested_task_review_reason(str(selected_scope)),
        "calibration": _calibration_metadata("nested_task_review", policy, selected_policy=selected_scope),
    }


def _calibrated_draft_review(
    profile: SimulationProfile,
    draft: str,
    used_selected_context: bool,
    calibration: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    policy = _calibration_policy(calibration, "draft_review")
    accept_rate = _policy_float(policy, "saved_draft_rate", 0.75)
    if not used_selected_context and profile.approval_criteria:
        accept_rate = min(accept_rate * 0.35, 0.25)
    if "no selected context" in draft.lower():
        accept_rate = min(accept_rate, 0.2)
    accepted = _sample_probability(rng, accept_rate)
    return {
        "action": "accept" if accepted else "pushback",
        "reason": (
            "This is useful enough to save as a working draft."
            if accepted
            else "This feels generic and should use my relevant context first."
        ),
        "calibration": _calibration_metadata("draft_review", policy, accept_rate=round(accept_rate, 4)),
    }


def _calibrated_final_artifact_review(
    completed_nodes: list[str],
    node_drafts: dict[str, str],
    calibration: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    policy = _calibration_policy(calibration, "final_artifact_review")
    completion_ratio = len(completed_nodes) / max(1, len(node_drafts))
    threshold = _sample_completion_threshold(policy, rng)
    approval_floor = _policy_float(policy, "approval_completion_floor", 0.75)
    approved = bool(completed_nodes) and completion_ratio >= max(threshold, approval_floor)
    return {
        "action": "approve" if approved else "needs_revision",
        "completed_nodes": completed_nodes,
        "completion_ratio": round(completion_ratio, 4),
        "approval_status": "approved" if approved else "not_ready",
        "calibration": _calibration_metadata(
            "final_artifact_review",
            policy,
            sampled_completion_threshold=threshold,
            approval_completion_floor=approval_floor,
        ),
    }


def _calibration_policy(calibration: dict[str, Any], policy_name: str) -> dict[str, Any]:
    policy = calibration.get(policy_name) if isinstance(calibration, dict) else None
    return policy if isinstance(policy, dict) else {}


def _calibration_metadata(policy_name: str, policy: dict[str, Any], **extra: Any) -> dict[str, Any]:
    metadata = {
        "source": "real_user_study_logs",
        "policy": policy_name,
        "observations": policy.get("observations"),
        "proxy_definition": policy.get("proxy_definition") or policy.get("accept_proxy_definition"),
    }
    metadata.update(extra)
    return metadata


def _policy_float(policy: dict[str, Any], key: str, default: float) -> float:
    value = policy.get(key, default)
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _sample_probability(rng: random.Random, probability: float) -> bool:
    return rng.random() < max(0.0, min(1.0, probability))


def _weighted_choice(rng: random.Random, weights: dict[Any, Any], fallback: Any) -> Any:
    numeric_weights: list[tuple[Any, float]] = []
    for key, value in weights.items():
        try:
            weight = float(value)
        except (TypeError, ValueError):
            continue
        if weight > 0:
            numeric_weights.append((key, weight))
    if not numeric_weights:
        return fallback
    total = sum(weight for _key, weight in numeric_weights)
    cursor = rng.random() * total
    cumulative = 0.0
    for key, weight in numeric_weights:
        cumulative += weight
        if cursor <= cumulative:
            return key
    return numeric_weights[-1][0]


def _children_for_scope(children: list[dict[str, str]], selected_scope: str) -> list[dict[str, str]]:
    if not children:
        return []
    if selected_scope == "all_children":
        return children
    if selected_scope == "first_child":
        return [children[0]]
    if selected_scope == "middle_child":
        return [children[len(children) // 2]]
    return [children[-1]]


def _child_node_by_id(children: list[dict[str, str]], node_id: Any) -> dict[str, str] | None:
    return next((child for child in children if child.get("node_id") == node_id), None)


def _nested_task_review_reason(selected_scope: str) -> str:
    if selected_scope == "all_children":
        return "The child tasks look useful; I will start from the first one and keep the rest available."
    if selected_scope == "first_child":
        return "I will start with the first child task before moving deeper."
    if selected_scope == "middle_child":
        return "The middle child task seems like the most useful next target."
    return "This child task seems like the best next target."


def _sample_completion_threshold(policy: dict[str, Any], rng: random.Random) -> float:
    distribution = policy.get("completion_bucket_distribution")
    if not isinstance(distribution, dict) or not distribution:
        mean_completion = policy.get("mean_completion_ratio", 1.0)
        try:
            return max(0.0, min(1.0, float(mean_completion)))
        except (TypeError, ValueError):
            return 1.0
    bucket = _weighted_choice(rng, distribution, fallback="0.75-1.00")
    bucket_midpoints = {
        "0.00-0.25": 0.125,
        "0.25-0.50": 0.375,
        "0.50-0.75": 0.625,
        "0.75-1.00": 0.875,
    }
    return bucket_midpoints.get(str(bucket), 1.0)


def _simulated_user_answer_for_need(
    profile: SimulationProfile,
    need: str,
    question: str,
    model: str,
    live: bool,
    conversation_state: dict[str, Any],
) -> str:
    if not live or model == "deterministic":
        return _answer_for_need(profile, need)
    return generate_simulated_user_answer_live(
        profile,
        question=question,
        requested_context_key=need,
        conversation_state=conversation_state,
        model=model,
    )


def _live_question(
    profile: SimulationProfile,
    prompt: dict[str, str],
    model: str,
    fallback_question: str,
    fallback_key: str,
    question_type: str,
    target_context_key: str | None = None,
    previous_questions: list[str] | None = None,
    previous_context_keys: list[str] | None = None,
    existing_context: dict[str, dict[str, Any]] | None = None,
    remaining_context_keys: list[str] | None = None,
    enforce_target: bool = False,
) -> dict[str, str]:
    payload = _live_payload(
        profile,
        {
            "question_type": question_type,
            "target_context_key": target_context_key or fallback_key,
            "fallback_question": fallback_question,
            "fallback_requested_context_key": fallback_key,
            "previous_questions": previous_questions or [],
            "previous_requested_context_keys": previous_context_keys or [],
            "existing_context": existing_context or {},
            "remaining_context_keys_to_cover": remaining_context_keys or [],
            "known_private_context_labels": [fact.split(":")[0] for fact in profile.private_context_facts],
            "unknown_or_undecided_facts": profile.unknown_or_undecided_facts,
            "instruction": (
                "Ask one concise user-facing question for the target_context_key. "
                "Do not repeat or paraphrase any previous question or requested context key. "
                "If this is global elicitation, spread questions across different planning dimensions "
                "such as people/preferences, schedule, resources, location, budget, and constraints."
            ),
        },
    )
    response = parse_workflow_stage_live(
        prompt["rendered_prompt"],
        payload,
        WorkflowLiveQuestionResponse,
        model=_workflow_model(model),
    )
    if response is None:
        return {"question": fallback_question, "requested_context_key": fallback_key}
    question = response.question.strip() or fallback_question
    requested_key = response.requested_context_key.strip() or fallback_key
    if _should_use_fallback_question(
        question,
        requested_key,
        fallback_key,
        previous_questions or [],
        previous_context_keys or [],
        enforce_target=enforce_target,
    ):
        return {"question": fallback_question, "requested_context_key": fallback_key}
    return {"question": question, "requested_context_key": requested_key}


def _should_use_fallback_question(
    question: str,
    requested_key: str,
    fallback_key: str,
    previous_questions: list[str],
    previous_context_keys: list[str],
    enforce_target: bool,
) -> bool:
    if not question.strip() or not requested_key.strip():
        return True
    if any(_similar_context_request(question, previous, threshold=0.5) for previous in previous_questions):
        return True
    if any(_similar_context_request(requested_key, previous_key, threshold=0.5) for previous_key in previous_context_keys):
        return True
    if enforce_target and not (
        _similar_context_request(requested_key, fallback_key, threshold=0.25)
        or _similar_context_request(question, fallback_key, threshold=0.25)
    ):
        return True
    return False


def _similar_context_request(left: str, right: str, threshold: float) -> bool:
    left_tokens = set(_context_request_tokens(left))
    right_tokens = set(_context_request_tokens(right))
    if not left_tokens or not right_tokens:
        return False
    overlap = left_tokens & right_tokens
    return len(overlap) / min(len(left_tokens), len(right_tokens)) >= threshold


def _context_request_tokens(text: str) -> list[str]:
    generic = {
        "about",
        "account",
        "available",
        "context",
        "could",
        "current",
        "detail",
        "goal",
        "have",
        "know",
        "list",
        "main",
        "need",
        "night",
        "phd",
        "plan",
        "planning",
        "provide",
        "question",
        "should",
        "specific",
        "students",
        "user",
        "what",
    }
    return [token.strip(".,?!:;()[]{}\"'").lower() for token in _key_tokens(text) if token.lower() not in generic]


def _live_task_nodes(
    profile: SimulationProfile,
    prompt: dict[str, str],
    model: str,
    fallback_nodes: list[dict[str, str]],
    parent_node_id: str | None = None,
) -> list[dict[str, str]]:
    payload = _live_payload(
        profile,
        {
            "fallback_nodes": fallback_nodes,
            "parent_node_id": parent_node_id,
            "approval_criteria": profile.approval_criteria,
            "instruction": "Return 2-4 concise task nodes. Each node must have a title and description only.",
        },
    )
    response = parse_workflow_stage_live(
        prompt["rendered_prompt"],
        payload,
        WorkflowLiveTaskDecompositionResponse,
        model=_workflow_model(model),
    )
    if response is None:
        return fallback_nodes
    nodes = []
    for index, node in enumerate(response.nodes[:4], start=1):
        title = node.title.strip()
        description = node.description.strip()
        if not title or not description:
            continue
        node_id = f"{parent_node_id}.{index}" if parent_node_id else f"N{index}"
        nodes.append({"node_id": node_id, "title": title, "description": description})
    return nodes or fallback_nodes


def _live_subtask_detection(
    profile: SimulationProfile,
    node: dict[str, str],
    prompt: dict[str, str],
    model: str,
    fallback: dict[str, str],
) -> dict[str, str]:
    payload = _live_payload(
        profile,
        {
            "node": node,
            "available_actions": ["draft_answer", "decompose_further"],
            "fallback": fallback,
            "instruction": "Choose whether this node is concrete enough to draft now or should be decomposed further.",
        },
    )
    response = parse_workflow_stage_live(
        prompt["rendered_prompt"],
        payload,
        WorkflowLiveSubtaskDetectionResponse,
        model=_workflow_model(model),
    )
    if response is None:
        return fallback
    return {"suggested_action": response.suggested_action, "rationale": response.rationale.strip() or fallback["rationale"]}


def _live_task_forking(
    profile: SimulationProfile,
    node: dict[str, str],
    context_bank: dict[str, dict[str, Any]],
    prompt: dict[str, str],
    model: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    payload = _live_payload(
        profile,
        {
            "node": node,
            "available_context": context_bank,
            "fallback": fallback,
            "instruction": (
                "Decide if the task should be forked across entities from available context. "
                "Answer Yes only when the context bank already contains a concrete list of entities "
                "to iterate over. Do not invent placeholder entities such as Entity 1 or Entity 2."
            ),
        },
    )
    response = parse_workflow_stage_live(
        prompt["rendered_prompt"],
        payload,
        WorkflowLiveTaskForkingResponse,
        model=_workflow_model(model),
    )
    if response is None:
        return _validated_task_forking_decision(fallback, context_bank, node)
    source_context_id = response.entity_source_context_id
    if source_context_id not in context_bank:
        source_context_id = fallback.get("entity_source_context_id")
    entities = [entity.strip() for entity in response.entities if entity.strip()]
    if response.answer == "Yes" and not entities:
        entities = fallback.get("entities", [])
    return _validated_task_forking_decision(
        {
            "answer": response.answer,
            "reason": response.reason.strip() or fallback.get("reason", ""),
            "entity_source_context_id": source_context_id,
            "entities": entities[:8],
        },
        context_bank,
        node,
    )


def _live_select_fork_context(
    profile: SimulationProfile,
    node: dict[str, str],
    context_bank: dict[str, dict[str, Any]],
    prompt: dict[str, str],
    model: str,
    fallback_context_id: str | None,
) -> str | None:
    selection = _live_context_selection(
        profile,
        "full_jumpstarter",
        context_bank,
        node,
        prompt,
        model,
        fallback_ids=[fallback_context_id] if fallback_context_id else [],
        fallback_reason="fallback entity context selection",
        max_selected=1,
    )
    selected_context_id = selection["selected_context_ids"][0] if selection["selected_context_ids"] else None
    if _fork_entities_from_context(context_bank.get(str(selected_context_id), {})):
        return selected_context_id
    if _fork_entities_from_context(context_bank.get(str(fallback_context_id), {})):
        return fallback_context_id
    return None


def _live_context_selection(
    profile: SimulationProfile,
    condition: Condition,
    context_bank: dict[str, dict[str, Any]],
    node: dict[str, str],
    prompt: dict[str, str],
    model: str,
    fallback_ids: list[str],
    fallback_reason: str,
    max_selected: int | None = None,
) -> dict[str, Any]:
    relevance_hints = _ranked_context_candidates(context_bank, node)
    selection_instruction = (
        f"Select up to {max_selected} context IDs that are directly useful for this node."
        if max_selected is not None
        else "Select every context ID that is directly useful for this node."
    )
    payload = _live_payload(
        profile,
        {
            "condition": condition,
            "node": node,
            "available_context_ids": list(context_bank),
            "available_context": context_bank,
            "fallback_selected_context_ids": fallback_ids,
            "candidate_relevance_hints": [
                {
                    "context_id": context_id,
                    "label": str(context_bank[context_id].get("label", context_id)),
                    "relevance_score": score,
                }
                for context_id, score in relevance_hints
            ],
            "instruction": (
                f"{selection_instruction} "
                "Prefer context whose label or value is relevant to the current subtask's concrete "
                "decision or artifact. Exclude contexts that are unknown, undecided, or unrelated."
            ),
        },
    )
    response = parse_workflow_stage_live(
        prompt["rendered_prompt"],
        payload,
        WorkflowLiveContextSelectionResponse,
        model=_workflow_model(model),
    )
    if response is None:
        fallback_selection = fallback_ids[:max_selected] if max_selected is not None else fallback_ids
        return {"selected_context_ids": fallback_selection, "selection_reason": fallback_reason}
    valid_ids = [
        context_id
        for context_id in response.selected_context_ids
        if context_id in context_bank and _is_substantive_context(context_bank.get(context_id, {}))
    ]
    relevant_ids = {context_id for context_id, score in relevance_hints if score > CONTEXT_RELEVANCE_THRESHOLD}
    relevant_valid_ids = [context_id for context_id in valid_ids if context_id in relevant_ids]
    valid_ids = relevant_valid_ids
    if not valid_ids:
        valid_ids = fallback_ids
    selected_context_ids = valid_ids[:max_selected] if max_selected is not None else valid_ids
    return {
        "selected_context_ids": selected_context_ids,
        "selection_reason": response.selection_reason.strip() or fallback_reason,
    }


def _live_draft(
    profile: SimulationProfile,
    node: dict[str, str],
    reused_contexts: dict[str, dict[str, Any]],
    prompt: dict[str, str],
    model: str,
    fallback_draft: str,
    context_digest: dict[str, Any] | None = None,
) -> str:
    if context_digest is None:
        context_digest = _context_digest_for_node(profile, node, reused_contexts, reused_contexts)
    payload = _live_payload(
        profile,
        {
            "node": node,
            "reused_context": reused_contexts,
            "context_digest": context_digest,
            "approval_criteria": profile.approval_criteria,
            "fallback_draft": fallback_draft,
            "instruction": (
                "Write the actual reusable artifact for this node. Do not say what to draft; draft it. "
                "Use facts_to_use and drafts_to_build_on from context_digest as concrete inputs. "
                "Preserve open_decisions as explicit fields to fill instead of inventing facts. "
                "Produce tables, templates, checklists, schedules, or message drafts when the task calls for them."
            ),
        },
    )
    response = parse_workflow_stage_live(
        prompt["rendered_prompt"],
        payload,
        WorkflowLiveDraftResponse,
        model=_workflow_model(model),
    )
    if response is None:
        return fallback_draft
    return response.draft.strip() or fallback_draft


def _live_payload(profile: SimulationProfile, extra: dict[str, Any]) -> str:
    payload = {
        "goal_text": profile.goal_text,
        "persona_id": profile.persona_id,
        "simulation_profile_id": profile.simulation_profile_id,
        "stable_persona_traits": profile.stable_persona_traits.model_dump(),
        "private_context_facts_available_to_simulated_user": profile.private_context_facts,
        "unknown_or_undecided_facts": profile.unknown_or_undecided_facts,
        "must_reveal_if_asked": profile.must_reveal_if_asked,
        "approval_criteria": profile.approval_criteria,
        **extra,
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def workflow_fidelity_report(sessions: list[WorkflowSession]) -> WorkflowFidelityReport:
    errors: list[str] = []
    warnings: list[str] = []
    if not sessions:
        errors.append("No workflow sessions were generated")

    user_answers: list[str] = []
    front_loading_events = 0
    unknown_answer_events = 0
    pushback_events = 0
    approval_events = 0
    private_fact_leakage_events = 0
    subtask_detection_events = 0
    decompose_further_events = 0
    task_forking_detection_events = 0
    task_forking_events = 0
    context_selection_events = 0
    saved_local_context_events = 0
    completed_subtasks = 0
    stage_counter: Counter[str] = Counter()
    sessions_with_pushback_and_approval: list[str] = []

    for session in sessions:
        stage_counter.update(event.stage for event in session.events)
        if not any(event.event_type == "goal_input" for event in session.events):
            errors.append(f"{session.session_id} missing goal_input event")
        is_chatgpt_baseline = session.condition == "chatgpt_vanilla" or session.condition.startswith("chatgpt_with_")
        is_agent_baseline = session.condition in {
            "adapt_recursive_decomposition",
            "ask_before_plan",
            "unstructured_memory_rag",
            "long_context_planner",
            "react_integrated_planner",
        }
        is_single_turn_baseline = session.condition == "single_turn_decomposition"
        if session.condition.startswith("chatgpt_with_") or is_single_turn_baseline:
            _validate_workflow_stage(session, "global_context_elicitation", errors)
            _validate_workflow_stage(session, "one_shot_response", errors)
        if is_agent_baseline:
            if session.condition == "adapt_recursive_decomposition":
                _validate_workflow_stage(session, "environment_observation", errors)
            if session.condition == "ask_before_plan":
                _validate_workflow_stage(session, "environment_execution", errors)
                _validate_workflow_stage(session, "global_context_elicitation", errors)
                _validate_workflow_stage(session, "planning_agent", errors)
            if session.condition == "unstructured_memory_rag":
                _validate_workflow_stage(session, "memory_retrieval", errors)
            if session.condition == "long_context_planner":
                _validate_workflow_stage(session, "long_context_assembly", errors)
            if session.condition == "react_integrated_planner":
                _validate_workflow_stage(session, "global_context_elicitation", errors)
                _validate_workflow_stage(session, "agentic_retrieval", errors)
            _validate_workflow_stage(session, "task_decomposition", errors)
            _validate_workflow_stage(session, "subtask_detection", errors)
            _validate_workflow_stage(session, "context_selection", errors)
            _validate_workflow_stage(session, "context_reuse", errors)
        elif not is_chatgpt_baseline and not is_single_turn_baseline:
            if session.condition != "no_elicitation":
                _validate_workflow_stage(session, "global_context_elicitation", errors)
            _validate_workflow_stage(session, "task_decomposition", errors)
            _validate_workflow_stage(session, "subtask_detection", errors)
            if any(event.event_type == "task_forking_detection" for event in session.events):
                _validate_workflow_stage(session, "task_forking_detection", errors)
            _validate_workflow_stage(session, "context_selection", errors)
            _validate_workflow_stage(session, "context_reuse", errors)
            if session.condition != "no_elicitation":
                _validate_workflow_stage(session, "local_context_elicitation", errors)
        for event in session.events:
            if event.event_type in {"global_context_answer", "local_context_answer"}:
                answer = str(event.payload.get("answer", ""))
                user_answers.append(answer)
                if event.payload.get("answer_status") == "unknown":
                    unknown_answer_events += 1
                if len(_words(answer)) > 35:
                    front_loading_events += 1
            if event.event_type == "draft_review" and event.payload.get("action") == "pushback":
                pushback_events += 1
            if event.event_type == "final_artifact_review" and event.payload.get("action") == "approve":
                approval_events += 1
            if event.event_type == "subtask_detection":
                subtask_detection_events += 1
                if event.payload.get("suggested_action") == "decompose_further":
                    decompose_further_events += 1
            if event.event_type == "task_forking_detection":
                task_forking_detection_events += 1
            if event.event_type == "task_forking_decomposition":
                task_forking_events += 1
            if event.event_type == "context_selection":
                context_selection_events += 1
            if event.event_type == "saved_local_context":
                saved_local_context_events += 1
        completed_subtasks += len(session.final_state.get("completed_nodes", []))
        session_has_pushback = any(
            event.event_type == "draft_review" and event.payload.get("action") == "pushback"
            for event in session.events
        )
        session_has_approval = any(
            event.event_type == "final_artifact_review" and event.payload.get("action") == "approve"
            for event in session.events
        )
        if session_has_pushback and session_has_approval:
            sessions_with_pushback_and_approval.append(session.session_id)
        serialized = session.model_dump_json().lower()
        if "prior source-task details should not be used" in serialized and ("game night" in serialized or "phd students" in serialized):
            private_fact_leakage_events += 1

    if sessions_with_pushback_and_approval:
        warnings.append(
            "Some sessions had pushback events but still reached final approval; inspect traces for lenient acceptance: "
            + ", ".join(sessions_with_pushback_and_approval[:10])
        )

    word_counts = [len(_words(answer)) for answer in user_answers]
    return WorkflowFidelityReport(
        valid=not errors,
        total_sessions=len(sessions),
        condition_counts=dict(Counter(session.condition for session in sessions)),
        average_user_response_words=round(sum(word_counts) / len(word_counts), 2) if word_counts else 0.0,
        max_user_response_words=max(word_counts) if word_counts else 0,
        front_loading_events=front_loading_events,
        unknown_answer_events=unknown_answer_events,
        pushback_events=pushback_events,
        approval_events=approval_events,
        private_fact_leakage_events=private_fact_leakage_events,
        subtask_detection_events=subtask_detection_events,
        decompose_further_events=decompose_further_events,
        task_forking_detection_events=task_forking_detection_events,
        task_forking_events=task_forking_events,
        context_selection_events=context_selection_events,
        saved_local_context_events=saved_local_context_events,
        completed_subtasks=completed_subtasks,
        stage_counts=dict(stage_counter),
        errors=errors,
        warnings=warnings,
    )


def _build_session(
    profile: SimulationProfile,
    condition: Condition,
    seed: int,
    events: list[WorkflowEvent],
    context_bank: dict[str, dict[str, Any]],
    node_selected_contexts: dict[str, list[str]],
    node_drafts: dict[str, str],
    completed_nodes: list[str],
    subtask_detection_decisions: dict[str, dict[str, Any]],
    nested_task_nodes: dict[str, list[dict[str, str]]],
    task_forking_decisions: dict[str, dict[str, Any]],
    final_artifact: str | None = None,
) -> WorkflowSession:
    final_state = {
        "context_bank": context_bank,
        "context_bank_size": len(context_bank),
        "task_tree": [event.payload["nodes"] for event in events if event.event_type == "task_decomposition"],
        "subtask_detection_decisions": subtask_detection_decisions,
        "nested_task_nodes": nested_task_nodes,
        "task_forking_decisions": task_forking_decisions,
        "node_selected_contexts": node_selected_contexts,
        "node_drafts": node_drafts,
        "completed_nodes": completed_nodes,
        "approval_status": _final_approval_status(events, completed_nodes, node_drafts),
    }
    if final_artifact and final_artifact.strip():
        final_state["final_artifact"] = final_artifact
    return WorkflowSession(
        session_id=f"{profile.simulation_profile_id}_{condition}_seed{seed}",
        condition=condition,
        simulation_profile_id=profile.simulation_profile_id,
        persona_id=profile.persona_id,
        goal_id=profile.goal_id,
        goal_text=profile.goal_text,
        seed=seed,
        events=events,
        final_state=final_state,
    )


def _final_approval_status(
    events: list[WorkflowEvent],
    completed_nodes: list[str],
    node_drafts: dict[str, str],
) -> str:
    for event in reversed(events):
        if event.event_type == "final_artifact_review":
            status = event.payload.get("approval_status")
            if isinstance(status, str) and status:
                return status
    return "approved" if completed_nodes and len(completed_nodes) == len(node_drafts) else "not_ready"


def _compile_full_jumpstarter_final_artifact(
    profile: SimulationProfile,
    context_bank: dict[str, dict[str, Any]],
    node_drafts: dict[str, str],
    node_selected_contexts: dict[str, list[str]],
    completed_nodes: list[str],
    model: str,
    live_stages: LiveStageMode,
) -> dict[str, Any]:
    package = _final_artifact_compiler_package(profile, context_bank, node_drafts, node_selected_contexts, completed_nodes)
    final_artifact = _deterministic_compiled_final_artifact(profile, package)
    generation_mode = "deterministic"
    compiler_prompt: dict[str, Any] | None = None
    if _live_enabled(live_stages, "working_solution_draft_creation"):
        prompt_text = _final_artifact_compiler_prompt()
        compiler_prompt = {
            "prompt_id": "final_artifact_compiler",
            "prompt_version": PROMPT_VERSION,
            "rendered_prompt": prompt_text,
        }
        final_artifact = _live_final_artifact_compiler(
            profile,
            package,
            prompt_text,
            model,
            fallback_artifact=final_artifact,
        )
        generation_mode = "live"
    final_artifact = _ensure_compiler_coverage(final_artifact, profile, package)

    return {
        "final_artifact": final_artifact,
        "generation_mode": generation_mode,
        "confirmed_context_ids": [item["context_id"] for item in package["confirmed_contexts"]],
        "todo_context_ids": [item["context_id"] for item in package["todo_contexts"]],
        "selected_context_ids": package["selected_context_ids"],
        "reused_context_ids": package["reused_context_ids"],
        "completed_nodes": completed_nodes,
        "draft_node_ids": list(node_drafts),
        "todo_items": package["todo_items"],
        "assumptions_avoided": package["assumptions_avoided"],
        "reusable_artifact_count": len(package["reusable_artifacts"]),
        "subtask_coverage_map": package["subtask_coverage_map"],
        "coverage_warnings": package["coverage_warnings"],
        "compiler_prompt": compiler_prompt,
    }


def _final_artifact_compiler_package(
    profile: SimulationProfile,
    context_bank: dict[str, dict[str, Any]],
    node_drafts: dict[str, str],
    node_selected_contexts: dict[str, list[str]],
    completed_nodes: list[str],
) -> dict[str, Any]:
    selected_context_ids = _unique_strings(
        [context_id for ids in node_selected_contexts.values() for context_id in ids]
    )
    draft_source_ids = _unique_strings(
        [
            str(source_id)
            for context in context_bank.values()
            for source_id in context.get("source_context_ids", [])
            if isinstance(context, dict)
        ]
    )
    reused_context_ids = _unique_strings(draft_source_ids + selected_context_ids)
    confirmed_contexts = _prioritized_context_items(
        context_bank,
        priority_ids=reused_context_ids + selected_context_ids,
        include_drafts=False,
    )
    todo_contexts = _unknown_context_items(context_bank)
    todo_items = _final_artifact_todo_items(profile, context_bank, node_drafts, todo_contexts)
    assumptions_avoided = _final_artifact_assumptions_avoided(todo_contexts, todo_items)
    draft_artifacts = [
        {
            "node_id": node_id,
            "title": _draft_title(node_id, draft),
            "text": _clean_draft_for_final_artifact(draft),
            "raw_text": draft,
            "selected_context_ids": node_selected_contexts.get(node_id, []),
            "completed": node_id in completed_nodes,
        }
        for node_id, draft in node_drafts.items()
    ]
    reusable_artifacts = _reusable_artifacts_from_drafts(draft_artifacts, profile.approval_criteria)
    subtask_coverage_map = _subtask_coverage_map(draft_artifacts, context_bank)
    coverage_warnings = _compiler_coverage_warnings(profile, reusable_artifacts, draft_artifacts)
    return {
        "goal_text": profile.goal_text,
        "approval_criteria": profile.approval_criteria,
        "selected_context_ids": selected_context_ids,
        "reused_context_ids": reused_context_ids,
        "confirmed_contexts": confirmed_contexts[:12],
        "todo_contexts": todo_contexts[:12],
        "todo_items": todo_items[:12],
        "assumptions_avoided": assumptions_avoided[:8],
        "draft_artifacts": draft_artifacts,
        "reusable_artifacts": reusable_artifacts[:8],
        "subtask_coverage_map": subtask_coverage_map,
        "coverage_warnings": coverage_warnings,
    }


def _deterministic_compiled_final_artifact(profile: SimulationProfile, package: dict[str, Any]) -> str:
    confirmed_lines = [item["text"] for item in package["confirmed_contexts"]] or [
        "No confirmed user-specific context was available; concrete details remain marked as TODO."
    ]
    todo_items = package["todo_items"] or ["Review once more for owner, deadline, and unstated constraints before use."]
    assumptions = package["assumptions_avoided"] or [
        "No unsupported dates, names, contact details, capacities, or policies were introduced."
    ]
    deliverable_lines = _final_deliverable_overview(profile, package, confirmed_lines)
    reusable_lines = _reusable_artifact_markdown(package["reusable_artifacts"])
    coverage_lines = _subtask_coverage_markdown(package["subtask_coverage_map"])
    coverage_warning_lines = package.get("coverage_warnings") or []

    sections = [
        f"# {profile.goal_text} - Final JumpStarter Deliverable",
        "",
        "## Confirmed Inputs Used",
        *_bullet_lines(confirmed_lines[:10]),
        "",
        "## Final Deliverable",
        *deliverable_lines,
        "",
        "## Reusable Artifacts",
        *reusable_lines,
        "",
        "## Subtask Coverage Map",
        *coverage_lines,
        *(_compiler_warning_markdown(coverage_warning_lines) if coverage_warning_lines else []),
        "",
        "## TODO Before Use",
        *_bullet_lines(todo_items[:10]),
        "",
        "## Assumptions Avoided",
        *_bullet_lines(assumptions[:8]),
    ]
    return _sanitize_compiled_artifact("\n".join(sections))


def _final_artifact_compiler_prompt() -> str:
    return (
        "You are compiling a JumpStarter workflow into one polished final deliverable. "
        "Use confirmed_contexts as the only source of concrete facts. Use draft_artifacts as source material, "
        "but rewrite them into a coherent artifact instead of concatenating process notes. Remove all local "
        "refinement notes, context-reuse notes, acceptance checks, duplicated sections, and stale open decisions. "
        "Preserve concrete reusable artifacts from reusable_artifacts, such as templates, message drafts, trackers, "
        "tables, schedules, worksheets, and checklists. Keep the final answer compact but substantial: target "
        "650-850 words unless the provided artifacts are shorter. "
        "If a detail is unknown, unsupported, or only appears as a placeholder, keep it in TODO Before Use. "
        "Do not invent dates, venue names, capacities, contact information, deadlines, policies, or personal facts. "
        "If a draft asks to confirm a fact that is already in confirmed_contexts, replace the prompt with the confirmed value. "
        "Return one polished markdown deliverable with these sections: Confirmed Inputs Used, Final Deliverable, "
        "Reusable Artifacts, Subtask Coverage Map, TODO Before Use, Assumptions Avoided."
    )


def _live_final_artifact_compiler(
    profile: SimulationProfile,
    package: dict[str, Any],
    prompt_text: str,
    model: str,
    fallback_artifact: str,
) -> str:
    payload = json.dumps(package, ensure_ascii=True, sort_keys=True)
    response = parse_workflow_stage_live(
        prompt_text,
        payload,
        WorkflowLiveDraftResponse,
        model=_workflow_model(model),
    )
    if response is None:
        return fallback_artifact
    return _sanitize_compiled_artifact(response.draft.strip() or fallback_artifact)


def _ensure_compiler_coverage(final_artifact: str, profile: SimulationProfile, package: dict[str, Any]) -> str:
    artifact = _sanitize_compiled_artifact(final_artifact)
    lowered = artifact.lower()
    missing_sections: list[str] = []
    if "## reusable artifacts" not in lowered:
        missing_sections.extend(["", "## Reusable Artifacts", *_reusable_artifact_markdown(package["reusable_artifacts"])])
    if "## subtask coverage map" not in lowered:
        missing_sections.extend(["", "## Subtask Coverage Map", *_subtask_coverage_markdown(package["subtask_coverage_map"])])
    if missing_sections:
        artifact = _sanitize_compiled_artifact(artifact + "\n" + "\n".join(missing_sections))

    artifact_lowered = artifact.lower()
    missing_reusable = [
        item
        for item in package.get("reusable_artifacts", [])
        if str(item.get("title", "")).strip().lower() not in artifact_lowered
    ]
    if missing_reusable:
        artifact = _append_section_block(artifact, "Reusable Artifacts", _reusable_artifact_markdown(missing_reusable))

    artifact_lowered = artifact.lower()
    missing_coverage_rows = [
        row
        for row in package.get("subtask_coverage_map", [])
        if str(row.get("subtask", "")).strip().lower() not in artifact_lowered
    ]
    if missing_coverage_rows:
        artifact = _append_section_block(artifact, "Subtask Coverage Map", _subtask_coverage_markdown(missing_coverage_rows))

    repaired_lowered = artifact.lower()
    missing_targets = [
        target
        for target in _approval_artifact_targets(profile.approval_criteria)
        if target.lower() not in repaired_lowered
    ]
    if missing_targets:
        artifact = _append_section_items(
            artifact,
            "TODO Before Use",
            [f"Coverage check: complete or verify {target} before treating the deliverable as final." for target in missing_targets],
        )

    if len(_words(artifact)) < 650 and package.get("draft_artifacts"):
        expansion_lines = ["", "## Source Draft Highlights"]
        for draft in package["draft_artifacts"][:4]:
            text = str(draft.get("text", "")).strip()
            if text and text.lower() not in artifact.lower():
                expansion_lines.extend(["", f"### {draft['title']}", "", _trim_words(text, 90)])
        artifact = _sanitize_compiled_artifact(artifact + "\n" + "\n".join(expansion_lines))

    return _sanitize_compiled_artifact(_remove_irrelevant_compiler_lines(artifact, profile))


def _reusable_artifacts_from_drafts(
    draft_artifacts: list[dict[str, Any]],
    approval_criteria: list[str],
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    seen: set[str] = set()
    targets = _approval_artifact_targets(approval_criteria)
    for draft in draft_artifacts:
        text = str(draft.get("raw_text") or draft.get("text", "")).strip()
        reusable_text = _extract_reusable_artifact_text(text) or str(draft.get("text", "")).strip()
        reusable_text = _sanitize_compiled_artifact(reusable_text)
        if not reusable_text:
            continue
        title = str(draft.get("title", "")).strip() or str(draft.get("node_id", "Artifact"))
        target = _best_matching_target(title + "\n" + reusable_text, targets)
        artifact_title = target.title() if target else title
        key = re.sub(r"\s+", " ", (artifact_title + " " + reusable_text[:240]).lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(
            {
                "node_id": str(draft.get("node_id", "")),
                "title": artifact_title[:90],
                "text": _trim_words(reusable_text, 150),
            }
        )
    return artifacts


def _final_deliverable_overview(
    profile: SimulationProfile,
    package: dict[str, Any],
    confirmed_lines: list[str],
) -> list[str]:
    reusable_titles = [item["title"] for item in package.get("reusable_artifacts", [])]
    coverage_rows = package.get("subtask_coverage_map", [])
    lines = [
        f"**Objective:** {profile.goal_text}",
        "",
        "Use this as the working packet: confirmed facts stay fixed, reusable artifacts are ready to customize, and unresolved details stay in TODO rather than being guessed.",
        "",
        "**Primary outputs preserved:**",
        *_bullet_lines(reusable_titles[:6] or ["Compiled planning artifact"]),
        "",
        "**Confirmed constraints to honor:**",
        *_bullet_lines(confirmed_lines[:5]),
        "",
        "**Recommended work sequence:**",
        *_numbered_lines([row["subtask"] for row in coverage_rows[:6]] or ["Review reusable artifacts", "Resolve TODOs", "Finalize and use"]),
    ]
    return lines


def _extract_reusable_artifact_text(text: str) -> str:
    marker_match = re.search(r"(?im)^reusable artifact:\s*$", text)
    if not marker_match:
        return ""
    start = marker_match.end()
    end = len(text)
    for stop_match in re.finditer(r"(?im)^(next steps|open decisions before finalizing|acceptance check|local refinement):\s*$", text[start:]):
        end = start + stop_match.start()
        break
    return text[start:end].strip()


def _subtask_coverage_map(
    draft_artifacts: list[dict[str, Any]],
    context_bank: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for draft in draft_artifacts:
        selected_ids = [str(context_id) for context_id in draft.get("selected_context_ids", [])]
        context_labels = [
            str(context_bank.get(context_id, {}).get("label", context_id)).strip() or context_id
            for context_id in selected_ids
            if context_id in context_bank
        ]
        text = str(draft.get("text", "")).strip()
        rows.append(
            {
                "node_id": str(draft.get("node_id", "")),
                "subtask": str(draft.get("title", "")).strip()[:80],
                "artifact_produced": _artifact_summary(text),
                "context_used": ", ".join(context_labels[:4]) if context_labels else "No selected context reused",
                "status": "completed" if draft.get("completed") else "drafted",
                "remaining_todo": _draft_remaining_todo(str(draft.get("raw_text", ""))),
            }
        )
    return rows


def _compiler_coverage_warnings(
    profile: SimulationProfile,
    reusable_artifacts: list[dict[str, str]],
    draft_artifacts: list[dict[str, Any]],
) -> list[str]:
    artifact_text = "\n".join(item["title"] + "\n" + item["text"] for item in reusable_artifacts)
    warnings: list[str] = []
    for target in _approval_artifact_targets(profile.approval_criteria):
        if target.lower() not in artifact_text.lower():
            warnings.append(f"Expected artifact not visibly preserved yet: {target}.")
    if len(reusable_artifacts) < max(1, min(3, len(draft_artifacts))):
        warnings.append("Compiler preserved fewer reusable artifacts than drafted subtasks; inspect final artifact breadth.")
    return _unique_strings(warnings)


def _reusable_artifact_markdown(reusable_artifacts: list[dict[str, str]]) -> list[str]:
    if not reusable_artifacts:
        return ["- No concrete reusable artifact was available from completed drafts."]
    lines: list[str] = []
    for artifact in reusable_artifacts:
        lines.extend(["", f"### {artifact['title']}", "", artifact["text"]])
    return lines


def _subtask_coverage_markdown(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["No subtasks were completed before final compilation."]
    lines = [
        "| Subtask | Artifact Produced | Context Used | Status | Remaining TODO |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                _table_cell(row[key])
                for key in ("subtask", "artifact_produced", "context_used", "status", "remaining_todo")
            )
            + " |"
        )
    return lines


def _compiler_warning_markdown(warnings: list[str]) -> list[str]:
    return ["", "Coverage checks:", *_bullet_lines(warnings[:6])]


def _append_section_items(artifact: str, section_title: str, items: list[str]) -> str:
    if not items:
        return artifact
    section_header = f"## {section_title}"
    if section_header not in artifact:
        return artifact + "\n\n" + section_header + "\n" + "\n".join(_bullet_lines(items))
    lines = artifact.splitlines()
    output: list[str] = []
    inserted = False
    in_section = False
    for line in lines:
        if line.strip() == section_header:
            in_section = True
            output.append(line)
            continue
        if in_section and line.startswith("## ") and line.strip() != section_header:
            output.extend(_bullet_lines(items))
            inserted = True
            in_section = False
        output.append(line)
    if in_section and not inserted:
        output.extend(_bullet_lines(items))
    return "\n".join(output)


def _append_section_block(artifact: str, section_title: str, block_lines: list[str]) -> str:
    if not block_lines:
        return artifact
    section_header = f"## {section_title}"
    if section_header not in artifact:
        return artifact + "\n\n" + section_header + "\n" + "\n".join(block_lines)
    lines = artifact.splitlines()
    output: list[str] = []
    inserted = False
    in_section = False
    for line in lines:
        if line.strip() == section_header:
            in_section = True
            output.append(line)
            continue
        if in_section and line.startswith("## ") and line.strip() != section_header:
            output.extend(["", *block_lines])
            inserted = True
            in_section = False
        output.append(line)
    if in_section and not inserted:
        output.extend(["", *block_lines])
    return "\n".join(output)


def _remove_irrelevant_compiler_lines(artifact: str, profile: SimulationProfile) -> str:
    domain_text = f"{profile.goal_text}\n" + "\n".join(profile.approval_criteria)
    domain_tokens = set(_key_tokens(domain_text))
    keep_lines: list[str] = []
    for line in artifact.splitlines():
        lowered = line.lower()
        is_venue_boilerplate = (
            ("venue/resource" in lowered or ("venue" in lowered and "capacity" in lowered))
            and not (domain_tokens & {"venue", "event", "room", "location", "reunion", "apartment", "sublease", "moving"})
        )
        if is_venue_boilerplate:
            continue
        keep_lines.append(line)
    return "\n".join(keep_lines)


def _approval_artifact_targets(approval_criteria: list[str]) -> list[str]:
    targets = []
    for criterion in approval_criteria:
        criterion = criterion.strip()
        if criterion.lower().startswith("includes "):
            targets.append(criterion[9:].strip())
    return _unique_strings([target for target in targets if target])


def _best_matching_target(text: str, targets: list[str]) -> str | None:
    text_tokens = set(_key_tokens(text))
    best: tuple[int, str] | None = None
    for target in targets:
        target_tokens = set(_key_tokens(target))
        score = len(text_tokens & target_tokens)
        if score and (best is None or score > best[0]):
            best = (score, target)
    return best[1] if best else None


def _artifact_summary(text: str) -> str:
    lowered = text.lower()
    artifacts = []
    for label, terms in (
        ("template", ("template", "draft message", "message draft", "email")),
        ("tracker/table", ("|", "tracker", "worksheet", "table")),
        ("checklist", ("checklist", "- [ ]")),
        ("schedule/plan", ("schedule", "calendar", "timeline", "plan")),
    ):
        if any(term in lowered for term in terms):
            artifacts.append(label)
    if artifacts:
        return ", ".join(_unique_strings(artifacts))
    first_line = next((line.strip("# -") for line in text.splitlines() if line.strip()), "")
    return first_line[:80] or "Draft artifact"


def _draft_remaining_todo(raw_text: str) -> str:
    match = re.search(r"(?is)^open decisions before finalizing:\s*(.*?)(?:^acceptance check:|\Z)", raw_text, flags=re.MULTILINE)
    if not match:
        return "Review unresolved owner/date/constraints"
    lines = [
        line.strip(" -\t")
        for line in match.group(1).splitlines()
        if line.strip(" -\t")
    ]
    return "; ".join(lines[:2])[:120] if lines else "Review unresolved owner/date/constraints"


def _table_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).replace("|", "/")).strip()


def _trim_words(text: str, max_words: int) -> str:
    words = _words(text)
    if len(words) <= max_words:
        return text.strip()
    pieces = re.findall(r"\S+\s*", text)
    kept: list[str] = []
    count = 0
    for piece in pieces:
        if re.search(r"\w", piece):
            count += 1
        if count > max_words:
            break
        kept.append(piece)
    return "".join(kept).rstrip() + " ..."


def _prioritized_context_items(
    context_bank: dict[str, dict[str, Any]],
    priority_ids: list[str],
    include_drafts: bool,
) -> list[dict[str, str]]:
    ordered_ids = _unique_strings(priority_ids + list(context_bank))
    items: list[dict[str, str]] = []
    seen_text: set[str] = set()
    for context_id in ordered_ids:
        context = context_bank.get(context_id)
        if not isinstance(context, dict):
            continue
        if not include_drafts and context.get("scope") == "draft":
            continue
        if not _is_substantive_context(context):
            continue
        label = str(context.get("label", context_id)).strip() or context_id
        value = str(context.get("value", "")).strip()
        text = value if ":" in value or label.lower() in value.lower() else f"{label}: {value}"
        if _looks_like_process_note(text):
            continue
        key = re.sub(r"\s+", " ", text.lower()).strip()
        if key in seen_text:
            continue
        seen_text.add(key)
        items.append({"context_id": context_id, "label": label, "text": text, "scope": str(context.get("scope", ""))})
    return items


def _unknown_context_items(context_bank: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    for context_id, context in context_bank.items():
        if not isinstance(context, dict) or context.get("scope") == "draft":
            continue
        value = str(context.get("value", "")).strip()
        if not value or _answer_status(value) != "unknown":
            continue
        label = str(context.get("label", context_id)).strip() or context_id
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        items.append({"context_id": context_id, "label": label, "value": value})
    return items


def _final_artifact_todo_items(
    profile: SimulationProfile,
    context_bank: dict[str, dict[str, Any]],
    node_drafts: dict[str, str],
    todo_contexts: list[dict[str, str]],
) -> list[str]:
    todos = [f"{item['label']}: still unknown; leave unfilled until confirmed." for item in todo_contexts]
    confirmed_labels = {
        str(context.get("label", "")).strip().lower()
        for context in context_bank.values()
        if isinstance(context, dict) and context.get("scope") != "draft" and _is_substantive_context(context)
    }
    for unknown in profile.unknown_or_undecided_facts:
        label = unknown.split(":", 1)[0].strip()
        if label and label.lower() not in confirmed_labels:
            todos.append(f"{label}: confirm before final use.")
    combined_drafts = "\n".join(node_drafts.values())
    if _contains_placeholder(combined_drafts):
        todos.append("Replace any remaining bracketed placeholders, TBD fields, names, contact details, dates, or deadlines before sending.")
    for topic in _unsupported_specific_risk_topics(combined_drafts):
        todos.append(f"Verify any unconfirmed {topic} against a real source before relying on them.")
    return _unique_strings(todos)


def _final_artifact_assumptions_avoided(todo_contexts: list[dict[str, str]], todo_items: list[str]) -> list[str]:
    assumptions = [
        f"Did not invent {item['label']}; kept it as a TODO because the user did not provide it."
        for item in todo_contexts[:6]
    ]
    if any("venue" in item.lower() or "capacity" in item.lower() or "location" in item.lower() for item in todo_items):
        assumptions.append("Did not treat venue names, capacities, or availability as confirmed without evidence.")
    if any("policy" in item.lower() or "permission" in item.lower() for item in todo_items):
        assumptions.append("Did not treat policies, permissions, or requirements as confirmed without evidence.")
    if any("cost" in item.lower() or "budget" in item.lower() or "fee" in item.lower() for item in todo_items):
        assumptions.append("Did not treat costs, fees, or budget figures as confirmed without evidence.")
    if any("date" in item.lower() or "deadline" in item.lower() or "schedule" in item.lower() for item in todo_items):
        assumptions.append("Did not treat dates, deadlines, or schedules as confirmed without evidence.")
    assumptions.append("Did not replace unknown personal preferences, dates, owners, contacts, or deadlines with guesses.")
    return _unique_strings(assumptions)


def _draft_title(node_id: str, draft: str) -> str:
    for line in draft.splitlines():
        stripped = line.strip().strip("#").strip()
        if not stripped:
            continue
        stripped = re.sub(r"\s+-\s+working artifact.*$", "", stripped, flags=re.IGNORECASE)
        return stripped[:90]
    return f"Compiled section for {node_id}"


def _clean_draft_for_final_artifact(draft: str) -> str:
    text = _strip_process_blocks(draft)
    marker = "Reusable artifact:"
    if marker in text:
        text = text.split(marker, 1)[1]
    for stop_marker in ("\nNext steps:", "\nOpen decisions before finalizing:", "\nAcceptance check:"):
        if stop_marker in text:
            text = text.split(stop_marker, 1)[0]
    return _sanitize_compiled_artifact(text.strip())


def _strip_process_blocks(text: str) -> str:
    text = re.sub(r"\nLocal refinement:\n.*?(?=\n\n[A-Z0-9][^\n]{0,90}:|\Z)", "", text, flags=re.DOTALL)
    lines: list[str] = []
    skip_section = False
    process_headers = {
        "context used as evidence:",
        "context not used as evidence:",
        "acceptance check:",
    }
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped in process_headers:
            skip_section = True
            continue
        if skip_section and stripped and not stripped.endswith(":"):
            continue
        if skip_section and (not stripped or stripped.endswith(":")):
            skip_section = False
        if _looks_like_process_note(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _sanitize_compiled_artifact(text: str) -> str:
    text = re.sub(r"\nLocal refinement:\n.*?(?=\n\n[A-Z0-9][^\n]{0,90}:|\Z)", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _contains_placeholder(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\[[^\]]+\]", text)) or any(
        marker in lowered
        for marker in ("tbd", "to be specified", "insert ", "your name", "your email", "open field")
    )


def _unsupported_specific_risk_topics(text: str) -> list[str]:
    lowered = text.lower()
    topics: list[str] = []
    if any(term in lowered for term in ("venue", "capacity", "reservation", "room booking")):
        topics.append("venue names, capacities, reservation rules, or availability")
    if any(term in lowered for term in ("policy", "permission", "requirement", "approval process")):
        topics.append("policies, permissions, requirements, or approval processes")
    if any(term in lowered for term in ("cost", "fee", "budget", "price")):
        topics.append("costs, fees, budget figures, or prices")
    if re.search(r"\brent\b", lowered):
        topics.append("rent or housing payment figures")
    if any(term in lowered for term in ("deadline", "date", "schedule", "calendar", "timeline")):
        topics.append("dates, deadlines, schedules, calendars, or timelines")
    if any(term in lowered for term in ("contact", "email", "phone", "linkedin")):
        topics.append("contact details, profiles, or communication channels")
    return _unique_strings(topics)


def _looks_like_process_note(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "local refinement",
            "reuse note",
            "replace the matching open field",
            "selected context digest",
            "context used as evidence",
            "context not used as evidence",
            "acceptance check",
        )
    )


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        value = str(value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _validate_workflow_stage(session: WorkflowSession, stage: str, errors: list[str]) -> None:
    if not any(event.stage == stage for event in session.events):
        errors.append(f"{session.session_id} missing {stage} stage")


def _global_needs(profile: SimulationProfile) -> list[str]:
    known_candidates: list[str] = []
    unknown_candidates: list[str] = []
    for fact in profile.private_context_facts:
        label = fact.split(":", 1)[0].strip()
        if ":" in fact and _useful_global_need(label):
            known_candidates.append(label)
    for need in profile.must_reveal_if_asked:
        label = need.split(":", 1)[0].strip()
        if _matches_private_context(label, profile.private_context_facts):
            known_candidates.append(label)
        else:
            unknown_candidates.append(label)
    for unknown in profile.unknown_or_undecided_facts:
        unknown_candidates.append(unknown.split(":", 1)[0].strip())

    known = sorted(_unique_context_needs(known_candidates), key=_global_need_rank)
    unknown = sorted(_unique_context_needs(unknown_candidates), key=_global_need_rank)
    needs = _unique_context_needs(known[:2] + unknown[:1] + known[2:] + unknown[1:])
    return needs[:3] or ["timeline", "preferences", "constraints"]


def _question_for_context_need(goal_text: str, need: str) -> str:
    label = need.split(":", 1)[0].strip()
    lowered = label.lower()
    if any(term in lowered for term in ("availability", "schedule", "time", "date", "deadline")):
        return f"What timing or availability constraints should I plan around for {goal_text}?"
    if any(term in lowered for term in ("interest", "preference", "game type", "format", "audience")):
        return f"What preferences or audience interests should shape {goal_text}?"
    if any(term in lowered for term in ("size", "participant", "attendee", "group")):
        return f"How many people should I plan for, and does that affect {goal_text}?"
    if any(term in lowered for term in ("location", "venue", "campus", "place")):
        return f"What location or venue constraints should I account for in {goal_text}?"
    if any(term in lowered for term in ("budget", "cost", "funding")):
        return f"What budget or cost constraints should I keep in mind for {goal_text}?"
    if any(term in lowered for term in ("document", "resume", "cv", "portfolio", "materials")):
        return f"What existing documents or materials can you provide for {goal_text}?"
    return f"What should I know about {label} for {goal_text}?"


def _useful_global_need(label: str) -> bool:
    lowered = label.lower()
    low_signal_terms = ("current goal requires", "goal time horizon")
    return bool(label) and not any(term in lowered for term in low_signal_terms)


def _matches_private_context(label: str, private_context_facts: list[str]) -> bool:
    return any(
        _similar_context_request(label, fact.split(":", 1)[0], threshold=0.4)
        or _similar_context_request(label, fact, threshold=0.4)
        for fact in private_context_facts
    )


def _unique_context_needs(candidates: list[str]) -> list[str]:
    unique: list[str] = []
    for candidate in candidates:
        cleaned = candidate.strip()
        if not cleaned:
            continue
        if any(_similar_context_request(cleaned, existing, threshold=0.6) for existing in unique):
            continue
        unique.append(cleaned)
    return unique


def _global_need_rank(need: str) -> tuple[int, str]:
    lowered = need.lower()
    priority_terms = (
        ("availability", "schedule", "time", "date", "deadline"),
        ("interest", "preference", "audience", "game type", "format"),
        ("size", "participant", "attendee", "group"),
        ("location", "venue", "campus", "place"),
        ("budget", "cost", "funding"),
        ("constraint", "requirement"),
    )
    for index, terms in enumerate(priority_terms):
        if any(term in lowered for term in terms):
            return (index, lowered)
    return (len(priority_terms), lowered)


def _task_forking_suggestion(
    profile: SimulationProfile,
    node: dict[str, str],
    context_bank: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    entities_by_context = {
        context_id: entities
        for context_id, context in context_bank.items()
        if (entities := _fork_entities_from_context(context))
    }
    node_tokens = set(_key_tokens(node["title"] + " " + node["description"]))
    fork_likely_terms = {
        "contact",
        "contacts",
        "outreach",
        "interview",
        "schools",
        "programs",
        "documents",
        "venues",
        "people",
        "participants",
        "applications",
    }
    if entities_by_context and node_tokens & fork_likely_terms:
        first_context_id = next(iter(entities_by_context))
        return {
            "answer": "Yes",
            "reason": "The subtask can be decomposed by iterating over entities available in selected context.",
            "entity_source_context_id": first_context_id,
            "entities": entities_by_context[first_context_id],
        }
    return _no_task_forking_decision("No reusable entity list is available in context for entity-based decomposition.")


def _validated_task_forking_decision(
    decision: dict[str, Any],
    context_bank: dict[str, dict[str, Any]],
    node: dict[str, str],
) -> dict[str, Any]:
    if decision.get("answer") != "Yes":
        return {
            "answer": "No",
            "reason": str(decision.get("reason") or "No entity-based fork is needed."),
            "entity_source_context_id": None,
            "entities": [],
        }

    source_context_id = decision.get("entity_source_context_id")
    entities = _fork_entities_from_context(context_bank.get(str(source_context_id), {}))
    if not entities:
        source_context_id = _select_fork_context_id(context_bank, node)
        entities = _fork_entities_from_context(context_bank.get(str(source_context_id), {}))
    if not entities:
        return _no_task_forking_decision(
            "No concrete entity list exists in the context bank, so this task should be decomposed normally."
        )
    return {
        "answer": "Yes",
        "reason": str(decision.get("reason") or "The task can iterate over a concrete entity list from context."),
        "entity_source_context_id": source_context_id,
        "entities": entities[:8],
    }


def _no_task_forking_decision(reason: str) -> dict[str, Any]:
    return {
        "answer": "No",
        "reason": reason,
        "entity_source_context_id": None,
        "entities": [],
    }


def _subtask_detection_suggestion(profile: SimulationProfile, node: dict[str, str]) -> dict[str, str]:
    if _should_decompose_further(profile, node):
        return {
            "suggested_action": "decompose_further",
            "rationale": "The subtask is broad enough that a smaller child node should be planned before drafting.",
        }
    return {
        "suggested_action": "draft_answer",
        "rationale": "The subtask is concrete enough to draft a reusable answer artifact now.",
    }


def _subtask_detection_decision_reason(profile: SimulationProfile, chosen_next_step: str) -> str:
    if chosen_next_step == "decompose_further":
        if profile.stable_persona_traits.decision_style == "opinionated":
            return "I want to break this down before accepting a draft."
        return "That split seems helpful before drafting."
    if profile.stable_persona_traits.decision_style == "deferential":
        return "I will go with the suggestion and draft this now."
    return "This seems specific enough to draft."


def _should_decompose_further(profile: SimulationProfile, node: dict[str, str]) -> bool:
    broad_terms = {"plan", "strategy", "schedule", "tracker", "roadmap", "calendar"}
    node_tokens = set(_key_tokens(node["title"] + " " + node["description"]))
    if profile.stable_persona_traits.context_richness == "high" and node["node_id"] == "N1":
        return True
    return bool(node_tokens & broad_terms)


def _nested_task_nodes(node: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "node_id": f"{node['node_id']}.1",
            "title": f"Clarify {node['title']} Inputs",
            "description": f"Identify the required user-specific inputs before drafting {node['title']}.",
        },
        {
            "node_id": f"{node['node_id']}.2",
            "title": f"Draft {node['title']}",
            "description": f"Use selected and local context to draft {node['title']}.",
        },
    ]


def _forked_task_nodes(node: dict[str, str], context: dict[str, Any]) -> list[dict[str, str]]:
    entities = _fork_entities_from_context(context)[:4]
    return [
        {
            "node_id": f"{node['node_id']}.F{index}",
            "title": f"{node['title']} For {entity.title()}",
            "description": f"Complete {node['title']} specifically for {entity}.",
        }
        for index, entity in enumerate(entities, start=1)
    ]


def _select_fork_context_id(context_bank: dict[str, dict[str, Any]], node: dict[str, str]) -> str | None:
    node_tokens = set(_key_tokens(node["title"] + " " + node["description"]))
    scored: list[tuple[int, str]] = []
    for context_id, context in context_bank.items():
        entities = _fork_entities_from_context(context)
        if not entities:
            continue
        context_tokens = set(_key_tokens(str(context.get("label", "")) + " " + str(context.get("value", ""))))
        score = len(node_tokens & context_tokens) + len(entities)
        scored.append((score, context_id))
    if not scored:
        return None
    return sorted(scored, reverse=True)[0][1]


def _fork_entities_from_context(context: dict[str, Any]) -> list[str]:
    if not isinstance(context, dict):
        return []
    value = str(context.get("value", ""))
    if _answer_status(value) == "unknown":
        return []
    entities = [
        entity
        for entity in _extract_fork_entities(value)
        if not _is_placeholder_fork_entity(entity)
    ]
    return entities if len(entities) >= 2 else []


def _is_placeholder_fork_entity(entity: str) -> bool:
    normalized = re.sub(r"\s+", " ", entity.strip().lower())
    return bool(re.fullmatch(r"(entity|item|option|person|participant|student)\s*(\d+|[a-z])", normalized))


def _extract_fork_entities(text: str) -> list[str]:
    text = text.replace(" and ", ", ")
    if "," not in text and ";" not in text:
        return []
    raw_parts = [part.strip(" .:-") for chunk in text.split(";") for part in chunk.split(",")]
    entities: list[str] = []
    for part in raw_parts:
        words = _words(part)
        if not 1 <= len(words) <= 7:
            continue
        lowered = part.lower()
        if lowered.startswith(("current goal", "goal time", "use the stable", "prior source")):
            continue
        if part and part not in entities:
            entities.append(part)
    return entities[:8]


def _task_nodes(profile: SimulationProfile) -> list[dict[str, str]]:
    outputs = [criterion.replace("includes ", "") for criterion in profile.approval_criteria if criterion.startswith("includes ")]
    if not outputs:
        outputs = ["task plan", "checklist", "next steps"]
    return [
        {"node_id": f"N{index}", "title": output.title(), "description": f"Create or refine the {output} for {profile.goal_text}."}
        for index, output in enumerate(outputs[:3], start=1)
    ]


def _node_level(node: dict[str, str]) -> int:
    return str(node["node_id"]).count(".") + 1


def _task_tree_summary(nodes: list[dict[str, str]]) -> str:
    return "; ".join(f"{node['node_id']}: {node['title']}" for node in nodes)


def _context_bank_json(context_bank: dict[str, dict[str, Any]]) -> str:
    return json.dumps(context_bank, ensure_ascii=True, sort_keys=True)


def _answer_for_need(profile: SimulationProfile, need: str) -> str:
    lowered = need.lower()
    for fact in profile.private_context_facts:
        fact_lowered = fact.lower()
        if lowered in fact_lowered or any(token in fact_lowered for token in _key_tokens(lowered)):
            return _fit_turn_style(profile, fact)
    if "unknown" in lowered or any(need.lower().startswith(item.split(":")[0].lower()) for item in profile.unknown_or_undecided_facts):
        return "I do not know yet."
    return "I am not sure yet."


def _answer_status(answer: str) -> str:
    lowered = answer.lower()
    unknown_markers = (
        "not sure",
        "do not know",
        "don't know",
        "do not have",
        "don't have",
        "have not decided",
        "haven't decided",
        "undecided",
        "unknown",
    )
    return "unknown" if any(marker in lowered for marker in unknown_markers) else "substantive"


def _select_context_ids(condition: Condition, context_bank: dict[str, dict[str, Any]], node: dict[str, str], rng: random.Random) -> list[str]:
    ids = list(context_bank)
    if condition in {"no_selection", "no_elicitation", "chatgpt_vanilla"}:
        return []
    if condition == "all_context":
        return ids
    if condition == "random_selection":
        target_ids = _ranked_relevant_context_ids(context_bank, node) or _first_substantive_context_ids(context_bank)
        target_tokens = _context_token_count_for_ids(context_bank, target_ids)
        candidate_ids = [context_id for context_id in ids if _is_substantive_context(context_bank.get(context_id, {}))]
        return _token_matched_random_context_ids(
            candidate_ids,
            context_bank,
            target_tokens=target_tokens,
            max_items=max(1, len(target_ids)),
            rng=rng,
        )
    relevant = _ranked_relevant_context_ids(context_bank, node)
    return relevant or _first_substantive_context_ids(context_bank)


def _ranked_relevant_context_ids(
    context_bank: dict[str, dict[str, Any]],
    node: dict[str, str],
    max_selected: int | None = None,
) -> list[str]:
    relevant_ids = [
        context_id
        for context_id, score in _ranked_context_candidates(context_bank, node)
        if score > CONTEXT_RELEVANCE_THRESHOLD
    ]
    return relevant_ids[:max_selected] if max_selected is not None else relevant_ids


def _ranked_context_candidates(
    context_bank: dict[str, dict[str, Any]],
    node: dict[str, str],
) -> list[tuple[str, float]]:
    task_text = f"{node.get('title', '')} {node.get('description', '')}"
    scored = [
        (context_id, _context_relevance_score(task_text, context), index)
        for index, (context_id, context) in enumerate(context_bank.items())
    ]
    scored.sort(key=lambda item: (-item[1], item[2]))
    return [(context_id, score) for context_id, score, _index in scored]


def _token_matched_random_context_ids(
    ids: list[str],
    context_bank: dict[str, dict[str, Any]],
    target_tokens: int,
    max_items: int,
    rng: random.Random,
) -> list[str]:
    if not ids:
        return []
    max_items = max(1, min(max_items, len(ids)))
    if target_tokens <= 0:
        shuffled = ids[:]
        rng.shuffle(shuffled)
        return shuffled[:max_items]

    candidates: list[tuple[int, int, list[str]]] = []
    for size in range(1, max_items + 1):
        for combo in combinations(ids, size):
            token_count = _context_token_count_for_ids(context_bank, combo)
            candidates.append((abs(token_count - target_tokens), token_count, list(combo)))
    if not candidates:
        return []
    best_diff = min(diff for diff, _token_count, _combo in candidates)
    tolerance = max(best_diff, round(target_tokens * 0.15))
    near_matches = [combo for diff, _token_count, combo in candidates if diff <= tolerance]
    return rng.choice(near_matches)


def _context_token_count_for_ids(context_bank: dict[str, dict[str, Any]], context_ids: Any) -> int:
    return sum(_context_token_count(context_bank.get(str(context_id), {})) for context_id in context_ids)


def _context_token_count(context: dict[str, Any]) -> int:
    if not isinstance(context, dict):
        return 0
    if not _is_substantive_context(context):
        return 0
    label = str(context.get("label", ""))
    value = str(context.get("value", ""))
    return len(_key_tokens(f"{label} {value}"))


def _first_substantive_context_ids(context_bank: dict[str, dict[str, Any]]) -> list[str]:
    for context_id, context in context_bank.items():
        if _is_substantive_context(context):
            return [context_id]
    return []


def _is_substantive_context(context: dict[str, Any]) -> bool:
    if not isinstance(context, dict):
        return False
    value = str(context.get("value", "")).strip()
    if not value or _answer_status(value) == "unknown":
        return False
    lowered = value.lower().strip()
    return lowered not in {"undefined", "undefined: undefined", "none", "null", "[]", "{}"}


def _context_relevance_score(task_text: str, context: dict[str, Any]) -> float:
    if not isinstance(context, dict):
        return 0
    value = str(context.get("value", ""))
    if not value.strip() or _answer_status(value) == "unknown":
        return 0

    task_tokens = set(_key_tokens(task_text))
    label_tokens = set(_key_tokens(str(context.get("label", ""))))
    value_tokens = set(_key_tokens(value))
    context_tokens = label_tokens | value_tokens
    if not task_tokens or not context_tokens:
        return 0

    direct_overlap = task_tokens & context_tokens
    label_overlap = task_tokens & label_tokens
    task_concepts = _semantic_context_concepts(task_tokens)
    context_concepts = _semantic_context_concepts(context_tokens)
    concept_overlap = task_concepts & context_concepts

    direct_ratio = len(direct_overlap) / max(1, min(len(task_tokens), len(context_tokens)))
    label_ratio = len(label_overlap) / max(1, min(len(task_tokens), len(label_tokens)))
    concept_ratio = len(concept_overlap) / max(1, len(task_concepts))
    score = (0.2 * direct_ratio) + (0.45 * label_ratio) + (0.35 * concept_ratio)
    if context.get("scope") == "local" and (label_overlap or concept_overlap):
        score += 0.05
    return round(min(score, 1.0), 4)


def _semantic_context_concepts(tokens: set[str]) -> set[str]:
    concepts: set[str] = set()
    concept_terms = {
        "schedule": {
            "availability",
            "available",
            "calendar",
            "date",
            "dates",
            "deadline",
            "evening",
            "friday",
            "saturday",
            "schedule",
            "timeline",
            "time",
            "times",
            "week",
            "weekly",
        },
        "place": {"apartment", "campus", "location", "manhattan", "place", "queens", "room", "venue", "venues"},
        "people": {
            "audience",
            "attendee",
            "attendees",
            "contact",
            "contacts",
            "family",
            "group",
            "participant",
            "participants",
            "people",
            "students",
            "subtenant",
            "team",
        },
        "preferences": {
            "format",
            "game",
            "games",
            "interest",
            "interests",
            "preference",
            "preferences",
            "style",
            "topic",
            "topics",
        },
        "budget": {"budget", "cost", "costs", "funding", "money", "price"},
        "content": {
            "application",
            "applications",
            "content",
            "design",
            "draft",
            "essay",
            "lsat",
            "portfolio",
            "project",
            "script",
            "study",
            "tutorial",
            "video",
            "website",
        },
        "communication": {
            "announcement",
            "email",
            "follow",
            "invitation",
            "invite",
            "message",
            "outreach",
            "reminder",
            "survey",
        },
        "logistics": {"equipment", "lease", "materials", "move", "moving", "reservation", "transportation"},
    }
    for concept, terms in concept_terms.items():
        if tokens & terms:
            concepts.add(concept)
    return concepts


def _selection_reason(condition: Condition, selected_ids: list[str]) -> str:
    if condition == "full_jumpstarter":
        return "selected contexts with the highest relevance to the current subtask"
    if condition == "all_context":
        return "baseline reuses every available context"
    if condition == "random_selection":
        return "baseline randomly samples available contexts"
    if condition == "no_reuse":
        return "baseline may select context but blocks reuse during drafting"
    if condition == "flat_decomposition":
        return "flat baseline selects context for top-level tasks only"
    if condition == "adapt_recursive_decomposition":
        return "ADaPT baseline follows initial planning, executor attempts, failure-triggered replanning, and AND/OR child execution"
    if condition == "ask_before_plan":
        return "Ask-before-Plan baseline runs tool trajectories, asks clarifying questions when needed, then plans once"
    if condition == "unstructured_memory_rag":
        return "memory-RAG baseline retrieves generic top-k snippets from unstructured memory"
    if condition == "long_context_planner":
        return "long-context baseline includes all available substantive context up to the input budget"
    if condition == "react_integrated_planner":
        return "integrated agent dynamically retrieves and selects the top-k relevant contexts for the current subtask"
    if condition == "no_elicitation":
        return "baseline has no elicited context to select"
    if not selected_ids:
        return "baseline does not reuse context for this draft"
    return "selected by condition policy"


def _context_digest_for_node(
    profile: SimulationProfile,
    node: dict[str, str],
    reused_contexts: dict[str, dict[str, Any]],
    context_bank: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    facts = _substantive_context_items(reused_contexts)
    unknown_contexts = [
        {
            "context_id": context_id,
            "label": str(context.get("label", context_id)),
            "value": str(context.get("value", "")),
        }
        for context_id, context in context_bank.items()
        if isinstance(context, dict) and str(context.get("value", "")).strip() and _answer_status(str(context.get("value", ""))) == "unknown"
    ]
    open_decisions = _missing_inputs_for_node(profile, node)
    for context in unknown_contexts:
        label = context["label"]
        if label and label not in open_decisions:
            open_decisions.append(label)
    constraints = [fact["text"] for fact in facts if _semantic_context_concepts(set(_key_tokens(fact["text"]))) & {"schedule", "budget", "place", "people"}]
    drafts_to_build_on = [
        {
            "context_id": fact["context_id"],
            "label": fact["label"],
            "text": fact["text"],
        }
        for fact in facts
        if fact["scope"] == "draft"
    ]
    return {
        "task_name": node["title"],
        "task_description": node["description"],
        "facts_to_use": facts[:8],
        "constraints": constraints[:6],
        "drafts_to_build_on": drafts_to_build_on[:4],
        "open_decisions": open_decisions[:8],
        "excluded_unknown_contexts": unknown_contexts[:8],
        "do_not_assume": [
            f"Do not invent {decision}; leave it as an open field if needed."
            for decision in open_decisions[:4]
        ],
    }


def _draft_for_node(
    profile: SimulationProfile,
    node: dict[str, str],
    reused_contexts: dict[str, dict[str, Any]],
    context_digest: dict[str, Any] | None = None,
) -> str:
    if context_digest is None:
        context_digest = _context_digest_for_node(profile, node, reused_contexts, reused_contexts)
    context_facts = [str(item.get("text", "")) for item in context_digest.get("facts_to_use", []) if isinstance(item, dict)]
    deliverables = _deliverable_lines(profile, node, context_facts, context_digest)
    missing_inputs = [str(item) for item in context_digest.get("open_decisions", []) if str(item).strip()]
    sections = [
        f"{node['title']} - working artifact for {profile.goal_text}",
        "",
        "Context used as evidence:",
        *_bullet_lines(context_facts or ["No selected context was reused for this draft; treat concrete details as placeholders to verify."]),
        "",
        "Context not used as evidence:",
        *_bullet_lines(_excluded_context_lines(context_digest) or ["No unknown selected context was treated as evidence."]),
        "",
        "Reusable artifact:",
        *deliverables,
        "",
        "Next steps:",
        *_numbered_lines(_next_step_lines(profile, node, context_facts)),
        "",
        "Open decisions before finalizing:",
        *_bullet_lines(missing_inputs[:3] or ["Confirm owner, date, and any constraints not yet elicited."]),
        "",
        "Acceptance check:",
        *_bullet_lines(_acceptance_lines(profile, node)),
    ]
    return "\n".join(sections)


def _local_need_for_node(profile: SimulationProfile, node: dict[str, str]) -> str:
    node_tokens = set(_key_tokens(node["title"] + " " + node["description"]))
    for unknown in profile.unknown_or_undecided_facts:
        key = unknown.split(":")[0]
        if node_tokens & set(_key_tokens(key)):
            return key
    if profile.unknown_or_undecided_facts:
        return profile.unknown_or_undecided_facts[0].split(":")[0]
    return node["title"].lower()


def _refined_draft_for_node(draft: str, local_answer: str) -> str:
    if _answer_status(local_answer) == "unknown":
        refinement = [
            "",
            "Local refinement:",
            "- The user did not know the requested detail yet, so the artifact keeps that item as a decision to confirm.",
        ]
    else:
        refinement = [
            "",
            "Local refinement:",
            f"- User-provided detail incorporated: {local_answer}",
            "",
            "| Artifact field | Updated value | Action |",
            "| --- | --- | --- |",
            f"| Newly confirmed detail | {local_answer} | Replace the matching open field in the artifact above. |",
            "| Reuse note | Save this value as local context | Use it in downstream subtasks instead of asking again. |",
        ]
    return draft + "\n" + "\n".join(refinement)


def _review_draft(profile: SimulationProfile, draft: str, used_selected_context: bool) -> dict[str, str]:
    if not used_selected_context and profile.approval_criteria:
        return {"action": "pushback", "reason": "This feels generic and should use my relevant context first."}
    return {"action": "accept", "reason": "This is useful enough to save as a working draft."}


def _vanilla_draft(profile: SimulationProfile, user_context: str = "") -> str:
    outputs = [criterion.replace("includes ", "") for criterion in profile.approval_criteria if criterion.startswith("includes ")]
    context_facts = _context_facts_from_text(user_context)
    artifact_targets = outputs[:3] or ["task plan", "checklist", "next steps"]
    sections = [
        f"One-shot planning package for {profile.goal_text}",
        "",
        "Assumptions and context:",
        *_bullet_lines(context_facts[:4] or ["No user-specific context was available, so details below should be verified."]),
        "",
        "Deliverables:",
    ]
    for index, target in enumerate(artifact_targets, start=1):
        node = {"node_id": f"D{index}", "title": target.title(), "description": f"Create {target}."}
        sections.extend([f"{index}. {target.title()}:", *_bullet_lines(_deliverable_lines(profile, node, context_facts)[:3])])
    sections.extend(
        [
            "",
            "Immediate next steps:",
            *_numbered_lines(_next_step_lines(profile, {"title": profile.goal_text, "description": profile.goal_text}, context_facts)),
            "",
            "Information still needed:",
            *_bullet_lines(_missing_inputs_for_node(profile, {"title": profile.goal_text, "description": profile.goal_text})[:4]),
        ]
    )
    return "\n".join(sections)


def _structured_context_summary(context_bank: dict[str, dict[str, Any]]) -> str:
    if not context_bank:
        return "No elicited user context is available."
    lines = []
    for context_id, context in context_bank.items():
        if not _is_substantive_context(context):
            continue
        label = str(context.get("label", context_id))
        value = str(context.get("value", ""))
        lines.append(f"- {label}: {value}")
    if not lines:
        return "No substantive elicited user context is available."
    return "Structured user context summary:\n" + "\n".join(lines)


def _substantive_context_items(contexts: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    facts: list[dict[str, str]] = []
    seen: set[str] = set()
    for context_id, context in contexts.items():
        if not _is_substantive_context(context):
            continue
        label = str(context.get("label", "")).strip()
        value = str(context.get("value", "")).strip()
        fact = value if ":" in value or not label or label.lower() in value.lower() else f"{label}: {value}"
        if fact in seen:
            continue
        seen.add(fact)
        facts.append(
            {
                "context_id": str(context_id),
                "scope": str(context.get("scope", "")),
                "label": label or str(context_id),
                "text": fact,
            }
        )
    return facts


def _substantive_context_values(contexts: dict[str, dict[str, Any]]) -> list[str]:
    return [item["text"] for item in _substantive_context_items(contexts)[:6]]


def _excluded_context_lines(context_digest: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in context_digest.get("excluded_unknown_contexts", []):
        if isinstance(item, dict):
            label = str(item.get("label", "")).strip()
            value = str(item.get("value", "")).strip()
            if label or value:
                lines.append(f"{label or 'unknown context'}: {value or 'unknown'}")
    return lines[:4]


def _context_facts_from_text(text: str) -> list[str]:
    if not text:
        return []
    stripped = text.strip()
    facts: list[str] = []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for context in payload.values():
            if isinstance(context, dict):
                facts.extend(_substantive_context_values({"item": context}))
    else:
        for line in stripped.splitlines():
            cleaned = line.strip(" -")
            if cleaned and _answer_status(cleaned) != "unknown":
                facts.append(cleaned)
    return facts[:6]


def _deliverable_lines(
    profile: SimulationProfile,
    node: dict[str, str],
    context_facts: list[str],
    context_digest: dict[str, Any] | None = None,
) -> list[str]:
    title = node["title"].lower()
    context_anchor = _context_anchor(profile, context_facts)
    open_decisions = [str(item) for item in (context_digest or {}).get("open_decisions", []) if str(item).strip()]
    open_a = open_decisions[0] if open_decisions else "unconfirmed detail"
    open_b = open_decisions[1] if len(open_decisions) > 1 else "owner/date"
    if any(term in title for term in ("calendar", "content calendar", "posting", "schedule", "timeline", "roadmap", "semester")):
        return [
            "| Date/Week | Artifact or action | Context used | Owner | Status | Missing field |",
            "| --- | --- | --- | --- | --- | --- |",
            f"| Week 1 | Confirm {open_a} and collect any needed replies | {context_anchor} | User | Ready to start | {open_a} |",
            f"| Week 2 | Produce first concrete artifact for {profile.goal_text} | {context_anchor} | User | Draft | {open_b} |",
            "| Week 3 | Review results, update tracker, and revise artifact | Prior draft feedback | User | Planned | success metric |",
            "| Week 4 | Repeat the working cadence and archive reusable decisions | Saved draft context | User | Planned | next milestone |",
        ]
    if any(term in title for term in ("audit", "profile audit")):
        return [
            "| Area | Check | Current answer | Action | Priority |",
            "| --- | --- | --- | --- | --- |",
            f"| Positioning | Does the profile clearly support {profile.goal_text}? | Unknown | Write one-sentence positioning statement | High |",
            f"| Audience fit | Is the target audience/role explicit? | {open_a} | Fill audience or role field before publishing | High |",
            "| Evidence | Are examples, projects, or posts linked? | Unknown | Add 3 proof points or mark as not available | Medium |",
            "| Next action | Is there a clear contact/follow/subscribe action? | Unknown | Add one primary call to action | Medium |",
        ]
    if any(term in title for term in ("project description", "description", "portfolio")):
        return [
            "Project description template:",
            f"- Project name: [{open_a}]",
            f"- Target role/audience supported: [{open_b}]",
            f"- One-line summary: Built/created [artifact] to solve [problem] for {profile.goal_text}.",
            "- Evidence: [metric, screenshot, link, course/project context]",
            "- Skills demonstrated: [skill 1], [skill 2], [skill 3]",
            "- Next edit: replace bracketed fields with confirmed project inventory before launch.",
        ]
    if any(term in title for term in ("launch checklist", "posting checklist", "checklist")):
        return [
            "| Step | Done? | Detail to fill | Why it matters |",
            "| --- | --- | --- | --- |",
            f"| Confirm core constraint | [ ] | {open_a} | Prevents generic or wrong recommendations |",
            f"| Fill reusable artifact | [ ] | Use {context_anchor} | Converts context into action |",
            "| Review for unsupported claims | [ ] | Remove invented names, dates, venues, links | Keeps output trustworthy |",
            "| Save final version | [ ] | Store as draft context for later subtasks | Enables future reuse |",
            "| Send/publish/execute | [ ] | Owner and deadline | Turns plan into progress |",
        ]
    if any(term in title for term in ("survey", "questionnaire", "research worksheet", "audience research")):
        return [
            "Ready-to-use intake questions:",
            f"1. Which option best fits your availability or constraint for {profile.goal_text}?",
            "2. What is your top preference among the options already mentioned in context?",
            "3. What would make this plan inconvenient or unrealistic for you?",
            "4. What concrete example, link, venue, project, or resource should be included?",
            "5. Anything you do not know yet that should stay marked as an open decision?",
            f"Analysis table columns: respondent | answer summary | decision affected | follow-up needed | applies to {open_a}",
        ]
    if any(term in title for term in ("invitation", "message", "email", "outreach")):
        return [
            f"Subject: {profile.goal_text} - quick reply requested",
            "Message draft:",
            f"Hi [Name], I am organizing {profile.goal_text}. Current confirmed context: {context_anchor}.",
            f"Could you reply with: 1) your answer for {open_a}, 2) any constraints, and 3) whether you want to participate or help?",
            "I will use replies to finalize the next artifact and will keep unconfirmed details marked as open decisions.",
            "Thanks!",
        ]
    if any(term in title for term in ("venue", "shortlist", "location", "place")):
        return [
            "| Option | Fit with context | Verify before choosing | Risk |",
            "| --- | --- | --- | --- |",
            f"| Option A: closest/default venue | Anchored in {context_anchor} | capacity, access, reservation rule | may be unavailable |",
            "| Option B: quiet reservable room | Good for focused or small-group work | booking process, hours | may need sponsor |",
            "| Option C: flexible public/shared space | Good when attendance is uncertain | noise, cost, backup plan | less reliable |",
            "Decision rule: choose the first option that satisfies capacity, timing, cost, and accessibility; otherwise keep as open.",
        ]
    if any(term in title for term in ("tracker", "list", "contacts", "application", "documents")):
        return [
            "| Item | Owner | Status | Deadline | Dependency/context | Next action |",
            "| --- | --- | --- | --- | --- | --- |",
            f"| Highest-priority row for {profile.goal_text} | User | Not started | [{open_b}] | {context_anchor} | Confirm {open_a} |",
            "| Context-dependent row | User | Draft | [date] | selected context digest | Fill artifact-specific details |",
            "| Review row | User | Planned | [date] | saved draft context | Check unsupported assumptions |",
        ]
    if any(term in title for term in ("draft", "template", "artifact", "outline")):
        return [
            f"Artifact purpose: support {profile.goal_text} with a reusable draft grounded in {context_anchor}.",
            f"Section 1 - Confirmed facts: {context_anchor}.",
            f"Section 2 - Fields to fill: [{open_a}], [{open_b}], [deadline/success metric].",
            "Section 3 - Finished output: [write/send/publish the concrete artifact here].",
            "Reuse note: save the completed fields as context for downstream subtasks.",
        ]
    if any(term in title for term in ("plan", "strategy", "checklist")):
        return [
            "| Phase | Concrete output | Context used | Open decision |",
            "| --- | --- | --- | --- |",
            f"| 1 | Decision brief for {profile.goal_text} | {context_anchor} | {open_a} |",
            "| 2 | First reusable artifact | selected context digest | owner/deadline |",
            "| 3 | Review and update | saved draft context | success metric |",
            "| 4 | Repeat or execute | approved artifact | next milestone |",
        ]
    return [
        f"- Primary deliverable: a usable {node['title'].lower()} for {profile.goal_text}.",
        f"- Personalization: ground the artifact in {context_anchor}.",
        f"- Required fields: owner, deadline, next action, {open_a}.",
        "- Reuse: save the filled output as draft context so later subtasks can build on it.",
    ]


def _next_step_lines(profile: SimulationProfile, node: dict[str, str], context_facts: list[str]) -> list[str]:
    missing = _missing_inputs_for_node(profile, node)
    first_missing = missing[0] if missing else "the most important unconfirmed constraint"
    return [
        f"Verify {first_missing}.",
        f"Fill the artifact with confirmed details for {profile.goal_text}.",
        "Ask the user to approve, revise, or mark any assumption as unknown.",
        "Save the finished piece in the context bank so later subtasks can reuse it.",
    ]


def _missing_inputs_for_node(profile: SimulationProfile, node: dict[str, str]) -> list[str]:
    node_tokens = set(_key_tokens(node["title"] + " " + node["description"]))
    missing: list[str] = []
    for fact in profile.unknown_or_undecided_facts:
        key = fact.split(":")[0].strip()
        if not key:
            continue
        if node_tokens & set(_key_tokens(key)) or len(missing) < 2:
            missing.append(key)
    return missing or ["owner", "deadline", "success criteria"]


def _acceptance_lines(profile: SimulationProfile, node: dict[str, str]) -> list[str]:
    node_tokens = set(_key_tokens(node["title"] + " " + node["description"]))
    criteria: list[str] = []
    for criterion in profile.approval_criteria:
        cleaned = criterion.removeprefix("the assistant ").strip()
        if criterion.startswith("includes "):
            if node_tokens & set(_key_tokens(criterion)):
                criteria.append(cleaned)
        elif len(criteria) < 3:
            criteria.append(cleaned)
    return criteria[:4] or [f"Supports {profile.goal_text}", "Uses known context only", "Names missing information clearly"]


def _context_anchor(profile: SimulationProfile, context_facts: list[str]) -> str:
    if context_facts:
        return _short_fact(context_facts[0])
    if profile.private_context_facts:
        # This is only a generic anchor when context was not selected; the draft still tells the user to verify it.
        return "the user's known constraints once confirmed"
    return "the user's confirmed constraints"


def _short_fact(text: str) -> str:
    words = _words(text)
    if len(words) <= 14:
        return text
    return " ".join(words[:14]) + "..."


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _numbered_lines(items: list[str]) -> list[str]:
    return [f"{index}. {item}" for index, item in enumerate(items, start=1)]


def _fit_turn_style(profile: SimulationProfile, text: str) -> str:
    max_words = max(6, min(profile.turn_style.max_tokens // 2, 35))
    words = _words(text)
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def _key_tokens(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "goal",
        "current",
        "unknown",
        "until",
        "asked",
        "task",
        "draft",
        "create",
        "make",
        "use",
        "using",
    }
    return [token for token in _words(text.lower()) if token not in stop and len(token) > 2]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text).lower())
