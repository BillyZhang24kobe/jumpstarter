from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Domain = Literal[
    "career_education",
    "creative_personal",
    "everyday_admin_home",
    "events_coordination",
    "health_wellness_training",
]

DOMAIN_TARGETS: dict[Domain, int] = {
    "career_education": 16,
    "creative_personal": 14,
    "everyday_admin_home": 14,
    "events_coordination": 10,
    "health_wellness_training": 6,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnchorSession(StrictModel):
    anchor_id: str
    participant_id: str | None = None
    anchor_type: Literal["human_study_trace", "ablation_trace", "ignored_unusable"]
    first_condition: str | None = None
    goal: str
    domain: Domain
    docx_path: str | None = None
    stats_row_id: int | None = None
    jumpstarter_log_file: str | None = None
    jumpstarter_log_line: int | None = None
    chatgpt_share_url: str | None = None
    usable_for_trace_replay: bool
    human_rated: bool
    docx_goal: str | None = None
    background: str | None = None
    docx_excerpt: str | None = None
    rating_snippets: list[str] = Field(default_factory=list)
    root_task: str | None = None
    root_node: dict[str, Any] | None = None
    user_global_context: dict[str, Any] = Field(default_factory=dict)
    user_context: dict[str, Any] = Field(default_factory=dict)
    saved_draft_context: dict[str, str] = Field(default_factory=dict)
    parse_warnings: list[str] = Field(default_factory=list)


class BenchmarkGoal(StrictModel):
    goal_id: str
    goal_text: str
    source: Literal["anchor", "generated"]
    anchor_goal_id: str | None = None
    anchor_type: Literal["human_study_trace", "ablation_trace"] | None = None
    domain: Domain
    time_horizon: str
    expected_context_richness: Literal["low", "medium", "high"]
    complexity: str
    requires_personalization: bool
    requires_decomposition: bool
    expected_tangible_outputs: list[str]
    known_context_needs: list[str]
    avoid: list[str] = Field(default_factory=lambda: ["pure fact lookup", "one-shot generic advice"])


class GeneratedGoalCandidate(StrictModel):
    goal_id: str | None = None
    goal_text: str
    anchor_goal_id: str | None = None
    domain: Domain
    time_horizon: str
    expected_context_richness: Literal["low", "medium", "high"]
    complexity: str
    requires_personalization: bool
    requires_decomposition: bool
    expected_tangible_outputs: list[str]
    known_context_needs: list[str]
    avoid: list[str] = Field(default_factory=lambda: ["pure fact lookup", "one-shot generic advice"])


class GoalGenerationBatch(StrictModel):
    candidates: list[GeneratedGoalCandidate]


class FilterDecision(StrictModel):
    goal_id: str | None = None
    goal_text: str
    accepted: bool
    realism: bool
    needs_personal_context: bool
    benefits_from_decomposition: bool
    produces_tangible_artifact: bool
    not_mostly_search: bool
    rejection_reason: str | None = None
    nearest_goal_id: str | None = None
    similarity_score: float | None = None


class Persona(StrictModel):
    persona_id: str
    persona_type: Literal["base", "controlled_variant"]
    source_participant: str
    source_anchor_id: str
    goal: str
    user_description: str
    goal_domain_preferences: list[Domain]
    expertise_level: Literal["novice", "intermediate", "expert"]
    context_richness: Literal["low", "medium", "high"]
    decision_style: Literal["deferential", "collaborative", "opinionated"]
    communication_style: Literal["terse", "balanced", "verbose"]
    task_objectives: list[str]
    known_facts: list[str]
    preferences: list[str]
    gaps_in_self_knowledge: list[str]
    constraints_to_remember: list[str]
    information_disclosure_policy: list[str]
    response_style_rules: list[str]
    success_criteria: list[str]
    pushback_triggers: list[str]
    evidence_quotes: list[str]
    variant_axis: str | None = None
    variant_description: str | None = None
    extraction_warnings: list[str] = Field(default_factory=list)


class PersonaBatch(StrictModel):
    personas: list[Persona]


class PersonaExtractionReport(StrictModel):
    valid: bool
    total_personas: int
    base_personas: int
    controlled_variants: int
    source_participants: list[str]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TurnStyle(StrictModel):
    max_tokens: int
    front_loading_allowed: bool
    allow_bullets: bool
    tone: str


class StablePersonaTraits(StrictModel):
    expertise_level: Literal["novice", "intermediate", "expert"]
    context_richness: Literal["low", "medium", "high"]
    decision_style: Literal["deferential", "collaborative", "opinionated"]
    communication_style: Literal["terse", "balanced", "verbose"]
    task_objectives: list[str]
    preferences: list[str]
    information_disclosure_policy: list[str]
    response_style_rules: list[str]
    persona_pushback_triggers: list[str]


class SimulationProfile(StrictModel):
    simulation_profile_id: str
    persona_id: str
    goal_id: str
    goal_text: str
    domain: Domain
    private_context_facts: list[str]
    unknown_or_undecided_facts: list[str]
    must_reveal_if_asked: list[str]
    do_not_volunteer: list[str]
    approval_criteria: list[str]
    pushback_rules: list[str]
    stable_persona_traits: StablePersonaTraits
    turn_style: TurnStyle
    initial_state: dict[str, Any] = Field(default_factory=dict)
    state_tracking_notes: list[str] = Field(default_factory=list)
    source_persona_summary: str


class SimulationProfileBatch(StrictModel):
    profiles: list[SimulationProfile]


class SimulationProfileReport(StrictModel):
    valid: bool
    total_profiles: int
    persona_count: int
    goal_count: int
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SimulationProfileSplitReport(StrictModel):
    valid: bool
    source_profiles_path: str
    validation_output_path: str
    test_output_path: str
    test_300_output_path: str | None = None
    metadata_output_path: str
    total_profiles: int
    validation_profile_count: int
    test_profile_count: int
    test_300_profile_count: int = 0
    validation_persona_count: int
    validation_goal_count: int
    validation_source_participant_count: int
    test_300_persona_count: int = 0
    test_300_goal_count: int = 0
    test_300_domain_counts: dict[str, int] = Field(default_factory=dict)
    validation_profile_ids: list[str]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowEvent(StrictModel):
    event_id: int
    event_type: str
    actor: Literal["user", "system", "simulator", "evaluator"]
    stage: str
    node_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowSession(StrictModel):
    session_id: str
    condition: str
    simulation_profile_id: str
    persona_id: str
    goal_id: str
    goal_text: str
    seed: int
    events: list[WorkflowEvent]
    final_state: dict[str, Any] = Field(default_factory=dict)


class WorkflowLiveQuestionResponse(StrictModel):
    question: str
    requested_context_key: str


class WorkflowLiveTaskNode(StrictModel):
    title: str
    description: str


class WorkflowLiveTaskDecompositionResponse(StrictModel):
    nodes: list[WorkflowLiveTaskNode]


class WorkflowLiveSubtaskDetectionResponse(StrictModel):
    suggested_action: Literal["draft_answer", "decompose_further"]
    rationale: str


class WorkflowLiveTaskForkingResponse(StrictModel):
    answer: Literal["Yes", "No"]
    reason: str
    entity_source_context_id: str | None = None
    entities: list[str] = Field(default_factory=list)


class WorkflowLiveContextSelectionResponse(StrictModel):
    selected_context_ids: list[str] = Field(default_factory=list)
    selection_reason: str


class WorkflowLiveDraftResponse(StrictModel):
    draft: str


class WorkflowFidelityReport(StrictModel):
    valid: bool
    total_sessions: int
    condition_counts: dict[str, int]
    average_user_response_words: float
    max_user_response_words: int
    front_loading_events: int
    unknown_answer_events: int
    pushback_events: int
    approval_events: int
    private_fact_leakage_events: int
    subtask_detection_events: int
    decompose_further_events: int
    task_forking_detection_events: int
    task_forking_events: int
    context_selection_events: int
    saved_local_context_events: int
    completed_subtasks: int
    stage_counts: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExperimentRunReport(StrictModel):
    valid: bool
    experiment_id: str
    total_sessions: int
    total_profiles: int
    conditions: list[str]
    runs_per_profile: int
    max_workers: int = 1
    workflow_model: str = "deterministic"
    simulated_user_model: str = "deterministic"
    live_stages: str = "deterministic"
    live_simulated_user: bool = False
    condition_counts: dict[str, int]
    expected_sessions: int
    grid_complete: bool
    artifact_count: int
    judge_input_count: int
    average_output_words: float
    average_selected_context_items: float
    average_reused_context_items: float
    workflow_fidelity: WorkflowFidelityReport
    output_dir: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MetricSummary(StrictModel):
    count: int
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    stderr: float | None = None


class WorkflowConditionScoreSummary(StrictModel):
    condition: str
    count: int
    study_quality_score: MetricSummary
    overall_score: MetricSummary
    rubric_means: dict[str, float] = Field(default_factory=dict)
    output_words: MetricSummary
    selected_context_item_count: MetricSummary
    reused_context_item_count: MetricSummary
    selected_context_token_count: MetricSummary
    reused_context_token_count: MetricSummary
    context_precision_proxy: MetricSummary
    context_recall_proxy: MetricSummary
    selected_relevance_score_mean: MetricSummary
    component_trace_metrics: dict[str, MetricSummary] = Field(default_factory=dict)
    gpt_context_relevance_metrics: dict[str, MetricSummary] = Field(default_factory=dict)


class WorkflowConditionComparison(StrictModel):
    baseline_condition: str
    comparator_condition: str
    aggregate_only: bool = False
    matched_profile_count: int
    mean_delta: float | None = None
    stderr_delta: float | None = None
    ci95_low: float | None = None
    ci95_high: float | None = None
    wins: int
    ties: int
    losses: int


class WorkflowExperimentAnalysisReport(StrictModel):
    valid: bool
    run_dir: str
    baseline_condition: str
    score_count: int
    condition_count: int
    conditions: list[str]
    condition_summaries: list[WorkflowConditionScoreSummary]
    comparisons: list[WorkflowConditionComparison]
    output_json_path: str
    output_markdown_path: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UserDecisionCalibrationReport(StrictModel):
    valid: bool
    source_logs: list[str]
    output_path: str
    report_path: str
    total_log_records: int
    final_session_count: int
    policies: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class JudgeCalibrationExample(StrictModel):
    calibration_id: str
    anchor_id: str
    participant_id: str
    condition_label: Literal["jumpstarter", "chatgpt"]
    goal_text: str
    user_context: str
    system_output: str
    human_scores_1_7: dict[str, float]
    human_overall_1_7: float
    source_docx_path: str
    source_log_file: str | None = None
    source_log_line: int | None = None
    source_chatgpt_path: str | None = None
    extraction_warnings: list[str] = Field(default_factory=list)


class JudgeCriterionScore(StrictModel):
    score: int = Field(ge=1, le=7)
    evidence: str


class JudgeRubricScore(StrictModel):
    plan_quality: JudgeCriterionScore
    tangible_result_quality: JudgeCriterionScore
    confidence_support: JudgeCriterionScore
    personalization_context_grounding: JudgeCriterionScore
    completeness_coverage: JudgeCriterionScore
    specificity: JudgeCriterionScore
    decomposition_quality: JudgeCriterionScore
    context_curation_reuse: JudgeCriterionScore
    workflow_progress_support: JudgeCriterionScore
    user_burden_reduction: JudgeCriterionScore
    no_contradiction_hallucination: JudgeCriterionScore
    overall: JudgeCriterionScore


class JudgeExtractedEvidence(StrictModel):
    tangible_outputs_found: list[str] = Field(default_factory=list)
    confirmed_user_context_used: list[str] = Field(default_factory=list)
    unresolved_todos_or_placeholders: list[str] = Field(default_factory=list)
    unsupported_or_invented_details: list[str] = Field(default_factory=list)
    workflow_progress_evidence: list[str] = Field(default_factory=list)
    context_reuse_evidence: list[str] = Field(default_factory=list)
    user_burden_evidence: list[str] = Field(default_factory=list)
    final_actionability_summary: str
    extraction_warnings: list[str] = Field(default_factory=list)


class ContextRelevanceLabel(StrictModel):
    relevance_score: float = Field(ge=0.0, le=1.0)
    relevant: bool
    relevance_rationale: str
    relevance_type: Literal["direct", "supporting", "background", "irrelevant", "unknown_or_unusable"]


class JudgeScoreRecord(StrictModel):
    score_id: str
    blind_id: str
    goal_id: str | None = None
    calibration_id: str | None = None
    anchor_id: str | None = None
    condition_label: str | None = None
    model: str
    dry_run: bool
    score: JudgeRubricScore
    study_quality_score: float | None = None
    output_words: int
    extracted_evidence: JudgeExtractedEvidence | None = None
    evidence_model: str | None = None


class JudgeRunReport(StrictModel):
    valid: bool
    input_path: str
    output_path: str
    model: str
    dry_run: bool
    max_workers: int = 1
    total_inputs: int
    total_scores: int
    average_overall: float
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class JudgeCalibrationReport(StrictModel):
    valid: bool
    passes_validation_gates: bool
    calibration_examples: int
    scored_examples: int
    spearman_overall: float | None = None
    mae_overall: float | None = None
    directional_pair_accuracy: float | None = None
    aggregate_direction_passes: bool | None = None
    length_adjusted_directional_accuracy: float | None = None
    order_consistency_accuracy: float | None = None
    study_quality_directional_accuracy: float | None = None
    study_quality_order_averaged_directional_accuracy: float | None = None
    study_quality_order_consistency_accuracy: float | None = None
    study_quality_aggregate_direction_passes: bool | None = None
    study_quality_mean_margin: float | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PairedJudgeOutput(StrictModel):
    artifact_id: str
    condition_label: Literal["jumpstarter", "chatgpt"]
    text: str


class PairedJudgeCalibrationRecord(StrictModel):
    pair_id: str
    pair_family_id: str
    order_variant: Literal["study_order", "reversed_order"]
    anchor_id: str
    participant_id: str
    goal_text: str
    user_context: str
    outputs: list[PairedJudgeOutput]
    human_scores_1_7: dict[str, dict[str, float]]
    human_overall_1_7: dict[str, float]
    source_paths: dict[str, str | None] = Field(default_factory=dict)
    extraction_warnings: list[str] = Field(default_factory=list)


class PairedPointwiseScores(StrictModel):
    A: JudgeRubricScore
    B: JudgeRubricScore


class PairedJudgeResponse(StrictModel):
    pointwise_scores: PairedPointwiseScores
    pairwise_preference: Literal["A", "B", "tie"]
    preference_rationale: str


class PairedJudgeScoreRecord(StrictModel):
    pair_score_id: str
    pair_id: str
    pair_family_id: str
    order_variant: Literal["study_order", "reversed_order"]
    anchor_id: str
    participant_id: str
    model: str
    dry_run: bool
    output_a_condition: Literal["jumpstarter", "chatgpt"]
    output_b_condition: Literal["jumpstarter", "chatgpt"]
    pointwise_scores: PairedPointwiseScores
    pairwise_preference: Literal["A", "B", "tie"]
    preferred_condition: Literal["jumpstarter", "chatgpt", "tie"]
    human_preferred_condition: Literal["jumpstarter", "chatgpt", "tie"]
    study_quality_scores: dict[str, float] = Field(default_factory=dict)
    study_quality_preferred_condition: Literal["jumpstarter", "chatgpt", "tie"] = "tie"
    study_quality_margin: float = 0.0
    preference_rationale: str
    evidence_extractions: dict[str, JudgeExtractedEvidence] = Field(default_factory=dict)
    evidence_model: str | None = None


class PairedJudgeRunReport(StrictModel):
    valid: bool
    input_path: str
    output_path: str
    model: str
    dry_run: bool
    max_workers: int = 1
    total_pairs: int
    total_scores: int
    pairwise_accuracy: float | None = None
    order_consistency_accuracy: float | None = None
    study_quality_pairwise_accuracy: float | None = None
    study_quality_order_averaged_accuracy: float | None = None
    study_quality_order_consistency_accuracy: float | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QualityReport(StrictModel):
    valid: bool
    total_goals: int
    source_counts: dict[str, int]
    domain_counts: dict[str, int]
    personalization_count: int
    decomposition_count: int
    anchor_counts: dict[str, int]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
