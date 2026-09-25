from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .openai_generation import extract_judge_evidence_live, score_pairwise_planning_output_live, score_planning_output_live
from .parsers import read_docx_paragraphs
from .personas import _sanitize_text
from .pipeline import DEFAULT_DATA_DIR, DEFAULT_REPORTS_DIR, REPO_ROOT, build_anchor_sessions, read_anchor_sessions
from .progress import progress
from .schemas import (
    AnchorSession,
    JudgeExtractedEvidence,
    JudgeCalibrationExample,
    JudgeCalibrationReport,
    JudgeCriterionScore,
    PairedJudgeCalibrationRecord,
    PairedJudgeOutput,
    PairedJudgeResponse,
    PairedJudgeRunReport,
    PairedJudgeScoreRecord,
    PairedPointwiseScores,
    JudgeRubricScore,
    JudgeRunReport,
    JudgeScoreRecord,
)


DEFAULT_JUDGE_MODEL = "gpt-5.5"
DEFAULT_JUDGE_CALIBRATION_PATH = DEFAULT_DATA_DIR / "judge_calibration.jsonl"
DEFAULT_PAIRED_JUDGE_CALIBRATION_PATH = DEFAULT_DATA_DIR / "paired_judge_calibration.jsonl"
DEFAULT_STUDY_JUDGE_INPUTS_PATH = DEFAULT_DATA_DIR / "study_judge_inputs.jsonl"
DEFAULT_STUDY_POINTWISE_JUDGE_INPUTS_PATH = DEFAULT_DATA_DIR / "study_pointwise_judge_inputs.jsonl"
DEFAULT_USER_STUDY_JUMPSTARTER_OUTPUT_PATH = DEFAULT_DATA_DIR / "user_study_jumpstarter_output.json"
DEFAULT_JUDGE_CALIBRATION_REPORT_PATH = DEFAULT_REPORTS_DIR / "judge_calibration_report.json"
DEFAULT_PAIRED_JUDGE_CALIBRATION_REPORT_PATH = DEFAULT_REPORTS_DIR / "paired_judge_calibration_report.json"
DEFAULT_STUDY_POINTWISE_JUDGE_CALIBRATION_REPORT_PATH = DEFAULT_REPORTS_DIR / "study_pointwise_judge_calibration_report.json"
DEFAULT_CHATGPT_OUTPUTS_DIR = DEFAULT_DATA_DIR / "chatgpt_outputs"
MAX_CALIBRATION_OUTPUT_CHARS = 40000
PROMPT_JUDGE = Path(__file__).resolve().parent / "prompts" / "judge_planning_output_v1.txt"
PROMPT_PAIRWISE_JUDGE = Path(__file__).resolve().parent / "prompts" / "judge_pairwise_planning_output_v1.txt"
PROMPT_JUDGE_EVIDENCE = Path(__file__).resolve().parent / "prompts" / "judge_evidence_extraction_v1.txt"
JUDGE_CRITERIA = (
    "plan_quality",
    "tangible_result_quality",
    "confidence_support",
    "personalization_context_grounding",
    "completeness_coverage",
    "specificity",
    "decomposition_quality",
    "context_curation_reuse",
    "workflow_progress_support",
    "user_burden_reduction",
    "no_contradiction_hallucination",
    "overall",
)
STUDY_QUALITY_WEIGHTS = {
    "plan_quality": 0.15,
    "tangible_result_quality": 0.15,
    "confidence_support": 0.15,
    "personalization_context_grounding": 0.10,
    "completeness_coverage": 0.10,
    "decomposition_quality": 0.10,
    "context_curation_reuse": 0.10,
    "workflow_progress_support": 0.10,
    "user_burden_reduction": 0.05,
}
STUDY_QUALITY_TIE_THRESHOLD = 0.05


def build_judge_calibration_set(
    anchors_path: Path = DEFAULT_DATA_DIR / "anchor_sessions.jsonl",
    chatgpt_outputs_dir: Path = DEFAULT_CHATGPT_OUTPUTS_DIR,
    output_path: Path = DEFAULT_JUDGE_CALIBRATION_PATH,
    report_path: Path | None = DEFAULT_JUDGE_CALIBRATION_REPORT_PATH,
) -> JudgeCalibrationReport:
    anchors = read_anchor_sessions(anchors_path) if anchors_path.exists() else build_anchor_sessions()
    anchors_by_id = {session.anchor_id: session for session in anchors}
    examples: list[JudgeCalibrationExample] = []
    errors: list[str] = []
    warnings: list[str] = []
    for session in anchors:
        if not _is_jumpstarter_calibration_candidate(session):
            continue
        example, example_warnings = _calibration_example_from_anchor(session)
        warnings.extend(example_warnings)
        if example is None:
            errors.append(f"{session.anchor_id}: could not build JumpStarter calibration example")
            continue
        examples.append(example)

    chatgpt_files = _chatgpt_output_files(chatgpt_outputs_dir)
    recovered_chatgpt_ids: set[str] = set()
    for path in chatgpt_files:
        anchor_id = _anchor_id_from_chatgpt_path(path)
        if anchor_id is None:
            warnings.append(f"Could not infer participant ID from ChatGPT history file: {path}")
            continue
        recovered_chatgpt_ids.add(anchor_id)
        session = anchors_by_id.get(anchor_id)
        if session is None:
            warnings.append(f"{anchor_id}: ChatGPT history file has no matching anchor session")
            continue
        example, example_warnings = _chatgpt_calibration_example_from_anchor(session, path)
        warnings.extend(example_warnings)
        if example is None:
            errors.append(f"{anchor_id}: could not build ChatGPT calibration example from {path.name}")
            continue
        examples.append(example)

    expected_chatgpt_ids = {
        session.anchor_id
        for session in anchors
        if session.anchor_type in {"human_study_trace", "ignored_unusable"} and session.human_rated
    }
    missing_chatgpt_ids = sorted(expected_chatgpt_ids - recovered_chatgpt_ids)
    if missing_chatgpt_ids:
        warnings.append("Missing recovered ChatGPT histories for: " + ", ".join(missing_chatgpt_ids))
    paired_ids = sorted(
        anchor_id
        for anchor_id in {example.anchor_id for example in examples}
        if {example.condition_label for example in examples if example.anchor_id == anchor_id} == {"jumpstarter", "chatgpt"}
    )
    if paired_ids:
        warnings.append(f"Calibration set has {len(paired_ids)} paired JumpStarter/ChatGPT participant examples: {', '.join(paired_ids)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_path, [example.model_dump() for example in examples])
    if examples and not any(example.condition_label == "chatgpt" for example in examples):
        warnings.append("Calibration set currently contains JumpStarter outputs only; add ChatGPT share/output artifacts for paired judge validation.")

    report = JudgeCalibrationReport(
        valid=not errors and bool(examples),
        passes_validation_gates=False,
        calibration_examples=len(examples),
        scored_examples=0,
        errors=errors,
        warnings=warnings,
    )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.model_dump_json(indent=2))
    return report


def build_paired_judge_calibration(
    calibration_path: Path = DEFAULT_JUDGE_CALIBRATION_PATH,
    output_path: Path = DEFAULT_PAIRED_JUDGE_CALIBRATION_PATH,
) -> JudgeCalibrationReport:
    if not calibration_path.exists():
        build_judge_calibration_set(output_path=calibration_path)
    examples = [JudgeCalibrationExample.model_validate(record) for record in _read_jsonl(calibration_path)]
    by_anchor: dict[str, dict[str, JudgeCalibrationExample]] = defaultdict(dict)
    for example in examples:
        by_anchor[example.anchor_id][example.condition_label] = example

    pairs: list[PairedJudgeCalibrationRecord] = []
    warnings: list[str] = []
    for anchor_id in sorted(by_anchor):
        conditions = by_anchor[anchor_id]
        if {"jumpstarter", "chatgpt"} - set(conditions):
            continue
        jumpstarter = conditions["jumpstarter"]
        chatgpt = conditions["chatgpt"]
        base_family_id = f"{anchor_id}_jumpstarter_vs_chatgpt"
        jumpstarter_output = PairedJudgeOutput(
            artifact_id=jumpstarter.calibration_id,
            condition_label="jumpstarter",
            text=jumpstarter.system_output,
        )
        chatgpt_output = PairedJudgeOutput(
            artifact_id=chatgpt.calibration_id,
            condition_label="chatgpt",
            text=chatgpt.system_output,
        )
        study_first = _study_first_condition(jumpstarter.source_docx_path) or _study_first_condition(chatgpt.source_docx_path)
        if study_first == "chatgpt":
            study_order_outputs = [chatgpt_output, jumpstarter_output]
        else:
            study_order_outputs = [jumpstarter_output, chatgpt_output]
            if study_first is None:
                warnings.append(f"{anchor_id}: could not infer real study first condition; defaulted study_order to JumpStarter first")
        pairs.append(
            _paired_record(
                pair_family_id=base_family_id,
                order_variant="study_order",
                anchor_id=anchor_id,
                jumpstarter=jumpstarter,
                chatgpt=chatgpt,
                outputs=study_order_outputs,
            )
        )
        pairs.append(
            _paired_record(
                pair_family_id=base_family_id,
                order_variant="reversed_order",
                anchor_id=anchor_id,
                jumpstarter=jumpstarter,
                chatgpt=chatgpt,
                outputs=list(reversed(study_order_outputs)),
            )
        )

    pair_families = {pair.pair_family_id for pair in pairs}
    if len(pair_families) < 6:
        warnings.append(f"Only {len(pair_families)} paired calibration participant pairs available; validation will be fragile.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_path, [pair.model_dump() for pair in pairs])
    report = JudgeCalibrationReport(
        valid=bool(pairs),
        passes_validation_gates=False,
        calibration_examples=len(pairs),
        scored_examples=0,
        errors=[] if pairs else ["No paired JumpStarter/ChatGPT calibration records found"],
        warnings=warnings,
    )
    return report


def build_study_judge_inputs(
    anchors_path: Path = DEFAULT_DATA_DIR / "anchor_sessions.jsonl",
    chatgpt_outputs_dir: Path = DEFAULT_CHATGPT_OUTPUTS_DIR,
    jumpstarter_output_path: Path = DEFAULT_USER_STUDY_JUMPSTARTER_OUTPUT_PATH,
    output_path: Path = DEFAULT_STUDY_JUDGE_INPUTS_PATH,
) -> JudgeCalibrationReport:
    anchors = read_anchor_sessions(anchors_path) if anchors_path.exists() else build_anchor_sessions()
    anchors_by_id = {session.anchor_id: session for session in anchors}
    jumpstarter_outputs = _load_user_study_jumpstarter_outputs(jumpstarter_output_path)
    examples: list[JudgeCalibrationExample] = []
    warnings: list[str] = []
    errors: list[str] = []

    chatgpt_files = _chatgpt_output_files(chatgpt_outputs_dir)
    for path in chatgpt_files:
        anchor_id = _anchor_id_from_chatgpt_path(path)
        if anchor_id is None:
            warnings.append(f"Could not infer participant ID from ChatGPT history file: {path}")
            continue
        session = anchors_by_id.get(anchor_id)
        if session is None:
            warnings.append(f"{anchor_id}: ChatGPT history file has no matching anchor session")
            continue
        if not _is_jumpstarter_calibration_candidate(session):
            warnings.append(f"{anchor_id}: skipped study judge pair because JumpStarter trace is not usable for paired calibration")
            continue
        output_entry = _best_jumpstarter_output_entry(session, jumpstarter_outputs.get(anchor_id, []))
        render_session = _session_with_jumpstarter_output_entry(session, output_entry) if output_entry else session
        if output_entry:
            warnings.append(f"{anchor_id}: rendered JumpStarter artifact from {jumpstarter_output_path.name}")
        else:
            warnings.append(f"{anchor_id}: no matching entry in {jumpstarter_output_path.name}; used log-derived anchor")
        jumpstarter_example, jumpstarter_warnings = _study_calibration_example_from_anchor(render_session)
        chatgpt_example, chatgpt_warnings = _study_chatgpt_calibration_example_from_anchor(session, path)
        warnings.extend(jumpstarter_warnings)
        warnings.extend(chatgpt_warnings)
        if jumpstarter_example is None:
            errors.append(f"{anchor_id}: could not build structured JumpStarter study artifact")
            continue
        if chatgpt_example is None:
            errors.append(f"{anchor_id}: could not build ChatGPT calibration artifact from {path.name}")
            continue
        examples.extend([jumpstarter_example, chatgpt_example])

    pairs, pair_warnings = _paired_records_from_examples(examples)
    warnings.extend(pair_warnings)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_path, [pair.model_dump() for pair in pairs])
    report = JudgeCalibrationReport(
        valid=not errors and bool(pairs),
        passes_validation_gates=False,
        calibration_examples=len(pairs),
        scored_examples=0,
        errors=errors if errors else ([] if pairs else ["No paired study judge inputs found"]),
        warnings=warnings,
    )
    return report


