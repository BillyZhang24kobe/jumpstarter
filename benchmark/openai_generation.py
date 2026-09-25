from __future__ import annotations

import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from .schemas import (
    ContextRelevanceLabel,
    FilterDecision,
    GeneratedGoalCandidate,
    GoalGenerationBatch,
    JudgeExtractedEvidence,
    PairedJudgeResponse,
    JudgeRubricScore,
    Persona,
    PersonaBatch,
    SimulationProfile,
    SimulationProfileBatch,
)


DEFAULT_GENERATION_MODEL = "gpt-5.5"
DEFAULT_WORKFLOW_MODEL = "gpt-4o"
DEFAULT_USER_SIMULATOR_MODEL = "gpt-4o"
DEFAULT_CONTEXT_RELEVANCE_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 120.0
DEFAULT_OPENAI_SDK_MAX_RETRIES = 0
DEFAULT_OPENAI_RETRY_ATTEMPTS = 3
DEFAULT_OPENAI_RETRY_INITIAL_SLEEP_SECONDS = 2.0
DEFAULT_OPENAI_RETRY_MAX_SLEEP_SECONDS = 30.0
T = TypeVar("T")
_RESPONSES_PARSE_LOCK = threading.RLock()


def configured_model() -> str:
    return os.environ.get("BENCHMARK_GENERATION_MODEL", DEFAULT_GENERATION_MODEL)


def configured_workflow_model() -> str:
    return os.environ.get("BENCHMARK_WORKFLOW_MODEL", DEFAULT_WORKFLOW_MODEL)


def load_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set the OPENAI_API_KEY environment variable for --live benchmark runs")
    org_id = os.environ.get("OPENAI_ORG_ID", "").strip()

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": _env_float("BENCHMARK_OPENAI_TIMEOUT_SECONDS", DEFAULT_OPENAI_TIMEOUT_SECONDS),
        "max_retries": _env_int("BENCHMARK_OPENAI_SDK_MAX_RETRIES", DEFAULT_OPENAI_SDK_MAX_RETRIES),
    }
    if org_id:
        client_kwargs["organization"] = org_id

    from openai import OpenAI

    return OpenAI(**client_kwargs)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number, got {value!r}") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be positive, got {value!r}")
    return parsed


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {value!r}") from exc
    if parsed < 0:
        raise RuntimeError(f"{name} must be non-negative, got {value!r}")
    return parsed


def _openai_retry_attempts() -> int:
    attempts = _env_int("BENCHMARK_OPENAI_RETRY_ATTEMPTS", DEFAULT_OPENAI_RETRY_ATTEMPTS)
    if attempts <= 0:
        raise RuntimeError("BENCHMARK_OPENAI_RETRY_ATTEMPTS must be at least 1")
    return attempts


def _is_retryable_openai_error(exc: BaseException) -> bool:
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
    except ImportError:
        return False

    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {408, 409, 429} or exc.status_code >= 500
    return False


def _is_retryable_parse_error(operation: str, exc: BaseException) -> bool:
    if operation != "responses.parse":
        return False
    errors_method = getattr(exc, "errors", None)
    if not callable(errors_method):
        return False
    try:
        errors = errors_method()
    except Exception:
        return False
    return any(isinstance(error, dict) and error.get("type") == "json_invalid" for error in errors)


def _sleep_before_retry(attempt_index: int) -> float:
    initial_sleep = _env_float(
        "BENCHMARK_OPENAI_RETRY_INITIAL_SLEEP_SECONDS",
        DEFAULT_OPENAI_RETRY_INITIAL_SLEEP_SECONDS,
    )
    max_sleep = _env_float(
        "BENCHMARK_OPENAI_RETRY_MAX_SLEEP_SECONDS",
        DEFAULT_OPENAI_RETRY_MAX_SLEEP_SECONDS,
    )
    return min(max_sleep, initial_sleep * (2 ** max(0, attempt_index - 1)))


def _log_openai_retry(operation: str, attempt: int, attempts: int, exc: BaseException, sleep_seconds: float | None) -> None:
    message = f"[openai] {operation} attempt {attempt}/{attempts} failed with {type(exc).__name__}: {exc}"
    if sleep_seconds is not None:
        message += f"; retrying in {sleep_seconds:.1f}s"
    else:
        message += "; no retries left"
    print(message, file=sys.stderr, flush=True)


