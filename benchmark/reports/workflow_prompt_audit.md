# Workflow Prompt Audit

Date: 2026-05-04

Scope: compare the current repo prompts and `benchmark/workflow_simulator.py` against the prompts exposed in `2410.03882v4.pdf` / arXiv v4.

## Bottom Line

The current benchmark `workflow_simulator.py` is deterministic and does not call LLM prompts yet. Therefore, it is not currently using the exact paper prompts. It models the workflow stages, but not the prompt-level behavior.

The original Flask app contains many prompts that closely match the paper, but not all are exact. Some paper prompts are embedded in figure images, so exact character-level matching requires a canonical text source.

## Prompt Status

| Workflow component | Paper appendix / figure | Current repo source | Status |
| --- | --- | --- | --- |
| Goal/global context elicitation | E.1.1 / Figure 10 | `server.py::elicit_context_root` | Close match / likely exact, but should still be canonicalized from source text. |
| Local context elicitation for answer draft iteration | E.1.2 / Figure 11 | `server.py::context_elicitation_draft` | Not exact. The paper prompt includes a readiness judgment; the active server prompt omits that and always asks for extra info. The paper-like prompt exists only as a commented-out block. |
| Context selection for answer drafting | E.2.1 / Figure 12 | `server.py::context_curation_draft` | Not exact. The server prompt adds stricter one-key-per-line parsing instructions beyond the paper figure. |
| Context selection for forking | E.2.2 | `server.py::context_curation_fork` | Not exact. The paper format is `<context_key>: <reasons>`; the server prompt currently formats the key and reason on separated lines. |
| Subtask generation | E.3 / Figure 13 | `static/task.js`, `server.py::get_started_all` | Close but not guaranteed exact. The prompt is split between frontend constants and server-side system/context augmentation. |
| Subtask detection | E.3 / Figure 14 | `server.py::detect_subtasks` | Not exact. The paper figure includes tree-level information in the instruction and user prompt; the current route accepts only node title and description. |
| Task forking detection | E.3 / Figure 15 | `server.py::fork_detection` | Close match / likely exact. |
| Working solution draft generation | E.4 | `static/task.js`, `server.py::get_started_all` | Close conceptually, but assembled dynamically and not stored as a single canonical paper prompt. |
| Technical-evaluation subtask detection prompts | E.5 / Figures 16-19 | Not used in workflow simulator | Not relevant to the UI workflow unless reproducing the technical prompt ablation. Exact figure text for Figures 18-19 is too long/small to safely transcribe from rendered PDF alone. |

## Prompt Text I Need From You

Please paste canonical text for these prompts before we claim exact prompt parity in the simulator:

1. Figure 11: Context Elicitation for Answer Draft Creation.
2. Figure 12: Context Selection for Answer Draft Creation.
3. Figure 13: Subtask Generation.
4. Figure 14: Subtask Detection.
5. Figure 15: Task Forking.
6. E.4 Working Solution Draft Creation, if the paper text is not the complete prompt used in the deployed system.

Optional, only if we reproduce the technical prompt ablation:

7. Figure 18: Few-shot + CoT + Draft for Subtask Detection.
8. Figure 19: Few-shot + CoT + Tree + Draft for Subtask Detection.

## Recommended Next Patch

After receiving canonical prompt text:

1. Add `benchmark/prompts/paper_workflow_v1/` with one prompt file per workflow component.
2. Add a small prompt registry module that loads these files by stable IDs.
3. Update `workflow_simulator.py` live mode to record the exact prompt ID, prompt version, system prompt, user prompt, model ID, and output for each LLM-backed stage.
4. Keep deterministic mode as the no-network test fixture path.