def build_study_pointwise_judge_inputs(
    paired_inputs_path: Path = DEFAULT_STUDY_JUDGE_INPUTS_PATH,
    output_path: Path = DEFAULT_STUDY_POINTWISE_JUDGE_INPUTS_PATH,
) -> JudgeCalibrationReport:
    if not paired_inputs_path.exists():
        build_study_judge_inputs(output_path=paired_inputs_path)
    pairs = [PairedJudgeCalibrationRecord.model_validate(record) for record in _read_jsonl(paired_inputs_path)]
    examples_by_id: dict[str, JudgeCalibrationExample] = {}
    warnings: list[str] = []
    errors: list[str] = []
    for pair in pairs:
        for output in pair.outputs:
            condition = output.condition_label
            human_scores = pair.human_scores_1_7.get(condition)
            human_overall = pair.human_overall_1_7.get(condition)
            if human_scores is None or human_overall is None:
                errors.append(f"{pair.pair_id}: missing human scores for {condition}")
                continue
            calibration_id = output.artifact_id
            if calibration_id in examples_by_id:
                continue
            examples_by_id[calibration_id] = JudgeCalibrationExample(
                calibration_id=calibration_id,
                anchor_id=pair.anchor_id,
                participant_id=pair.participant_id,
                condition_label=condition,
                goal_text=pair.goal_text,
                user_context=pair.user_context,
                system_output=output.text,
                human_scores_1_7=human_scores,
                human_overall_1_7=float(human_overall),
                source_docx_path=str(pair.source_paths.get(f"{condition}_docx") or pair.source_paths.get("jumpstarter_docx") or ""),
                source_log_file=pair.source_paths.get("jumpstarter_log") if condition == "jumpstarter" else None,
                source_log_line=None,
                source_chatgpt_path=pair.source_paths.get("chatgpt_history") if condition == "chatgpt" else None,
                extraction_warnings=pair.extraction_warnings,
            )

    examples = list(examples_by_id.values())
    anchor_conditions: dict[str, set[str]] = defaultdict(set)
    for example in examples:
        anchor_conditions[example.anchor_id].add(example.condition_label)
    missing_pairs = sorted(anchor_id for anchor_id, conditions in anchor_conditions.items() if conditions != {"jumpstarter", "chatgpt"})
    if missing_pairs:
        warnings.append("Pointwise study calibration has incomplete condition pairs for: " + ", ".join(missing_pairs))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_path, [example.model_dump() for example in examples])
    report = JudgeCalibrationReport(
        valid=not errors and bool(examples),
        passes_validation_gates=False,
        calibration_examples=len(examples),
        scored_examples=0,
        errors=errors if errors else ([] if examples else ["No study pointwise judge inputs found"]),
        warnings=warnings,
    )
    return report


def run_paired_judge(
    input_path: Path = DEFAULT_PAIRED_JUDGE_CALIBRATION_PATH,
    output_path: Path | None = None,
    report_path: Path | None = None,
    live: bool = False,
    model: str | None = None,
    max_workers: int = 4,
) -> PairedJudgeRunReport:
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")
    records = [PairedJudgeCalibrationRecord.model_validate(record) for record in _read_jsonl(input_path)]
    if output_path is None:
        output_path = input_path.with_name("paired_judge_scores.jsonl")
    if report_path is None:
        report_path = output_path.with_name("paired_judge_run_report.json")
    selected_model = model or DEFAULT_JUDGE_MODEL
    scores: list[PairedJudgeScoreRecord] = []
    errors: list[str] = []
    warnings: list[str] = []
    jobs = [(index, record, live, selected_model) for index, record in enumerate(records, start=1)]
    for index, score, error in _run_judge_jobs(
        jobs,
        worker=_score_paired_record_job,
        max_workers=max_workers,
        live=live,
        desc=f"Scoring paired judge records ({max_workers} workers)" if max_workers > 1 else "Scoring paired judge records",
        unit="pair",
    ):
        if error:
            record = records[index - 1]
            errors.append(f"Pair {record.pair_id}: {error}")
            continue
        assert isinstance(score, PairedJudgeScoreRecord)
        scores.append(score)
    scores.sort(key=lambda score: int(score.pair_score_id.removeprefix("PS")))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_path, [score.model_dump() for score in scores])
    if not live:
        warnings.append("Dry-run paired judge scores are heuristic fixtures and must not be used as calibrated GPT-5 evidence.")
    pairwise_accuracy = _pairwise_score_accuracy(scores)
    order_consistency = _order_consistency_accuracy(scores)
    study_quality_accuracy = _study_quality_pairwise_accuracy(scores)
    study_quality_order_averaged_accuracy = _study_quality_order_averaged_accuracy(scores)
    study_quality_order_consistency = _study_quality_order_consistency_accuracy(scores)
    report = PairedJudgeRunReport(
        valid=not errors and len(scores) == len(records),
        input_path=str(input_path),
        output_path=str(output_path),
        model=selected_model,
        dry_run=not live,
        max_workers=max_workers,
        total_pairs=len(records),
        total_scores=len(scores),
        pairwise_accuracy=round(pairwise_accuracy, 4) if pairwise_accuracy is not None else None,
        order_consistency_accuracy=round(order_consistency, 4) if order_consistency is not None else None,
        study_quality_pairwise_accuracy=round(study_quality_accuracy, 4) if study_quality_accuracy is not None else None,
        study_quality_order_averaged_accuracy=round(study_quality_order_averaged_accuracy, 4)
        if study_quality_order_averaged_accuracy is not None
        else None,
        study_quality_order_consistency_accuracy=round(study_quality_order_consistency, 4)
        if study_quality_order_consistency is not None
        else None,
        errors=errors,
        warnings=warnings,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2))
    return report


def validate_paired_judge_calibration(
    scores_path: Path = DEFAULT_PAIRED_JUDGE_CALIBRATION_PATH.with_name("paired_judge_scores.jsonl"),
    report_path: Path | None = DEFAULT_PAIRED_JUDGE_CALIBRATION_REPORT_PATH,
) -> JudgeCalibrationReport:
    scores = [PairedJudgeScoreRecord.model_validate(record) for record in _read_jsonl(scores_path)]
    errors: list[str] = []
    warnings: list[str] = []
    if not scores:
        errors.append("No paired judge scores found")
    pairwise_accuracy = _pairwise_score_accuracy(scores)
    order_consistency = _order_consistency_accuracy(scores)
    aggregate_direction_passes = _aggregate_direction_passes(scores)
    length_adjusted_accuracy = _length_adjusted_pairwise_accuracy(scores)
    study_quality_accuracy = _study_quality_pairwise_accuracy(scores)
    study_quality_order_averaged_accuracy = _study_quality_order_averaged_accuracy(scores)
    study_quality_order_consistency = _study_quality_order_consistency_accuracy(scores)
    study_quality_aggregate_direction_passes = _study_quality_aggregate_direction_passes(scores)
    study_quality_mean_margin = _study_quality_mean_margin(scores)
    if pairwise_accuracy is not None and pairwise_accuracy < 0.7:
        warnings.append(f"Raw pairwise directional accuracy diagnostic is low: {pairwise_accuracy:.3f} < 0.700")
    if not aggregate_direction_passes:
        warnings.append("Raw aggregate direction diagnostic not met for plan/tangible/confidence scores.")
    if length_adjusted_accuracy is not None and length_adjusted_accuracy < 0.7:
        warnings.append(f"Raw length-adjusted directional accuracy diagnostic is low: {length_adjusted_accuracy:.3f} < 0.700")
    if order_consistency is not None and order_consistency < 0.8:
        warnings.append(f"Raw A/B order-consistency diagnostic is low: {order_consistency:.3f} < 0.800")
    if study_quality_order_averaged_accuracy is not None and study_quality_order_averaged_accuracy < 0.7:
        warnings.append(
            "Study-quality order-averaged directional accuracy gate not met: "
            f"{study_quality_order_averaged_accuracy:.3f} < 0.700"
        )
    if not study_quality_aggregate_direction_passes:
        warnings.append("Study-quality aggregate direction gate not met.")
    if study_quality_order_consistency is not None and study_quality_order_consistency < 0.8:
        warnings.append(f"Study-quality A/B order-consistency diagnostic is low: {study_quality_order_consistency:.3f} < 0.800")

    passes = (
        not errors
        and study_quality_order_averaged_accuracy is not None
        and study_quality_order_averaged_accuracy >= 0.7
        and bool(study_quality_aggregate_direction_passes)
    )
    report = JudgeCalibrationReport(
        valid=not errors,
        passes_validation_gates=passes,
        calibration_examples=len(scores),
        scored_examples=len(scores),
        directional_pair_accuracy=round(pairwise_accuracy, 4) if pairwise_accuracy is not None else None,
        aggregate_direction_passes=aggregate_direction_passes,
        length_adjusted_directional_accuracy=round(length_adjusted_accuracy, 4) if length_adjusted_accuracy is not None else None,
        order_consistency_accuracy=round(order_consistency, 4) if order_consistency is not None else None,
        study_quality_directional_accuracy=round(study_quality_accuracy, 4) if study_quality_accuracy is not None else None,
        study_quality_order_averaged_directional_accuracy=round(study_quality_order_averaged_accuracy, 4)
        if study_quality_order_averaged_accuracy is not None
        else None,
        study_quality_order_consistency_accuracy=round(study_quality_order_consistency, 4)
        if study_quality_order_consistency is not None
        else None,
        study_quality_aggregate_direction_passes=study_quality_aggregate_direction_passes,
        study_quality_mean_margin=round(study_quality_mean_margin, 4) if study_quality_mean_margin is not None else None,
        errors=errors,
        warnings=warnings,
    )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.model_dump_json(indent=2))
    return report


