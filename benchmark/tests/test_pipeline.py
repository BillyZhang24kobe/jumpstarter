from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmark.manifest import study_docx_path
from benchmark.parsers import parse_jumpstarter_log_record, parse_study_docx
from benchmark.experiment_runner import run_workflow_experiment
from benchmark.judge import (
    build_judge_calibration_set,
    build_paired_judge_calibration,
    build_study_judge_inputs,
    build_study_pointwise_judge_inputs,
    run_judge,
    run_paired_judge,
    validate_judge_calibration,
    validate_paired_judge_calibration,
    validate_study_pointwise_judge_calibration,
)
from benchmark.personas import build_personas, validate_personas
from benchmark.pipeline import (
    REPO_ROOT,
    anchor_sessions_to_goals,
    build_all,
    build_anchor_sessions,
    concise_goal_issues,
    filter_goals,
    validate_benchmark,
)
from benchmark.schemas import (
    GeneratedGoalCandidate,
    WorkflowLiveContextSelectionResponse,
    WorkflowLiveDraftResponse,
    WorkflowLiveQuestionResponse,
    WorkflowLiveSubtaskDetectionResponse,
    WorkflowLiveTaskDecompositionResponse,
    WorkflowLiveTaskForkingResponse,
)
from benchmark.simulation_profiles import (
    build_simulation_profile_splits,
    build_simulation_profiles,
    validate_simulation_profiles,
)
from benchmark.workflow_analysis import analyze_workflow_experiment
from benchmark.workflow_prompts import PROMPT_DIR
from benchmark.workflow_simulator import run_workflow_pilot, simulate_workflow_session, workflow_fidelity_report

# The user-study logs, documents, and ChatGPT transcripts are not part of the public release.
STUDY_DATA_AVAILABLE = all(
    path.exists()
    for path in (REPO_ROOT / "userstudy.log", REPO_ROOT / "userstudy_data", REPO_ROOT / "benchmark/data/chatgpt_outputs")
)
requires_study_data = unittest.skipUnless(STUDY_DATA_AVAILABLE, "needs the private user-study data")


class ParserTests(unittest.TestCase):
    @requires_study_data
    def test_docx_parser_extracts_goal_background_and_share_link(self) -> None:
        parsed = parse_study_docx(REPO_ROOT / study_docx_path(2, "JumpStarter"))

        self.assertEqual(parsed.goal, "Organize a weekly PhD game night")
        self.assertIn("Never organized game night", parsed.background or "")
        self.assertTrue((parsed.chatgpt_share_url or "").startswith("https://chatgpt.com/share/"))
        self.assertGreater(len(parsed.rating_snippets), 3)

    @requires_study_data
    def test_log_parser_recovers_root_and_context(self) -> None:
        parsed = parse_jumpstarter_log_record(REPO_ROOT / "userstudy.log", 1348)

        self.assertEqual(parsed.task, "Create weekly game night for PhD students")
        self.assertIsNotNone(parsed.root_node)
        self.assertIn("Venue Selection", json.dumps(parsed.root_node))
        self.assertTrue(parsed.saved_draft_context)
        self.assertIsInstance(parsed.user_context, dict)


class OpenAIGenerationTests(unittest.TestCase):
    def test_retry_helper_retries_retryable_openai_errors(self) -> None:
        from benchmark import openai_generation

        calls: list[int] = []

        def flaky_call() -> str:
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("temporary outage")
            return "ok"

        env = {
            "BENCHMARK_OPENAI_RETRY_ATTEMPTS": "3",
            "BENCHMARK_OPENAI_RETRY_INITIAL_SLEEP_SECONDS": "0.01",
            "BENCHMARK_OPENAI_RETRY_MAX_SLEEP_SECONDS": "0.01",
        }
        with patch.dict(os.environ, env), patch.object(
            openai_generation, "_is_retryable_openai_error", return_value=True
        ), patch.object(openai_generation.time, "sleep") as mock_sleep:
            result = openai_generation._call_openai_with_retries("test.call", flaky_call)

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_retry_helper_does_not_retry_permanent_openai_errors(self) -> None:
        from benchmark import openai_generation

        calls: list[int] = []

        def failing_call() -> str:
            calls.append(1)
            raise RuntimeError("permission denied")

        with patch.dict(os.environ, {"BENCHMARK_OPENAI_RETRY_ATTEMPTS": "3"}), patch.object(
            openai_generation, "_is_retryable_openai_error", return_value=False
        ), patch.object(openai_generation.time, "sleep") as mock_sleep:
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                openai_generation._call_openai_with_retries("test.call", failing_call)

        self.assertEqual(len(calls), 1)
        mock_sleep.assert_not_called()

    def test_retry_helper_retries_structured_parse_invalid_json_errors(self) -> None:
        from benchmark import openai_generation

        class FakeValidationError(Exception):
            def errors(self) -> list[dict[str, str]]:
                return [{"type": "json_invalid"}]

        calls: list[int] = []

        def flaky_parse() -> str:
            calls.append(1)
            if len(calls) == 1:
                raise FakeValidationError("Invalid JSON: EOF while parsing a string")
            return "ok"

        env = {
            "BENCHMARK_OPENAI_RETRY_ATTEMPTS": "2",
            "BENCHMARK_OPENAI_RETRY_INITIAL_SLEEP_SECONDS": "0.01",
            "BENCHMARK_OPENAI_RETRY_MAX_SLEEP_SECONDS": "0.01",
        }
        with patch.dict(os.environ, env), patch.object(openai_generation.time, "sleep") as mock_sleep:
            result = openai_generation._call_openai_with_retries("responses.parse", flaky_parse)

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 2)
        mock_sleep.assert_called_once()

    def test_openai_client_uses_configured_timeout_and_sdk_retries(self) -> None:
        from benchmark import openai_generation

        captured_kwargs: dict[str, object] = {}

        class FakeOpenAI:
            def __init__(self, **kwargs: object) -> None:
                captured_kwargs.update(kwargs)

        fake_openai_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
        env = {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_ORG_ID": "test-org",
            "BENCHMARK_OPENAI_TIMEOUT_SECONDS": "45.5",
            "BENCHMARK_OPENAI_SDK_MAX_RETRIES": "1",
        }

        with patch.dict(sys.modules, {"openai": fake_openai_module}), patch.dict(os.environ, env):
            openai_generation.load_openai_client()

        self.assertEqual(captured_kwargs["api_key"], "test-key")
        self.assertEqual(captured_kwargs["organization"], "test-org")
        self.assertEqual(captured_kwargs["timeout"], 45.5)
        self.assertEqual(captured_kwargs["max_retries"], 1)


class PipelineTests(unittest.TestCase):
    def test_condition_presets_expand_component_ablations(self) -> None:
        from benchmark.experiment_runner import parse_condition_list

        component_conditions = parse_condition_list("component_ablation")
        agent_conditions = parse_condition_list("agent_baselines")
        all_conditions = parse_condition_list("all")

        self.assertEqual(
            component_conditions,
            [
                "full_jumpstarter",
                "all_context",
                "random_selection",
                "no_selection",
                "no_elicitation",
                "flat_decomposition",
                "no_reuse",
            ],
        )
        self.assertEqual(
            agent_conditions,
            [
                "full_jumpstarter",
                "adapt_recursive_decomposition",
                "ask_before_plan",
                "unstructured_memory_rag",
                "long_context_planner",
                "react_integrated_planner",
            ],
        )
        self.assertIn("chatgpt_vanilla", all_conditions)
        self.assertIn("flat_decomposition", all_conditions)
        self.assertIn("long_context_planner", all_conditions)
        self.assertEqual(len(all_conditions), len(set(all_conditions)))

    def test_anchor_builder_has_twelve_usable_and_p1_unusable(self) -> None:
        sessions = build_anchor_sessions()
        usable = [s for s in sessions if s.usable_for_trace_replay and s.anchor_type != "ignored_unusable"]
        p1 = next(s for s in sessions if s.anchor_id == "P1")

        self.assertEqual(len(sessions), 13)
        self.assertEqual(len(usable), 12)
        self.assertFalse(p1.usable_for_trace_replay)
        self.assertEqual(p1.anchor_type, "ignored_unusable")

    def test_build_all_dry_run_produces_valid_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = build_all(dry_run=True, data_dir=tmp_path / "data", reports_dir=tmp_path / "reports")

            self.assertTrue(report.valid)
            self.assertEqual(report.total_goals, 60)
            self.assertTrue((tmp_path / "data" / "anchor_sessions.jsonl").exists())
            self.assertTrue((tmp_path / "data" / "benchmark.json").exists())
            self.assertTrue((tmp_path / "reports" / "benchmark_quality.json").exists())

    def test_validator_rejects_missing_generated_goals(self) -> None:
        goals = anchor_sessions_to_goals(build_anchor_sessions())
        report = validate_benchmark(goals)

        self.assertFalse(report.valid)
        self.assertIn("Expected 60 benchmark goals", "\n".join(report.errors))

    def test_validator_rejects_domain_cap_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            build_all(dry_run=True, data_dir=tmp_path / "data", reports_dir=tmp_path / "reports")
            payload = json.loads((tmp_path / "data" / "benchmark.json").read_text())
            for item in payload:
                if item["source"] == "generated":
                    item["domain"] = "career_education"
            from benchmark.schemas import BenchmarkGoal

            goals = [BenchmarkGoal.model_validate(item) for item in payload]
            report = validate_benchmark(goals)

            self.assertFalse(report.valid)
            self.assertIn("exceeds 18-goal cap", "\n".join(report.errors))

    def test_validator_rejects_near_duplicate_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            build_all(dry_run=True, data_dir=tmp_path / "data", reports_dir=tmp_path / "reports")
            payload = json.loads((tmp_path / "data" / "benchmark.json").read_text())
            payload[13]["goal_text"] = payload[12]["goal_text"]
            from benchmark.schemas import BenchmarkGoal

            goals = [BenchmarkGoal.model_validate(item) for item in payload]
            report = validate_benchmark(goals)

            self.assertFalse(report.valid)
            self.assertIn("too similar", "\n".join(report.errors))

    def test_filter_rejects_verbose_generated_goal_text(self) -> None:
        candidate = GeneratedGoalCandidate(
            goal_id="G999",
            goal_text="Create a networking and informational interview plan for exploring nonprofit management careers.",
            anchor_goal_id=None,
            domain="career_education",
            time_horizon="6-10 weeks",
            expected_context_richness="medium",
            complexity="medium",
            requires_personalization=True,
            requires_decomposition=True,
            expected_tangible_outputs=["contact list template", "outreach message drafts"],
            known_context_needs=["current field", "causes of interest"],
            avoid=["mass messaging strangers"],
        )

        self.assertTrue(concise_goal_issues(candidate.goal_text))
        _accepted, decisions = filter_goals(anchor_sessions_to_goals(build_anchor_sessions()), [candidate], dry_run=True)

        self.assertFalse(decisions[0].accepted)
        self.assertIn("concise goal-text gate", decisions[0].rejection_reason or "")


