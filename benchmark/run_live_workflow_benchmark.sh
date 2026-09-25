#!/usr/bin/env bash
set -euo pipefail

CONDITION_SET="${CONDITION_SET:-primary}"
if [[ -n "${CONDITIONS:-}" ]]; then
  CONDITION_SET="custom"
else
  case "$CONDITION_SET" in
    primary)
      CONDITIONS="full_jumpstarter,all_context,random_selection,no_selection,chatgpt_with_elicited_context,chatgpt_with_structured_summary,chatgpt_vanilla"
      ;;
    component|component_ablation|ablations)
      CONDITION_SET="component_ablation"
      CONDITIONS="full_jumpstarter,all_context,random_selection,no_selection,no_elicitation,flat_decomposition,no_reuse"
      ;;
    agent|agent_baselines|planning_memory|planning_memory_agents)
      CONDITION_SET="agent_baselines"
      CONDITIONS="full_jumpstarter,adapt_recursive_decomposition,ask_before_plan,unstructured_memory_rag,long_context_planner"
      ;;
    all)
      CONDITIONS="full_jumpstarter,all_context,random_selection,no_selection,chatgpt_with_elicited_context,chatgpt_with_structured_summary,chatgpt_vanilla,no_elicitation,flat_decomposition,no_reuse,adapt_recursive_decomposition,ask_before_plan,unstructured_memory_rag,long_context_planner"
      ;;
    *)
      echo "Unknown CONDITION_SET=$CONDITION_SET. Use primary, component_ablation, agent_baselines, all, or set CONDITIONS directly." >&2
      exit 1
      ;;
  esac
fi
LIMIT="${LIMIT:-10}"
RUNS_PER_PROFILE="${RUNS_PER_PROFILE:-1}"
SEED="${SEED:-42}"
LIVE_STAGES="${LIVE_STAGES:-all}"
WORKFLOW_MODEL="${WORKFLOW_MODEL:-gpt-4o}"
SIMULATED_USER_MODEL="${SIMULATED_USER_MODEL:-gpt-4o}"
JUDGE_MODEL="${JUDGE_MODEL:-gpt-5.5}"
RUN_CONTEXT_RELEVANCE_LABELER="${RUN_CONTEXT_RELEVANCE_LABELER:-0}"
CONTEXT_RELEVANCE_MODEL="${CONTEXT_RELEVANCE_MODEL:-gpt-5.4-mini}"
CONTEXT_RELEVANCE_MAX_WORKERS="${CONTEXT_RELEVANCE_MAX_WORKERS:-4}"
MAX_WORKERS="${MAX_WORKERS:-6}"
JUDGE_MAX_WORKERS="${JUDGE_MAX_WORKERS:-4}"
BENCHMARK_OPENAI_TIMEOUT_SECONDS="${BENCHMARK_OPENAI_TIMEOUT_SECONDS:-120}"
BENCHMARK_OPENAI_SDK_MAX_RETRIES="${BENCHMARK_OPENAI_SDK_MAX_RETRIES:-0}"
BENCHMARK_OPENAI_RETRY_ATTEMPTS="${BENCHMARK_OPENAI_RETRY_ATTEMPTS:-3}"
BENCHMARK_OPENAI_RETRY_INITIAL_SLEEP_SECONDS="${BENCHMARK_OPENAI_RETRY_INITIAL_SLEEP_SECONDS:-2}"
BENCHMARK_OPENAI_RETRY_MAX_SLEEP_SECONDS="${BENCHMARK_OPENAI_RETRY_MAX_SLEEP_SECONDS:-30}"
export BENCHMARK_OPENAI_TIMEOUT_SECONDS
export BENCHMARK_OPENAI_SDK_MAX_RETRIES
export BENCHMARK_OPENAI_RETRY_ATTEMPTS
export BENCHMARK_OPENAI_RETRY_INITIAL_SLEEP_SECONDS
export BENCHMARK_OPENAI_RETRY_MAX_SLEEP_SECONDS
BASELINE="${BASELINE:-full_jumpstarter}"
PROFILE_SET="${PROFILE_SET:-full}"
VALIDATION_SIZE="${VALIDATION_SIZE:-10}"
TEST_300_SIZE="${TEST_300_SIZE:-300}"
BUILD_PROFILE_SPLIT="${BUILD_PROFILE_SPLIT:-1}"
FULL_PROFILES="${FULL_PROFILES:-benchmark/data/simulation_profiles.json}"
VALIDATION_PROFILES="${VALIDATION_PROFILES:-benchmark/data/simulation_profiles_validation_limit10.json}"
TEST_PROFILES="${TEST_PROFILES:-benchmark/data/simulation_profiles_test_excluding_validation.json}"
TEST_300_PROFILES="${TEST_300_PROFILES:-benchmark/data/simulation_profiles_test_300.json}"
PROFILE_SPLIT_METADATA="${PROFILE_SPLIT_METADATA:-benchmark/data/simulation_profile_split.json}"
PROFILE_SPLIT_REPORT="${PROFILE_SPLIT_REPORT:-benchmark/reports/simulation_profile_split_report.json}"

if [[ -n "${PROFILES:-}" && "$PROFILE_SET" == "full" ]]; then
  PROFILE_SET="custom"
fi

