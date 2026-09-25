from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from .manifest import ANCHOR_SPECS, REPO_ROOT
from .openai_generation import filter_goal_live, generate_candidates_live
from .parsers import parse_jumpstarter_log_record, parse_study_docx
from .schemas import (
    DOMAIN_TARGETS,
    AnchorSession,
    BenchmarkGoal,
    Domain,
    FilterDecision,
    GeneratedGoalCandidate,
    QualityReport,
)
from .similarity import nearest_goal


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PACKAGE_DIR / "data"
DEFAULT_REPORTS_DIR = PACKAGE_DIR / "reports"
# Judged results of the three runs reported in the paper (compact copies of runs/ directories).
DEFAULT_RESULTS_DIR = PACKAGE_DIR / "results"
FIXTURE_GENERATED_GOALS = PACKAGE_DIR / "fixtures" / "generated_goals.json"
PROMPT_GENERATE = PACKAGE_DIR / "prompts" / "generate_goals_v1.txt"
PROMPT_FILTER = PACKAGE_DIR / "prompts" / "filter_goal_v1.txt"
MAX_GENERATED_GOAL_WORDS = 9
MAX_GENERATED_GOAL_CHARS = 70
VERBOSE_GOAL_MARKERS = (
    " while ",
    " within ",
    " for exploring ",
    " in order to ",
    " that includes ",
    " that works ",
)


ANCHOR_OUTPUTS: dict[str, list[str]] = {
    "P2": ["venue shortlist", "semester calendar", "invitation message"],
    "P3": ["job-search tracker", "outreach messages", "interview prep plan"],
    "P4": ["study schedule", "resource list", "weekly checklist"],
    "P5": ["content calendar", "profile audit", "posting checklist"],
    "P6": ["sublease checklist", "moving timeline", "message templates"],
    "P7": ["portfolio site outline", "project descriptions", "launch checklist"],
    "P8": ["tutorial agenda", "practice plan", "slide outline"],
    "P9": ["channel positioning", "video pipeline", "content calendar"],
    "P10": ["travel itinerary", "family communication plan", "meal/activity schedule"],
    "A1": ["application checklist", "statement outline", "recommendation request plan"],
    "A2": ["study schedule", "practice checklist", "test-day plan"],
    "A3": ["outing itinerary", "reservation checklist", "team announcement"],
}

ANCHOR_CONTEXT_NEEDS: dict[str, list[str]] = {
    "P2": ["expected group size", "campus location constraints", "preferred game types"],
    "P3": ["target roles", "resume strengths", "application timeline"],
    "P4": ["target test date", "weekly availability", "current diagnostic score"],
    "P5": ["target audience", "platform preferences", "content strengths"],
    "P6": ["lease deadline", "budget", "moving constraints"],
    "P7": ["target jobs", "project inventory", "visual style preferences"],
    "P8": ["tutorial topic", "audience level", "delivery date"],
    "P9": ["channel niche", "recording constraints", "posting cadence"],
    "P10": ["attendee locations", "family ages", "date and accommodation constraints"],
    "A1": ["eligibility status", "application deadline", "research interests"],
    "A2": ["test date", "practice history", "local DMV constraints"],
    "A3": ["budget", "team preferences", "outing date and location"],
}