class PersonaTests(unittest.TestCase):
    def test_build_personas_creates_base_and_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = build_personas(output_path=tmp_path / "personas.json", report_path=tmp_path / "report.json")
            payload = json.loads((tmp_path / "personas.json").read_text())

            self.assertTrue(report.valid)
            self.assertEqual(report.base_personas, 9)
            self.assertEqual(report.controlled_variants, 11)
            self.assertEqual(len(payload), 20)
            self.assertNotIn("A1", {item["source_participant"] for item in payload})

    def test_persona_validator_rejects_missing_base_persona(self) -> None:
        from benchmark.personas import build_base_personas

        personas = build_base_personas(build_anchor_sessions())
        report = validate_personas(personas[:-1])

        self.assertFalse(report.valid)
        self.assertIn("Expected 9 base personas", "\n".join(report.errors))

    @requires_study_data
    def test_personas_anonymize_real_university_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            build_personas(output_path=tmp_path / "personas.json", report_path=tmp_path / "report.json")
            text = (tmp_path / "personas.json").read_text()

            self.assertNotIn("Columbia University", text)
            self.assertNotIn("Barnard College", text)
            self.assertIn("Cedarwick Hollow University", text)


class SimulationProfileTests(unittest.TestCase):
    def test_build_simulation_profiles_covers_persona_goal_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            build_personas(output_path=tmp_path / "personas.json", report_path=tmp_path / "persona_report.json")
            build_all(dry_run=True, data_dir=tmp_path / "data", reports_dir=tmp_path / "reports")
            report = build_simulation_profiles(
                personas_path=tmp_path / "personas.json",
                benchmark_path=tmp_path / "data" / "benchmark.json",
                output_path=tmp_path / "simulation_profiles.json",
                report_path=tmp_path / "simulation_report.json",
            )
            payload = json.loads((tmp_path / "simulation_profiles.json").read_text())

            self.assertTrue(report.valid)
            self.assertEqual(report.total_profiles, 1200)
            self.assertEqual(len(payload), 1200)
            sample = payload[0]
            self.assertIn("private_context_facts", sample)
            self.assertIn("unknown_or_undecided_facts", sample)
            self.assertIn("approval_criteria", sample)
            self.assertEqual(sample["initial_state"]["approval_status"], "not_ready")

    def test_simulation_profile_validator_rejects_missing_pair(self) -> None:
        from benchmark.simulation_profiles import build_simulation_profile, read_benchmark_goals

        personas_path = Path("benchmark/data/personas.json")
        benchmark_path = Path("benchmark/data/benchmark.json")
        personas = json.loads(personas_path.read_text())
        from benchmark.schemas import Persona

        parsed_personas = [Persona.model_validate(item) for item in personas]
        goals = read_benchmark_goals(benchmark_path)
        profiles = [build_simulation_profile(parsed_personas[0], goals[0])]
        report = validate_simulation_profiles(profiles, parsed_personas[:2], goals[:2])

        self.assertFalse(report.valid)
        self.assertIn("Expected 4 simulation profiles", "\n".join(report.errors))

    def test_build_simulation_profile_splits_holds_out_distinct_validation_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = build_simulation_profile_splits(
                profiles_path=Path("benchmark/data/simulation_profiles.json"),
                validation_size=10,
                validation_output_path=tmp_path / "validation.json",
                test_output_path=tmp_path / "test.json",
                test_300_output_path=tmp_path / "test_300.json",
                metadata_output_path=tmp_path / "split.json",
                report_path=tmp_path / "split_report.json",
            )
            validation_profiles = json.loads((tmp_path / "validation.json").read_text())
            test_profiles = json.loads((tmp_path / "test.json").read_text())
            test_300_profiles = json.loads((tmp_path / "test_300.json").read_text())
            validation_ids = {profile["simulation_profile_id"] for profile in validation_profiles}
            test_ids = {profile["simulation_profile_id"] for profile in test_profiles}
            test_300_ids = {profile["simulation_profile_id"] for profile in test_300_profiles}
            test_300_goal_counts = {}
            test_300_persona_counts = {}
            for profile in test_300_profiles:
                test_300_goal_counts[profile["goal_id"]] = test_300_goal_counts.get(profile["goal_id"], 0) + 1
                test_300_persona_counts[profile["persona_id"]] = test_300_persona_counts.get(profile["persona_id"], 0) + 1

            self.assertTrue(report.valid)
            self.assertEqual(report.validation_profile_count, 10)
            self.assertEqual(report.test_profile_count, report.total_profiles - 10)
            self.assertEqual(report.test_300_profile_count, 300)
            self.assertEqual(len({profile["persona_id"] for profile in validation_profiles}), 10)
            self.assertEqual(len({profile["goal_id"] for profile in validation_profiles}), 10)
            self.assertEqual(len({profile["goal_id"] for profile in test_300_profiles}), 60)
            self.assertEqual(len({profile["persona_id"] for profile in test_300_profiles}), 20)
            self.assertEqual(set(test_300_goal_counts.values()), {5})
            self.assertEqual(set(test_300_persona_counts.values()), {15})
            self.assertFalse(validation_ids & test_ids)
            self.assertFalse(validation_ids & test_300_ids)
            self.assertTrue(test_300_ids.issubset(test_ids))
            self.assertEqual(validation_ids, set(report.validation_profile_ids))

    def test_cross_goal_simulation_profile_does_not_leak_source_task_facts(self) -> None:
        from benchmark.simulation_profiles import build_simulation_profile
        from benchmark.schemas import BenchmarkGoal, Persona

        personas = [Persona.model_validate(item) for item in json.loads(Path("benchmark/data/personas.json").read_text())]
        p2 = next(persona for persona in personas if persona.persona_id == "P2_base")
        job_goal = BenchmarkGoal(
            goal_id="G999",
            goal_text="Land a job offer",
            source="generated",
            anchor_goal_id=None,
            anchor_type=None,
            domain="career_education",
            time_horizon="multi-month",
            expected_context_richness="high",
            complexity="multi-track",
            requires_personalization=True,
            requires_decomposition=True,
            expected_tangible_outputs=["job-search tracker", "outreach messages", "interview prep plan"],
            known_context_needs=["target roles", "resume strengths", "application timeline"],
            avoid=["pure fact lookup", "one-shot generic advice"],
        )
        profile = build_simulation_profile(p2, job_goal)
        serialized = profile.model_dump_json()

        self.assertNotIn("game night", serialized.lower())
        self.assertNotIn("PhD Students", serialized)
        self.assertIn("stable_persona_traits", serialized)
        self.assertIn("prior source-task details should not be used", serialized)
        self.assertIn("balanced", profile.source_persona_summary)
        self.assertEqual(profile.stable_persona_traits.preferences, ["prefers help that is specific to the current benchmark goal"])