def run_judge(
    input_path: Path,
    output_path: Path | None = None,
    report_path: Path | None = None,
    live: bool = False,
    model: str | None = None,
    max_workers: int = 4,
) -> JudgeRunReport:
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")
    records = _read_jsonl(input_path)
    if output_path is None:
        output_path = input_path.with_name("judge_scores.jsonl")
    if report_path is None:
        report_path = output_path.with_name("judge_run_report.json")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    expected_blind_ids = {
        _judge_record_blind_id(record, index)
        for index, record in enumerate(records, start=1)
    }
    existing_scores = [
        score
        for score in _read_checkpointed_judge_scores(output_path)
        if score.blind_id in expected_blind_ids
    ]
    existing_by_blind_id = {score.blind_id: score for score in existing_scores}
    scores: list[JudgeScoreRecord] = list(existing_by_blind_id.values())
    if existing_scores:
        scores.sort(key=lambda score: int(score.score_id.removeprefix("S")))
        _write_jsonl(output_path, [score.model_dump() for score in scores])
    else:
        output_path.write_text("")

    errors: list[str] = []
    warnings: list[str] = []
    selected_model = model or DEFAULT_JUDGE_MODEL
    jobs = [
        (index, record, live, selected_model)
        for index, record in enumerate(records, start=1)
        if _judge_record_blind_id(record, index) not in existing_by_blind_id
    ]

    def checkpoint_score(result: tuple[int, Any, str | None]) -> None:
        _index, score_record, error = result
        if error or not isinstance(score_record, JudgeScoreRecord):
            return
        _append_jsonl_record(output_path, score_record.model_dump())

    for index, score_record, error in _run_judge_jobs(
        jobs,
        worker=_score_record_job,
        max_workers=max_workers,
        live=live,
        desc=f"Scoring judge inputs ({max_workers} workers)" if max_workers > 1 else "Scoring judge inputs",
        unit="input",
        on_result=checkpoint_score,
    ):
        if error:
            errors.append(f"Input {index}: {error}")
            continue
        assert isinstance(score_record, JudgeScoreRecord)
        scores.append(score_record)
    scores.sort(key=lambda score: int(score.score_id.removeprefix("S")))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_path, [score.model_dump() for score in scores])
    if not live:
        warnings.append("Dry-run judge scores are heuristic fixtures and must not be used as calibrated GPT-5 evidence.")

    report = JudgeRunReport(
        valid=not errors and len(scores) == len(records),
        input_path=str(input_path),
        output_path=str(output_path),
        model=selected_model,
        dry_run=not live,
        max_workers=max_workers,
        total_inputs=len(records),
        total_scores=len(scores),
        average_overall=_mean([score.score.overall.score for score in scores]),
        errors=errors,
        warnings=warnings,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2))
    return report


def _score_record_job(job: tuple[int, dict[str, Any], bool, str]) -> tuple[int, JudgeScoreRecord | None, str | None]:
    index, record, live, model = job
    try:
        return index, _score_record(record, index=index, live=live, model=model), None
    except Exception as exc:  # noqa: BLE001
        return index, None, str(exc)


def _score_paired_record_job(
    job: tuple[int, PairedJudgeCalibrationRecord, bool, str],
) -> tuple[int, PairedJudgeScoreRecord | None, str | None]:
    index, record, live, model = job
    try:
        return index, _score_paired_record(record, index=index, live=live, model=model), None
    except Exception as exc:  # noqa: BLE001
        return index, None, str(exc)


def _run_judge_jobs(
    jobs: list[tuple[Any, ...]],
    worker: Any,
    max_workers: int,
    live: bool,
    desc: str,
    unit: str,
    on_result: Any | None = None,
) -> list[tuple[int, Any, str | None]]:
    if max_workers == 1 or len(jobs) <= 1:
        results = []
        for job in progress(jobs, total=len(jobs), desc=desc, unit=unit):
            result = worker(job)
            results.append(result)
            if on_result is not None:
                on_result(result)
        return results

    executor_cls = ProcessPoolExecutor if live else ThreadPoolExecutor
    results: list[tuple[int, Any, str | None]] = []
    with executor_cls(max_workers=max_workers) as executor:
        future_to_index = {executor.submit(worker, job): int(job[0]) for job in jobs}
        for future in progress(as_completed(future_to_index), total=len(future_to_index), desc=desc, unit=unit):
            index = future_to_index[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = (index, None, str(exc))
            results.append(result)
            if on_result is not None:
                on_result(result)
    results.sort(key=lambda item: item[0])
    return results


def validate_judge_calibration(
    calibration_path: Path = DEFAULT_JUDGE_CALIBRATION_PATH,
    scores_path: Path | None = None,
    report_path: Path | None = DEFAULT_JUDGE_CALIBRATION_REPORT_PATH,
) -> JudgeCalibrationReport:
    if scores_path is None:
        scores_path = calibration_path.with_name("judge_scores.jsonl")
    examples = [JudgeCalibrationExample.model_validate(record) for record in _read_jsonl(calibration_path)]
    scores = [JudgeScoreRecord.model_validate(record) for record in _read_jsonl(scores_path)]
    examples_by_id = {example.calibration_id: example for example in examples}
    scores_by_id = {score.calibration_id: score for score in scores if score.calibration_id}

    errors: list[str] = []
    warnings: list[str] = []
    missing_scores = sorted(set(examples_by_id) - set(scores_by_id))
    if missing_scores:
        errors.append(f"Missing judge scores for calibration IDs: {', '.join(missing_scores[:10])}")

    paired_human: list[float] = []
    paired_judge: list[float] = []
    for calibration_id, example in examples_by_id.items():
        score = scores_by_id.get(calibration_id)
        if not score:
            continue
        paired_human.append(example.human_overall_1_7)
        paired_judge.append(float(score.score.overall.score))

    spearman = _spearman(paired_human, paired_judge) if len(paired_human) >= 2 else None
    mae = _mean_absolute_error(paired_human, paired_judge) if paired_human else None
    directional_accuracy = _directional_pair_accuracy(examples_by_id, scores_by_id)
    if directional_accuracy is None:
        warnings.append("No paired JumpStarter/ChatGPT calibration examples available for directional pair accuracy.")

    gates: list[bool] = []
    if spearman is not None:
        gates.append(spearman >= 0.6)
        if spearman < 0.6:
            warnings.append(f"Spearman gate not met: {spearman:.3f} < 0.600")
    else:
        gates.append(False)
        warnings.append("Could not compute Spearman correlation; judge or human scores may be constant, or too few examples are scored.")
    if mae is not None:
        gates.append(mae <= 1.0)
        if mae > 1.0:
            warnings.append(f"MAE gate not met: {mae:.3f} > 1.000")

    report = JudgeCalibrationReport(
        valid=not errors and bool(examples),
        passes_validation_gates=not errors and bool(gates) and all(gates),
        calibration_examples=len(examples),
        scored_examples=len(scores_by_id),
        spearman_overall=round(spearman, 4) if spearman is not None else None,
        mae_overall=round(mae, 4) if mae is not None else None,
        directional_pair_accuracy=round(directional_accuracy, 4) if directional_accuracy is not None else None,
        errors=errors,
        warnings=warnings,
    )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.model_dump_json(indent=2))
    return report


def validate_study_pointwise_judge_calibration(
    calibration_path: Path = DEFAULT_STUDY_POINTWISE_JUDGE_INPUTS_PATH,
    scores_path: Path | None = None,
    report_path: Path | None = DEFAULT_STUDY_POINTWISE_JUDGE_CALIBRATION_REPORT_PATH,
) -> JudgeCalibrationReport:
    if scores_path is None:
        scores_path = calibration_path.with_name("study_pointwise_judge_scores.jsonl")
    examples = [JudgeCalibrationExample.model_validate(record) for record in _read_jsonl(calibration_path)]
    scores = [JudgeScoreRecord.model_validate(record) for record in _read_jsonl(scores_path)]
    examples_by_id = {example.calibration_id: example for example in examples}
    scores_by_id = {score.calibration_id: score for score in scores if score.calibration_id}

    errors: list[str] = []
    warnings: list[str] = []
    missing_scores = sorted(set(examples_by_id) - set(scores_by_id))
    if missing_scores:
        errors.append(f"Missing judge scores for calibration IDs: {', '.join(missing_scores[:10])}")

    paired_human: list[float] = []
    paired_judge_study_quality: list[float] = []
    for calibration_id, example in examples_by_id.items():
        score = scores_by_id.get(calibration_id)
        if not score:
            continue
        paired_human.append(example.human_overall_1_7)
        paired_judge_study_quality.append(_judge_score_study_quality(score))

    spearman = _spearman(paired_human, paired_judge_study_quality) if len(paired_human) >= 2 else None
    mae = _mean_absolute_error(paired_human, paired_judge_study_quality) if paired_human else None
    directional_accuracy = _directional_pair_accuracy(examples_by_id, scores_by_id)
    study_quality_accuracy = _pointwise_study_quality_directional_accuracy(examples_by_id, scores_by_id)
    study_quality_aggregate_direction_passes = _pointwise_study_quality_aggregate_direction_passes(examples_by_id, scores_by_id)
    study_quality_mean_margin = _pointwise_study_quality_mean_margin(examples_by_id, scores_by_id)

    if directional_accuracy is None:
        warnings.append("No paired JumpStarter/ChatGPT calibration examples available for raw pointwise directional accuracy.")
    if study_quality_accuracy is None:
        warnings.append("No paired JumpStarter/ChatGPT calibration examples available for study-quality directional accuracy.")
    elif study_quality_accuracy < 0.7:
        warnings.append(f"Study-quality pointwise directional accuracy gate not met: {study_quality_accuracy:.3f} < 0.700")
    if not study_quality_aggregate_direction_passes:
        warnings.append("Study-quality pointwise aggregate direction gate not met.")
    if mae is not None and mae > 1.25:
        warnings.append(f"Study-quality MAE diagnostic is high: {mae:.3f} > 1.250")
    if spearman is None:
        warnings.append("Could not compute pointwise Spearman correlation; scores may be constant or too few examples are scored.")
    elif spearman < 0:
        warnings.append(f"Pointwise Spearman diagnostic is negative: {spearman:.3f}")

    passes = (
        not errors
        and study_quality_accuracy is not None
        and study_quality_accuracy >= 0.7
        and bool(study_quality_aggregate_direction_passes)
        and (mae is None or mae <= 1.25)
    )
    report = JudgeCalibrationReport(
        valid=not errors and bool(examples),
        passes_validation_gates=passes,
        calibration_examples=len(examples),
        scored_examples=len(scores_by_id),
        spearman_overall=round(spearman, 4) if spearman is not None else None,
        mae_overall=round(mae, 4) if mae is not None else None,
        directional_pair_accuracy=round(directional_accuracy, 4) if directional_accuracy is not None else None,
        study_quality_directional_accuracy=round(study_quality_accuracy, 4) if study_quality_accuracy is not None else None,
        study_quality_aggregate_direction_passes=study_quality_aggregate_direction_passes,
        study_quality_mean_margin=round(study_quality_mean_margin, 4) if study_quality_mean_margin is not None else None,
        errors=errors,
        warnings=warnings,
    )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.model_dump_json(indent=2))
    return report


def _merge_pair_context(jumpstarter: JudgeCalibrationExample, chatgpt: JudgeCalibrationExample) -> str:
    chunks = [
        "Shared study context:",
        jumpstarter.user_context,
        "ChatGPT-session user turns:",
        chatgpt.user_context,
    ]
    return _sanitize_text("\n".join(chunk for chunk in chunks if chunk))


