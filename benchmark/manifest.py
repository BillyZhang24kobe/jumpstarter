from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schemas import Domain


REPO_ROOT = Path(__file__).resolve().parents[1]
STUDY_DOCS_DIR = "userstudy_data"


def study_docx_path(participant_number: int, first_condition: str) -> str:
    """Relative path of a participant's study document, found by participant number and condition order.

    The documents are named "<number> - <first name> - first <condition>.docx"; looking them up by pattern
    keeps participant names out of the code. The documents are not part of the public release, where the
    unresolved pattern is returned.
    """
    pattern = f"{participant_number} - * - first {first_condition}.docx"
    matches = sorted((REPO_ROOT / STUDY_DOCS_DIR).glob(pattern))
    return f"{STUDY_DOCS_DIR}/{matches[0].name if len(matches) == 1 else pattern}"


@dataclass(frozen=True)
class AnchorSpec:
    anchor_id: str
    participant_id: str | None
    anchor_type: str
    first_condition: str | None
    goal: str
    domain: Domain
    docx_path: str | None
    stats_row_id: int | None
    jumpstarter_log_file: str | None
    jumpstarter_log_line: int | None
    usable_for_trace_replay: bool
    human_rated: bool


ANCHOR_SPECS: list[AnchorSpec] = [
    AnchorSpec("P1", "P1", "ignored_unusable", "ChatGPT", "Start a side job", "career_education", study_docx_path(1, "ChatGPT"), 1, None, None, False, True),
    AnchorSpec("P2", "P2", "human_study_trace", "JumpStarter", "Organize a weekly PhD game night", "events_coordination", study_docx_path(2, "JumpStarter"), 2, "userstudy.log", 1348, True, True),
    AnchorSpec("P3", "P3", "human_study_trace", "ChatGPT", "Land a job offer", "career_education", study_docx_path(3, "ChatGPT"), 3, "userstudy.log", 2611, True, True),
    AnchorSpec("P4", "P4", "human_study_trace", "JumpStarter", "Prepare for the LSAT", "career_education", study_docx_path(4, "JumpStarter"), 4, "userstudy.log", 3767, True, True),
    AnchorSpec("P5", "P5", "human_study_trace", "ChatGPT", "Run social media to attract followers", "creative_personal", study_docx_path(5, "ChatGPT"), 5, "userstudy.log", 4834, True, True),
    AnchorSpec("P6", "P6", "human_study_trace", "JumpStarter", "Sublease a Manhattan apartment and move to Queens", "everyday_admin_home", study_docx_path(6, "JumpStarter"), 6, "userstudy.log", 5746, True, True),
    AnchorSpec("P7", "P7", "human_study_trace", "ChatGPT", "Create a portfolio website for job applications", "career_education", study_docx_path(7, "ChatGPT"), 7, "userstudy2.log", 799, True, True),
    AnchorSpec("P8", "P8", "human_study_trace", "JumpStarter", "Prepare to deliver a first tutorial", "career_education", study_docx_path(8, "JumpStarter"), 8, "userstudy2.log", 2036, True, True),
    AnchorSpec("P9", "P9", "human_study_trace", "ChatGPT", "Start a personal YouTube channel", "creative_personal", study_docx_path(9, "ChatGPT"), 9, "userstudy2.log", 5231, True, True),
    AnchorSpec("P10", "P10", "human_study_trace", "JumpStarter", "Organize a family reunion", "events_coordination", study_docx_path(10, "JumpStarter"), 10, "userstudy2.log", 13278, True, True),
    AnchorSpec("A1", None, "ablation_trace", None, "Apply for NSF CSGrad4US Fellowship", "career_education", None, None, "ablation2.log", 370, True, False),
    AnchorSpec("A2", None, "ablation_trace", None, "Prepare driver license exam", "everyday_admin_home", None, None, "ablation2.log", 553, True, False),
    AnchorSpec("A3", None, "ablation_trace", None, "Organize a team outing for a 10-people group", "events_coordination", None, None, "ablation2.log", 675, True, False),
]