class WorkflowSimulatorTests(unittest.TestCase):
    def test_user_decision_calibration_extractor_reads_multiple_study_logs(self) -> None:
        from benchmark.user_decision_calibration import build_user_decision_calibration

        root_with_tree = {
            "id": "0",
            "text": "Plan event",
            "level": 1,
            "need_subtasks": True,
            "is_completed": False,
            "children": [
                {
                    "id": "1",
                    "text": "Choose venue",
                    "level": 2,
                    "need_subtasks": False,
                    "is_completed": True,
                    "gpt_response": ["Venue suggestion"],
                    "answer_draft": {"answer_draft_input": "Use the library common room."},
                    "children": [],
                    "curated_context_draft": "Availability: Friday evening",
                },
                {
                    "id": "2",
                    "text": "Prepare invitations",
                    "level": 2,
                    "need_subtasks": True,
                    "is_completed": False,
                    "gpt_response_steps": [{"response": "Break down invitation work"}],
                    "answer_draft": {"answer_draft_input": ""},
                    "children": [
                        {
                            "id": "2.1",
                            "text": "Draft message",
                            "level": 3,
                            "need_subtasks": False,
                            "is_completed": True,
                            "gpt_response": ["Message v1", "Message v2"],
                            "answer_draft": {"answer_draft_input": "Please join game night Friday."},
                            "children": [],
                        }
                    ],
                },
            ],
        }
        root_without_tree = {
            "id": "0",
            "text": "One-shot task",
            "level": 1,
            "need_subtasks": False,
            "is_completed": False,
            "children": [],
            "answer_draft": {"answer_draft_input": ""},
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log1 = tmp_path / "userstudy.log"
            log2 = tmp_path / "userstudy2.log"
            log1.write_text(
                repr(
                    {
                        "task": "Plan event",
                        "username": "u1",
                        "root_node": root_with_tree,
                        "userGlobalContext": {"Availability": "Friday evening"},
                        "user_context": {"1-Choose venue": "Use the library common room."},
                    }
                )
                + "\n"
            )
            log2.write_text(
                repr(
                    {
                        "task": "One-shot task",
                        "username": "u2",
                        "root_node": root_without_tree,
                        "userGlobalContext": {},
                        "user_context": {},
                    }
                )
                + "\n"
            )

            report = build_user_decision_calibration(
                log_paths=[log1, log2],
                output_path=tmp_path / "calibration.json",
                report_path=tmp_path / "calibration_report.json",
            )

            self.assertTrue(report.valid)
            self.assertEqual(report.total_log_records, 2)
            self.assertEqual(report.final_session_count, 2)
            self.assertTrue((tmp_path / "calibration.json").exists())
            self.assertEqual(report.policies["task_tree_review"]["accept_rate"], 0.5)
            self.assertEqual(report.policies["source_summary"]["records_by_log"][str(log1)], 1)
            self.assertGreater(report.policies["draft_review"]["revision_proxy_rate"], 0)

    def test_workflow_user_actions_use_calibration_policies(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        calibration = {
            "task_tree_review": {"observations": 10, "accept_rate": 1.0, "accept_proxy_definition": "test"},
            "subtask_detection_decision": {
                "observations": 10,
                "decompose_further_rate": 1.0,
                "draft_answer_rate": 0.0,
                "proxy_definition": "test",
            },
            "nested_task_review": {
                "observations": 10,
                "selected_child_position_distribution": {"first_child": 1.0},
                "proxy_definition": "test",
            },
            "draft_review": {"observations": 10, "saved_draft_rate": 1.0, "proxy_definition": "test"},
            "final_artifact_review": {
                "observations": 10,
                "completion_bucket_distribution": {"0.00-0.25": 1.0},
                "proxy_definition": "test",
            },
        }

        session = simulate_workflow_session(
            profile,
            condition="full_jumpstarter",
            seed=42,
            user_decision_calibration=calibration,
        )

        tree_review = next(event for event in session.events if event.event_type == "task_tree_review")
        subtask_decisions = [event for event in session.events if event.event_type == "subtask_detection_decision"]
        nested_reviews = [event for event in session.events if event.event_type == "nested_task_review"]
        final_review = next(event for event in session.events if event.event_type == "final_artifact_review")

        self.assertEqual(tree_review.payload["calibration"]["policy"], "task_tree_review")
        self.assertTrue(all(event.payload["chosen_next_step"] == "decompose_further" for event in subtask_decisions))
        self.assertTrue(nested_reviews)
        self.assertTrue(all(event.payload["selected_child_policy"] == "first_child" for event in nested_reviews))
        self.assertTrue(all(str(event.payload["selected_child_node_id"]).endswith(".1") for event in nested_reviews))
        self.assertEqual(final_review.payload["calibration"]["sampled_completion_threshold"], 0.125)

    def test_workflow_pilot_writes_ui_stage_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = run_workflow_pilot(
                profiles_path=Path("benchmark/data/simulation_profiles.json"),
                output_dir=tmp_path / "workflow_run",
                condition="full_jumpstarter",
                limit=3,
                seed=42,
            )
            sessions_path = tmp_path / "workflow_run" / "sessions.jsonl"
            trace_files = list((tmp_path / "workflow_run" / "traces").glob("*.json"))
            first_session = json.loads(sessions_path.read_text().splitlines()[0])
            event_types = {event["event_type"] for event in first_session["events"]}
            stages = {event["stage"] for event in first_session["events"]}

            self.assertTrue(report.valid)
            self.assertEqual(report.total_sessions, 3)
            self.assertEqual(report.condition_counts["full_jumpstarter"], 3)
            self.assertTrue(sessions_path.exists())
            self.assertEqual(len(trace_files), 3)
            self.assertIn("goal_input", event_types)
            self.assertIn("global_context_elicitation", event_types)
            self.assertIn("task_decomposition", event_types)
            self.assertIn("subtask_detection", event_types)
            self.assertIn("subtask_detection_decision", event_types)
            self.assertIn("task_forking_detection", event_types)
            self.assertIn("context_selection", event_types)
            self.assertIn("context_reuse", event_types)
            self.assertIn("local_context_elicitation", event_types)
            self.assertIn("saved_local_context", event_types)
            self.assertIn("draft_refinement", event_types)
            self.assertIn("subtask_detection", stages)
            self.assertIn("final_review", stages)
            self.assertGreater(report.subtask_detection_events, 0)
            self.assertGreater(report.decompose_further_events, 0)
            self.assertGreater(report.task_forking_detection_events, 0)
            self.assertIn("subtask_detection_decisions", first_session["final_state"])
            self.assertIn("task_forking_decisions", first_session["final_state"])
            prompt_payloads = [
                event["payload"]["prompt"]
                for event in first_session["events"]
                if isinstance(event.get("payload"), dict) and "prompt" in event["payload"]
            ]
            self.assertTrue(prompt_payloads)
            self.assertTrue(all(prompt["prompt_version"] == "paper_workflow_v1" for prompt in prompt_payloads))
            self.assertTrue(all(str(PROMPT_DIR) in prompt["prompt_path"] for prompt in prompt_payloads))
            self.assertTrue(all(prompt["rendered_prompt"].strip() for prompt in prompt_payloads))
            self.assertLessEqual(
                {
                    "global_context_elicitation",
                    "local_context_elicitation",
                    "context_selection_draft",
                    "subtask_generation",
                    "subtask_detection",
                    "task_forking",
                    "working_solution_draft_creation",
                },
                {prompt["prompt_id"] for prompt in prompt_payloads},
            )
            drafts = first_session["final_state"]["node_drafts"]
            self.assertTrue(all("Reusable artifact:" in draft for draft in drafts.values()))
            self.assertFalse(any("Include concrete next steps and a reusable artifact." in draft for draft in drafts.values()))

    def test_no_selection_condition_never_selects_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = run_workflow_pilot(
                profiles_path=Path("benchmark/data/simulation_profiles.json"),
                output_dir=tmp_path / "workflow_run",
                condition="no_selection",
                limit=2,
                seed=42,
            )
            sessions = [json.loads(line) for line in (tmp_path / "workflow_run" / "sessions.jsonl").read_text().splitlines()]
            selection_events = [
                event
                for session in sessions
                for event in session["events"]
                if event["event_type"] == "context_selection"
            ]

            self.assertTrue(report.valid)
            self.assertGreater(len(selection_events), 0)
            self.assertTrue(all(not event["payload"]["selected_context_ids"] for event in selection_events))

    def test_agent_baselines_generate_valid_judge_ready_sessions(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        conditions = [
            "adapt_recursive_decomposition",
            "ask_before_plan",
            "unstructured_memory_rag",
            "long_context_planner",
        ]
        sessions = [simulate_workflow_session(profile, condition=condition, seed=42) for condition in conditions]
        report = workflow_fidelity_report(sessions)

        self.assertTrue(report.valid, report.errors)
        for session in sessions:
            self.assertIn("final_artifact", session.final_state)
            self.assertTrue(session.final_state["node_selected_contexts"])
            self.assertGreater(len(session.final_state["node_drafts"]), 0)
        memory_session = next(session for session in sessions if session.condition == "unstructured_memory_rag")
        long_context_session = next(session for session in sessions if session.condition == "long_context_planner")
        adapt_session = next(session for session in sessions if session.condition == "adapt_recursive_decomposition")
        ask_before_plan_session = next(session for session in sessions if session.condition == "ask_before_plan")
        adapt_event_types = {event.event_type for event in adapt_session.events}
        ask_event_types = {event.event_type for event in ask_before_plan_session.events}
        self.assertIn("adapt_initial_planner", adapt_event_types)
        self.assertIn("adapt_executor_attempt", adapt_event_types)
        self.assertTrue({"adapt_info_propagation", "adapt_depth_limit"} & adapt_event_types)
        self.assertIn("abp_tool_agent_run", ask_event_types)
        self.assertIn("abp_clarification_decision", ask_event_types)
        self.assertIn("abp_planning_agent_run", ask_event_types)
        self.assertTrue(any(event.stage == "memory_retrieval" for event in memory_session.events))
        self.assertTrue(any(event.stage == "long_context_assembly" for event in long_context_session.events))

    def test_workflow_experiment_resumes_checkpointed_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "workflow_run"
            run_workflow_experiment(
                profiles_path=Path("benchmark/data/simulation_profiles.json"),
                output_dir=output_dir,
                conditions=["full_jumpstarter", "no_selection"],
                limit=1,
                seed=42,
            )
            sessions_path = output_dir / "sessions.jsonl"
            first_line = sessions_path.read_text().splitlines()[0]
            sessions_path.write_text(first_line + "\n")

            report = run_workflow_experiment(
                profiles_path=Path("benchmark/data/simulation_profiles.json"),
                output_dir=output_dir,
                conditions=["full_jumpstarter", "no_selection"],
                limit=1,
                seed=42,
            )
            sessions = [json.loads(line) for line in sessions_path.read_text().splitlines() if line.strip()]

        self.assertTrue(report.valid)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(len({session["session_id"] for session in sessions}), 2)

    def test_judge_resumes_checkpointed_scores(self) -> None:
        records = [
            {"blind_id": "B00001", "goal_id": "G001", "goal_text": "Plan a study night", "user_context": "", "system_output": "Make a checklist."},
            {"blind_id": "B00002", "goal_id": "G002", "goal_text": "Plan a move", "user_context": "", "system_output": "Pack boxes."},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            input_path = run_dir / "judge_inputs_blinded.jsonl"
            output_path = run_dir / "judge_scores.jsonl"
            input_path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
            run_judge(input_path, output_path=output_path, live=False, max_workers=1)
            first_line = output_path.read_text().splitlines()[0]
            output_path.write_text(first_line + "\n")

            report = run_judge(input_path, output_path=output_path, live=False, max_workers=1)
            scores = [json.loads(line) for line in output_path.read_text().splitlines() if line.strip()]

        self.assertTrue(report.valid)
        self.assertEqual(len(scores), 2)
        self.assertEqual([score["score_id"] for score in scores], ["S00001", "S00002"])
        self.assertEqual(len({score["blind_id"] for score in scores}), 2)

    def test_context_relevance_labeler_resumes_checkpointed_labels(self) -> None:
        from benchmark.context_relevance import run_context_relevance_labeler

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "workflow_run"
            run_workflow_experiment(
                profiles_path=Path("benchmark/data/simulation_profiles.json"),
                output_dir=run_dir,
                conditions=["full_jumpstarter"],
                limit=1,
                seed=42,
            )
            first_report = run_context_relevance_labeler(run_dir, live=False, max_workers=1)
            labels_path = run_dir / "context_relevance_labels.jsonl"
            partial_lines = labels_path.read_text().splitlines()[:2]
            labels_path.write_text("\n".join(partial_lines) + "\n")

            report = run_context_relevance_labeler(run_dir, live=False, max_workers=1)
            labels = [json.loads(line) for line in labels_path.read_text().splitlines() if line.strip()]

        self.assertTrue(report["valid"])
        self.assertEqual(report["label_count"], first_report["label_count"])
        self.assertEqual(len(labels), first_report["label_count"])
        self.assertEqual(len({label["label_id"] for label in labels}), len(labels))

    def test_pushback_warning_requires_same_session_final_approval(self) -> None:
        from benchmark.schemas import SimulationProfile, WorkflowEvent

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        pushback_session = simulate_workflow_session(profile, condition="no_selection", seed=42)
        approved_session = simulate_workflow_session(profile, condition="full_jumpstarter", seed=42)
        report = workflow_fidelity_report([pushback_session, approved_session])

        self.assertGreater(report.pushback_events, 0)
        self.assertGreater(report.approval_events, 0)
        self.assertFalse(any("pushback events but still reached final approval" in warning for warning in report.warnings))

        events = list(pushback_session.events)
        events.append(
            WorkflowEvent(
                event_id=len(events) + 1,
                event_type="final_artifact_review",
                actor="user",
                stage="final_review",
                node_id=None,
                payload={"action": "approve", "approval_status": "approved"},
            )
        )
        lenient_session = pushback_session.model_copy(update={"events": events})
        report = workflow_fidelity_report([lenient_session])

        self.assertTrue(any("pushback events but still reached final approval" in warning for warning in report.warnings))

    def test_context_bank_grows_with_global_local_and_draft_contexts(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        session = simulate_workflow_session(profile, condition="full_jumpstarter", seed=42)
        context_bank = session.final_state["context_bank"]
        selection_events = [event for event in session.events if event.event_type == "context_selection"]
        available_counts = [len(event.payload["available_context_ids"]) for event in selection_events]
        available_context_ids = [context_id for event in selection_events for context_id in event.payload["available_context_ids"]]
        scopes = {context["scope"] for context in context_bank.values()}
        draft_contexts = {
            context_id: context
            for context_id, context in context_bank.items()
            if context.get("scope") == "draft"
        }

        self.assertLessEqual({"global", "local", "draft"}, scopes)
        self.assertEqual(len(draft_contexts), len(session.final_state["node_drafts"]))
        self.assertEqual(available_counts, sorted(available_counts))
        self.assertTrue(any(context_id.startswith("draft_") for context_id in available_context_ids))
        for node_id, draft in session.final_state["node_drafts"].items():
            self.assertEqual(draft_contexts[f"draft_{node_id}"]["value"], draft)

    def test_full_jumpstarter_compiles_polished_final_artifact(self) -> None:
        from benchmark.experiment_runner import _final_artifact_text
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        session = simulate_workflow_session(profile, condition="full_jumpstarter", seed=42)
        final_artifact = session.final_state["final_artifact"]
        compilation_event = next(event for event in session.events if event.event_type == "final_artifact_compilation")

        self.assertIn("Confirmed Inputs Used", final_artifact)
        self.assertIn("Reusable Artifacts", final_artifact)
        self.assertIn("Subtask Coverage Map", final_artifact)
        self.assertIn("TODO Before Use", final_artifact)
        self.assertIn("Assumptions Avoided", final_artifact)
        self.assertNotIn("Local refinement", final_artifact)
        self.assertNotIn("Context used as evidence", final_artifact)
        self.assertEqual(_final_artifact_text(session), final_artifact)
        self.assertEqual(compilation_event.payload["generation_mode"], "deterministic")
        self.assertGreater(len(compilation_event.payload["confirmed_context_ids"]), 0)
        self.assertGreater(compilation_event.payload["reusable_artifact_count"], 0)
        self.assertEqual(
            len(compilation_event.payload["subtask_coverage_map"]),
            len(session.final_state["node_drafts"]),
        )

    def test_compiler_todos_are_domain_specific(self) -> None:
        from benchmark.workflow_simulator import _final_artifact_todo_items

        todos = _final_artifact_todo_items(
            profile=type(
                "Profile",
                (),
                {
                    "unknown_or_undecided_facts": ["Target roles: unknown"],
                },
            )(),
            context_bank={},
            node_drafts={
                "N1": (
                    "Reusable artifact:\n"
                    "- Job-search tracker with columns for Company, Role, Application deadline, and Contact.\n"
                    "- Cover letter template with [Company] and [Role] placeholders."
                )
            },
            todo_contexts=[],
        )

        joined = "\n".join(todos).lower()
        self.assertIn("dates, deadlines", joined)
        self.assertIn("contact details", joined)
        self.assertNotIn("venue/resource", joined)
        self.assertNotIn("capacities", joined)

    def test_context_relevance_labeler_writes_session_metrics(self) -> None:
        from benchmark.context_relevance import run_context_relevance_labeler
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        session = simulate_workflow_session(profile, condition="full_jumpstarter", seed=42)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "sessions.jsonl").write_text(session.model_dump_json() + "\n")
            report = run_context_relevance_labeler(run_dir, live=False, max_workers=2)
            labels = [
                json.loads(line)
                for line in (run_dir / "context_relevance_labels.jsonl").read_text().splitlines()
                if line.strip()
            ]
            metrics = json.loads((run_dir / "context_relevance_metrics.json").read_text())

        self.assertTrue(report["valid"])
        self.assertGreater(report["label_count"], 0)
        self.assertTrue(labels)
        self.assertIn("gpt_relevance_score", labels[0])
        self.assertEqual(len(metrics), 1)
        self.assertIn("gpt_context_precision", metrics[0])

    def test_random_context_selection_matches_relevance_token_budget(self) -> None:
        from benchmark.workflow_simulator import (
            CONTEXT_RELEVANCE_THRESHOLD,
            _context_relevance_score,
            _context_token_count_for_ids,
            _ranked_relevant_context_ids,
            _select_context_ids,
        )

        context_bank = {
            "venue": {
                "scope": "global",
                "label": "Venue options",
                "value": "library common room campus cafe",
            },
            "availability": {
                "scope": "global",
                "label": "Availability",
                "value": "friday evening saturday evening",
            },
            "budget": {
                "scope": "global",
                "label": "Budget",
                "value": "small snacks budget",
            },
            "games": {
                "scope": "global",
                "label": "Game preferences",
                "value": "board games card games",
            },
            "unrelated": {
                "scope": "global",
                "label": "Favorite color",
                "value": "blue",
            },
        }
        node = {
            "node_id": "N1",
            "title": "Plan Event Logistics",
            "description": "Choose venue, availability, budget, and game preferences for the event.",
        }
        task_text = f"{node['title']} {node['description']}"

        full_ids = _select_context_ids("full_jumpstarter", context_bank, node, random.Random(42))
        random_ids = _select_context_ids("random_selection", context_bank, node, random.Random(42))

        self.assertEqual(full_ids, _ranked_relevant_context_ids(context_bank, node))
        self.assertTrue(all(_context_relevance_score(task_text, context_bank[context_id]) > CONTEXT_RELEVANCE_THRESHOLD for context_id in full_ids))
        self.assertLessEqual(_context_relevance_score(task_text, context_bank["unrelated"]), CONTEXT_RELEVANCE_THRESHOLD)
        self.assertNotIn("unrelated", full_ids)
        self.assertGreater(len(full_ids), 3)
        self.assertLessEqual(len(random_ids), len(full_ids))
        self.assertLessEqual(
            abs(_context_token_count_for_ids(context_bank, random_ids) - _context_token_count_for_ids(context_bank, full_ids)),
            2,
        )

    def test_unknown_context_is_not_reused_as_useful_evidence(self) -> None:
        from benchmark.schemas import SimulationProfile
        from benchmark.workflow_simulator import _context_digest_for_node, _is_substantive_context

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        node = {
            "node_id": "N1",
            "title": "Create Invitations",
            "description": "Draft an invitation using the known schedule and audience constraints.",
        }
        context_bank = {
            "known": {
                "scope": "global",
                "label": "Availability",
                "value": "Students prefer Friday after 7:30pm.",
            },
            "unknown": {
                "scope": "global",
                "label": "Preferred game types",
                "value": "I do not know yet.",
            },
        }

        digest = _context_digest_for_node(profile, node, {"known": context_bank["known"]}, context_bank)

        self.assertTrue(_is_substantive_context(context_bank["known"]))
        self.assertFalse(_is_substantive_context(context_bank["unknown"]))
        self.assertIn("Students prefer Friday", json.dumps(digest["facts_to_use"]))
        self.assertIn("Preferred game types", json.dumps(digest["excluded_unknown_contexts"]))
        self.assertNotIn("I do not know yet", json.dumps(digest["facts_to_use"]))

    def test_task_forking_decomposition_uses_entity_context(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload).model_copy(
            update={
                "goal_text": "Research PhD programs",
                "private_context_facts": ["Potential programs: University A, University B, University C"],
                "must_reveal_if_asked": ["Potential programs"],
                "approval_criteria": ["the plan directly supports: Research PhD programs", "includes outreach plan"],
            }
        )
        session = simulate_workflow_session(profile, condition="full_jumpstarter", seed=42)
        event_types = {event.event_type for event in session.events}
        forking_events = [event for event in session.events if event.event_type == "task_forking_decomposition"]

        self.assertIn("task_forking_context_selection", event_types)
        self.assertIn("task_forking_decomposition", event_types)
        self.assertTrue(forking_events)
        self.assertEqual(forking_events[0].payload["decomposition_type"], "task_forking")
        self.assertIn("University A", json.dumps(forking_events[0].payload))

    def test_live_task_forking_rejects_placeholder_entities_without_context_list(self) -> None:
        from benchmark.schemas import SimulationProfile, WorkflowLiveTaskForkingResponse
        from benchmark.workflow_simulator import _forked_task_nodes, _live_task_forking

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        node = {
            "node_id": "N1",
            "title": "Identify Game Preferences",
            "description": "Survey PhD students to determine specific types of fantasy and party games they prefer.",
        }
        context_bank = {
            "global_3": {
                "scope": "global",
                "label": "preferred game types",
                "value": "I do not know the specific types of fantasy or party games preferred yet.",
            }
        }
        fallback = {
            "answer": "No",
            "reason": "No reusable entity list is available in context for entity-based decomposition.",
            "entity_source_context_id": None,
            "entities": [],
        }

        def fake_live_stage(_prompt: str, _payload: str, text_format: object, model: str | None = None) -> object:
            self.assertIs(text_format, WorkflowLiveTaskForkingResponse)
            return WorkflowLiveTaskForkingResponse(
                answer="Yes",
                reason="The task can iterate over individual students.",
                entity_source_context_id="global_3",
                entities=["Entity 1", "Entity 2"],
            )

        with patch("benchmark.workflow_simulator.parse_workflow_stage_live", side_effect=fake_live_stage):
            decision = _live_task_forking(
                profile,
                node,
                context_bank,
                {"rendered_prompt": "Should this task fork?"},
                "gpt-4o",
                fallback,
            )

        self.assertEqual(decision["answer"], "No")
        self.assertEqual(decision["entities"], [])
        self.assertEqual(_forked_task_nodes(node, context_bank["global_3"]), [])

    def test_live_drafts_mode_only_model_backs_working_solution_drafts(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)

        def fake_live_stage(_prompt: str, _payload: str, text_format: object, model: str | None = None) -> object:
            self.assertIs(model, None)
            self.assertIs(text_format, WorkflowLiveDraftResponse)
            return WorkflowLiveDraftResponse(draft="LIVE DRAFT ARTIFACT")

        with patch("benchmark.workflow_simulator.parse_workflow_stage_live", side_effect=fake_live_stage) as mock_live:
            session = simulate_workflow_session(
                profile,
                condition="full_jumpstarter",
                seed=42,
                model="deterministic",
                live_stages="drafts",
            )

        self.assertGreater(mock_live.call_count, 0)
        self.assertTrue(all("LIVE DRAFT ARTIFACT" in draft for draft in session.final_state["node_drafts"].values()))
        draft_events = [event for event in session.events if event.event_type == "subtask_draft"]
        self.assertTrue(all(event.payload["generation_mode"] == "live" for event in draft_events))
        task_events = [event for event in session.events if event.event_type == "task_decomposition"]
        self.assertTrue(all(event.payload.get("generation_mode") != "live" for event in task_events))

    def test_live_planning_mode_model_backs_decomposition_detection_and_drafts(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)

        def fake_live_stage(_prompt: str, _payload: str, text_format: object, model: str | None = None) -> object:
            if text_format is WorkflowLiveTaskDecompositionResponse:
                return WorkflowLiveTaskDecompositionResponse(
                    nodes=[
                        {"title": "Live Plan Artifact", "description": "Create a live generated plan artifact."},
                        {"title": "Live Message Artifact", "description": "Create a live generated message artifact."},
                    ]
                )
            if text_format is WorkflowLiveSubtaskDetectionResponse:
                return WorkflowLiveSubtaskDetectionResponse(suggested_action="draft_answer", rationale="Live detection says draft now.")
            if text_format is WorkflowLiveDraftResponse:
                return WorkflowLiveDraftResponse(draft="LIVE PLANNING DRAFT")
            raise AssertionError(f"Unexpected live text format: {text_format}")

        with patch("benchmark.workflow_simulator.parse_workflow_stage_live", side_effect=fake_live_stage):
            session = simulate_workflow_session(
                profile,
                condition="full_jumpstarter",
                seed=42,
                model="test-model",
                live_stages="planning",
            )

        task_event = next(event for event in session.events if event.event_type == "task_decomposition")
        detection_events = [event for event in session.events if event.event_type == "subtask_detection"]
        draft_events = [event for event in session.events if event.event_type == "subtask_draft"]
        self.assertEqual(task_event.payload["generation_mode"], "live")
        self.assertTrue(all(event.payload["generation_mode"] == "live" for event in detection_events))
        self.assertTrue(all(event.payload["generation_mode"] == "live" for event in draft_events))
        self.assertEqual([node["title"] for node in task_event.payload["nodes"]], ["Live Plan Artifact", "Live Message Artifact"])

    def test_live_all_mode_model_backs_context_elicitation_and_selection(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)

        def fake_live_stage(_prompt: str, payload: str, text_format: object, model: str | None = None) -> object:
            if text_format is WorkflowLiveQuestionResponse:
                data = json.loads(payload)
                return WorkflowLiveQuestionResponse(
                    question=data["fallback_question"],
                    requested_context_key=data["fallback_requested_context_key"],
                )
            if text_format is WorkflowLiveTaskDecompositionResponse:
                return WorkflowLiveTaskDecompositionResponse(
                    nodes=[{"title": "Live Context-Aware Plan", "description": "Create the context-aware plan."}]
                )
            if text_format is WorkflowLiveSubtaskDetectionResponse:
                return WorkflowLiveSubtaskDetectionResponse(suggested_action="draft_answer", rationale="Draft now.")
            if text_format is WorkflowLiveTaskForkingResponse:
                return WorkflowLiveTaskForkingResponse(
                    answer="No",
                    reason="No concrete entity list is available for forking.",
                    entity_source_context_id=None,
                    entities=[],
                )
            if text_format is WorkflowLiveContextSelectionResponse:
                data = json.loads(payload)
                return WorkflowLiveContextSelectionResponse(
                    selected_context_ids=data["available_context_ids"][:1],
                    selection_reason="Live selected the most relevant context.",
                )
            if text_format is WorkflowLiveDraftResponse:
                return WorkflowLiveDraftResponse(draft="LIVE ALL-STAGES DRAFT")
            raise AssertionError(f"Unexpected live text format: {text_format}")

        with patch("benchmark.workflow_simulator.parse_workflow_stage_live", side_effect=fake_live_stage):
            session = simulate_workflow_session(
                profile,
                condition="full_jumpstarter",
                seed=42,
                model="test-model",
                live_stages="all",
            )

        global_events = [event for event in session.events if event.event_type == "global_context_elicitation"]
        local_events = [event for event in session.events if event.event_type == "local_context_elicitation"]
        selection_events = [event for event in session.events if event.event_type == "context_selection"]
        self.assertTrue(all(event.payload["generation_mode"] == "live" for event in global_events))
        self.assertTrue(all(event.payload["generation_mode"] == "live" for event in local_events))
        self.assertTrue(all(event.payload["generation_mode"] == "live" for event in selection_events))

    def test_repeated_live_global_questions_fall_back_to_distinct_context_targets(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)

        def fake_live_stage(_prompt: str, payload: str, text_format: object, model: str | None = None) -> object:
            if text_format is WorkflowLiveQuestionResponse:
                data = json.loads(payload)
                if data["question_type"] == "global_context_elicitation":
                    return WorkflowLiveQuestionResponse(
                        question="Do you have a list of available campus locations for the game night?",
                        requested_context_key="campus location constraints",
                    )
                return WorkflowLiveQuestionResponse(
                    question=data["fallback_question"],
                    requested_context_key=data["fallback_requested_context_key"],
                )
            if text_format is WorkflowLiveTaskDecompositionResponse:
                return WorkflowLiveTaskDecompositionResponse(nodes=[{"title": "Live Plan", "description": "Create the live plan."}])
            if text_format is WorkflowLiveSubtaskDetectionResponse:
                return WorkflowLiveSubtaskDetectionResponse(suggested_action="draft_answer", rationale="Draft now.")
            if text_format is WorkflowLiveTaskForkingResponse:
                return WorkflowLiveTaskForkingResponse(
                    answer="No",
                    reason="No concrete entity list is available for forking.",
                    entity_source_context_id=None,
                    entities=[],
                )
            if text_format is WorkflowLiveContextSelectionResponse:
                data = json.loads(payload)
                return WorkflowLiveContextSelectionResponse(
                    selected_context_ids=data["fallback_selected_context_ids"],
                    selection_reason="Use fallback selection.",
                )
            if text_format is WorkflowLiveDraftResponse:
                return WorkflowLiveDraftResponse(draft="LIVE DRAFT")
            raise AssertionError(f"Unexpected live text format: {text_format}")

        with patch("benchmark.workflow_simulator.parse_workflow_stage_live", side_effect=fake_live_stage):
            session = simulate_workflow_session(
                profile,
                condition="full_jumpstarter",
                seed=42,
                model="test-model",
                live_stages="all",
            )

        global_events = [event for event in session.events if event.event_type == "global_context_elicitation"]
        global_questions = [event.payload["question"] for event in global_events]
        global_keys = [event.payload["requested_context_key"] for event in global_events]

        self.assertEqual(len(global_questions), 3)
        self.assertEqual(len(set(global_questions)), 3)
        self.assertEqual(len(set(global_keys)), 3)
        self.assertTrue(any("availability" in key.lower() for key in global_keys))
        self.assertFalse(all("campus" in question.lower() for question in global_questions))

    def test_live_stage_none_responses_fall_back_to_deterministic_outputs(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        deterministic_session = simulate_workflow_session(
            profile,
            condition="full_jumpstarter",
            seed=42,
            model="deterministic",
            live_stages="deterministic",
        )

        with patch("benchmark.workflow_simulator.parse_workflow_stage_live", return_value=None) as mock_live:
            live_session = simulate_workflow_session(
                profile,
                condition="full_jumpstarter",
                seed=42,
                model="test-model",
                live_stages="all",
            )

        self.assertGreater(mock_live.call_count, 0)
        self.assertEqual(live_session.final_state["task_tree"], deterministic_session.final_state["task_tree"])
        self.assertEqual(live_session.final_state["node_drafts"], deterministic_session.final_state["node_drafts"])

    def test_live_simulated_user_uses_separate_model(self) -> None:
        from benchmark.schemas import SimulationProfile

        profile_payload = json.loads(Path("benchmark/data/simulation_profiles.json").read_text())[0]
        profile = SimulationProfile.model_validate(profile_payload)
        seen_models: list[str | None] = []

        def fake_user_answer(
            _profile: SimulationProfile,
            question: str,
            requested_context_key: str,
            conversation_state: dict[str, object],
            model: str | None = None,
        ) -> str:
            seen_models.append(model)
            self.assertIn("stage", conversation_state)
            return f"Simulated user answer to {question} about {requested_context_key}."

        with patch("benchmark.workflow_simulator.generate_simulated_user_answer_live", side_effect=fake_user_answer):
            session = simulate_workflow_session(
                profile,
                condition="full_jumpstarter",
                seed=42,
                live_simulated_user=True,
                simulated_user_model="user-model",
            )

        answer_events = [
            event
            for event in session.events
            if event.event_type in {"global_context_answer", "local_context_answer"}
        ]
        self.assertGreater(len(seen_models), 0)
        self.assertEqual(set(seen_models), {"user-model"})
        self.assertTrue(all(event.payload["generation_mode"] == "live" for event in answer_events))
        self.assertTrue(all(event.payload["simulated_user_model"] == "user-model" for event in answer_events))

    def test_live_simulated_user_question_sanitizer_removes_followups(self) -> None:
        from benchmark.openai_generation import _strip_simulated_user_questions
        from benchmark.workflow_simulator import _answer_status

        answer = _strip_simulated_user_questions(
            "I don't have a list of potential venues yet. Are there any specific campus location constraints I should consider?"
        )

        self.assertEqual(answer, "I don't have a list of potential venues yet.")
        self.assertNotIn("?", answer)
        self.assertEqual(_answer_status(answer), "unknown")

    def test_workflow_experiment_writes_balanced_judge_ready_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = run_workflow_experiment(
                profiles_path=Path("benchmark/data/simulation_profiles.json"),
                output_dir=tmp_path / "experiment_run",
                conditions=["full_jumpstarter", "chatgpt_with_elicited_context", "chatgpt_vanilla"],
                limit=2,
                runs_per_profile=1,
                seed=42,
            )
            output_dir = tmp_path / "experiment_run"
            artifacts = (output_dir / "artifacts.jsonl").read_text().splitlines()
            judge_inputs = (output_dir / "judge_inputs_blinded.jsonl").read_text().splitlines()
            condition_key = (output_dir / "condition_key.jsonl").read_text().splitlines()
            mechanism_metrics = json.loads((output_dir / "mechanism_metrics.json").read_text())
            first_judge_input = json.loads(judge_inputs[0])
            full_mechanism_metrics = [item for item in mechanism_metrics if item["condition"] == "full_jumpstarter"]

            self.assertTrue(report.valid)
            self.assertEqual(report.total_sessions, 6)
            self.assertEqual(report.expected_sessions, 6)
            self.assertTrue(report.grid_complete)
            self.assertEqual(report.condition_counts["full_jumpstarter"], 2)
            self.assertEqual(report.condition_counts["chatgpt_with_elicited_context"], 2)
            self.assertEqual(report.condition_counts["chatgpt_vanilla"], 2)
            self.assertEqual(len(artifacts), 6)
            self.assertEqual(len(judge_inputs), 6)
            self.assertEqual(len(condition_key), 6)
            self.assertIn("blind_id", first_judge_input)
            self.assertNotIn("condition", first_judge_input)
            self.assertTrue((output_dir / "mechanism_metrics.json").exists())
            self.assertTrue((output_dir / "experiment_report.json").exists())
            self.assertTrue(any(item["available_relevant_context_mentions"] > 0 for item in full_mechanism_metrics))
            self.assertTrue(any((item["context_precision_proxy"] or 0) > 0 for item in full_mechanism_metrics))
            self.assertTrue(all("selected_relevance_score_mean" in item for item in full_mechanism_metrics))
            self.assertTrue(all("reused_context_mention_rate" in item for item in full_mechanism_metrics))
            self.assertTrue(all("open_decision_field_rate" in item for item in full_mechanism_metrics))


class WorkflowAnalysisTests(unittest.TestCase):
    def test_analyze_workflow_experiment_writes_score_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _build_scored_workflow_experiment(Path(tmp))

            report = analyze_workflow_experiment(run_dir)
            summary = json.loads((run_dir / "score_summary.json").read_text())
            markdown = (run_dir / "score_summary.md").read_text()
            comparison = next(item for item in summary["comparisons"] if item["comparator_condition"] == "chatgpt_vanilla")

            self.assertTrue(report.valid)
            self.assertTrue((run_dir / "score_summary.json").exists())
            self.assertTrue((run_dir / "score_summary.md").exists())
            self.assertEqual(report.score_count, 4)
            self.assertEqual(report.condition_count, 2)
            self.assertEqual({item.condition for item in report.condition_summaries}, {"full_jumpstarter", "chatgpt_vanilla"})
            self.assertEqual(comparison["baseline_condition"], "full_jumpstarter")
            self.assertEqual(comparison["matched_profile_count"], 2)
            self.assertEqual(comparison["wins"] + comparison["ties"] + comparison["losses"], 2)
            self.assertIn("Workflow Experiment Score Summary", markdown)
            self.assertIn("Study quality mean", markdown)

    def test_analyze_workflow_experiment_rejects_missing_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze_workflow_experiment(Path(tmp))

            self.assertFalse(report.valid)
            self.assertIn("Missing required experiment analysis input", "\n".join(report.errors))
            self.assertFalse((Path(tmp) / "score_summary.json").exists())

    def test_analyze_workflow_experiment_rejects_duplicate_blind_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _build_scored_workflow_experiment(Path(tmp))
            scores_path = run_dir / "judge_scores.jsonl"
            first_score = scores_path.read_text().splitlines()[0]
            with scores_path.open("a") as handle:
                handle.write(first_score + "\n")

            report = analyze_workflow_experiment(run_dir)

            self.assertFalse(report.valid)
            self.assertIn("Duplicate blind_id values in judge_scores", "\n".join(report.errors))

    def test_analyze_workflow_experiment_rejects_unmapped_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _build_scored_workflow_experiment(Path(tmp))
            scores_path = run_dir / "judge_scores.jsonl"
            records = [json.loads(line) for line in scores_path.read_text().splitlines()]
            records[0]["blind_id"] = "B99999"
            scores_path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

            report = analyze_workflow_experiment(run_dir)

            self.assertFalse(report.valid)
            errors = "\n".join(report.errors)
            self.assertIn("Missing judge scores for blind IDs", errors)
            self.assertIn("Judge scores without condition-key rows", errors)

    def test_analyze_workflow_experiment_uses_aggregate_fallback_for_duplicate_profile_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run_dir = tmp_path / "experiment_run"
            run_workflow_experiment(
                profiles_path=Path("benchmark/data/simulation_profiles.json"),
                output_dir=run_dir,
                conditions=["full_jumpstarter", "chatgpt_vanilla"],
                limit=1,
                runs_per_profile=2,
                seed=42,
            )
            run_judge(
                run_dir / "judge_inputs_blinded.jsonl",
                output_path=run_dir / "judge_scores.jsonl",
                report_path=run_dir / "judge_run_report.json",
                live=False,
            )

            report = analyze_workflow_experiment(run_dir)

            self.assertTrue(report.valid)
            self.assertTrue(report.comparisons[0].aggregate_only)
            self.assertEqual(report.comparisons[0].matched_profile_count, 0)
            self.assertIn("aggregate condition means", "\n".join(report.warnings))


class JudgeTests(unittest.TestCase):
    @requires_study_data
    def test_build_judge_calibration_set_from_human_study_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = build_judge_calibration_set(
                output_path=tmp_path / "judge_calibration.jsonl",
                report_path=tmp_path / "judge_calibration_report.json",
            )
            records = [json.loads(line) for line in (tmp_path / "judge_calibration.jsonl").read_text().splitlines()]
            serialized = json.dumps(records)
            condition_counts = {}
            for record in records:
                condition_counts[record["condition_label"]] = condition_counts.get(record["condition_label"], 0) + 1
            paired_anchor_ids = {
                record["anchor_id"]
                for record in records
                if {item["condition_label"] for item in records if item["anchor_id"] == record["anchor_id"]} == {"jumpstarter", "chatgpt"}
            }

            self.assertTrue(report.valid)
            self.assertEqual(report.calibration_examples, 16)
            self.assertEqual(len(records), 16)
            self.assertEqual(condition_counts["jumpstarter"], 9)
            self.assertEqual(condition_counts["chatgpt"], 7)
            self.assertEqual(paired_anchor_ids, {"P2", "P5", "P6", "P7", "P8", "P9"})
            self.assertIn("human_overall_1_7", records[0])
            self.assertIn("system_output", records[0])
            self.assertTrue(any(record["source_chatgpt_path"] for record in records if record["condition_label"] == "chatgpt"))
            self.assertNotIn("Columbia University", serialized)

    @requires_study_data
    def test_dry_run_judge_scores_and_validation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            calibration_path = tmp_path / "judge_calibration.jsonl"
            scores_path = tmp_path / "judge_scores.jsonl"
            build_judge_calibration_set(output_path=calibration_path, report_path=tmp_path / "calibration_build_report.json")
            run_report = run_judge(
                input_path=calibration_path,
                output_path=scores_path,
                report_path=tmp_path / "judge_run_report.json",
                live=False,
            )
            validation_report = validate_judge_calibration(
                calibration_path=calibration_path,
                scores_path=scores_path,
                report_path=tmp_path / "judge_calibration_report.json",
            )
            scores = [json.loads(line) for line in scores_path.read_text().splitlines()]

            self.assertTrue(run_report.valid)
            self.assertEqual(run_report.total_scores, 16)
            self.assertEqual(len(scores), 16)
            self.assertTrue(scores[0]["dry_run"])
            self.assertIn("plan_quality", scores[0]["score"])
            self.assertIn("tangible_result_quality", scores[0]["score"])
            self.assertIn("confidence_support", scores[0]["score"])
            self.assertIn("decomposition_quality", scores[0]["score"])
            self.assertIn("context_curation_reuse", scores[0]["score"])
            self.assertIn("workflow_progress_support", scores[0]["score"])
            self.assertIn("user_burden_reduction", scores[0]["score"])
            self.assertIn("extracted_evidence", scores[0])
            self.assertIn("tangible_outputs_found", scores[0]["extracted_evidence"])
            self.assertIn("final_actionability_summary", scores[0]["extracted_evidence"])
            self.assertEqual(scores[0]["evidence_model"], "dry_run")
            self.assertTrue(validation_report.valid)
            self.assertFalse(validation_report.passes_validation_gates)
            self.assertIsNotNone(validation_report.directional_pair_accuracy)

    @requires_study_data
    def test_paired_judge_calibration_builds_and_validates_pairwise_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            calibration_path = tmp_path / "judge_calibration.jsonl"
            paired_path = tmp_path / "paired_judge_calibration.jsonl"
            paired_scores_path = tmp_path / "paired_judge_scores.jsonl"
            build_judge_calibration_set(output_path=calibration_path, report_path=tmp_path / "calibration_build_report.json")
            paired_report = build_paired_judge_calibration(calibration_path=calibration_path, output_path=paired_path)
            run_report = run_paired_judge(
                input_path=paired_path,
                output_path=paired_scores_path,
                report_path=tmp_path / "paired_judge_run_report.json",
                live=False,
            )
            validation_report = validate_paired_judge_calibration(
                scores_path=paired_scores_path,
                report_path=tmp_path / "paired_judge_validation_report.json",
            )
            pairs = [json.loads(line) for line in paired_path.read_text().splitlines()]
            scores = [json.loads(line) for line in paired_scores_path.read_text().splitlines()]

            self.assertTrue(paired_report.valid)
            self.assertEqual(paired_report.calibration_examples, 12)
            self.assertEqual(len(pairs), 12)
            self.assertEqual(len({pair["pair_family_id"] for pair in pairs}), 6)
            self.assertEqual({pair["order_variant"] for pair in pairs}, {"study_order", "reversed_order"})
            self.assertIn("outputs", pairs[0])
            self.assertEqual({output["condition_label"] for output in pairs[0]["outputs"]}, {"jumpstarter", "chatgpt"})
            self.assertTrue(run_report.valid)
            self.assertEqual(run_report.total_scores, 12)
            self.assertEqual(len(scores), 12)
            self.assertIn("pairwise_preference", scores[0])
            self.assertIn("pointwise_scores", scores[0])
            self.assertIn("study_quality_scores", scores[0])
            self.assertIn("study_quality_preferred_condition", scores[0])
            self.assertIn("order_variant", scores[0])
            self.assertIn("evidence_extractions", scores[0])
            self.assertIn("A", scores[0]["evidence_extractions"])
            self.assertIn("B", scores[0]["evidence_extractions"])
            self.assertIsNotNone(run_report.order_consistency_accuracy)
            self.assertIsNotNone(run_report.study_quality_order_averaged_accuracy)
            self.assertTrue(validation_report.valid)
            self.assertFalse(validation_report.passes_validation_gates)
            self.assertIsNotNone(validation_report.order_consistency_accuracy)
            self.assertIsNotNone(validation_report.study_quality_order_averaged_directional_accuracy)
            self.assertIsNotNone(validation_report.study_quality_aggregate_direction_passes)

    @requires_study_data
    def test_study_judge_inputs_render_structured_jumpstarter_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_path = tmp_path / "study_judge_inputs.jsonl"
            report = build_study_judge_inputs(output_path=output_path)
            pairs = [json.loads(line) for line in output_path.read_text().splitlines()]
            jumpstarter_texts = [
                output["text"]
                for pair in pairs
                for output in pair["outputs"]
                if output["condition_label"] == "jumpstarter"
            ]
            chatgpt_texts = [
                output["text"]
                for pair in pairs
                for output in pair["outputs"]
                if output["condition_label"] == "chatgpt"
            ]

            self.assertTrue(report.valid)
            self.assertEqual(report.calibration_examples, 12)
            self.assertEqual(len({pair["pair_family_id"] for pair in pairs}), 6)
            self.assertTrue(jumpstarter_texts)
            self.assertTrue(chatgpt_texts)
            self.assertTrue(all("Structured JumpStarter workflow summary" in text for text in jumpstarter_texts))
            self.assertTrue(all("Structured ChatGPT study-session summary" in text for text in chatgpt_texts))
            self.assertTrue(any("Most Usable Outputs Created" in text for text in jumpstarter_texts))
            self.assertTrue(any("Context Curation And Reuse Notes" in text for text in chatgpt_texts))
            self.assertTrue(any("Task Decomposition Tree" in text for text in jumpstarter_texts))
            self.assertTrue(any("Global Context Elicited" in text for text in jumpstarter_texts))

    @requires_study_data
    def test_study_pointwise_judge_inputs_build_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paired_path = tmp_path / "study_judge_inputs.jsonl"
            pointwise_path = tmp_path / "study_pointwise_judge_inputs.jsonl"
            scores_path = tmp_path / "study_pointwise_judge_scores.jsonl"
            build_study_judge_inputs(output_path=paired_path)
            build_report = build_study_pointwise_judge_inputs(
                paired_inputs_path=paired_path,
                output_path=pointwise_path,
            )
            run_report = run_judge(
                pointwise_path,
                output_path=scores_path,
                report_path=tmp_path / "study_pointwise_judge_run_report.json",
                live=False,
            )
            validation_report = validate_study_pointwise_judge_calibration(
                calibration_path=pointwise_path,
                scores_path=scores_path,
                report_path=tmp_path / "study_pointwise_judge_validation_report.json",
            )
            examples = [json.loads(line) for line in pointwise_path.read_text().splitlines()]
            scores = [json.loads(line) for line in scores_path.read_text().splitlines()]

            self.assertTrue(build_report.valid)
            self.assertEqual(build_report.calibration_examples, 12)
            self.assertEqual(len(examples), 12)
            self.assertEqual(len({example["anchor_id"] for example in examples}), 6)
            self.assertEqual({example["condition_label"] for example in examples}, {"jumpstarter", "chatgpt"})
            self.assertTrue(run_report.valid)
            self.assertEqual(run_report.total_scores, 12)
            self.assertIn("study_quality_score", scores[0])
            self.assertIn("extracted_evidence", scores[0])
            self.assertTrue(validation_report.valid)
            self.assertIsNotNone(validation_report.study_quality_directional_accuracy)
            self.assertIsNotNone(validation_report.study_quality_aggregate_direction_passes)


class FailureAnalysisTests(unittest.TestCase):
    def test_pairs_runs_by_profile_and_counts_exact_ties(self) -> None:
        from benchmark.failure_analysis import analyze_failure_cases

        # Shallow - single-turn deltas: +0.5 (win), 0.0 (tie), -0.25 (loss).
        scores = {
            "flat_decomposition": [4.5, 4.0, 3.75],
            "full_jumpstarter": [4.0, 4.0, 4.0],
            "single_turn_decomposition": [4.0, 4.0, 4.0],
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            main_run, single_turn_run = tmp_path / "main", tmp_path / "single_turn"
            _write_failure_analysis_run(main_run, {c: scores[c] for c in ("flat_decomposition", "full_jumpstarter")})
            _write_failure_analysis_run(single_turn_run, {"single_turn_decomposition": scores["single_turn_decomposition"]})
            benchmark_path = tmp_path / "benchmark.json"
            benchmark_path.write_text(json.dumps([
                {"goal_id": f"G{i}", "goal_text": f"Goal {i}", "complexity": complexity, "time_horizon": horizon, "domain": "career_education"}
                for i, (complexity, horizon) in enumerate([("medium", "2 to 6 weeks"), ("high", "3 to 6 months"), ("multi-track", "multi-month")])
            ]))
            personas_path = tmp_path / "personas.json"
            personas_path.write_text(json.dumps([{"persona_id": "P2_base", "context_richness": "medium"}]))

            report = analyze_failure_cases(
                main_run_dir=main_run,
                single_turn_run_dir=single_turn_run,
                benchmark_path=benchmark_path,
                personas_path=personas_path,
                output_dir=tmp_path / "reports",
            )

            summary = report["shallow_vs_single_turn"]
            self.assertEqual((summary["wins"], summary["ties"], summary["losses"]), (1, 1, 1))
            self.assertEqual(report["breakdowns"]["complexity"]["simple"]["wins"], 1)
            self.assertEqual(report["dimensions_shallow_vs_single_turn"]["loss_profiles"]["overall"]["n"], 1)
            self.assertEqual([case["goal_id"] for case in report["largest_losses"]], ["G2"])
            self.assertTrue((tmp_path / "reports" / "failure_analysis.md").exists())


class PaperTablesTests(unittest.TestCase):
    def test_table2_pairs_every_condition_against_shallow_across_runs(self) -> None:
        from benchmark.paper_tables import TABLE2_COMPARATORS, build_paper_tables

        # Shallow scores 4.5 / 4.0 / 3.75 on three profiles; every other condition scores 4.0.
        shallow = [4.5, 4.0, 3.75]
        runs = {"main": {"flat_decomposition": shallow}, "single_turn": {}, "agent": {"full_jumpstarter": [4.0] * 3}}
        for condition, run in TABLE2_COMPARATORS:
            runs[run][condition] = [4.0] * 3
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for run, scores in runs.items():
                _write_failure_analysis_run(tmp_path / run, scores)
                summaries = [
                    {"condition": condition, "selected_context_token_count": {"mean": 1.0}, "component_trace_metrics": {}}
                    for condition in scores
                ]
                (tmp_path / run / "score_summary.json").write_text(json.dumps({"condition_summaries": summaries}))
            benchmark_path = tmp_path / "benchmark.json"
            benchmark_path.write_text(json.dumps([
                {"goal_id": f"G{i}", "goal_text": f"Goal {i}", "complexity": complexity, "time_horizon": "multi-month", "domain": "career_education"}
                for i, complexity in enumerate(["medium", "high", "multi-track"])
            ]))

            report = build_paper_tables(
                main_run_dir=tmp_path / "main",
                single_turn_run_dir=tmp_path / "single_turn",
                agent_run_dir=tmp_path / "agent",
                benchmark_path=benchmark_path,
                output_dir=tmp_path / "reports",
            )

            self.assertEqual(len(report["table2"]), len(TABLE2_COMPARATORS) + 1)
            agent_row = report["table2"][-1]
            self.assertEqual((agent_row["condition"], agent_row["run"]), ("react_integrated_planner", "agent"))
            comparison = agent_row["shallow_minus_condition"]
            self.assertEqual((comparison["wins"], comparison["ties"], comparison["losses"]), (1, 1, 1))
            self.assertAlmostEqual(comparison["mean_delta"], 0.0833)
            self.assertTrue((tmp_path / "reports" / "paper_tables_table2.tex").exists())


def _write_failure_analysis_run(run_dir: Path, scores_by_condition: dict[str, list[float]]) -> None:
    run_dir.mkdir(parents=True)
    keys, scores = [], []
    for condition, values in scores_by_condition.items():
        for goal_index, value in enumerate(values):
            blind_id = f"B{len(keys):05d}"
            keys.append({
                "blind_id": blind_id,
                "condition": condition,
                "simulation_profile_id": f"P2_base_G{goal_index}",
                "persona_id": "P2_base",
                "goal_id": f"G{goal_index}",
            })
            subscore = 5 if value > 4.0 else 3 if value < 4.0 else 4
            scores.append({
                "blind_id": blind_id,
                "study_quality_score": value,
                "score": {"overall": {"score": subscore, "evidence": ""}},
                "output_words": 100,
            })
    (run_dir / "condition_key.jsonl").write_text("".join(json.dumps(row) + "\n" for row in keys))
    (run_dir / "judge_scores.jsonl").write_text("".join(json.dumps(row) + "\n" for row in scores))


def _build_scored_workflow_experiment(tmp_path: Path) -> Path:
    run_dir = tmp_path / "experiment_run"
    run_workflow_experiment(
        profiles_path=Path("benchmark/data/simulation_profiles.json"),
        output_dir=run_dir,
        conditions=["full_jumpstarter", "chatgpt_vanilla"],
        limit=2,
        runs_per_profile=1,
        seed=42,
    )
    run_judge(
        run_dir / "judge_inputs_blinded.jsonl",
        output_path=run_dir / "judge_scores.jsonl",
        report_path=run_dir / "judge_run_report.json",
        live=False,
    )
    return run_dir


if __name__ == "__main__":
    unittest.main()