def build_anchor_sessions(repo_root: Path = REPO_ROOT) -> list[AnchorSession]:
    sessions: list[AnchorSession] = []
    for spec in ANCHOR_SPECS:
        warnings: list[str] = []
        docx_goal = None
        background = None
        chatgpt_share_url = None
        docx_excerpt = None
        rating_snippets: list[str] = []
        if spec.docx_path:
            parsed_docx = parse_study_docx(repo_root / spec.docx_path)
            docx_goal = parsed_docx.goal
            background = parsed_docx.background
            chatgpt_share_url = parsed_docx.chatgpt_share_url
            docx_excerpt = parsed_docx.excerpt
            rating_snippets = parsed_docx.rating_snippets
            warnings.extend(parsed_docx.warnings)

        parsed_log = None
        if spec.jumpstarter_log_file:
            parsed_log = parse_jumpstarter_log_record(repo_root / spec.jumpstarter_log_file, spec.jumpstarter_log_line)
            warnings.extend(parsed_log.warnings)

        sessions.append(
            AnchorSession(
                anchor_id=spec.anchor_id,
                participant_id=spec.participant_id,
                anchor_type=spec.anchor_type,  # type: ignore[arg-type]
                first_condition=spec.first_condition,
                goal=spec.goal,
                domain=spec.domain,
                docx_path=spec.docx_path,
                stats_row_id=spec.stats_row_id,
                jumpstarter_log_file=spec.jumpstarter_log_file,
                jumpstarter_log_line=spec.jumpstarter_log_line,
                chatgpt_share_url=chatgpt_share_url,
                usable_for_trace_replay=spec.usable_for_trace_replay,
                human_rated=spec.human_rated,
                docx_goal=docx_goal,
                background=background,
                docx_excerpt=docx_excerpt,
                rating_snippets=rating_snippets,
                root_task=parsed_log.task if parsed_log else None,
                root_node=parsed_log.root_node if parsed_log else None,
                user_global_context=parsed_log.user_global_context if parsed_log else {},
                user_context=parsed_log.user_context if parsed_log else {},
                saved_draft_context=parsed_log.saved_draft_context if parsed_log else {},
                parse_warnings=warnings,
            )
        )
    return sessions


def write_anchor_sessions(
    output_path: Path = DEFAULT_DATA_DIR / "anchor_sessions.jsonl",
    repo_root: Path = REPO_ROOT,
) -> list[AnchorSession]:
    sessions = build_anchor_sessions(repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        for session in sessions:
            handle.write(session.model_dump_json() + "\n")
    return sessions


def read_anchor_sessions(path: Path) -> list[AnchorSession]:
    return [AnchorSession.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def anchor_sessions_to_goals(sessions: Iterable[AnchorSession]) -> list[BenchmarkGoal]:
    goals: list[BenchmarkGoal] = []
    usable_sessions = [session for session in sessions if session.usable_for_trace_replay and session.anchor_type != "ignored_unusable"]
    for index, session in enumerate(usable_sessions, start=1):
        goals.append(
            BenchmarkGoal(
                goal_id=f"G{index:03d}",
                goal_text=session.goal,
                source="anchor",
                anchor_goal_id=session.anchor_id,
                anchor_type=session.anchor_type,  # type: ignore[arg-type]
                domain=session.domain,
                time_horizon=_anchor_time_horizon(session.domain),
                expected_context_richness="high",
                complexity="multi-track",
                requires_personalization=True,
                requires_decomposition=True,
                expected_tangible_outputs=ANCHOR_OUTPUTS[session.anchor_id],
                known_context_needs=ANCHOR_CONTEXT_NEEDS[session.anchor_id],
                avoid=["pure fact lookup", "one-shot generic advice"],
            )
        )
    return goals


def generate_goals(
    anchors: list[AnchorSession],
    dry_run: bool = True,
    seed: int = 42,
    output_path: Path | None = None,
    model: str | None = None,
    start_id: int = 13,
    needed_by_domain: dict[str, int] | None = None,
) -> list[GeneratedGoalCandidate]:
    if dry_run:
        payload = json.loads(FIXTURE_GENERATED_GOALS.read_text())
        candidates = [GeneratedGoalCandidate.model_validate(item) for item in payload["candidates"]]
    else:
        anchor_payload = "\n".join(
            json.dumps({"anchor_id": a.anchor_id, "goal": a.goal, "domain": a.domain, "background": a.background})
            for a in anchors
            if a.usable_for_trace_replay and a.anchor_type != "ignored_unusable"
        )
        if needed_by_domain is None:
            existing = Counter(a.domain for a in anchors if a.usable_for_trace_replay and a.anchor_type != "ignored_unusable")
            needed_by_domain = {domain: DOMAIN_TARGETS[domain] - existing.get(domain, 0) for domain in DOMAIN_TARGETS}
        candidates = generate_candidates_live(PROMPT_GENERATE, anchor_payload, needed_by_domain, model=model)

    candidates = _assign_generated_ids([_normalize_candidate(candidate) for candidate in candidates], start=start_id)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"seed": seed, "candidates": [c.model_dump() for c in candidates]}, indent=2))
    return candidates


