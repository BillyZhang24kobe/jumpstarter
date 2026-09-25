from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .openai_generation import DEFAULT_USER_SIMULATOR_MODEL, DEFAULT_WORKFLOW_MODEL
from .pipeline import (
    DEFAULT_DATA_DIR,
    DEFAULT_REPORTS_DIR,
    build_all,
    build_anchor_sessions,
    filter_goals,
    generate_goals,
    read_anchor_sessions,
    validate_benchmark_file,
    write_anchor_sessions,
    anchor_sessions_to_goals,
)
from .experiment_runner import parse_condition_list, run_workflow_experiment
from .paper_tables import DEFAULT_AGENT_RUN_DIR, build_paper_tables
from .failure_analysis import (
    DEFAULT_MAIN_RUN_DIR,
    DEFAULT_SINGLE_TURN_RUN_DIR,
    PAPER_TIE_THRESHOLD,
    analyze_failure_cases,
)
from .context_relevance import (
    DEFAULT_CONTEXT_RELEVANCE_LABELS_NAME,
    DEFAULT_CONTEXT_RELEVANCE_METRICS_NAME,
    DEFAULT_CONTEXT_RELEVANCE_MODEL,
    DEFAULT_CONTEXT_RELEVANCE_REPORT_NAME,
    run_context_relevance_labeler,
)
from .judge import (
    DEFAULT_JUDGE_CALIBRATION_PATH,
    DEFAULT_JUDGE_CALIBRATION_REPORT_PATH,
    DEFAULT_PAIRED_JUDGE_CALIBRATION_REPORT_PATH,
    DEFAULT_PAIRED_JUDGE_CALIBRATION_PATH,
    DEFAULT_STUDY_JUDGE_INPUTS_PATH,
    DEFAULT_STUDY_POINTWISE_JUDGE_CALIBRATION_REPORT_PATH,
    DEFAULT_STUDY_POINTWISE_JUDGE_INPUTS_PATH,
    DEFAULT_USER_STUDY_JUMPSTARTER_OUTPUT_PATH,
    build_judge_calibration_set,
    build_paired_judge_calibration,
    build_study_judge_inputs,
    build_study_pointwise_judge_inputs,
    run_paired_judge,
    run_judge,
    validate_judge_calibration,
    validate_paired_judge_calibration,
    validate_study_pointwise_judge_calibration,
)
from .personas import (
    DEFAULT_PERSONAS_PATH,
    DEFAULT_PERSONA_REPORT_PATH,
    build_personas,
    validate_personas_file,
)
from .schemas import GeneratedGoalCandidate
from .simulation_profiles import (
    DEFAULT_SIMULATION_PROFILE_REPORT_PATH,
    DEFAULT_SIMULATION_PROFILE_SPLIT_PATH,
    DEFAULT_SIMULATION_PROFILE_SPLIT_REPORT_PATH,
    DEFAULT_SIMULATION_PROFILES_PATH,
    DEFAULT_TEST_300_SIMULATION_PROFILES_PATH,
    DEFAULT_TEST_SIMULATION_PROFILES_PATH,
    DEFAULT_VALIDATION_SIMULATION_PROFILES_PATH,
    build_simulation_profile_splits,
    build_simulation_profiles,
    validate_simulation_profiles_file,
)
from .user_decision_calibration import (
    DEFAULT_USER_DECISION_CALIBRATION_PATH,
    DEFAULT_USER_DECISION_CALIBRATION_REPORT_PATH,
    DEFAULT_USER_STUDY_LOG_PATHS,
    build_user_decision_calibration,
)
from .workflow_analysis import analyze_workflow_experiment
from .workflow_simulator import (
    DEFAULT_RUNS_DIR,
    EXPERIMENT_CONDITION_PRESETS,
    PRIMARY_EXPERIMENT_CONDITIONS,
    WORKFLOW_CONDITIONS,
    WORKFLOW_LIVE_STAGE_MODES,
    run_workflow_pilot,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="JumpStarter simulation benchmark: build the data, run workflow experiments, judge, and analyze."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    anchors = subparsers.add_parser("build-anchors", help="Extract anchor session metadata from logs and DOCX files.")
    anchors.add_argument("--output", type=Path, default=DEFAULT_DATA_DIR / "anchor_sessions.jsonl")

    generate = subparsers.add_parser("generate-goals", help="Generate or load synthetic benchmark goal candidates.")
    generate.add_argument("--anchors", type=Path, default=DEFAULT_DATA_DIR / "anchor_sessions.jsonl")
    generate.add_argument("--output", type=Path, default=DEFAULT_DATA_DIR / "generated_candidates.json")
    generate.add_argument("--live", action="store_true", help="Call OpenAI instead of loading dry-run fixtures.")
    generate.add_argument("--dry-run", action="store_true", help="Force fixture generation.")
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--model", default=None)

    filter_parser = subparsers.add_parser("filter-goals", help="Filter generated candidates and write accepted goals.")
    filter_parser.add_argument("--anchors", type=Path, default=DEFAULT_DATA_DIR / "anchor_sessions.jsonl")
    filter_parser.add_argument("--input", type=Path, default=DEFAULT_DATA_DIR / "generated_candidates.json")
    filter_parser.add_argument("--output", type=Path, default=DEFAULT_DATA_DIR / "filtered_generated_goals.json")
    filter_parser.add_argument("--decisions", type=Path, default=DEFAULT_DATA_DIR / "filter_decisions.json")
    filter_parser.add_argument("--live", action="store_true")
    filter_parser.add_argument("--dry-run", action="store_true")
    filter_parser.add_argument("--model", default=None)

    validate = subparsers.add_parser("validate", help="Validate a benchmark JSON file.")
    validate.add_argument("benchmark", type=Path)
    validate.add_argument("--report", type=Path, default=None)

    build = subparsers.add_parser("build-all", help="Build anchors, candidates, benchmark, and quality report.")
    build.add_argument("--live", action="store_true")
    build.add_argument("--dry-run", action="store_true")
    build.add_argument("--seed", type=int, default=42)
    build.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    build.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    build.add_argument("--model", default=None)

    personas = subparsers.add_parser("build-personas", help="Extract P2-P10 base personas and controlled variants.")
    personas.add_argument("--anchors", type=Path, default=DEFAULT_DATA_DIR / "anchor_sessions.jsonl")
    personas.add_argument("--output", type=Path, default=DEFAULT_PERSONAS_PATH)
    personas.add_argument("--report", type=Path, default=DEFAULT_PERSONA_REPORT_PATH)
    personas.add_argument("--live", action="store_true", help="Call OpenAI to refine base personas.")
    personas.add_argument("--model", default=None)

    validate_personas = subparsers.add_parser("validate-personas", help="Validate personas JSON.")
    validate_personas.add_argument("personas", type=Path)
    validate_personas.add_argument("--report", type=Path, default=None)

    sim_profiles = subparsers.add_parser("build-simulation-profiles", help="Build persona-goal private state profiles.")
    sim_profiles.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS_PATH)
    sim_profiles.add_argument("--benchmark", type=Path, default=DEFAULT_DATA_DIR / "benchmark.json")
    sim_profiles.add_argument("--output", type=Path, default=DEFAULT_SIMULATION_PROFILES_PATH)
    sim_profiles.add_argument("--report", type=Path, default=DEFAULT_SIMULATION_PROFILE_REPORT_PATH)
    sim_profiles.add_argument("--live", action="store_true", help="Call OpenAI to refine simulation profiles.")
    sim_profiles.add_argument("--model", default=None)

    validate_sim_profiles = subparsers.add_parser("validate-simulation-profiles", help="Validate simulation profiles JSON.")
    validate_sim_profiles.add_argument("profiles", type=Path)
    validate_sim_profiles.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS_PATH)
    validate_sim_profiles.add_argument("--benchmark", type=Path, default=DEFAULT_DATA_DIR / "benchmark.json")
    validate_sim_profiles.add_argument("--report", type=Path, default=None)

    sim_profile_splits = subparsers.add_parser(
        "build-simulation-profile-splits",
        help="Build a validation profile subset and a full test profile file excluding it.",
    )
    sim_profile_splits.add_argument("--profiles", type=Path, default=DEFAULT_SIMULATION_PROFILES_PATH)
    sim_profile_splits.add_argument("--validation-size", type=int, default=10)
    sim_profile_splits.add_argument("--validation-output", type=Path, default=DEFAULT_VALIDATION_SIMULATION_PROFILES_PATH)
    sim_profile_splits.add_argument("--test-output", type=Path, default=DEFAULT_TEST_SIMULATION_PROFILES_PATH)
    sim_profile_splits.add_argument("--test-300-size", type=int, default=300)
    sim_profile_splits.add_argument("--test-300-output", type=Path, default=DEFAULT_TEST_300_SIMULATION_PROFILES_PATH)
    sim_profile_splits.add_argument("--metadata-output", type=Path, default=DEFAULT_SIMULATION_PROFILE_SPLIT_PATH)
    sim_profile_splits.add_argument("--report", type=Path, default=DEFAULT_SIMULATION_PROFILE_SPLIT_REPORT_PATH)

    workflow = subparsers.add_parser("run-workflow-pilot", help="Run deterministic JumpStarter UI workflow simulations.")
    workflow.add_argument("--profiles", type=Path, default=DEFAULT_SIMULATION_PROFILES_PATH)
    workflow.add_argument("--output-dir", type=Path, default=None)
    workflow.add_argument("--condition", choices=WORKFLOW_CONDITIONS, default="full_jumpstarter")
    workflow.add_argument("--limit", type=int, default=10)
    workflow.add_argument("--seed", type=int, default=42)
    workflow.add_argument("--model", default=None, help="Deprecated alias for --workflow-model.")
    workflow.add_argument("--workflow-model", default=None, help=f"Model for live workflow backend stages. Defaults to {DEFAULT_WORKFLOW_MODEL}.")
    workflow.add_argument(
        "--simulated-user-model",
        default=DEFAULT_USER_SIMULATOR_MODEL,
        help=f"Model for live simulated-user answers. Defaults to {DEFAULT_USER_SIMULATOR_MODEL}.",
    )
    workflow.add_argument(
        "--live-simulated-user",
        action="store_true",
        help="Force model-backed simulated-user answers. This is already the default when --live-stages is not deterministic.",
    )
    workflow.add_argument(
        "--deterministic-simulated-user",
        action="store_true",
        help="Use deterministic profile lookup for user answers even when workflow stages are live.",
    )
    workflow.add_argument("--max-workers", type=int, default=1, help="Reserved for parity with experiment runs; pilot runs are sequential.")
    workflow.add_argument(
        "--live-stages",
        choices=WORKFLOW_LIVE_STAGE_MODES,
        default="deterministic",
        help="Enable live model-backed workflow stages: drafts, planning, or all.",
    )

    experiment = subparsers.add_parser("run-workflow-experiment", help="Run a balanced multi-condition workflow experiment.")
    experiment.add_argument("--profiles", type=Path, default=DEFAULT_SIMULATION_PROFILES_PATH)
    experiment.add_argument("--output-dir", type=Path, default=None)
    experiment.add_argument(
        "--conditions",
        default="primary",
        help=(
            "Comma-separated conditions or presets. "
            f"Presets: {', '.join(sorted(EXPERIMENT_CONDITION_PRESETS))}. Defaults to primary."
        ),
    )
    experiment.add_argument("--limit", type=int, default=10)
    experiment.add_argument("--runs-per-profile", type=int, default=1)
    experiment.add_argument("--seed", type=int, default=42)
    experiment.add_argument("--model", default=None, help="Deprecated alias for --workflow-model.")
    experiment.add_argument("--workflow-model", default=None, help=f"Model for live workflow backend stages. Defaults to {DEFAULT_WORKFLOW_MODEL}.")
    experiment.add_argument(
        "--simulated-user-model",
        default=DEFAULT_USER_SIMULATOR_MODEL,
        help=f"Model for live simulated-user answers. Defaults to {DEFAULT_USER_SIMULATOR_MODEL}.",
    )
    experiment.add_argument(
        "--live-simulated-user",
        action="store_true",
        help="Force model-backed simulated-user answers. This is already the default when --live-stages is not deterministic.",
    )
    experiment.add_argument(
        "--deterministic-simulated-user",
        action="store_true",
        help="Use deterministic profile lookup for user answers even when workflow stages are live.",
    )
    experiment.add_argument("--max-workers", type=int, default=1, help="Parallel workflow sessions. Use 3-4 for live API smoke tests.")
    experiment.add_argument(
        "--live-stages",
        choices=WORKFLOW_LIVE_STAGE_MODES,
        default="deterministic",
        help="Enable live model-backed workflow stages: drafts, planning, or all.",
    )

    analysis = subparsers.add_parser("analyze-workflow-experiment", help="Summarize judged workflow experiment scores by condition.")
    analysis.add_argument("run_dir", type=Path)
    analysis.add_argument("--baseline", default="full_jumpstarter")

    failure = subparsers.add_parser(
        "analyze-failure-cases",
        help="Break down where JumpStarter-Shallow loses to the single-turn decomposition baseline.",
    )
    failure.add_argument("--main-run", type=Path, default=DEFAULT_MAIN_RUN_DIR)
    failure.add_argument("--single-turn-run", type=Path, default=DEFAULT_SINGLE_TURN_RUN_DIR)
    failure.add_argument("--output-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    failure.add_argument("--top-k", type=int, default=10)
    failure.add_argument(
        "--tie-threshold",
        type=float,
        default=PAPER_TIE_THRESHOLD,
        help="Treat |delta| <= this as a tie (default: exact ties, as reported in the paper).",
    )

    tables = subparsers.add_parser(
        "paper-tables",
        help="Rebuild the paper's Table 2 and mechanism numbers from the three judged result runs.",
    )
    tables.add_argument("--main-run", type=Path, default=DEFAULT_MAIN_RUN_DIR)
    tables.add_argument("--single-turn-run", type=Path, default=DEFAULT_SINGLE_TURN_RUN_DIR)
    tables.add_argument("--agent-run", type=Path, default=DEFAULT_AGENT_RUN_DIR)
    tables.add_argument("--output-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    tables.add_argument(
        "--tie-threshold",
        type=float,
        default=PAPER_TIE_THRESHOLD,
        help="Treat |delta| <= this as a tie (default: exact ties, as reported in the paper).",
    )

    relevance = subparsers.add_parser(
        "run-context-relevance-labeler",
        help="Use GPT labels for paper-quality context relevance mechanism metrics.",
    )
    relevance.add_argument("run_dir", type=Path)
    relevance.add_argument("--output", type=Path, default=None)
    relevance.add_argument("--metrics", type=Path, default=None)
    relevance.add_argument("--report", type=Path, default=None)
    relevance.add_argument("--model", default=DEFAULT_CONTEXT_RELEVANCE_MODEL)
    relevance.add_argument("--max-workers", type=int, default=4)
    relevance.add_argument("--dry-run", action="store_true", help="Use deterministic lexical labels instead of calling OpenAI.")

    judge_calibration = subparsers.add_parser("build-judge-calibration", help="Build human-study judge calibration inputs.")
    judge_calibration.add_argument("--anchors", type=Path, default=DEFAULT_DATA_DIR / "anchor_sessions.jsonl")
    judge_calibration.add_argument("--chatgpt-outputs-dir", type=Path, default=DEFAULT_DATA_DIR / "chatgpt_outputs")
    judge_calibration.add_argument("--output", type=Path, default=DEFAULT_JUDGE_CALIBRATION_PATH)
    judge_calibration.add_argument("--report", type=Path, default=DEFAULT_JUDGE_CALIBRATION_REPORT_PATH)

    judge = subparsers.add_parser("run-judge", help="Score calibration or experiment judge inputs.")
    judge.add_argument("input", type=Path)
    judge.add_argument("--output", type=Path, default=None)
    judge.add_argument("--report", type=Path, default=None)
    judge.add_argument("--live", action="store_true", help="Call OpenAI instead of using dry-run heuristic scores.")
    judge.add_argument("--model", default=None)
    judge.add_argument("--max-workers", type=int, default=4, help="Parallel judge workers. Live runs use processes to avoid parser thread contention.")

    validate_judge = subparsers.add_parser("validate-judge-calibration", help="Compare judge scores against human ratings.")
    validate_judge.add_argument("--calibration", type=Path, default=DEFAULT_JUDGE_CALIBRATION_PATH)
    validate_judge.add_argument("--scores", type=Path, default=None)
    validate_judge.add_argument("--report", type=Path, default=DEFAULT_JUDGE_CALIBRATION_REPORT_PATH)

    paired_calibration = subparsers.add_parser("build-paired-judge-calibration", help="Build paired JumpStarter-vs-ChatGPT judge calibration records.")
    paired_calibration.add_argument("--calibration", type=Path, default=DEFAULT_JUDGE_CALIBRATION_PATH)
    paired_calibration.add_argument("--output", type=Path, default=DEFAULT_PAIRED_JUDGE_CALIBRATION_PATH)

    study_judge_inputs = subparsers.add_parser("build-study-judge-inputs", help="Build paired study-judge inputs with structured JumpStarter workflow artifacts.")
    study_judge_inputs.add_argument("--anchors", type=Path, default=DEFAULT_DATA_DIR / "anchor_sessions.jsonl")
    study_judge_inputs.add_argument("--chatgpt-outputs-dir", type=Path, default=DEFAULT_DATA_DIR / "chatgpt_outputs")
    study_judge_inputs.add_argument("--jumpstarter-output-json", type=Path, default=DEFAULT_USER_STUDY_JUMPSTARTER_OUTPUT_PATH)
    study_judge_inputs.add_argument("--output", type=Path, default=DEFAULT_STUDY_JUDGE_INPUTS_PATH)

    study_pointwise_judge_inputs = subparsers.add_parser(
        "build-study-pointwise-judge-inputs",
        help="Flatten structured study judge pairs into unique pointwise calibration artifacts.",
    )
    study_pointwise_judge_inputs.add_argument("--paired-inputs", type=Path, default=DEFAULT_STUDY_JUDGE_INPUTS_PATH)
    study_pointwise_judge_inputs.add_argument("--output", type=Path, default=DEFAULT_STUDY_POINTWISE_JUDGE_INPUTS_PATH)

    paired_judge = subparsers.add_parser("run-paired-judge", help="Run pairwise judge on paired calibration records.")
    paired_judge.add_argument("--input", type=Path, default=DEFAULT_PAIRED_JUDGE_CALIBRATION_PATH)
    paired_judge.add_argument("--output", type=Path, default=None)
    paired_judge.add_argument("--report", type=Path, default=None)
    paired_judge.add_argument("--live", action="store_true", help="Call OpenAI instead of using dry-run heuristic pairwise scores.")
    paired_judge.add_argument("--model", default=None)
    paired_judge.add_argument("--max-workers", type=int, default=4, help="Parallel paired-judge workers.")

    validate_paired_judge = subparsers.add_parser("validate-paired-judge-calibration", help="Validate pairwise judge scores against human paired preferences.")
    validate_paired_judge.add_argument("--scores", type=Path, default=DEFAULT_PAIRED_JUDGE_CALIBRATION_PATH.with_name("paired_judge_scores.jsonl"))
    validate_paired_judge.add_argument("--report", type=Path, default=DEFAULT_PAIRED_JUDGE_CALIBRATION_REPORT_PATH)

    validate_study_pointwise_judge = subparsers.add_parser(
        "validate-study-pointwise-judge-calibration",
        help="Validate pointwise study-quality judge scores against human study ratings.",
    )
    validate_study_pointwise_judge.add_argument("--calibration", type=Path, default=DEFAULT_STUDY_POINTWISE_JUDGE_INPUTS_PATH)
    validate_study_pointwise_judge.add_argument("--scores", type=Path, default=None)
    validate_study_pointwise_judge.add_argument("--report", type=Path, default=DEFAULT_STUDY_POINTWISE_JUDGE_CALIBRATION_REPORT_PATH)

    user_decision_calibration = subparsers.add_parser(
        "build-user-decision-calibration",
        help="Extract simulated-user decision calibration policies from real JumpStarter study logs.",
    )
    user_decision_calibration.add_argument("--logs", type=Path, nargs="+", default=list(DEFAULT_USER_STUDY_LOG_PATHS))
    user_decision_calibration.add_argument("--output", type=Path, default=DEFAULT_USER_DECISION_CALIBRATION_PATH)
    user_decision_calibration.add_argument("--report", type=Path, default=DEFAULT_USER_DECISION_CALIBRATION_REPORT_PATH)

    args = parser.parse_args()
    if args.command == "build-anchors":
        sessions = write_anchor_sessions(args.output)
        usable = sum(session.usable_for_trace_replay and session.anchor_type != "ignored_unusable" for session in sessions)
        print(f"Wrote {len(sessions)} anchor sessions ({usable} usable) to {args.output}")
    elif args.command == "generate-goals":
        anchor_sessions = _read_or_build_anchors(args.anchors)
        dry_run = not args.live
        candidates = generate_goals(anchor_sessions, dry_run=dry_run, seed=args.seed, output_path=args.output, model=args.model)
        print(f"Wrote {len(candidates)} generated candidates to {args.output}")
    elif args.command == "filter-goals":
        anchor_sessions = _read_or_build_anchors(args.anchors)
        payload = json.loads(args.input.read_text())
        candidates = [GeneratedGoalCandidate.model_validate(item) for item in payload["candidates"]]
        accepted, decisions = filter_goals(
            anchor_sessions_to_goals(anchor_sessions),
            candidates,
            dry_run=not args.live,
            output_path=args.decisions,
            model=args.model,
        )
        args.output.write_text(json.dumps([goal.model_dump() for goal in accepted], indent=2))
        print(f"Accepted {len(accepted)} generated goals; wrote decisions to {args.decisions}")
    elif args.command == "validate":
        report = validate_benchmark_file(args.benchmark)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(report.model_dump_json(indent=2))
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "build-all":
        report = build_all(
            dry_run=not args.live,
            seed=args.seed,
            data_dir=args.data_dir,
            reports_dir=args.reports_dir,
            model=args.model,
        )
        print(report.model_dump_json(indent=2))
    elif args.command == "build-personas":
        report = build_personas(
            anchors_path=args.anchors,
            output_path=args.output,
            report_path=args.report,
            live=args.live,
            model=args.model,
        )
        print(report.model_dump_json(indent=2))
    elif args.command == "validate-personas":
        report = validate_personas_file(args.personas)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(report.model_dump_json(indent=2))
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "build-simulation-profiles":
        report = build_simulation_profiles(
            personas_path=args.personas,
            benchmark_path=args.benchmark,
            output_path=args.output,
            report_path=args.report,
            live=args.live,
            model=args.model,
        )
        print(report.model_dump_json(indent=2))
    elif args.command == "validate-simulation-profiles":
        report = validate_simulation_profiles_file(
            profiles_path=args.profiles,
            personas_path=args.personas,
            benchmark_path=args.benchmark,
        )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(report.model_dump_json(indent=2))
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "build-simulation-profile-splits":
        report = build_simulation_profile_splits(
            profiles_path=args.profiles,
            validation_size=args.validation_size,
            validation_output_path=args.validation_output,
            test_output_path=args.test_output,
            test_300_size=args.test_300_size,
            test_300_output_path=args.test_300_output,
            metadata_output_path=args.metadata_output,
            report_path=args.report,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "run-workflow-pilot":
        output_dir = args.output_dir
        if output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = DEFAULT_RUNS_DIR / f"workflow_pilot_{args.condition}_{timestamp}"
        workflow_model = _workflow_model_arg(args.workflow_model, args.model, args.live_stages)
        live_simulated_user = _live_simulated_user_arg(
            args.live_simulated_user,
            args.deterministic_simulated_user,
            args.live_stages,
        )
        report = run_workflow_pilot(
            profiles_path=args.profiles,
            output_dir=output_dir,
            condition=args.condition,
            limit=args.limit,
            seed=args.seed,
            model=workflow_model,
            live_stages=args.live_stages,
            simulated_user_model=args.simulated_user_model,
            live_simulated_user=live_simulated_user,
            max_workers=args.max_workers,
        )
        print(report.model_dump_json(indent=2))
        print(f"Workflow run written to {output_dir}")
    elif args.command == "run-workflow-experiment":
        output_dir = args.output_dir
        if output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = DEFAULT_RUNS_DIR / f"workflow_experiment_{timestamp}"
        workflow_model = _workflow_model_arg(args.workflow_model, args.model, args.live_stages)
        live_simulated_user = _live_simulated_user_arg(
            args.live_simulated_user,
            args.deterministic_simulated_user,
            args.live_stages,
        )
        report = run_workflow_experiment(
            profiles_path=args.profiles,
            output_dir=output_dir,
            conditions=parse_condition_list(args.conditions),
            limit=args.limit,
            runs_per_profile=args.runs_per_profile,
            seed=args.seed,
            model=workflow_model,
            live_stages=args.live_stages,
            simulated_user_model=args.simulated_user_model,
            live_simulated_user=live_simulated_user,
            max_workers=args.max_workers,
        )
        print(report.model_dump_json(indent=2))
        print(f"Workflow experiment written to {output_dir}")
    elif args.command == "analyze-workflow-experiment":
        report = analyze_workflow_experiment(
            run_dir=args.run_dir,
            baseline_condition=args.baseline,
        )
        print(report.model_dump_json(indent=2))
        if report.valid:
            print(f"Workflow score summary written to {report.output_json_path} and {report.output_markdown_path}")
        else:
            raise SystemExit(1)
    elif args.command == "analyze-failure-cases":
        report = analyze_failure_cases(
            main_run_dir=args.main_run,
            single_turn_run_dir=args.single_turn_run,
            output_dir=args.output_dir,
            top_k=args.top_k,
            tie_threshold=args.tie_threshold,
        )
        print(f"Failure-case analysis written to {report['output_json_path']} and {report['output_markdown_path']}")
    elif args.command == "paper-tables":
        report = build_paper_tables(
            main_run_dir=args.main_run,
            single_turn_run_dir=args.single_turn_run,
            agent_run_dir=args.agent_run,
            output_dir=args.output_dir,
            tie_threshold=args.tie_threshold,
        )
        print("Paper tables written to " + ", ".join(report["output_paths"]))
    elif args.command == "run-context-relevance-labeler":
        output_path = args.output or args.run_dir / DEFAULT_CONTEXT_RELEVANCE_LABELS_NAME
        metrics_path = args.metrics or args.run_dir / DEFAULT_CONTEXT_RELEVANCE_METRICS_NAME
        report_path = args.report or args.run_dir / DEFAULT_CONTEXT_RELEVANCE_REPORT_NAME
        report = run_context_relevance_labeler(
            run_dir=args.run_dir,
            output_path=output_path,
            metrics_path=metrics_path,
            report_path=report_path,
            model=args.model,
            live=not args.dry_run,
            max_workers=args.max_workers,
        )
        print(json.dumps(report, indent=2))
    elif args.command == "build-judge-calibration":
        report = build_judge_calibration_set(
            anchors_path=args.anchors,
            chatgpt_outputs_dir=args.chatgpt_outputs_dir,
            output_path=args.output,
            report_path=args.report,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "run-judge":
        report = run_judge(
            input_path=args.input,
            output_path=args.output,
            report_path=args.report,
            live=args.live,
            model=args.model,
            max_workers=args.max_workers,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "validate-judge-calibration":
        report = validate_judge_calibration(
            calibration_path=args.calibration,
            scores_path=args.scores,
            report_path=args.report,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "build-paired-judge-calibration":
        report = build_paired_judge_calibration(
            calibration_path=args.calibration,
            output_path=args.output,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "build-study-judge-inputs":
        report = build_study_judge_inputs(
            anchors_path=args.anchors,
            chatgpt_outputs_dir=args.chatgpt_outputs_dir,
            jumpstarter_output_path=args.jumpstarter_output_json,
            output_path=args.output,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "build-study-pointwise-judge-inputs":
        report = build_study_pointwise_judge_inputs(
            paired_inputs_path=args.paired_inputs,
            output_path=args.output,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "run-paired-judge":
        report = run_paired_judge(
            input_path=args.input,
            output_path=args.output,
            report_path=args.report,
            live=args.live,
            model=args.model,
            max_workers=args.max_workers,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "validate-paired-judge-calibration":
        report = validate_paired_judge_calibration(
            scores_path=args.scores,
            report_path=args.report,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "validate-study-pointwise-judge-calibration":
        report = validate_study_pointwise_judge_calibration(
            calibration_path=args.calibration,
            scores_path=args.scores,
            report_path=args.report,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)
    elif args.command == "build-user-decision-calibration":
        report = build_user_decision_calibration(
            log_paths=args.logs,
            output_path=args.output,
            report_path=args.report,
        )
        print(report.model_dump_json(indent=2))
        if not report.valid:
            raise SystemExit(1)


def _read_or_build_anchors(path: Path):
    if path.exists():
        return read_anchor_sessions(path)
    return build_anchor_sessions()


def _workflow_model_arg(workflow_model: str | None, legacy_model: str | None, live_stages: str) -> str:
    selected_model = workflow_model or legacy_model
    if selected_model:
        return selected_model
    if live_stages != "deterministic":
        return DEFAULT_WORKFLOW_MODEL
    return "deterministic"


def _live_simulated_user_arg(force_live: bool, force_deterministic: bool, live_stages: str) -> bool:
    if force_live and force_deterministic:
        raise ValueError("Choose either --live-simulated-user or --deterministic-simulated-user, not both.")
    if force_deterministic:
        return False
    return force_live or live_stages != "deterministic"


if __name__ == "__main__":
    main()
