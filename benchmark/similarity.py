from __future__ import annotations

import re
from difflib import SequenceMatcher


TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def token_overlap(a: str, b: str) -> float:
    a_tokens = normalize_tokens(a)
    b_tokens = normalize_tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / min(len(a_tokens), len(b_tokens))


def sequence_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def nearest_goal(goal_text: str, existing: list[tuple[str, str]]) -> tuple[str | None, float]:
    best_id: str | None = None
    best_score = 0.0
    for existing_id, existing_text in existing:
        score = max(token_overlap(goal_text, existing_text), sequence_similarity(goal_text, existing_text))
        if score > best_score:
            best_id = existing_id
            best_score = score
    return best_id, best_score
