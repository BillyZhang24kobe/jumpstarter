# JumpStarter app

The interactive web app used in the paper's user study. A Flask backend (`server.py`, `utils.py`) serves a single-page task-tree interface (`templates/`, `static/`).

## Run

From the repository root:

```bash
export OPENAI_API_KEY="<your-openai-api-key>"
python app/server.py
```

Open http://127.0.0.1:55113 and log in with any username and password. A new username creates an account; accounts, task trees, and saved drafts are stored as JSON files in `app/database/`, in plain text, so don't reuse a real password. Uploaded context files go to `app/uploads/`. To serve other machines, set `JUMPSTARTER_HOST=0.0.0.0`. The Flask debugger stays on, so only do this on a trusted network.

Every route calls `gpt-4o`. To use another OpenAI chat model, set `JUMPSTARTER_MODEL` to its name before starting the server. The version used in the user study called `gpt-4-turbo` and `gpt-4`.

## Routes and the paper's mechanisms

The prompt text files in [`../benchmark/prompts/paper_workflow_v1/`](../benchmark/prompts/paper_workflow_v1/) are the prompts from the paper's appendix figures. The simulation benchmark uses them to replay this workflow.

| Mechanism | Route (`server.py`) | Prompt |
| --- | --- | --- |
| Global context elicitation for the goal | `/elicit_context_root` | `Figure10_context_elicitation_for_global_input.txt` |
| Subtask generation (task decomposition) | `/get_started_all`, with the prompt `prompt_steps_start` in `static/task.js` | `Figure13_subtask_generation.txt` |
| Subtask detection: decompose further or draft | `/detect_subtasks` | `Figure14_subtask_detection.txt` |
| Task forking: split a task by entity | `/fork_detection`, `/context_curation_breakdown`, `/get_fork_steps` | `Figure15_task_forking.txt`, `E22_task_forking_context_selection.txt` |
| Local context elicitation before drafting | `/context_elicitation_draft` | `Figure11_context_elicitation_for_answer_draft_creation.txt` |
| Context selection for a subtask draft | `/context_curation_draft` | `Figure12_context_selection_for_answer_draft_creation.txt` |
| Working-solution draft for a subtask | `/get_started`, with the prompt `prompt_need_help` in `static/task.js` | `E4_working_solution_draft_creation.txt` |
| Saving drafts and files as reusable context | `/submit_draft_and_upload_files`, `/submit_file`, `/uploadUserContextFile` | — |
| Refining a draft; side chat | `/synthesize`, `/regenerate`, `/chatresponse` | — |
| Task-tree persistence | `/task`, `/task_continue`, `/save_task`, `/get_tasks` | — |

`/get_general_steps`, `/get_emotional_support`, `/get_detailed_steps`, and `/request_context_info` are general helpers from an earlier prototype (step lists, timelines, encouragement, recommendation-letter details). They are not part of the context-curation workflow described in the paper.