def _call_openai_with_retries(operation: str, call: Callable[[], T]) -> T:
    attempts = _openai_retry_attempts()
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:
            retryable = _is_retryable_openai_error(exc) or _is_retryable_parse_error(operation, exc)
            if not retryable or attempt >= attempts:
                if retryable:
                    _log_openai_retry(operation, attempt, attempts, exc, None)
                raise
            sleep_seconds = _sleep_before_retry(attempt)
            _log_openai_retry(operation, attempt, attempts, exc, sleep_seconds)
            time.sleep(sleep_seconds)
    raise RuntimeError(f"{operation} failed without returning or raising")


def _responses_parse(client: Any, **kwargs: Any) -> Any:
    def call() -> Any:
        if os.environ.get("BENCHMARK_OPENAI_PARSE_LOCK", "1") == "0":
            return client.responses.parse(**kwargs)
        with _RESPONSES_PARSE_LOCK:
            return client.responses.parse(**kwargs)

    return _call_openai_with_retries("responses.parse", call)


def _responses_create(client: Any, **kwargs: Any) -> Any:
    return _call_openai_with_retries("responses.create", lambda: client.responses.create(**kwargs))



def generate_candidates_live(
    prompt_path: Path,
    anchor_payload: str,
    needed_by_domain: dict[str, int],
    model: str | None = None,
) -> list[GeneratedGoalCandidate]:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    prompt = prompt_path.read_text()
    response = _responses_parse(
        client,
        model=model or configured_model(),
        input=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "Generate benchmark planning goals as JSON using the schema.\n\n"
                    f"Needed by domain: {needed_by_domain}\n\n"
                    f"Anchor sessions:\n{anchor_payload}"
                ),
            },
        ],
        text_format=GoalGenerationBatch,
    )
    return response.output_parsed.candidates


def filter_goal_live(
    prompt_path: Path,
    candidate: GeneratedGoalCandidate,
    nearest_goal_id: str | None,
    similarity_score: float,
    model: str | None = None,
) -> FilterDecision:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    prompt = prompt_path.read_text()
    response = _responses_parse(
        client,
        model=model or configured_model(),
        input=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": candidate.model_dump_json(indent=2)
                + f"\n\nNearest deterministic match: {nearest_goal_id}, score={similarity_score:.3f}",
            },
        ],
        text_format=FilterDecision,
    )
    return response.output_parsed


def refine_personas_live(personas: list[Persona], model: str | None = None) -> list[Persona]:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    prompt_path = Path(__file__).resolve().parent / "prompts" / "extract_personas_v1.txt"
    prompt = prompt_path.read_text()
    response = _responses_parse(
        client,
        model=model or configured_model(),
        input=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "Refine these base personas while preserving persona IDs, source participants, "
                    "evidence quotes, and schema shape. Return exactly the same number of personas.\n\n"
                    + json_dump_personas(personas)
                ),
            },
        ],
        text_format=PersonaBatch,
    )
    return response.output_parsed.personas


def json_dump_personas(personas: list[Persona]) -> str:
    import json

    return json.dumps([persona.model_dump() for persona in personas], indent=2)


def refine_simulation_profiles_live(
    profiles: list[SimulationProfile],
    model: str | None = None,
    batch_size: int = 20,
) -> list[SimulationProfile]:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    prompt_path = Path(__file__).resolve().parent / "prompts" / "simulation_profiles_v1.txt"
    prompt = prompt_path.read_text()
    refined: list[SimulationProfile] = []
    for index in range(0, len(profiles), batch_size):
        batch = profiles[index : index + batch_size]
        response = _responses_parse(
            client,
            model=model or configured_model(),
            input=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Refine these simulation profiles while preserving IDs and schema shape. "
                        "Return exactly the same number of profiles.\n\n"
                        + json_dump_simulation_profiles(batch)
                    ),
                },
            ],
            text_format=SimulationProfileBatch,
        )
        refined.extend(response.output_parsed.profiles)
    return refined


def score_planning_output_live(
    prompt_path: Path,
    judge_payload: str,
    model: str | None = None,
) -> JudgeRubricScore:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    prompt = prompt_path.read_text()
    response = _responses_parse(
        client,
        model=model or os.environ.get("BENCHMARK_JUDGE_MODEL") or configured_model(),
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": judge_payload},
        ],
        text_format=JudgeRubricScore,
    )
    return response.output_parsed


