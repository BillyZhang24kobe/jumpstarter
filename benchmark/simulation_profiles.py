from __future__ import annotations

import json
import hashlib
from collections import Counter
from pathlib import Path

from .openai_generation import refine_simulation_profiles_live
from .pipeline import DEFAULT_DATA_DIR, DEFAULT_REPORTS_DIR
from .schemas import (
    BenchmarkGoal,
    Persona,
    SimulationProfile,
    SimulationProfileReport,
    SimulationProfileSplitReport,
    StablePersonaTraits,
    TurnStyle,
)


DEFAULT_SIMULATION_PROFILES_PATH = DEFAULT_DATA_DIR / "simulation_profiles.json"
DEFAULT_SIMULATION_PROFILE_REPORT_PATH = DEFAULT_REPORTS_DIR / "simulation_profile_report.json"
DEFAULT_VALIDATION_SIMULATION_PROFILES_PATH = DEFAULT_DATA_DIR / "simulation_profiles_validation_limit10.json"
DEFAULT_TEST_SIMULATION_PROFILES_PATH = DEFAULT_DATA_DIR / "simulation_profiles_test_excluding_validation.json"
DEFAULT_TEST_300_SIMULATION_PROFILES_PATH = DEFAULT_DATA_DIR / "simulation_profiles_test_300.json"
DEFAULT_SIMULATION_PROFILE_SPLIT_PATH = DEFAULT_DATA_DIR / "simulation_profile_split.json"
DEFAULT_SIMULATION_PROFILE_SPLIT_REPORT_PATH = DEFAULT_REPORTS_DIR / "simulation_profile_split_report.json"


def build_simulation_profiles(
    personas_path: Path = DEFAULT_DATA_DIR / "personas.json",
    benchmark_path: Path = DEFAULT_DATA_DIR / "benchmark.json",
    output_path: Path = DEFAULT_SIMULATION_PROFILES_PATH,
    report_path: Path = DEFAULT_SIMULATION_PROFILE_REPORT_PATH,
    live: bool = False,
    model: str | None = None,
) -> SimulationProfileReport:
    personas = read_personas(personas_path)
    goals = read_benchmark_goals(benchmark_path)
    profiles = [build_simulation_profile(persona, goal) for persona in personas for goal in goals]
    if live:
        profiles = refine_simulation_profiles_live(profiles, model=model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps([profile.model_dump() for profile in profiles], indent=2))
    report = validate_simulation_profiles(profiles, personas, goals)
    report_path.write_text(report.model_dump_json(indent=2))
    if not report.valid:
        raise RuntimeError(f"Simulation profile validation failed: {report.errors}")
    return report


def read_personas(path: Path) -> list[Persona]:
    payload = json.loads(path.read_text())
    return [Persona.model_validate(item) for item in payload]


def read_benchmark_goals(path: Path) -> list[BenchmarkGoal]:
    payload = json.loads(path.read_text())
    return [BenchmarkGoal.model_validate(item) for item in payload]


def build_simulation_profile(persona: Persona, goal: BenchmarkGoal) -> SimulationProfile:
    known_goal_facts = [f"{need}: unknown until asked" for need in goal.known_context_needs[:4]]
    is_source_goal = _is_source_goal_pair(persona, goal)
    private_context_facts = _dedupe(_goal_private_facts(persona, goal, is_source_goal))
    unknowns = _dedupe(known_goal_facts + persona.gaps_in_self_knowledge[:3])
    approval = _dedupe(
        [
            f"the plan directly supports: {goal.goal_text}",
            "the assistant uses stated context without inventing facts",
            "the assistant asks for missing information before finalizing details",
        ]
        + [f"includes {output}" for output in goal.expected_tangible_outputs[:4]]
    )

    return SimulationProfile(
        simulation_profile_id=f"{persona.persona_id}_{goal.goal_id}",
        persona_id=persona.persona_id,
        goal_id=goal.goal_id,
        goal_text=goal.goal_text,
        domain=goal.domain,
        private_context_facts=private_context_facts[:8],
        unknown_or_undecided_facts=unknowns[:8],
        must_reveal_if_asked=_must_reveal_if_asked(persona, goal, is_source_goal)[:8],
        do_not_volunteer=_do_not_volunteer(persona, goal, is_source_goal)[:8],
        approval_criteria=approval[:8],
        pushback_rules=_dedupe(persona.pushback_triggers + _goal_pushback_rules(goal))[:8],
        stable_persona_traits=_stable_persona_traits(persona, is_source_goal),
        turn_style=_turn_style_for_persona(persona),
        initial_state={
            "revealed_facts": [],
            "answered_questions": [],
            "approval_status": "not_ready",
            "satisfaction": "neutral",
            "turn_count": 0,
        },
        state_tracking_notes=[
            "Track which private_context_facts have been revealed.",
            "Only approve when approval_criteria are substantially met.",
            "If the assistant contradicts pushback_rules, respond with a correction.",
        ],
        source_persona_summary=_session_persona_summary(persona, goal, is_source_goal),
    )


