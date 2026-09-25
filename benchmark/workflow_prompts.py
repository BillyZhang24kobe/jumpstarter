from __future__ import annotations

from pathlib import Path
from typing import Any


PROMPT_VERSION = "paper_workflow_v1"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / PROMPT_VERSION

PROMPT_FILES: dict[str, str] = {
    "global_context_elicitation": "Figure10_context_elicitation_for_global_input.txt",
    "local_context_elicitation": "Figure11_context_elicitation_for_answer_draft_creation.txt",
    "context_selection_draft": "Figure12_context_selection_for_answer_draft_creation.txt",
    "task_forking_context_selection": "E22_task_forking_context_selection.txt",
    "subtask_generation": "Figure13_subtask_generation.txt",
    "subtask_detection": "Figure14_subtask_detection.txt",
    "task_forking": "Figure15_task_forking.txt",
    "working_solution_draft_creation": "E4_working_solution_draft_creation.txt",
    "single_turn_decomposition": "single_turn_decomposition_baseline.txt",
}


def prompt_ids() -> list[str]:
    return sorted(PROMPT_FILES)


def prompt_path(prompt_id: str) -> Path:
    try:
        filename = PROMPT_FILES[prompt_id]
    except KeyError as exc:
        raise KeyError(f"Unknown paper workflow prompt id: {prompt_id}") from exc
    return PROMPT_DIR / filename


def load_prompt_template(prompt_id: str) -> str:
    path = prompt_path(prompt_id)
    if not path.exists():
        raise FileNotFoundError(f"Missing paper workflow prompt file for {prompt_id}: {path}")
    return path.read_text().strip()


def render_prompt(prompt_id: str, **values: Any) -> dict[str, str]:
    template = load_prompt_template(prompt_id)
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", _stringify(value))
    return {
        "prompt_id": prompt_id,
        "prompt_version": PROMPT_VERSION,
        "prompt_path": str(prompt_path(prompt_id)),
        "rendered_prompt": rendered,
    }


def validate_prompt_files() -> list[str]:
    errors: list[str] = []
    for prompt_id in prompt_ids():
        path = prompt_path(prompt_id)
        if not path.exists():
            errors.append(f"Missing {prompt_id}: {path}")
        elif not path.read_text().strip():
            errors.append(f"Empty {prompt_id}: {path}")
    return errors


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)