case "$PROFILE_SET" in
  full)
    PROFILES="${PROFILES:-$FULL_PROFILES}"
    ;;
  validation|val)
    PROFILE_SET="validation"
    PROFILES="${PROFILES:-$VALIDATION_PROFILES}"
    ;;
  test|heldout|held-out)
    PROFILE_SET="test"
    PROFILES="${PROFILES:-$TEST_PROFILES}"
    ;;
  test-300|test300|heldout-300|held-out-300)
    PROFILE_SET="test-300"
    PROFILES="${PROFILES:-$TEST_300_PROFILES}"
    ;;
  custom)
    if [[ -z "${PROFILES:-}" ]]; then
      echo "PROFILE_SET=custom requires PROFILES=/path/to/profiles.json" >&2
      exit 1
    fi
    ;;
  *)
    echo "Unknown PROFILE_SET=$PROFILE_SET. Use full, validation, test, test-300, or custom." >&2
    exit 1
    ;;
esac

if [[ "$PROFILE_SET" != "full" && "$PROFILE_SET" != "custom" ]]; then
  if [[ "$BUILD_PROFILE_SPLIT" == "1" || ! -f "$PROFILES" ]]; then
    python -m benchmark.cli build-simulation-profile-splits \
      --profiles "$FULL_PROFILES" \
      --validation-size "$VALIDATION_SIZE" \
      --validation-output "$VALIDATION_PROFILES" \
      --test-output "$TEST_PROFILES" \
      --test-300-size "$TEST_300_SIZE" \
      --test-300-output "$TEST_300_PROFILES" \
      --metadata-output "$PROFILE_SPLIT_METADATA" \
      --report "$PROFILE_SPLIT_REPORT"
  fi
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${RUN_DIR:-benchmark/runs/workflow_experiment_${PROFILE_SET}_${CONDITION_SET}_live_${LIVE_STAGES}_limit${LIMIT}_${TIMESTAMP}}"

mkdir -p "$RUN_DIR"

echo "Starting live workflow benchmark"
echo "RUN_DIR=$RUN_DIR"
echo "PROFILE_SET=$PROFILE_SET"
echo "PROFILES=$PROFILES"
echo "CONDITION_SET=$CONDITION_SET"
echo "CONDITIONS=$CONDITIONS"
echo "LIMIT=$LIMIT"
echo "RUNS_PER_PROFILE=$RUNS_PER_PROFILE"
echo "SEED=$SEED"
echo "VALIDATION_SIZE=$VALIDATION_SIZE"
echo "TEST_300_SIZE=$TEST_300_SIZE"
echo "LIVE_STAGES=$LIVE_STAGES"
echo "WORKFLOW_MODEL=$WORKFLOW_MODEL"
echo "SIMULATED_USER_MODEL=$SIMULATED_USER_MODEL"
echo "JUDGE_MODEL=$JUDGE_MODEL"
echo "RUN_CONTEXT_RELEVANCE_LABELER=$RUN_CONTEXT_RELEVANCE_LABELER"
echo "CONTEXT_RELEVANCE_MODEL=$CONTEXT_RELEVANCE_MODEL"
echo "CONTEXT_RELEVANCE_MAX_WORKERS=$CONTEXT_RELEVANCE_MAX_WORKERS"
echo "MAX_WORKERS=$MAX_WORKERS"
echo "JUDGE_MAX_WORKERS=$JUDGE_MAX_WORKERS"
echo "BENCHMARK_OPENAI_TIMEOUT_SECONDS=$BENCHMARK_OPENAI_TIMEOUT_SECONDS"
echo "BENCHMARK_OPENAI_SDK_MAX_RETRIES=$BENCHMARK_OPENAI_SDK_MAX_RETRIES"
echo "BENCHMARK_OPENAI_RETRY_ATTEMPTS=$BENCHMARK_OPENAI_RETRY_ATTEMPTS"
echo "BENCHMARK_OPENAI_RETRY_INITIAL_SLEEP_SECONDS=$BENCHMARK_OPENAI_RETRY_INITIAL_SLEEP_SECONDS"
echo "BENCHMARK_OPENAI_RETRY_MAX_SLEEP_SECONDS=$BENCHMARK_OPENAI_RETRY_MAX_SLEEP_SECONDS"
echo

BENCHMARK_PROGRESS=1 python -m benchmark.cli run-workflow-experiment \
  --profiles "$PROFILES" \
  --conditions "$CONDITIONS" \
  --limit "$LIMIT" \
  --runs-per-profile "$RUNS_PER_PROFILE" \
  --live-stages "$LIVE_STAGES" \
  --workflow-model "$WORKFLOW_MODEL" \
  --live-simulated-user \
  --simulated-user-model "$SIMULATED_USER_MODEL" \
  --max-workers "$MAX_WORKERS" \
  --seed "$SEED" \
  --output-dir "$RUN_DIR"

echo
echo "Workflow experiment complete. Starting live judge."
echo

BENCHMARK_PROGRESS=1 python -m benchmark.cli run-judge \
  "$RUN_DIR/judge_inputs_blinded.jsonl" \
  --live \
  --model "$JUDGE_MODEL" \
  --max-workers "$JUDGE_MAX_WORKERS" \
  --output "$RUN_DIR/judge_scores.jsonl" \
  --report "$RUN_DIR/judge_run_report.json"

echo
echo "Judge complete. Analyzing scores."
echo

if [[ "$RUN_CONTEXT_RELEVANCE_LABELER" == "1" ]]; then
  echo "Starting GPT context relevance labeler."
  echo
  BENCHMARK_PROGRESS=1 python -m benchmark.cli run-context-relevance-labeler \
    "$RUN_DIR" \
    --model "$CONTEXT_RELEVANCE_MODEL" \
    --max-workers "$CONTEXT_RELEVANCE_MAX_WORKERS"
  echo
  echo "Context relevance labeler complete."
  echo
fi

python -m benchmark.cli analyze-workflow-experiment \
  "$RUN_DIR" \
  --baseline "$BASELINE"

echo
echo "Done."
echo "Score summary:"
echo "$RUN_DIR/score_summary.md"