def filter_goals(
    anchor_goals: list[BenchmarkGoal],
    candidates: list[GeneratedGoalCandidate],
    dry_run: bool = True,
    output_path: Path | None = None,
    model: str | None = None,
) -> tuple[list[BenchmarkGoal], list[FilterDecision]]:
    accepted: list[BenchmarkGoal] = []
    decisions: list[FilterDecision] = []
    existing: list[tuple[str, str]] = [(goal.goal_id, goal.goal_text) for goal in anchor_goals]
    domain_counts = Counter(goal.domain for goal in anchor_goals)

    for candidate in candidates:
        nearest_id, similarity = nearest_goal(candidate.goal_text, existing)
        style_issues = concise_goal_issues(candidate.goal_text)
        deterministic_ok = (
            candidate.requires_personalization
            and candidate.requires_decomposition
            and bool(candidate.expected_tangible_outputs)
            and bool(candidate.known_context_needs)
            and not style_issues
            and similarity < 0.82
            and domain_counts[candidate.domain] < DOMAIN_TARGETS[candidate.domain]
        )
        if dry_run:
            decision = FilterDecision(
                goal_id=candidate.goal_id,
                goal_text=candidate.goal_text,
                accepted=deterministic_ok,
                realism=True,
                needs_personal_context=candidate.requires_personalization,
                benefits_from_decomposition=candidate.requires_decomposition,
                produces_tangible_artifact=bool(candidate.expected_tangible_outputs),
                not_mostly_search="pure fact lookup" in candidate.avoid,
                rejection_reason=None if deterministic_ok else _deterministic_rejection_reason(style_issues),
                nearest_goal_id=nearest_id,
                similarity_score=similarity,
            )
        else:
            decision = filter_goal_live(PROMPT_FILTER, candidate, nearest_id, similarity, model=model)
            decision = decision.model_copy(update={"nearest_goal_id": nearest_id, "similarity_score": similarity})
            decision.accepted = decision.accepted and deterministic_ok
            if not deterministic_ok and decision.rejection_reason is None:
                decision.rejection_reason = _deterministic_rejection_reason(style_issues)

        decisions.append(decision)
        if decision.accepted:
            goal = _candidate_to_goal(candidate)
            accepted.append(goal)
            existing.append((goal.goal_id, goal.goal_text))
            domain_counts[goal.domain] += 1

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps([decision.model_dump() for decision in decisions], indent=2))
    return accepted, decisions


def build_all(
    dry_run: bool = True,
    seed: int = 42,
    repo_root: Path = REPO_ROOT,
    data_dir: Path = DEFAULT_DATA_DIR,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    model: str | None = None,
) -> QualityReport:
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    anchor_path = data_dir / "anchor_sessions.jsonl"
    benchmark_path = data_dir / "benchmark.json"
    candidate_path = data_dir / "generated_candidates.json"
    decision_path = data_dir / "filter_decisions.json"
    report_path = reports_dir / "benchmark_quality.json"

    anchors = write_anchor_sessions(anchor_path, repo_root=repo_root)
    anchor_goals = anchor_sessions_to_goals(anchors)
    generated_goals: list[BenchmarkGoal] = []
    all_candidates: list[GeneratedGoalCandidate] = []
    all_decisions: list[FilterDecision] = []
    next_goal_number = 13
    max_attempts = 1 if dry_run else 4

    for _attempt in range(max_attempts):
        current_domain_counts = Counter(goal.domain for goal in anchor_goals + generated_goals)
        needed_by_domain = {
            domain: target - current_domain_counts.get(domain, 0)
            for domain, target in DOMAIN_TARGETS.items()
            if target - current_domain_counts.get(domain, 0) > 0
        }
        if not needed_by_domain:
            break

        candidates = generate_goals(
            anchors,
            dry_run=dry_run,
            seed=seed,
            model=model,
            start_id=next_goal_number,
            needed_by_domain=needed_by_domain,
        )
        if not candidates:
            break

        next_goal_number += len(candidates)
        all_candidates.extend(candidates)
        accepted_goals, decisions = filter_goals(anchor_goals + generated_goals, candidates, dry_run=dry_run, model=model)
        generated_goals.extend(accepted_goals)
        all_decisions.extend(decisions)

        if len(anchor_goals) + len(generated_goals) >= 60:
            break

    candidate_path.write_text(json.dumps({"seed": seed, "candidates": [c.model_dump() for c in all_candidates]}, indent=2))
    decision_path.write_text(json.dumps([decision.model_dump() for decision in all_decisions], indent=2))
    benchmark = anchor_goals + generated_goals
    benchmark_path.write_text(json.dumps([goal.model_dump() for goal in benchmark], indent=2))
    report = validate_benchmark(benchmark)
    report_path.write_text(report.model_dump_json(indent=2))
    if not report.valid:
        raise RuntimeError(f"Benchmark validation failed: {report.errors}")
    return report