def validate_simulation_profiles(
    profiles: list[SimulationProfile],
    personas: list[Persona],
    goals: list[BenchmarkGoal],
) -> SimulationProfileReport:
    errors: list[str] = []
    warnings: list[str] = []
    persona_ids = {persona.persona_id for persona in personas}
    goal_ids = {goal.goal_id for goal in goals}
    expected_count = len(persona_ids) * len(goal_ids)
    if len(profiles) != expected_count:
        errors.append(f"Expected {expected_count} simulation profiles, found {len(profiles)}")
    if len({profile.simulation_profile_id for profile in profiles}) != len(profiles):
        errors.append("Simulation profile IDs must be unique")

    seen_pairs: set[tuple[str, str]] = set()
    for profile in profiles:
        pair = (profile.persona_id, profile.goal_id)
        seen_pairs.add(pair)
        if profile.persona_id not in persona_ids:
            errors.append(f"{profile.simulation_profile_id} references unknown persona {profile.persona_id}")
        if profile.goal_id not in goal_ids:
            errors.append(f"{profile.simulation_profile_id} references unknown goal {profile.goal_id}")
        if not profile.private_context_facts:
            warnings.append(f"{profile.simulation_profile_id} has no private_context_facts")
        if not profile.unknown_or_undecided_facts:
            warnings.append(f"{profile.simulation_profile_id} has no unknown_or_undecided_facts")
        if not profile.approval_criteria:
            errors.append(f"{profile.simulation_profile_id} has no approval_criteria")
        if not profile.pushback_rules:
            errors.append(f"{profile.simulation_profile_id} has no pushback_rules")
        if profile.turn_style.max_tokens <= 0:
            errors.append(f"{profile.simulation_profile_id} has invalid turn_style.max_tokens")

    missing_pairs = {(persona_id, goal_id) for persona_id in persona_ids for goal_id in goal_ids} - seen_pairs
    if missing_pairs:
        errors.append(f"Missing {len(missing_pairs)} persona-goal profile pairs")

    return SimulationProfileReport(
        valid=not errors,
        total_profiles=len(profiles),
        persona_count=len(persona_ids),
        goal_count=len(goal_ids),
        errors=errors,
        warnings=warnings,
    )


def validate_simulation_profiles_file(
    profiles_path: Path,
    personas_path: Path = DEFAULT_DATA_DIR / "personas.json",
    benchmark_path: Path = DEFAULT_DATA_DIR / "benchmark.json",
) -> SimulationProfileReport:
    profiles = [SimulationProfile.model_validate(item) for item in json.loads(profiles_path.read_text())]
    personas = read_personas(personas_path)
    goals = read_benchmark_goals(benchmark_path)
    return validate_simulation_profiles(profiles, personas, goals)