def score_pairwise_planning_output_live(
    prompt_path: Path,
    judge_payload: str,
    model: str | None = None,
) -> PairedJudgeResponse:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    prompt = prompt_path.read_text()
    response = _responses_parse(
        client,
        model=model or os.environ.get("BENCHMARK_JUDGE_MODEL") or configured_model(),
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": judge_payload},
        ],
        text_format=PairedJudgeResponse,
    )
    return response.output_parsed


def extract_judge_evidence_live(
    prompt_path: Path,
    judge_payload: str,
    model: str | None = None,
) -> JudgeExtractedEvidence:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    prompt = prompt_path.read_text()
    response = _responses_parse(
        client,
        model=model or os.environ.get("BENCHMARK_JUDGE_MODEL") or configured_model(),
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": judge_payload},
        ],
        text_format=JudgeExtractedEvidence,
    )
    return response.output_parsed


def label_context_relevance_live(
    prompt_path: Path,
    relevance_payload: str,
    model: str | None = None,
) -> ContextRelevanceLabel:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    prompt = prompt_path.read_text()
    response = _responses_parse(
        client,
        model=model or os.environ.get("BENCHMARK_CONTEXT_RELEVANCE_MODEL") or DEFAULT_CONTEXT_RELEVANCE_MODEL,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": relevance_payload},
        ],
        text_format=ContextRelevanceLabel,
    )
    return response.output_parsed


def parse_workflow_stage_live(
    rendered_prompt: str,
    stage_payload: str,
    text_format: type[T],
    model: str | None = None,
) -> T:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    response = _responses_parse(
        client,
        model=model or configured_workflow_model(),
        input=[
            {"role": "system", "content": rendered_prompt},
            {"role": "user", "content": stage_payload},
        ],
        text_format=text_format,
    )
    return response.output_parsed


def generate_simulated_user_answer_live(
    profile: SimulationProfile,
    question: str,
    requested_context_key: str,
    conversation_state: dict[str, Any],
    model: str | None = None,
) -> str:
    client = load_openai_client()
    if not hasattr(client, "responses"):
        raise RuntimeError("The installed openai package does not expose the Responses API; update environment.yml dependencies.")

    system_prompt = (
        "You are a simulated benchmark user. Answer only as the user, grounded strictly in the private "
        "simulation profile. Reveal known facts when the assistant asks about them. If the requested "
        "detail is unknown or undecided in the profile, say that you do not know yet. Keep the answer "
        "brief and natural according to the turn style. Do not invent new biographical or goal facts. "
        "Never ask the assistant, backend, or evaluator follow-up questions. Do not request suggestions, "
        "constraints, clarification, or next steps from the assistant. Do not include question marks. If "
        "you lack the requested detail, state only what you know or say: I do not know yet."
    )
    payload = {
        "question": question,
        "requested_context_key": requested_context_key,
        "goal_text": profile.goal_text,
        "private_context_facts": profile.private_context_facts,
        "unknown_or_undecided_facts": profile.unknown_or_undecided_facts,
        "must_reveal_if_asked": profile.must_reveal_if_asked,
        "do_not_volunteer": profile.do_not_volunteer,
        "stable_persona_traits": profile.stable_persona_traits.model_dump(),
        "turn_style": profile.turn_style.model_dump(),
        "conversation_state": conversation_state,
    }
    response = _responses_create(
        client,
        model=model or os.environ.get("BENCHMARK_USER_MODEL") or DEFAULT_USER_SIMULATOR_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json_dumps(payload)},
        ],
    )
    text = getattr(response, "output_text", "").strip()
    if not text:
        raise RuntimeError("Live simulated user returned an empty answer")
    return _strip_simulated_user_questions(text)


def _strip_simulated_user_questions(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [sentence.strip() for sentence in sentences if sentence.strip() and "?" not in sentence]
    if kept:
        return " ".join(kept)
    return "I do not know yet."


def json_dump_simulation_profiles(profiles: list[SimulationProfile]) -> str:
    import json

    return json.dumps([profile.model_dump() for profile in profiles], indent=2)


def json_dumps(payload: Any) -> str:
    import json

    return json.dumps(payload, ensure_ascii=True, indent=2)