def _load_user_study_jumpstarter_outputs(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        return {}
    outputs: dict[str, list[dict[str, Any]]] = {}
    for participant_id, entries in payload.items():
        if isinstance(entries, list):
            outputs[str(participant_id)] = [entry for entry in entries if isinstance(entry, dict)]
    return outputs


def _best_jumpstarter_output_entry(session: AnchorSession, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    goal = session.goal

    def score(entry: dict[str, Any]) -> float:
        root_node = entry.get("root_node") if isinstance(entry.get("root_node"), dict) else {}
        candidates = [
            str(entry.get("task_input") or ""),
            str(root_node.get("text") or ""),
            str(root_node.get("description") or ""),
        ]
        candidate_text = " ".join(candidates)
        return _text_match_score(goal, candidate_text)

    return max(entries, key=score)


def _text_match_score(left: str, right: str) -> float:
    left_norm = _normalize_match_text(left)
    right_norm = _normalize_match_text(right)
    if not left_norm or not right_norm:
        return 0.0
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    return (overlap * 0.65) + (sequence * 0.35)


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _session_with_jumpstarter_output_entry(session: AnchorSession, entry: dict[str, Any]) -> AnchorSession:
    root_node = entry.get("root_node") if isinstance(entry.get("root_node"), dict) else session.root_node
    user_global_context = entry.get("userGlobalContext") or entry.get("user_global_context") or session.user_global_context
    user_context = entry.get("user_context") or session.user_context
    saved_draft_context = entry.get("saved_draft_context") or session.saved_draft_context
    return session.model_copy(
        update={
            "root_task": _clean_artifact_text(entry.get("task_input")) or session.root_task,
            "root_node": root_node,
            "user_global_context": user_global_context if isinstance(user_global_context, dict) else {},
            "user_context": user_context if isinstance(user_context, dict) else {},
            "saved_draft_context": saved_draft_context if isinstance(saved_draft_context, dict) else {},
        }
    )


def _paired_records_from_examples(examples: list[JudgeCalibrationExample]) -> tuple[list[PairedJudgeCalibrationRecord], list[str]]:
    by_anchor: dict[str, dict[str, JudgeCalibrationExample]] = defaultdict(dict)
    for example in examples:
        by_anchor[example.anchor_id][example.condition_label] = example

    pairs: list[PairedJudgeCalibrationRecord] = []
    warnings: list[str] = []
    for anchor_id in sorted(by_anchor):
        conditions = by_anchor[anchor_id]
        if {"jumpstarter", "chatgpt"} - set(conditions):
            continue
        jumpstarter = conditions["jumpstarter"]
        chatgpt = conditions["chatgpt"]
        pair_family_id = f"{anchor_id}_jumpstarter_vs_chatgpt"
        jumpstarter_output = PairedJudgeOutput(
            artifact_id=jumpstarter.calibration_id,
            condition_label="jumpstarter",
            text=jumpstarter.system_output,
        )
        chatgpt_output = PairedJudgeOutput(
            artifact_id=chatgpt.calibration_id,
            condition_label="chatgpt",
            text=chatgpt.system_output,
        )
        study_first = _study_first_condition(jumpstarter.source_docx_path) or _study_first_condition(chatgpt.source_docx_path)
        if study_first == "chatgpt":
            study_order_outputs = [chatgpt_output, jumpstarter_output]
        else:
            study_order_outputs = [jumpstarter_output, chatgpt_output]
            if study_first is None:
                warnings.append(f"{anchor_id}: could not infer real study first condition; defaulted study_order to JumpStarter first")
        pairs.append(
            _paired_record(
                pair_family_id=pair_family_id,
                order_variant="study_order",
                anchor_id=anchor_id,
                jumpstarter=jumpstarter,
                chatgpt=chatgpt,
                outputs=study_order_outputs,
            )
        )
        pairs.append(
            _paired_record(
                pair_family_id=pair_family_id,
                order_variant="reversed_order",
                anchor_id=anchor_id,
                jumpstarter=jumpstarter,
                chatgpt=chatgpt,
                outputs=list(reversed(study_order_outputs)),
            )
        )
    if len({pair.pair_family_id for pair in pairs}) < 6:
        warnings.append(f"Only {len({pair.pair_family_id for pair in pairs})} paired calibration participant pairs available; validation will be fragile.")
    return pairs, warnings


def _paired_record(
    pair_family_id: str,
    order_variant: str,
    anchor_id: str,
    jumpstarter: JudgeCalibrationExample,
    chatgpt: JudgeCalibrationExample,
    outputs: list[PairedJudgeOutput],
) -> PairedJudgeCalibrationRecord:
    return PairedJudgeCalibrationRecord(
        pair_id=f"{pair_family_id}_{order_variant}",
        pair_family_id=pair_family_id,
        order_variant=order_variant,  # type: ignore[arg-type]
        anchor_id=anchor_id,
        participant_id=jumpstarter.participant_id,
        goal_text=jumpstarter.goal_text,
        user_context=_merge_pair_context(jumpstarter, chatgpt),
        outputs=outputs,
        human_scores_1_7={
            "jumpstarter": jumpstarter.human_scores_1_7,
            "chatgpt": chatgpt.human_scores_1_7,
        },
        human_overall_1_7={
            "jumpstarter": jumpstarter.human_overall_1_7,
            "chatgpt": chatgpt.human_overall_1_7,
        },
        source_paths={
            "jumpstarter_docx": jumpstarter.source_docx_path,
            "jumpstarter_log": jumpstarter.source_log_file,
            "chatgpt_docx": chatgpt.source_docx_path,
            "chatgpt_history": chatgpt.source_chatgpt_path,
        },
        extraction_warnings=jumpstarter.extraction_warnings + chatgpt.extraction_warnings,
    )


def _study_first_condition(source_docx_path: str | None) -> str | None:
    if not source_docx_path:
        return None
    lower_path = source_docx_path.lower()
    if "first chatgpt" in lower_path:
        return "chatgpt"
    if "first jumpstarter" in lower_path:
        return "jumpstarter"
    return None


def _score_paired_record(record: PairedJudgeCalibrationRecord, index: int, live: bool, model: str) -> PairedJudgeScoreRecord:
    output_a, output_b = record.outputs
    payload_a = {
        "goal_text": record.goal_text,
        "user_context": record.user_context,
        "system_output": output_a.text,
    }
    payload_b = {
        "goal_text": record.goal_text,
        "user_context": record.user_context,
        "system_output": output_b.text,
    }
    evidence_a = _extract_judge_evidence(payload_a, live=live, model=model)
    evidence_b = _extract_judge_evidence(payload_b, live=live, model=model)
    payload = {
        "pair_id": record.pair_id,
        "goal_text": record.goal_text,
        "user_context": record.user_context,
        "artifact_A": {
            "artifact_id": output_a.artifact_id,
            "text": output_a.text,
            "extracted_evidence": evidence_a.model_dump(),
        },
        "artifact_B": {
            "artifact_id": output_b.artifact_id,
            "text": output_b.text,
            "extracted_evidence": evidence_b.model_dump(),
        },
    }
    response = (
        score_pairwise_planning_output_live(PROMPT_PAIRWISE_JUDGE, json.dumps(payload, indent=2), model=model)
        if live
        else _dry_run_pairwise_score(output_a, output_b, evidence_a, evidence_b)
    )
    response = _bounded_pairwise_response(response)
    preferred_condition = _preferred_condition(response.pairwise_preference, output_a.condition_label, output_b.condition_label)
    study_quality_a = _study_quality_score(response.pointwise_scores.A)
    study_quality_b = _study_quality_score(response.pointwise_scores.B)
    study_quality_preferred_condition = _preferred_condition_from_values(
        study_quality_a,
        study_quality_b,
        output_a.condition_label,
        output_b.condition_label,
    )
    return PairedJudgeScoreRecord(
        pair_score_id=f"PS{index:05d}",
        pair_id=record.pair_id,
        pair_family_id=record.pair_family_id,
        order_variant=record.order_variant,
        anchor_id=record.anchor_id,
        participant_id=record.participant_id,
        model=model,
        dry_run=not live,
        output_a_condition=output_a.condition_label,
        output_b_condition=output_b.condition_label,
        pointwise_scores=response.pointwise_scores,
        pairwise_preference=response.pairwise_preference,
        preferred_condition=preferred_condition,
        human_preferred_condition=_human_preferred_condition(record.human_overall_1_7),
        study_quality_scores={
            "A": round(study_quality_a, 4),
            "B": round(study_quality_b, 4),
            output_a.condition_label: round(study_quality_a, 4),
            output_b.condition_label: round(study_quality_b, 4),
        },
        study_quality_preferred_condition=study_quality_preferred_condition,  # type: ignore[arg-type]
        study_quality_margin=round(abs(study_quality_a - study_quality_b), 4),
        preference_rationale=response.preference_rationale,
        evidence_extractions={
            "A": evidence_a,
            "B": evidence_b,
            output_a.condition_label: evidence_a,
            output_b.condition_label: evidence_b,
        },
        evidence_model=model if live else "dry_run",
    )


def _dry_run_pairwise_score(
    output_a: PairedJudgeOutput,
    output_b: PairedJudgeOutput,
    evidence_a: JudgeExtractedEvidence | None = None,
    evidence_b: JudgeExtractedEvidence | None = None,
) -> PairedJudgeResponse:
    score_a = _dry_run_score(
        {
            "goal_text": "",
            "user_context": "",
            "system_output": output_a.text,
            "extracted_evidence": evidence_a.model_dump() if evidence_a else {},
        }
    )
    score_b = _dry_run_score(
        {
            "goal_text": "",
            "user_context": "",
            "system_output": output_b.text,
            "extracted_evidence": evidence_b.model_dump() if evidence_b else {},
        }
    )
    preference = "tie"
    if score_a.overall.score > score_b.overall.score:
        preference = "A"
    elif score_b.overall.score > score_a.overall.score:
        preference = "B"
    return PairedJudgeResponse(
        pointwise_scores=PairedPointwiseScores(A=score_a, B=score_b),
        pairwise_preference=preference,  # type: ignore[arg-type]
        preference_rationale="Dry-run heuristic preference; replace with live judge output.",
    )


def _bounded_pairwise_response(response: PairedJudgeResponse) -> PairedJudgeResponse:
    return PairedJudgeResponse(
        pointwise_scores=PairedPointwiseScores(
            A=_bounded_rubric(response.pointwise_scores.A),
            B=_bounded_rubric(response.pointwise_scores.B),
        ),
        pairwise_preference=response.pairwise_preference,
        preference_rationale=response.preference_rationale,
    )


def _preferred_condition(preference: str, condition_a: str, condition_b: str) -> str:
    if preference == "A":
        return condition_a
    if preference == "B":
        return condition_b
    return "tie"


def _preferred_condition_from_values(value_a: float, value_b: float, condition_a: str, condition_b: str) -> str:
    if abs(value_a - value_b) <= STUDY_QUALITY_TIE_THRESHOLD:
        return "tie"
    return condition_a if value_a > value_b else condition_b


def _study_quality_score(rubric: JudgeRubricScore) -> float:
    return sum(getattr(rubric, criterion).score * weight for criterion, weight in STUDY_QUALITY_WEIGHTS.items())


def _judge_score_study_quality(score: JudgeScoreRecord) -> float:
    return float(score.study_quality_score) if score.study_quality_score is not None else _study_quality_score(score.score)


def _study_quality_scores_by_condition(score: PairedJudgeScoreRecord) -> dict[str, float]:
    value_a = _study_quality_score(score.pointwise_scores.A)
    value_b = _study_quality_score(score.pointwise_scores.B)
    return {
        score.output_a_condition: value_a,
        score.output_b_condition: value_b,
    }


def _study_quality_preferred_condition(score: PairedJudgeScoreRecord) -> str:
    values = _study_quality_scores_by_condition(score)
    jumpstarter = values.get("jumpstarter")
    chatgpt = values.get("chatgpt")
    if jumpstarter is None or chatgpt is None:
        return "tie"
    if abs(jumpstarter - chatgpt) <= STUDY_QUALITY_TIE_THRESHOLD:
        return "tie"
    return "jumpstarter" if jumpstarter > chatgpt else "chatgpt"


def _human_preferred_condition(human_overall_1_7: dict[str, float]) -> str:
    jumpstarter = human_overall_1_7.get("jumpstarter")
    chatgpt = human_overall_1_7.get("chatgpt")
    if jumpstarter is None or chatgpt is None:
        return "tie"
    if abs(jumpstarter - chatgpt) < 0.05:
        return "tie"
    return "jumpstarter" if jumpstarter > chatgpt else "chatgpt"


def _pairwise_score_accuracy(scores: list[PairedJudgeScoreRecord]) -> float | None:
    usable = [score for score in scores if score.human_preferred_condition != "tie"]
    if not usable:
        return None
    correct = sum(score.preferred_condition == score.human_preferred_condition for score in usable)
    return correct / len(usable)


def _order_consistency_accuracy(scores: list[PairedJudgeScoreRecord]) -> float | None:
    by_family: dict[str, list[PairedJudgeScoreRecord]] = defaultdict(list)
    for score in scores:
        by_family[score.pair_family_id].append(score)
    usable = [family_scores for family_scores in by_family.values() if len(family_scores) >= 2]
    if not usable:
        return None
    consistent = 0
    for family_scores in usable:
        preferred_conditions = {score.preferred_condition for score in family_scores}
        if len(preferred_conditions) == 1:
            consistent += 1
    return consistent / len(usable)


def _study_quality_pairwise_accuracy(scores: list[PairedJudgeScoreRecord]) -> float | None:
    usable = [score for score in scores if score.human_preferred_condition != "tie"]
    if not usable:
        return None
    correct = sum(_study_quality_preferred_condition(score) == score.human_preferred_condition for score in usable)
    return correct / len(usable)


def _study_quality_order_consistency_accuracy(scores: list[PairedJudgeScoreRecord]) -> float | None:
    by_family: dict[str, list[PairedJudgeScoreRecord]] = defaultdict(list)
    for score in scores:
        by_family[score.pair_family_id].append(score)
    usable = [family_scores for family_scores in by_family.values() if len(family_scores) >= 2]
    if not usable:
        return None
    consistent = 0
    for family_scores in usable:
        preferred_conditions = {_study_quality_preferred_condition(score) for score in family_scores}
        if len(preferred_conditions) == 1:
            consistent += 1
    return consistent / len(usable)


def _study_quality_order_averaged_accuracy(scores: list[PairedJudgeScoreRecord]) -> float | None:
    by_family: dict[str, list[PairedJudgeScoreRecord]] = defaultdict(list)
    for score in scores:
        by_family[score.pair_family_id].append(score)
    correct = 0
    total = 0
    for family_scores in by_family.values():
        human_preferred = family_scores[0].human_preferred_condition
        if human_preferred == "tie":
            continue
        averaged = _study_quality_order_averaged_preference(family_scores)
        total += 1
        if averaged == human_preferred:
            correct += 1
    return correct / total if total else None


def _study_quality_order_averaged_preference(scores: list[PairedJudgeScoreRecord]) -> str:
    values: dict[str, list[float]] = {"jumpstarter": [], "chatgpt": []}
    for score in scores:
        by_condition = _study_quality_scores_by_condition(score)
        for condition in values:
            if condition in by_condition:
                values[condition].append(by_condition[condition])
    if not values["jumpstarter"] or not values["chatgpt"]:
        return "tie"
    jumpstarter = sum(values["jumpstarter"]) / len(values["jumpstarter"])
    chatgpt = sum(values["chatgpt"]) / len(values["chatgpt"])
    if abs(jumpstarter - chatgpt) <= STUDY_QUALITY_TIE_THRESHOLD:
        return "tie"
    return "jumpstarter" if jumpstarter > chatgpt else "chatgpt"


def _study_quality_aggregate_direction_passes(scores: list[PairedJudgeScoreRecord]) -> bool | None:
    if not scores:
        return None
    jumpstarter_values: list[float] = []
    chatgpt_values: list[float] = []
    for score in scores:
        by_condition = _study_quality_scores_by_condition(score)
        if "jumpstarter" in by_condition:
            jumpstarter_values.append(by_condition["jumpstarter"])
        if "chatgpt" in by_condition:
            chatgpt_values.append(by_condition["chatgpt"])
    if not jumpstarter_values or not chatgpt_values:
        return None
    return sum(jumpstarter_values) / len(jumpstarter_values) > sum(chatgpt_values) / len(chatgpt_values)


def _study_quality_mean_margin(scores: list[PairedJudgeScoreRecord]) -> float | None:
    margins: list[float] = []
    for score in scores:
        by_condition = _study_quality_scores_by_condition(score)
        if "jumpstarter" in by_condition and "chatgpt" in by_condition:
            margins.append(by_condition["jumpstarter"] - by_condition["chatgpt"])
    return sum(margins) / len(margins) if margins else None


def _pointwise_study_quality_directional_accuracy(
    examples_by_id: dict[str, JudgeCalibrationExample],
    scores_by_id: dict[str, JudgeScoreRecord],
) -> float | None:
    by_anchor: dict[str, list[tuple[JudgeCalibrationExample, JudgeScoreRecord]]] = defaultdict(list)
    for calibration_id, example in examples_by_id.items():
        score = scores_by_id.get(calibration_id)
        if score:
            by_anchor[example.anchor_id].append((example, score))
    correct = 0
    total = 0
    for pairs in by_anchor.values():
        if len(pairs) < 2:
            continue
        for left_index in range(len(pairs)):
            for right_index in range(left_index + 1, len(pairs)):
                left_example, left_score = pairs[left_index]
                right_example, right_score = pairs[right_index]
                human_delta = left_example.human_overall_1_7 - right_example.human_overall_1_7
                judge_delta = _judge_score_study_quality(left_score) - _judge_score_study_quality(right_score)
                if abs(human_delta) < 0.05:
                    continue
                total += 1
                if human_delta * judge_delta > 0:
                    correct += 1
    return correct / total if total else None


def _pointwise_study_quality_aggregate_direction_passes(
    examples_by_id: dict[str, JudgeCalibrationExample],
    scores_by_id: dict[str, JudgeScoreRecord],
) -> bool | None:
    jumpstarter_values: list[float] = []
    chatgpt_values: list[float] = []
    for calibration_id, example in examples_by_id.items():
        score = scores_by_id.get(calibration_id)
        if not score:
            continue
        if example.condition_label == "jumpstarter":
            jumpstarter_values.append(_judge_score_study_quality(score))
        elif example.condition_label == "chatgpt":
            chatgpt_values.append(_judge_score_study_quality(score))
    if not jumpstarter_values or not chatgpt_values:
        return None
    return sum(jumpstarter_values) / len(jumpstarter_values) > sum(chatgpt_values) / len(chatgpt_values)


def _pointwise_study_quality_mean_margin(
    examples_by_id: dict[str, JudgeCalibrationExample],
    scores_by_id: dict[str, JudgeScoreRecord],
) -> float | None:
    by_anchor: dict[str, dict[str, float]] = defaultdict(dict)
    for calibration_id, example in examples_by_id.items():
        score = scores_by_id.get(calibration_id)
        if score:
            by_anchor[example.anchor_id][example.condition_label] = _judge_score_study_quality(score)
    margins = [
        values["jumpstarter"] - values["chatgpt"]
        for values in by_anchor.values()
        if "jumpstarter" in values and "chatgpt" in values
    ]
    return sum(margins) / len(margins) if margins else None


def _aggregate_direction_passes(scores: list[PairedJudgeScoreRecord]) -> bool | None:
    if not scores:
        return None
    criteria = (
        "plan_quality",
        "tangible_result_quality",
        "confidence_support",
        "decomposition_quality",
        "context_curation_reuse",
        "workflow_progress_support",
        "user_burden_reduction",
    )
    passes: list[bool] = []
    for criterion in criteria:
        jumpstarter_values: list[int] = []
        chatgpt_values: list[int] = []
        for score in scores:
            for label, rubric in (("A", score.pointwise_scores.A), ("B", score.pointwise_scores.B)):
                condition = score.output_a_condition if label == "A" else score.output_b_condition
                value = getattr(rubric, criterion).score
                if condition == "jumpstarter":
                    jumpstarter_values.append(value)
                elif condition == "chatgpt":
                    chatgpt_values.append(value)
        if not jumpstarter_values or not chatgpt_values:
            return None
        passes.append(sum(jumpstarter_values) / len(jumpstarter_values) > sum(chatgpt_values) / len(chatgpt_values))
    return all(passes)


def _length_adjusted_pairwise_accuracy(scores: list[PairedJudgeScoreRecord]) -> float | None:
    usable = [score for score in scores if score.human_preferred_condition != "tie"]
    if not usable:
        return None
    correct = 0
    total = 0
    for score in usable:
        score_a = score.pointwise_scores.A.overall.score
        score_b = score.pointwise_scores.B.overall.score
        # Penalize one-point wins that are likely just verbosity-driven; exact
        # length adjustment happens in later analysis when artifact lengths are joined.
        if abs(score_a - score_b) <= 1 and score.preferred_condition != score.human_preferred_condition:
            total += 1
            continue
        total += 1
        if score.preferred_condition == score.human_preferred_condition:
            correct += 1
    return correct / total if total else None


def _is_jumpstarter_calibration_candidate(session: AnchorSession) -> bool:
    return (
        session.anchor_type == "human_study_trace"
        and session.human_rated
        and session.usable_for_trace_replay
        and bool(session.docx_path)
        and bool(session.root_node)
    )


def _study_calibration_example_from_anchor(session: AnchorSession) -> tuple[JudgeCalibrationExample | None, list[str]]:
    warnings: list[str] = []
    if not _is_jumpstarter_calibration_candidate(session):
        return None, [f"{session.anchor_id}: not a usable JumpStarter human-study calibration anchor"]
    assert session.docx_path is not None
    docx_path = REPO_ROOT / session.docx_path
    scores = _parse_human_scores(docx_path, preferred_condition="Our system")
    if not scores:
        return None, [f"{session.anchor_id}: no usable human quality ratings found in {session.docx_path}"]
    output = _structured_jumpstarter_study_artifact(session)
    if not output:
        return None, [f"{session.anchor_id}: could not render structured JumpStarter study artifact"]
    if len(output) > MAX_CALIBRATION_OUTPUT_CHARS:
        warnings.append(f"{session.anchor_id}: structured study artifact truncated to {MAX_CALIBRATION_OUTPUT_CHARS} characters for judge calibration")
        output = output[:MAX_CALIBRATION_OUTPUT_CHARS]
    return (
        JudgeCalibrationExample(
            calibration_id=f"{session.anchor_id}_jumpstarter_study_artifact",
            anchor_id=session.anchor_id,
            participant_id=session.participant_id or session.anchor_id,
            condition_label="jumpstarter",
            goal_text=_sanitize_text(session.goal),
            user_context=_calibration_user_context(session),
            system_output=output,
            human_scores_1_7=scores,
            human_overall_1_7=_human_overall_1_7(scores),
            source_docx_path=session.docx_path,
            source_log_file=session.jumpstarter_log_file,
            source_log_line=session.jumpstarter_log_line,
            source_chatgpt_path=None,
            extraction_warnings=warnings + session.parse_warnings,
        ),
        warnings,
    )


def _calibration_example_from_anchor(session: AnchorSession) -> tuple[JudgeCalibrationExample | None, list[str]]:
    warnings: list[str] = []
    assert session.docx_path is not None
    docx_path = REPO_ROOT / session.docx_path
    scores = _parse_human_scores(docx_path, preferred_condition="Our system")
    if not scores:
        return None, [f"{session.anchor_id}: no usable human quality ratings found in {session.docx_path}"]
    output = _jumpstarter_output_text(session.root_node or {})
    if not output:
        return None, [f"{session.anchor_id}: no JumpStarter system output found in log root node"]
    if len(output) > MAX_CALIBRATION_OUTPUT_CHARS:
        warnings.append(f"{session.anchor_id}: system output truncated to {MAX_CALIBRATION_OUTPUT_CHARS} characters for judge calibration")
        output = output[:MAX_CALIBRATION_OUTPUT_CHARS]
    context = _calibration_user_context(session)
    human_overall = _human_overall_1_7(scores)
    return (
        JudgeCalibrationExample(
            calibration_id=f"{session.anchor_id}_jumpstarter",
            anchor_id=session.anchor_id,
            participant_id=session.participant_id or session.anchor_id,
            condition_label="jumpstarter",
            goal_text=_sanitize_text(session.goal),
            user_context=context,
            system_output=output,
            human_scores_1_7=scores,
            human_overall_1_7=human_overall,
            source_docx_path=session.docx_path,
            source_log_file=session.jumpstarter_log_file,
            source_log_line=session.jumpstarter_log_line,
            source_chatgpt_path=None,
            extraction_warnings=warnings + session.parse_warnings,
        ),
        warnings,
    )


def _chatgpt_calibration_example_from_anchor(
    session: AnchorSession,
    chatgpt_path: Path,
) -> tuple[JudgeCalibrationExample | None, list[str]]:
    warnings: list[str] = []
    if not session.docx_path:
        return None, [f"{session.anchor_id}: no DOCX path available for ChatGPT human ratings"]
    docx_path = REPO_ROOT / session.docx_path
    scores = _parse_human_scores(docx_path, preferred_condition="ChatGPT")
    if not scores:
        return None, [f"{session.anchor_id}: no usable ChatGPT quality ratings found in {session.docx_path}"]
    raw_history = chatgpt_path.read_text(errors="replace")
    user_turns, assistant_turns = _split_chatgpt_history(raw_history)
    if not assistant_turns:
        assistant_turns = [_sanitize_text(raw_history)]
        warnings.append(f"{session.anchor_id}: ChatGPT history did not use User:/ChatGPT: turn markers; using full file as output")
    system_output = _sanitize_text("\n\n".join(assistant_turns))
    if len(system_output) > MAX_CALIBRATION_OUTPUT_CHARS:
        warnings.append(f"{session.anchor_id}: ChatGPT output truncated to {MAX_CALIBRATION_OUTPUT_CHARS} characters for judge calibration")
        system_output = system_output[:MAX_CALIBRATION_OUTPUT_CHARS]
    if not system_output:
        return None, [f"{session.anchor_id}: empty ChatGPT output in {chatgpt_path}"]
    context = _sanitize_text(
        "\n".join(
            part
            for part in [
                f"Background: {session.background}" if session.background else "",
                "User turns from the ChatGPT session:\n" + "\n\n".join(user_turns) if user_turns else "",
            ]
            if part
        )
    )
    return (
        JudgeCalibrationExample(
            calibration_id=f"{session.anchor_id}_chatgpt",
            anchor_id=session.anchor_id,
            participant_id=session.participant_id or session.anchor_id,
            condition_label="chatgpt",
            goal_text=_sanitize_text(session.goal),
            user_context=context,
            system_output=system_output,
            human_scores_1_7=scores,
            human_overall_1_7=_human_overall_1_7(scores),
            source_docx_path=session.docx_path,
            source_log_file=None,
            source_log_line=None,
            source_chatgpt_path=str(chatgpt_path),
            extraction_warnings=warnings,
        ),
        warnings,
    )


def _study_chatgpt_calibration_example_from_anchor(
    session: AnchorSession,
    chatgpt_path: Path,
) -> tuple[JudgeCalibrationExample | None, list[str]]:
    warnings: list[str] = []
    if not session.docx_path:
        return None, [f"{session.anchor_id}: no DOCX path available for ChatGPT human ratings"]
    docx_path = REPO_ROOT / session.docx_path
    scores = _parse_human_scores(docx_path, preferred_condition="ChatGPT")
    if not scores:
        return None, [f"{session.anchor_id}: no usable ChatGPT quality ratings found in {session.docx_path}"]
    raw_history = chatgpt_path.read_text(errors="replace")
    user_turns, assistant_turns = _split_chatgpt_history(raw_history)
    if not assistant_turns:
        assistant_turns = [_sanitize_text(raw_history)]
        warnings.append(f"{session.anchor_id}: ChatGPT history did not use User:/ChatGPT: turn markers; using full file as output")
    artifact = _structured_chatgpt_study_artifact(session, user_turns, assistant_turns)
    if len(artifact) > MAX_CALIBRATION_OUTPUT_CHARS:
        warnings.append(f"{session.anchor_id}: structured ChatGPT study artifact truncated to {MAX_CALIBRATION_OUTPUT_CHARS} characters for judge calibration")
        artifact = artifact[:MAX_CALIBRATION_OUTPUT_CHARS]
    if not artifact:
        return None, [f"{session.anchor_id}: empty structured ChatGPT artifact in {chatgpt_path}"]
    context = _sanitize_text(
        "\n".join(
            part
            for part in [
                f"Background: {session.background}" if session.background else "",
                "User turns from the ChatGPT session:\n" + "\n\n".join(user_turns) if user_turns else "",
            ]
            if part
        )
    )
    return (
        JudgeCalibrationExample(
            calibration_id=f"{session.anchor_id}_chatgpt_study_artifact",
            anchor_id=session.anchor_id,
            participant_id=session.participant_id or session.anchor_id,
            condition_label="chatgpt",
            goal_text=_sanitize_text(session.goal),
            user_context=context,
            system_output=artifact,
            human_scores_1_7=scores,
            human_overall_1_7=_human_overall_1_7(scores),
            source_docx_path=session.docx_path,
            source_log_file=None,
            source_log_line=None,
            source_chatgpt_path=str(chatgpt_path),
            extraction_warnings=warnings,
        ),
        warnings,
    )


def _parse_human_scores(docx_path: Path, preferred_condition: str) -> dict[str, float]:
    paragraphs = read_docx_paragraphs(docx_path)
    try:
        start = paragraphs.index("Quality of the outputs/progress")
    except ValueError:
        return {}
    metric_labels = {
        "plan_quality": "Quality of the plan the tool helps you create",
        "tangible_result_quality": "Quality of the tangible results",
        "confidence": "How confident do you feel about taking action",
    }
    first_metric_index = min((paragraphs.index(label, start) for label in metric_labels.values() if label in paragraphs[start:]), default=len(paragraphs))
    condition_order = _condition_order(paragraphs[start + 1 : first_metric_index])
    try:
        condition_index = condition_order.index(preferred_condition)
    except ValueError:
        return {}

    scores: dict[str, float] = {}
    for metric_name, label in metric_labels.items():
        if label not in paragraphs[start:]:
            continue
        block_start = paragraphs.index(label, start) + 1
        block_end = _next_rating_label_index(paragraphs, block_start)
        ratings = _rating_values(paragraphs[block_start:block_end])
        if condition_index < len(ratings):
            scores[metric_name] = ratings[condition_index]
    return scores


def _chatgpt_output_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(file for file in path.glob("P*_chatgpt*.txt") if file.is_file())


def _anchor_id_from_chatgpt_path(path: Path) -> str | None:
    match = re.match(r"^(P\d+)_chatgpt", path.name)
    return match.group(1) if match else None


def _split_chatgpt_history(text: str) -> tuple[list[str], list[str]]:
    user_turns: list[str] = []
    assistant_turns: list[str] = []
    current_role: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_role
        content = _sanitize_text("\n".join(current_lines))
        if content:
            if current_role == "user":
                user_turns.append(content)
            elif current_role == "chatgpt":
                assistant_turns.append(content)
        current_lines = []

    for line in text.splitlines():
        if line.startswith("User:"):
            flush()
            current_role = "user"
            current_lines = [line.removeprefix("User:").strip()]
        elif line.startswith("ChatGPT:"):
            flush()
            current_role = "chatgpt"
            current_lines = [line.removeprefix("ChatGPT:").strip()]
        else:
            current_lines.append(line)
    flush()
    return user_turns, assistant_turns


def _condition_order(lines: list[str]) -> list[str]:
    order: list[str] = []
    for line in lines:
        if line.startswith("Our system") and "Our system" not in order:
            order.append("Our system")
        if line.startswith("ChatGPT") and "ChatGPT" not in order:
            order.append("ChatGPT")
    return order


def _next_rating_label_index(paragraphs: list[str], start: int) -> int:
    labels = {
        "Quality of the tangible results",
        "How confident do you feel about taking action",
        "System feature like/dislike",
        "Tool preference",
    }
    for index in range(start, len(paragraphs)):
        if paragraphs[index] in labels:
            return index
    return len(paragraphs)


def _rating_values(lines: list[str]) -> list[float]:
    values: list[float] = []
    for line in lines:
        match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*/\s*7\s*;?", line)
        if match:
            values.append(float(match.group(1)))
    return values


def _human_overall_1_7(scores_1_7: dict[str, float]) -> float:
    if not scores_1_7:
        return 1.0
    return round(sum(max(1.0, min(7.0, value)) for value in scores_1_7.values()) / len(scores_1_7), 3)


def _calibration_user_context(session: AnchorSession) -> str:
    pieces = []
    if session.background:
        pieces.append(f"Background: {session.background}")
    if session.user_global_context:
        pieces.append("Global context: " + json.dumps(session.user_global_context, ensure_ascii=True, sort_keys=True))
    if session.user_context:
        pieces.append("Local context: " + json.dumps(session.user_context, ensure_ascii=True, sort_keys=True))
    return _sanitize_text("\n".join(pieces))


def _structured_jumpstarter_study_artifact(session: AnchorSession) -> str:
    root_node = session.root_node or {}
    task_lines = _task_tree_lines(root_node)
    node_artifacts = _node_working_artifacts(root_node)
    sections = [
        "Artifact type: Structured JumpStarter workflow summary.",
        (
            "Evaluation note: This artifact summarizes the user's 25-minute JumpStarter workflow. "
            "It intentionally omits duplicated intermediate model responses and emphasizes tool-supported planning progress: "
            "task decomposition, context elicitation, context curation/reuse, and working solution drafts."
        ),
        (
            "Anonymization note: University, person, and place names may have been anonymized. "
            "Do not penalize anonymized names unless they contradict the provided user context."
        ),
        f"Goal: {_sanitize_text(session.goal)}",
    ]
    if session.background:
        sections.append(f"User background: {_sanitize_text(session.background)}")
    sections.append(_workflow_progress_summary(root_node))
    usable_outputs = _most_usable_outputs(session, root_node)
    if usable_outputs:
        sections.append("Most Usable Outputs Created:\n" + "\n\n".join(usable_outputs))
    sections.append(_format_context_section("Global Context Elicited", session.user_global_context))
    sections.append(_format_context_section("Local Contexts Selected Or Reused", session.user_context))
    sections.append(_format_context_section("Saved Draft Contexts", session.saved_draft_context))
    if task_lines:
        sections.append("Task Decomposition Tree:\n" + "\n".join(task_lines))
    if node_artifacts:
        sections.append("Working Solution Drafts And Reused Subtask Outputs:\n" + "\n\n".join(node_artifacts))
    if session.parse_warnings:
        sections.append("Parse warnings retained for provenance:\n" + "\n".join(f"- {warning}" for warning in session.parse_warnings))
    return "\n\n".join(section for section in sections if section.strip())


def _structured_chatgpt_study_artifact(session: AnchorSession, user_turns: list[str], assistant_turns: list[str]) -> str:
    usable_outputs = _chatgpt_usable_outputs(assistant_turns)
    subtasks = _chatgpt_subtasks_covered(session.goal, assistant_turns)
    friction = _chatgpt_user_effort_summary(user_turns)
    sections = [
        "Artifact type: Structured ChatGPT study-session summary.",
        (
            "Evaluation note: This artifact summarizes the user's 25-minute ChatGPT workflow in the same study-package style as JumpStarter. "
            "It highlights final usable outputs, subtasks covered, user-provided context, repeated prompting/revisions, and limits of context management."
        ),
        (
            "Anonymization note: University, person, and place names may have been anonymized. "
            "Do not penalize anonymized names unless they contradict the provided user context."
        ),
        f"Goal: {_sanitize_text(session.goal)}",
    ]
    if session.background:
        sections.append(f"User background: {_sanitize_text(session.background)}")
    sections.append(
        "Workflow Progress Summary:\n"
        f"- User turns in recovered ChatGPT session: {len(user_turns)}\n"
        f"- Assistant turns in recovered ChatGPT session: {len(assistant_turns)}\n"
        f"- Distinct usable output excerpts surfaced: {len(usable_outputs)}\n"
        f"- Subtask/topic areas covered: {len(subtasks)}\n"
        "- Explicit persistent task tree/context bank: none in ChatGPT interface\n"
        "- Explicit per-subtask context selection/reuse controls: none in ChatGPT interface"
    )
    if usable_outputs:
        sections.append("Most Usable Outputs Created:\n" + "\n\n".join(usable_outputs))
    if subtasks:
        sections.append("Subtasks Or Topic Areas Covered:\n" + "\n".join(f"- {item}" for item in subtasks))
    if user_turns:
        sections.append("User Inputs And Revision Burden:\n" + "\n".join(f"- {item}" for item in friction))
    sections.append(
        "Context Curation And Reuse Notes:\n"
        "- User context was available only through the linear chat history.\n"
        "- No explicit global context store, local context store, task tree node memory, or subtask-level context selection was available.\n"
        "- Any context reuse depended on the assistant inferring relevant details from prior turns."
    )
    return "\n\n".join(section for section in sections if section.strip())


def _chatgpt_usable_outputs(assistant_turns: list[str], max_items: int = 6) -> list[str]:
    outputs: list[tuple[int, str]] = []
    seen: set[str] = set()
    for index, turn in enumerate(assistant_turns, start=1):
        text = _clean_artifact_text(turn)
        if not text or len(text.split()) < 25:
            continue
        score = _usable_output_score(text)
        if score < 2 and len(outputs) >= 2:
            continue
        title = _infer_output_title(text, fallback=f"Assistant turn {index}")
        candidate = f"- {title}: {_clip_text(text, 1100)}"
        fingerprint = candidate[:260]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        outputs.append((score, candidate))
    ranked = sorted(outputs, key=lambda item: item[0], reverse=True)[:max_items]
    return [item[1] for item in ranked]


def _usable_output_score(text: str) -> int:
    lower = text.lower()
    markers = [
        "calendar",
        "schedule",
        "template",
        "checklist",
        "draft",
        "survey",
        "itinerary",
        "script",
        "table",
        "outline",
        "message",
        "email",
        "tracker",
        "plan",
        "steps",
    ]
    return sum(1 for marker in markers if marker in lower)


def _infer_output_title(text: str, fallback: str) -> str:
    first_line = next((line.strip("#: -*") for line in text.splitlines() if line.strip()), "")
    if first_line and len(first_line) <= 90:
        return _sanitize_text(first_line)
    lower = text.lower()
    for label, markers in {
        "Draft or Template": ("draft", "template", "email", "message"),
        "Schedule or Calendar": ("schedule", "calendar", "itinerary"),
        "Checklist or Tracker": ("checklist", "tracker"),
        "Plan or Outline": ("plan", "outline", "steps"),
        "Survey or Questions": ("survey", "question"),
        "Script or Content": ("script", "content", "video"),
    }.items():
        if any(marker in lower for marker in markers):
            return label
    return fallback


def _chatgpt_subtasks_covered(goal: str, assistant_turns: list[str], max_items: int = 10) -> list[str]:
    text = "\n".join(_clean_artifact_text(turn) for turn in assistant_turns)
    candidates: list[str] = []
    for line in text.splitlines():
        clean = _sanitize_text(line.strip(" -*#0123456789.:\t"))
        if not clean or len(clean.split()) < 2 or len(clean) > 120:
            continue
        if any(keyword in clean.lower() for keyword in ("step", "plan", "schedule", "draft", "create", "prepare", "research", "finalize", "identify", "organize", "write", "design")):
            candidates.append(clean)
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _normalize_match_text(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
        if len(deduped) >= max_items:
            break
    if not deduped and goal:
        deduped.append(f"General planning support for: {_sanitize_text(goal)}")
    return deduped


def _chatgpt_user_effort_summary(user_turns: list[str], max_items: int = 8) -> list[str]:
    if not user_turns:
        return ["No user turns recovered; effort and revision burden cannot be assessed."]
    items = [f"Initial request: {_clip_text(_clean_artifact_text(user_turns[0]), 300)}"]
    revision_markers = ("help me", "remove", "short", "make", "now", "also", "can you", "go through", "complete", "consolidate")
    revision_turns = [
        turn for turn in user_turns[1:] if any(marker in turn.lower() for marker in revision_markers)
    ]
    items.append(f"Follow-up/revision turns recovered: {len(user_turns) - 1}")
    if revision_turns:
        items.append(f"Turns that appear to request correction, refinement, or continued steering: {len(revision_turns)}")
    for turn in user_turns[1 : max_items - 2]:
        items.append(f"Follow-up: {_clip_text(_clean_artifact_text(turn), 300)}")
    return items


def _most_usable_outputs(session: AnchorSession, root_node: dict[str, Any], max_items: int = 6) -> list[str]:
    outputs: list[str] = []
    seen: set[str] = set()
    context_sources = [session.user_context, session.saved_draft_context]
    for context in context_sources:
        for key, value in sorted(context.items()):
            if len(outputs) >= max_items:
                return outputs
            text = _clean_artifact_text(value)
            if not text or len(text.split()) < 5:
                continue
            title = _sanitize_text(str(key))
            candidate = f"- {title}: {_clip_text(text, 700)}"
            fingerprint = candidate[:300]
            if fingerprint not in seen:
                outputs.append(candidate)
                seen.add(fingerprint)
    for node in _flatten_task_nodes(root_node):
        if len(outputs) >= max_items:
            break
        answer_draft = node.get("answer_draft") or {}
        draft = _clean_artifact_text(answer_draft.get("answer_draft_input"))
        if not draft or len(draft.split()) < 5:
            continue
        title = _clean_artifact_text(node.get("text")) or _clean_artifact_text(answer_draft.get("answer_draft_name")) or "Saved draft"
        candidate = f"- {title}: {_clip_text(draft, 700)}"
        fingerprint = candidate[:300]
        if fingerprint not in seen:
            outputs.append(candidate)
            seen.add(fingerprint)
    for node in _flatten_task_nodes(root_node):
        if len(outputs) >= max_items:
            break
        response = _representative_node_response(node)
        if not response or len(response.split()) < 20:
            continue
        title = _clean_artifact_text(node.get("text")) or "Generated working output"
        candidate = f"- {title}: {_clip_text(response, 700)}"
        fingerprint = candidate[:300]
        if fingerprint not in seen:
            outputs.append(candidate)
            seen.add(fingerprint)
    return outputs


def _workflow_progress_summary(root_node: dict[str, Any]) -> str:
    nodes = _flatten_task_nodes(root_node)
    completed = sum(1 for node in nodes if bool(node.get("is_completed")))
    expanded = sum(1 for node in nodes if bool(node.get("children")))
    drafts = sum(1 for node in nodes if _node_has_working_artifact(node))
    return (
        "Workflow Progress Summary:\n"
        f"- Total task nodes represented: {len(nodes)}\n"
        f"- Expanded/decomposed task nodes: {expanded}\n"
        f"- Nodes marked completed in the UI: {completed}\n"
        f"- Nodes with saved or generated working artifacts: {drafts}"
    )


def _format_context_section(title: str, context: dict[str, Any]) -> str:
    if not context:
        return f"{title}: none captured."
    lines = [f"{title}:"]
    for key, value in sorted(context.items()):
        lines.append(f"- {_sanitize_text(str(key))}: {_clip_text(_clean_artifact_text(value), 700)}")
    return "\n".join(lines)


def _task_tree_lines(root_node: dict[str, Any], max_nodes: int = 60) -> list[str]:
    lines: list[str] = []

    def visit(node: dict[str, Any], depth: int) -> None:
        if len(lines) >= max_nodes:
            return
        title = _clean_artifact_text(node.get("text"))
        if not title:
            title = _clean_artifact_text(node.get("id")) or "Untitled task"
        details = []
        duration = _clean_artifact_text(node.get("duration"))
        deadline = _clean_artifact_text(node.get("deadline"))
        if duration:
            details.append(f"duration={duration}")
        if deadline:
            details.append(f"deadline={deadline}")
        if node.get("need_subtasks") is not None:
            details.append(f"needs_subtasks={bool(node.get('need_subtasks'))}")
        if node.get("is_completed") is not None:
            details.append(f"completed={bool(node.get('is_completed'))}")
        suffix = f" ({'; '.join(details)})" if details else ""
        description = _clean_artifact_text(node.get("description"))
        if description:
            suffix += f": {_clip_text(description, 220)}"
        lines.append(f"{'  ' * depth}- {title}{suffix}")
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child, depth + 1)

    if root_node:
        visit(root_node, 0)
    if len(lines) >= max_nodes:
        lines.append(f"... task tree truncated after {max_nodes} nodes")
    return lines


def _node_working_artifacts(root_node: dict[str, Any], max_items: int = 10) -> list[str]:
    artifacts: list[str] = []
    seen: set[str] = set()
    for node in _flatten_task_nodes(root_node):
        if len(artifacts) >= max_items:
            break
        title = _clean_artifact_text(node.get("text")) or _clean_artifact_text(node.get("id")) or "Untitled task"
        snippets: list[str] = []
        answer_draft = node.get("answer_draft") or {}
        draft_input = _clean_artifact_text(answer_draft.get("answer_draft_input"))
        if draft_input:
            snippets.append("Saved answer draft: " + _clip_text(draft_input, 900))
        curated_context = _clean_artifact_text(node.get("curated_context_draft"))
        if curated_context:
            snippets.append("Curated/reused context for this subtask: " + _clip_text(curated_context, 500))
        if not snippets:
            response = _representative_node_response(node)
            if response:
                snippets.append("Generated working output: " + _clip_text(response, 900))
        if not snippets:
            continue
        text = f"Subtask: {title}\n" + "\n".join(f"- {snippet}" for snippet in snippets)
        fingerprint = text[:500]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        artifacts.append(text)
    return artifacts


def _representative_node_response(node: dict[str, Any]) -> str:
    candidates: list[str] = []
    for key in ("gpt_response", "gpt_response_steps"):
        for item in node.get(key) or []:
            if isinstance(item, dict):
                text = _clean_artifact_text(item.get("response"))
            else:
                text = _clean_artifact_text(item)
            if text:
                candidates.append(text)
    if not candidates:
        return ""
    return max(candidates, key=len)


def _node_has_working_artifact(node: dict[str, Any]) -> bool:
    answer_draft = node.get("answer_draft") or {}
    return bool(
        _clean_artifact_text(answer_draft.get("answer_draft_input"))
        or _clean_artifact_text(node.get("curated_context_draft"))
        or _representative_node_response(node)
    )


def _flatten_task_nodes(root_node: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def visit(node: dict[str, Any]) -> None:
        nodes.append(node)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child)

    if root_node:
        visit(root_node)
    return nodes


def _clean_artifact_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=True, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return _sanitize_text(_strip_html(value))


def _clip_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _jumpstarter_output_text(root_node: dict[str, Any]) -> str:
    chunks: list[str] = []

    def add_text(value: Any) -> None:
        if not isinstance(value, str):
            return
        text = _sanitize_text(_strip_html(value))
        if text and text not in chunks:
            chunks.append(text)

    def visit(node: dict[str, Any]) -> None:
        title = node.get("text")
        description = node.get("description")
        if title or description:
            add_text(f"{title}: {description}")
        for key in ("gpt_response_steps", "gpt_response_brainstorm", "gpt_response"):
            for item in node.get(key) or []:
                if isinstance(item, dict):
                    add_text(item.get("response"))
                else:
                    add_text(item)
        answer_draft = node.get("answer_draft") or {}
        add_text(answer_draft.get("answer_draft_input"))
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child)

    visit(root_node)
    return "\n\n".join(chunks)


def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_judge_evidence(payload: dict[str, Any], live: bool, model: str) -> JudgeExtractedEvidence:
    if live:
        try:
            return extract_judge_evidence_live(PROMPT_JUDGE_EVIDENCE, json.dumps(payload, indent=2), model=model)
        except Exception as exc:  # noqa: BLE001 - evidence extraction should not discard the artifact.
            fallback = _dry_run_evidence_extraction(payload)
            fallback.extraction_warnings.append(f"Live evidence extraction failed; used heuristic fallback: {exc}")
            return fallback
    return _dry_run_evidence_extraction(payload)


def _dry_run_evidence_extraction(payload: dict[str, Any]) -> JudgeExtractedEvidence:
    output = str(payload.get("system_output", ""))
    context = str(payload.get("user_context", ""))
    output_lines = _meaningful_lines(output)
    tangible = _evidence_lines(
        output_lines,
        [
            "checklist",
            "schedule",
            "calendar",
            "tracker",
            "template",
            "survey",
            "message",
            "email",
            "draft",
            "outline",
            "table",
            "subject:",
            "|",
        ],
        max_items=8,
    )
    unresolved = _evidence_lines(
        output_lines,
        [
            "todo",
            "tbd",
            "[",
            "insert",
            "placeholder",
            "open decision",
            "to be specified",
            "your name",
            "your email",
            "confirm before",
        ],
        max_items=8,
    )
    unsupported = _unsupported_specific_lines(output_lines, context)
    workflow = _evidence_lines(
        output_lines,
        [
            "task decomposition",
            "workflow progress",
            "subtask",
            "phase",
            "step",
            "completed",
            "saved draft",
            "working solution",
            "next action",
        ],
        max_items=8,
    )
    context_reuse = _evidence_lines(
        output_lines,
        [
            "context",
            "confirmed inputs",
            "global context",
            "local context",
            "selected",
            "reused",
            "saved draft",
            "context bank",
        ],
        max_items=8,
    )
    burden = _evidence_lines(
        output_lines,
        [
            "verify",
            "confirm",
            "replace",
            "todo",
            "placeholder",
            "open decision",
            "manual",
            "cleanup",
            "before use",
        ],
        max_items=8,
    )
    context_used = _context_used_lines(context, output)
    summary = _actionability_summary(tangible, unresolved, unsupported, workflow)
    return JudgeExtractedEvidence(
        tangible_outputs_found=tangible,
        confirmed_user_context_used=context_used,
        unresolved_todos_or_placeholders=unresolved,
        unsupported_or_invented_details=unsupported,
        workflow_progress_evidence=workflow,
        context_reuse_evidence=context_reuse,
        user_burden_evidence=burden,
        final_actionability_summary=summary,
        extraction_warnings=["Heuristic dry-run evidence extraction; use live extraction for calibrated judging."],
    )


def _meaningful_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line in {"---", "| --- | --- |", "| --- | --- | --- |"}:
            continue
        lines.append(line)
    if not lines and text.strip():
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        lines = [sentence.strip() for sentence in sentences if sentence.strip()]
    return lines


def _evidence_lines(lines: list[str], markers: list[str], max_items: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        lowered = line.lower()
        if not any(marker in lowered for marker in markers):
            continue
        clipped = _clip_text(line, 260)
        key = clipped.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(clipped)
        if len(output) >= max_items:
            break
    return output


def _unsupported_specific_lines(lines: list[str], user_context: str) -> list[str]:
    risk_markers = [
        "capacity",
        "available",
        "availability",
        "deadline",
        "venue",
        "room",
        "cost",
        "reservation",
        "policy",
        "requirement",
        "eligibility",
    ]
    context_tokens = set(_words(user_context))
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        lowered = line.lower()
        if not any(marker in lowered for marker in risk_markers):
            continue
        line_tokens = [token for token in _words(line) if len(token) > 3]
        if context_tokens and line_tokens and len(context_tokens & set(line_tokens)) / max(1, min(len(context_tokens), len(set(line_tokens)))) >= 0.4:
            continue
        clipped = _clip_text(line, 260)
        key = clipped.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(clipped)
        if len(output) >= 8:
            break
    return output


def _context_used_lines(user_context: str, output: str) -> list[str]:
    context_lines = _meaningful_lines(user_context)
    if not context_lines and user_context.strip():
        context_lines = [_clip_text(user_context, 300)]
    used: list[str] = []
    for line in context_lines:
        if _text_overlap(output, line) >= 0.28:
            used.append(_clip_text(line, 260))
        if len(used) >= 8:
            break
    return used


def _text_overlap(text: str, needle: str) -> float:
    haystack = set(_words(text))
    query = set(_words(needle))
    if not haystack or not query:
        return 0.0
    return len(haystack & query) / max(1, min(len(haystack), len(query)))


def _actionability_summary(
    tangible: list[str],
    unresolved: list[str],
    unsupported: list[str],
    workflow: list[str],
) -> str:
    if tangible and not unresolved and not unsupported:
        return "The artifact appears directly actionable with concrete outputs and no obvious placeholder or unsupported-specificity signals."
    if tangible and (unresolved or unsupported):
        return "The artifact contains usable outputs, but it still requires cleanup, confirmation, or verification before real-world use."
    if workflow and not tangible:
        return "The artifact shows workflow progress but few directly usable final outputs."
    return "The artifact has limited directly actionable evidence in the extracted fields."


def _score_record(record: dict[str, Any], index: int, live: bool, model: str) -> JudgeScoreRecord:
    payload = _judge_payload(record)
    extracted_evidence = _extract_judge_evidence(payload, live=live, model=model)
    payload = {
        **payload,
        "extracted_evidence": extracted_evidence.model_dump(),
    }
    rubric = score_planning_output_live(PROMPT_JUDGE, json.dumps(payload, indent=2), model=model) if live else _dry_run_score(payload)
    rubric = _bounded_rubric(rubric)
    blind_id = str(record.get("blind_id") or record.get("calibration_id") or f"J{index:05d}")
    return JudgeScoreRecord(
        score_id=f"S{index:05d}",
        blind_id=blind_id,
        goal_id=record.get("goal_id"),
        calibration_id=record.get("calibration_id"),
        anchor_id=record.get("anchor_id"),
        condition_label=record.get("condition_label"),
        model=model,
        dry_run=not live,
        score=rubric,
        study_quality_score=round(_study_quality_score(rubric), 4),
        output_words=len(_words(str(payload.get("system_output", "")))),
        extracted_evidence=extracted_evidence,
        evidence_model=model if live else "dry_run",
    )


def _judge_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal_text": str(record.get("goal_text", "")),
        "user_context": str(record.get("user_context", "")),
        "system_output": str(record.get("system_output", record.get("final_artifact", ""))),
    }


def _dry_run_score(payload: dict[str, Any]) -> JudgeRubricScore:
    output = payload["system_output"]
    context = payload["user_context"]
    evidence = payload.get("extracted_evidence") if isinstance(payload.get("extracted_evidence"), dict) else {}
    words = _words(output)
    has_context = bool(context.strip())
    has_artifact = bool(evidence.get("tangible_outputs_found")) or any(
        marker in output.lower() for marker in ["draft", "schedule", "checklist", "template", "plan", "tracker", "message", "survey"]
    )
    has_task_tree = "task decomposition tree" in output.lower() or "subtasks or topic areas covered" in output.lower()
    has_context_reuse = bool(evidence.get("context_reuse_evidence")) or any(
        marker in output.lower() for marker in ["context curation", "local contexts", "selected/reused", "global context", "context store"]
    )
    has_workflow = bool(evidence.get("workflow_progress_evidence")) or any(
        marker in output.lower() for marker in ["workflow progress summary", "task nodes", "user turns", "assistant turns"]
    )
    has_low_burden = bool(evidence.get("tangible_outputs_found")) and not evidence.get("unresolved_todos_or_placeholders")
    has_unsupported = bool(evidence.get("unsupported_or_invented_details"))
    length_score = 3 if len(words) < 40 else 4 if len(words) < 120 else 5
    specificity = 6 if has_context and len(words) >= 80 else length_score
    personalization = 6 if has_context else 3
    actionability = 6 if has_artifact else 4
    decomposition = 6 if has_task_tree else 4
    context_reuse = 6 if has_context_reuse else 3
    workflow = 6 if has_workflow else 4
    burden = 6 if has_low_burden else 4
    overall = round((length_score + specificity + personalization + actionability + decomposition + context_reuse + workflow + burden) / 8)
    values = {
        "plan_quality": length_score,
        "tangible_result_quality": 6 if has_artifact else 3,
        "confidence_support": actionability,
        "personalization_context_grounding": personalization,
        "completeness_coverage": length_score,
        "specificity": specificity,
        "decomposition_quality": decomposition,
        "context_curation_reuse": context_reuse,
        "workflow_progress_support": workflow,
        "user_burden_reduction": burden,
        "no_contradiction_hallucination": 3 if has_unsupported else 6 if has_context else 4,
        "overall": overall,
    }
    return JudgeRubricScore(
        **{
            criterion: JudgeCriterionScore(score=int(score), evidence="Dry-run heuristic score; replace with live judge output.")
            for criterion, score in values.items()
        }
    )


def _bounded_rubric(rubric: JudgeRubricScore) -> JudgeRubricScore:
    values = {}
    for criterion in JUDGE_CRITERIA:
        item = getattr(rubric, criterion)
        values[criterion] = JudgeCriterionScore(score=max(1, min(7, int(item.score))), evidence=item.evidence)
    return JudgeRubricScore(**values)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _read_checkpointed_judge_scores(path: Path) -> list[JudgeScoreRecord]:
    if not path.exists():
        return []
    scores_by_blind_id: dict[str, JudgeScoreRecord] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            score = JudgeScoreRecord.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
        scores_by_blind_id[score.blind_id] = score
    return list(scores_by_blind_id.values())


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _append_jsonl_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        handle.flush()


def _judge_record_blind_id(record: dict[str, Any], index: int) -> str:
    return str(record.get("blind_id") or record.get("calibration_id") or f"J{index:05d}")


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return _pearson(_ranks(xs), _ranks(ys))


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[index][1]:
            end += 1
        average_rank = (index + end + 2) / 2
        for rank_index in range(index, end + 1):
            ranks[indexed[rank_index][0]] = average_rank
        index = end + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return None
    return numerator / (denom_x * denom_y)


def _mean_absolute_error(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or not xs:
        return None
    return sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)


def _directional_pair_accuracy(
    examples_by_id: dict[str, JudgeCalibrationExample],
    scores_by_id: dict[str, JudgeScoreRecord],
) -> float | None:
    by_anchor: dict[str, list[tuple[JudgeCalibrationExample, JudgeScoreRecord]]] = defaultdict(list)
    for calibration_id, example in examples_by_id.items():
        score = scores_by_id.get(calibration_id)
        if score:
            by_anchor[example.anchor_id].append((example, score))
    correct = 0
    total = 0
    for pairs in by_anchor.values():
        if len(pairs) < 2:
            continue
        for left_index in range(len(pairs)):
            for right_index in range(left_index + 1, len(pairs)):
                left_example, left_score = pairs[left_index]
                right_example, right_score = pairs[right_index]
                human_delta = left_example.human_overall_1_7 - right_example.human_overall_1_7
                judge_delta = left_score.score.overall.score - right_score.score.overall.score
                if human_delta == 0:
                    continue
                total += 1
                if human_delta * judge_delta > 0:
                    correct += 1
    return correct / total if total else None


def _mean(values: list[int | float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _words(text: str) -> list[str]:
    return [token.strip(".,;:!?()[]{}\"'").lower() for token in text.split() if token.strip(".,;:!?()[]{}\"'")]