def build_simulation_profile_splits(
    profiles_path: Path = DEFAULT_SIMULATION_PROFILES_PATH,
    validation_size: int = 10,
    validation_output_path: Path = DEFAULT_VALIDATION_SIMULATION_PROFILES_PATH,
    test_output_path: Path = DEFAULT_TEST_SIMULATION_PROFILES_PATH,
    test_300_size: int = 300,
    test_300_output_path: Path = DEFAULT_TEST_300_SIMULATION_PROFILES_PATH,
    metadata_output_path: Path = DEFAULT_SIMULATION_PROFILE_SPLIT_PATH,
    report_path: Path = DEFAULT_SIMULATION_PROFILE_SPLIT_REPORT_PATH,
) -> SimulationProfileSplitReport:
    profiles = _read_simulation_profiles(profiles_path)
    validation_profiles, warnings = _select_validation_profiles(profiles, validation_size)
    validation_ids = {profile.simulation_profile_id for profile in validation_profiles}
    test_profiles = [profile for profile in profiles if profile.simulation_profile_id not in validation_ids]
    test_300_profiles, test_300_warnings = _select_balanced_test_subset(test_profiles, test_300_size)
    warnings.extend(test_300_warnings)

    errors = _validate_split(profiles, validation_profiles, test_profiles, validation_size)
    errors.extend(_validate_test_subset(test_profiles, test_300_profiles, test_300_size))
    validation_source_participants = _ordered_unique(
        [_source_participant_id(profile.persona_id) for profile in validation_profiles]
    )
    if len(validation_source_participants) < validation_size:
        warnings.append(
            f"Requested {validation_size} different users, but only "
            f"{len(validation_source_participants)} distinct source participants are represented in the selected split. "
            "The split uses distinct simulation persona_id values and distinct goals."
        )

    metadata = {
        "source_profiles_path": str(profiles_path),
        "validation_size": validation_size,
        "selection_policy": "diagonal_distinct_persona_goal_pairs",
        "validation_profile_ids": [profile.simulation_profile_id for profile in validation_profiles],
        "validation_persona_ids": [profile.persona_id for profile in validation_profiles],
        "validation_goal_ids": [profile.goal_id for profile in validation_profiles],
        "validation_source_participants": validation_source_participants,
        "test_profile_count": len(test_profiles),
        "test_300_size": test_300_size,
        "test_300_profile_ids": [profile.simulation_profile_id for profile in test_300_profiles],
        "test_300_persona_counts": dict(Counter(profile.persona_id for profile in test_300_profiles)),
        "test_300_goal_counts": dict(Counter(profile.goal_id for profile in test_300_profiles)),
        "test_300_domain_counts": dict(Counter(profile.domain for profile in test_300_profiles)),
        "test_300_selection_policy": "largest_remainder_goal_and_persona_balanced_subset_from_test_split",
    }

    validation_output_path.parent.mkdir(parents=True, exist_ok=True)
    test_output_path.parent.mkdir(parents=True, exist_ok=True)
    test_300_output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    validation_output_path.write_text(json.dumps([profile.model_dump() for profile in validation_profiles], indent=2))
    test_output_path.write_text(json.dumps([profile.model_dump() for profile in test_profiles], indent=2))
    test_300_output_path.write_text(json.dumps([profile.model_dump() for profile in test_300_profiles], indent=2))
    metadata_output_path.write_text(json.dumps(metadata, indent=2))

    report = SimulationProfileSplitReport(
        valid=not errors,
        source_profiles_path=str(profiles_path),
        validation_output_path=str(validation_output_path),
        test_output_path=str(test_output_path),
        test_300_output_path=str(test_300_output_path),
        metadata_output_path=str(metadata_output_path),
        total_profiles=len(profiles),
        validation_profile_count=len(validation_profiles),
        test_profile_count=len(test_profiles),
        test_300_profile_count=len(test_300_profiles),
        validation_persona_count=len({profile.persona_id for profile in validation_profiles}),
        validation_goal_count=len({profile.goal_id for profile in validation_profiles}),
        validation_source_participant_count=len(validation_source_participants),
        test_300_persona_count=len({profile.persona_id for profile in test_300_profiles}),
        test_300_goal_count=len({profile.goal_id for profile in test_300_profiles}),
        test_300_domain_counts=dict(Counter(profile.domain for profile in test_300_profiles)),
        validation_profile_ids=[profile.simulation_profile_id for profile in validation_profiles],
        errors=errors,
        warnings=warnings,
    )
    report_path.write_text(report.model_dump_json(indent=2))
    if not report.valid:
        raise RuntimeError(f"Simulation profile split validation failed: {report.errors}")
    return report