def validate_benchmark_file(path: Path) -> QualityReport:
    payload = json.loads(path.read_text())
    goals = [BenchmarkGoal.model_validate(item) for item in payload]
    return validate_benchmark(goals)


def validate_benchmark(goals: list[BenchmarkGoal]) -> QualityReport:
    errors: list[str] = []
    warnings: list[str] = []
    source_counts = Counter(goal.source for goal in goals)
    domain_counts = Counter(goal.domain for goal in goals)
    anchor_counts = Counter(goal.anchor_type for goal in goals if goal.source == "anchor")
    personalization_count = sum(goal.requires_personalization for goal in goals)
    decomposition_count = sum(goal.requires_decomposition for goal in goals)

    if len(goals) != 60:
        errors.append(f"Expected 60 benchmark goals, found {len(goals)}")
    if source_counts.get("anchor", 0) != 12:
        errors.append(f"Expected exactly 12 anchor goals, found {source_counts.get('anchor', 0)}")
    if anchor_counts.get("human_study_trace", 0) != 9:
        errors.append(f"Expected 9 human-study anchor goals, found {anchor_counts.get('human_study_trace', 0)}")
    if anchor_counts.get("ablation_trace", 0) != 3:
        errors.append(f"Expected 3 ablation anchor goals, found {anchor_counts.get('ablation_trace', 0)}")
    if personalization_count < 45:
        errors.append(f"Expected at least 45 personalized-context goals, found {personalization_count}")
    if decomposition_count < 40:
        errors.append(f"Expected at least 40 decomposition goals, found {decomposition_count}")
    for domain, count in domain_counts.items():
        if count > 18:
            errors.append(f"Domain {domain} exceeds 18-goal cap with {count} goals")
    for goal in goals:
        if not goal.domain or not goal.time_horizon or not goal.complexity:
            errors.append(f"{goal.goal_id} has incomplete metadata")
        if not goal.expected_tangible_outputs:
            errors.append(f"{goal.goal_id} has no expected tangible outputs")
        if not goal.known_context_needs:
            errors.append(f"{goal.goal_id} has no known context needs")
        if goal.source == "anchor" and not goal.anchor_goal_id:
            errors.append(f"{goal.goal_id} is an anchor without anchor_goal_id")
        if goal.source == "generated":
            style_issues = concise_goal_issues(goal.goal_text)
            if style_issues:
                errors.append(f"{goal.goal_id} has verbose or hard-to-parse goal_text: {'; '.join(style_issues)}")

    seen_ids: set[str] = set()
    for goal in goals:
        if goal.goal_id in seen_ids:
            errors.append(f"Duplicate goal_id: {goal.goal_id}")
        seen_ids.add(goal.goal_id)

    for index, goal in enumerate(goals):
        nearest_id, similarity = nearest_goal(
            goal.goal_text,
            [(other.goal_id, other.goal_text) for other in goals[index + 1 :]],
        )
        if nearest_id and similarity >= 0.9:
            errors.append(f"{goal.goal_id} is too similar to {nearest_id} ({similarity:.3f})")
        elif nearest_id and similarity >= 0.82:
            warnings.append(f"{goal.goal_id} is moderately similar to {nearest_id} ({similarity:.3f})")

    return QualityReport(
        valid=not errors,
        total_goals=len(goals),
        source_counts=dict(source_counts),
        domain_counts=dict(domain_counts),
        personalization_count=personalization_count,
        decomposition_count=decomposition_count,
        anchor_counts={str(key): value for key, value in anchor_counts.items()},
        errors=errors,
        warnings=warnings,
    )


def _assign_generated_ids(candidates: list[GeneratedGoalCandidate], start: int) -> list[GeneratedGoalCandidate]:
    assigned: list[GeneratedGoalCandidate] = []
    for offset, candidate in enumerate(candidates):
        assigned.append(candidate.model_copy(update={"goal_id": f"G{start + offset:03d}"}))
    return assigned