def _is_source_goal_pair(persona: Persona, goal: BenchmarkGoal) -> bool:
    return persona.goal == goal.goal_text or goal.anchor_goal_id == persona.source_anchor_id


def _goal_private_facts(persona: Persona, goal: BenchmarkGoal, is_source_goal: bool) -> list[str]:
    facts: list[str] = []
    if is_source_goal:
        facts.extend(persona.known_facts)
        facts.extend(persona.constraints_to_remember)
    else:
        facts.append("Use the stable_persona_traits block for user behavior; prior source-task details should not be used for this goal.")
        facts.append(f"Current benchmark goal: {goal.goal_text}")
    facts.append(f"Current goal requires tangible outputs: {', '.join(goal.expected_tangible_outputs[:3])}")
    facts.append(f"Goal time horizon: {goal.time_horizon}")
    return facts


def _must_reveal_if_asked(persona: Persona, goal: BenchmarkGoal, is_source_goal: bool) -> list[str]:
    if is_source_goal:
        return _dedupe(persona.constraints_to_remember + goal.known_context_needs)
    return _dedupe(goal.known_context_needs)


def _do_not_volunteer(persona: Persona, goal: BenchmarkGoal, is_source_goal: bool) -> list[str]:
    values = goal.known_context_needs[:]
    if is_source_goal:
        values.extend(persona.known_facts)
    else:
        values.append("do not mention facts from the persona's original source goal unless they are directly relevant to the current benchmark goal")
    return _dedupe(values)


def _session_persona_summary(persona: Persona, goal: BenchmarkGoal, is_source_goal: bool) -> str:
    if is_source_goal:
        return persona.user_description
    return (
        "Use this user's stable interaction style for the current benchmark goal: "
        f"{persona.communication_style} communication, {persona.decision_style} decision style, "
        f"{persona.context_richness} context richness, and {persona.expertise_level} expertise. "
        f"Current goal: {goal.goal_text}. "
        "Do not carry over private facts from the user's original source task unless they are directly relevant."
    )


def _stable_persona_traits(persona: Persona, is_source_goal: bool) -> StablePersonaTraits:
    return StablePersonaTraits(
        expertise_level=persona.expertise_level,
        context_richness=persona.context_richness,
        decision_style=persona.decision_style,
        communication_style=persona.communication_style,
        task_objectives=persona.task_objectives,
        preferences=persona.preferences if is_source_goal else ["prefers help that is specific to the current benchmark goal"],
        information_disclosure_policy=persona.information_disclosure_policy,
        response_style_rules=persona.response_style_rules,
        persona_pushback_triggers=persona.pushback_triggers,
    )


def _goal_pushback_rules(goal: BenchmarkGoal) -> list[str]:
    rules = [
        "push back if the assistant skips eliciting required personal context",
        "push back if the output lacks tangible artifacts",
    ]
    if goal.avoid:
        rules.append("push back if the assistant does any of: " + ", ".join(goal.avoid[:3]))
    return rules


def _turn_style_for_persona(persona: Persona) -> TurnStyle:
    if persona.communication_style == "terse":
        return TurnStyle(max_tokens=35, front_loading_allowed=False, allow_bullets=False, tone="brief and direct")
    if persona.communication_style == "verbose":
        return TurnStyle(max_tokens=80, front_loading_allowed=False, allow_bullets=True, tone="context-rich but natural")
    return TurnStyle(max_tokens=55, front_loading_allowed=False, allow_bullets=False, tone="collaborative and concise")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        value = str(value).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _read_simulation_profiles(path: Path) -> list[SimulationProfile]:
    payload = json.loads(path.read_text())
    return [SimulationProfile.model_validate(item) for item in payload]


def _select_validation_profiles(
    profiles: list[SimulationProfile],
    validation_size: int,
) -> tuple[list[SimulationProfile], list[str]]:
    if validation_size <= 0:
        raise ValueError("validation_size must be positive")
    warnings: list[str] = []
    by_pair = {(profile.persona_id, profile.goal_id): profile for profile in profiles}
    persona_ids = _ordered_unique([profile.persona_id for profile in profiles])
    goal_ids = _ordered_unique([profile.goal_id for profile in profiles])
    selected: list[SimulationProfile] = []
    used_personas: set[str] = set()
    used_goals: set[str] = set()

    for persona_id, goal_id in zip(persona_ids, goal_ids):
        profile = by_pair.get((persona_id, goal_id))
        if profile is None:
            continue
        selected.append(profile)
        used_personas.add(persona_id)
        used_goals.add(goal_id)
        if len(selected) == validation_size:
            return selected, warnings

    for profile in profiles:
        if profile.persona_id in used_personas or profile.goal_id in used_goals:
            continue
        selected.append(profile)
        used_personas.add(profile.persona_id)
        used_goals.add(profile.goal_id)
        if len(selected) == validation_size:
            return selected, warnings

    warnings.append(
        "Could not fill the validation split with fully distinct persona-goal pairs; "
        "using the largest distinct subset available."
    )
    return selected, warnings


def _validate_split(
    all_profiles: list[SimulationProfile],
    validation_profiles: list[SimulationProfile],
    test_profiles: list[SimulationProfile],
    validation_size: int,
) -> list[str]:
    errors: list[str] = []
    validation_ids = [profile.simulation_profile_id for profile in validation_profiles]
    test_ids = [profile.simulation_profile_id for profile in test_profiles]
    if len(validation_profiles) != validation_size:
        errors.append(f"Expected {validation_size} validation profiles, found {len(validation_profiles)}")
    if len(set(validation_ids)) != len(validation_ids):
        errors.append("Validation profile IDs must be unique")
    if len(set(validation_ids) & set(test_ids)) > 0:
        errors.append("Validation profiles must be excluded from the test profile file")
    if len(validation_profiles) + len(test_profiles) != len(all_profiles):
        errors.append("Validation and test profile counts do not sum to the full profile count")
    if len({profile.persona_id for profile in validation_profiles}) != len(validation_profiles):
        errors.append("Validation split must use distinct persona_id values")
    if len({profile.goal_id for profile in validation_profiles}) != len(validation_profiles):
        errors.append("Validation split must use distinct goal_id values")
    return errors


def _select_balanced_test_subset(
    test_profiles: list[SimulationProfile],
    sample_size: int,
) -> tuple[list[SimulationProfile], list[str]]:
    if sample_size <= 0:
        raise ValueError("test_300_size must be positive")
    if sample_size > len(test_profiles):
        return [], [f"Requested test-300 size {sample_size}, but only {len(test_profiles)} test profiles are available."]
    if sample_size == len(test_profiles):
        return list(test_profiles), []

    goal_counts = Counter(profile.goal_id for profile in test_profiles)
    persona_counts = Counter(profile.persona_id for profile in test_profiles)
    goal_targets = _largest_remainder_targets(goal_counts, sample_size)
    persona_targets = _largest_remainder_targets(persona_counts, sample_size)
    profiles_by_goal: dict[str, list[SimulationProfile]] = {}
    profiles_by_persona: dict[str, list[SimulationProfile]] = {}
    for profile in test_profiles:
        profiles_by_goal.setdefault(profile.goal_id, []).append(profile)
        profiles_by_persona.setdefault(profile.persona_id, []).append(profile)
    for goal_profiles in profiles_by_goal.values():
        goal_profiles.sort(key=lambda profile: _stable_profile_sort_key(profile.simulation_profile_id))
    for persona_profiles in profiles_by_persona.values():
        persona_profiles.sort(key=lambda profile: _stable_profile_sort_key(profile.simulation_profile_id))

    goal_remaining = dict(goal_targets)
    persona_remaining = dict(persona_targets)
    selected_by_id: dict[str, SimulationProfile] = {}
    persona_ids = sorted(
        persona_remaining,
        key=lambda persona_id: (-persona_remaining[persona_id], _stable_profile_sort_key(persona_id)),
    )

    for persona_id in persona_ids:
        while persona_remaining.get(persona_id, 0) > 0:
            candidates = [
                profile
                for profile in profiles_by_persona.get(persona_id, [])
                if profile.simulation_profile_id not in selected_by_id
                and goal_remaining.get(profile.goal_id, 0) > 0
            ]
            if not candidates:
                break
            candidates.sort(
                key=lambda profile: (
                    -goal_remaining.get(profile.goal_id, 0),
                    _stable_profile_sort_key(profile.goal_id),
                    _stable_profile_sort_key(profile.simulation_profile_id),
                )
            )
            selected = candidates[0]
            selected_by_id[selected.simulation_profile_id] = selected
            goal_remaining[selected.goal_id] -= 1
            persona_remaining[persona_id] -= 1
            if len(selected_by_id) == sample_size:
                break
        if len(selected_by_id) == sample_size:
            break

    if len(selected_by_id) < sample_size:
        remaining = [
            profile
            for profile in test_profiles
            if profile.simulation_profile_id not in selected_by_id
            and goal_remaining.get(profile.goal_id, 0) > 0
        ]
        remaining.sort(
            key=lambda profile: (
                -goal_remaining.get(profile.goal_id, 0),
                _stable_profile_sort_key(profile.simulation_profile_id),
            )
        )
        for profile in remaining[: sample_size - len(selected_by_id)]:
            selected_by_id[profile.simulation_profile_id] = profile
            goal_remaining[profile.goal_id] = max(0, goal_remaining.get(profile.goal_id, 0) - 1)

    if len(selected_by_id) < sample_size:
        remaining = [
            profile
            for profile in test_profiles
            if profile.simulation_profile_id not in selected_by_id
        ]
        remaining.sort(key=lambda profile: _stable_profile_sort_key(profile.simulation_profile_id))
        for profile in remaining[: sample_size - len(selected_by_id)]:
            selected_by_id[profile.simulation_profile_id] = profile

    selected_profiles = sorted(
        selected_by_id.values(),
        key=lambda profile: (
            _stable_profile_sort_key(profile.goal_id),
            _stable_profile_sort_key(profile.persona_id),
            _stable_profile_sort_key(profile.simulation_profile_id),
        ),
    )
    warnings = _test_subset_distribution_warnings(selected_profiles, goal_targets, persona_targets)
    return selected_profiles, warnings