def concise_goal_issues(goal_text: str) -> list[str]:
    clean_text = goal_text.strip()
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", clean_text)
    issues: list[str] = []
    if len(words) > MAX_GENERATED_GOAL_WORDS:
        issues.append(f"{len(words)} words exceeds {MAX_GENERATED_GOAL_WORDS}-word max")
    if len(clean_text) > MAX_GENERATED_GOAL_CHARS:
        issues.append(f"{len(clean_text)} characters exceeds {MAX_GENERATED_GOAL_CHARS}-character max")
    lowered = f" {clean_text.lower()} "
    for marker in VERBOSE_GOAL_MARKERS:
        if marker in lowered:
            issues.append(f"contains verbose phrase '{marker.strip()}'")
    if any(punctuation in clean_text for punctuation in [",", ";", ":"]):
        issues.append("contains clause punctuation")
    return issues


def _normalize_candidate(candidate: GeneratedGoalCandidate) -> GeneratedGoalCandidate:
    text = _compact_goal_text(candidate.goal_text)
    return candidate.model_copy(update={"goal_text": text})


def _compact_goal_text(goal_text: str) -> str:
    text = goal_text.strip()
    text = re.sub(r"[.!?]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    lowered = text.lower()

    match = re.match(r"^create an? .+ plan for exploring (.+)$", lowered)
    if match:
        return _title_goal(f"Explore {match.group(1)}")

    match = re.match(r"^(?:create|develop|build) an? (?:\d+[- ]\w+ )?.*? plan to (.+)$", lowered)
    if match:
        text = match.group(1)

    match = re.match(r"^move from .+ to (?:a |an )?(?:first )?(.+?) role(?: .*)?$", lowered)
    if match:
        return _title_goal(f"Become a {match.group(1)}")

    for delimiter in [
        " while ",
        " within ",
        " with ",
        " that ",
        " without ",
        " around ",
        " using ",
        " as ",
        " presenting ",
        " traveling ",
        " after ",
        " before ",
        " where ",
        " who ",
    ]:
        if delimiter in f" {text.lower()} ":
            text = re.split(delimiter.strip(), text, flags=re.IGNORECASE)[0].strip()
            break

    text = re.sub(r"\b(in|over) \d+[- ]?(?:day|days|week|weeks|month|months)\b$", "", text, flags=re.IGNORECASE).strip()
    if concise_goal_issues(text):
        text = _compact_goal_tail(text)
    return _title_goal(text)


def _title_goal(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    return text[0].upper() + text[1:]


def _compact_goal_tail(text: str) -> str:
    lowered = text.lower()
    if " to prepare " in lowered:
        return re.split(r"\s+to prepare\s+", text, flags=re.IGNORECASE)[0].strip()
    if " for managing " in lowered:
        return re.split(r"\s+for managing\s+", text, flags=re.IGNORECASE)[0].strip()
    if " for " in lowered and not lowered.startswith(("apply for ", "prepare for ")):
        return re.split(r"\s+for\s+", text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if "," in text:
        return text.split(",", 1)[0].strip()
    return text


def _deterministic_rejection_reason(style_issues: list[str]) -> str:
    if style_issues:
        return "Rejected by concise goal-text gate: " + "; ".join(style_issues)
    return "Rejected by deterministic similarity/domain/metadata gate"


def _candidate_to_goal(candidate: GeneratedGoalCandidate) -> BenchmarkGoal:
    if not candidate.goal_id:
        raise ValueError("Generated goal candidate is missing goal_id")
    return BenchmarkGoal(
        goal_id=candidate.goal_id,
        goal_text=candidate.goal_text,
        source="generated",
        anchor_goal_id=candidate.anchor_goal_id,
        anchor_type=None,
        domain=candidate.domain,
        time_horizon=candidate.time_horizon,
        expected_context_richness=candidate.expected_context_richness,
        complexity=candidate.complexity,
        requires_personalization=candidate.requires_personalization,
        requires_decomposition=candidate.requires_decomposition,
        expected_tangible_outputs=candidate.expected_tangible_outputs,
        known_context_needs=candidate.known_context_needs,
        avoid=candidate.avoid,
    )


def _anchor_time_horizon(domain: Domain) -> str:
    if domain == "events_coordination":
        return "multi-week"
    if domain == "career_education":
        return "multi-month"
    if domain == "everyday_admin_home":
        return "multi-week"
    if domain == "creative_personal":
        return "multi-month"
    return "multi-month"