def _largest_remainder_targets(counts: Counter[str], sample_size: int) -> dict[str, int]:
    total = sum(counts.values())
    raw_targets = {
        key: sample_size * count / total
        for key, count in counts.items()
    }
    targets = {key: int(raw_targets[key]) for key in counts}
    remaining = sample_size - sum(targets.values())
    ranked = sorted(
        counts,
        key=lambda key: (
            -(raw_targets[key] - targets[key]),
            -counts[key],
            _stable_profile_sort_key(key),
        ),
    )
    for key in ranked[:remaining]:
        targets[key] += 1
    return targets


def _test_subset_distribution_warnings(
    selected_profiles: list[SimulationProfile],
    goal_targets: dict[str, int],
    persona_targets: dict[str, int],
) -> list[str]:
    warnings: list[str] = []
    selected_goal_counts = Counter(profile.goal_id for profile in selected_profiles)
    selected_persona_counts = Counter(profile.persona_id for profile in selected_profiles)
    if any(selected_goal_counts.get(goal_id, 0) != target for goal_id, target in goal_targets.items()):
        warnings.append("test-300 subset could not exactly match largest-remainder goal_id targets.")
    if any(selected_persona_counts.get(persona_id, 0) != target for persona_id, target in persona_targets.items()):
        warnings.append("test-300 subset could not exactly match largest-remainder persona_id targets.")
    return warnings


def _validate_test_subset(
    test_profiles: list[SimulationProfile],
    test_subset: list[SimulationProfile],
    expected_size: int,
) -> list[str]:
    errors: list[str] = []
    test_ids = {profile.simulation_profile_id for profile in test_profiles}
    subset_ids = [profile.simulation_profile_id for profile in test_subset]
    if len(test_subset) != expected_size:
        errors.append(f"Expected {expected_size} test-300 profiles, found {len(test_subset)}")
    if len(set(subset_ids)) != len(subset_ids):
        errors.append("test-300 profile IDs must be unique")
    if not set(subset_ids).issubset(test_ids):
        errors.append("test-300 profiles must be sampled only from the held-out test profile file")
    return errors


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _source_participant_id(persona_id: str) -> str:
    return persona_id.split("_", 1)[0]


def _stable_profile_sort_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
