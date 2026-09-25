from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .openai_generation import refine_personas_live
from .pipeline import DEFAULT_DATA_DIR, DEFAULT_REPORTS_DIR, build_anchor_sessions, read_anchor_sessions
from .schemas import AnchorSession, Persona, PersonaExtractionReport


DEFAULT_PERSONAS_PATH = DEFAULT_DATA_DIR / "personas.json"
DEFAULT_PERSONA_REPORT_PATH = DEFAULT_REPORTS_DIR / "persona_extraction_report.json"
BASE_PERSONA_IDS = [f"P{index}" for index in range(2, 11)]
FAKE_UNIVERSITY_NAME = "Cedarwick Hollow University"

VARIANT_SPECS = [
    ("P2", "context_richness", "low", "low-context variant that answers with fewer specifics unless asked"),
    ("P3", "context_richness", "high", "high-context variant that provides richer constraints when prompted"),
    ("P4", "decision_style", "deferential", "deferential variant that asks the system to choose among options"),
    ("P5", "decision_style", "opinionated", "opinionated variant that pushes back on mismatched suggestions"),
    ("P6", "communication_style", "terse", "terse variant that answers in short fragments"),
    ("P7", "communication_style", "verbose", "verbose variant that explains reasoning and preferences"),
    ("P8", "expertise_level", "novice", "novice variant with more uncertainty about task process"),
    ("P9", "expertise_level", "intermediate", "intermediate variant with some prior creative planning knowledge"),
    ("P10", "context_richness", "medium", "medium-context variant that gives enough detail but not exhaustive background"),
    ("P2", "decision_style", "collaborative", "collaborative variant that co-develops plans with the system"),
    ("P6", "communication_style", "balanced", "balanced variant with concise but complete responses"),
]


def build_personas(
    anchors_path: Path = DEFAULT_DATA_DIR / "anchor_sessions.jsonl",
    output_path: Path = DEFAULT_PERSONAS_PATH,
    report_path: Path = DEFAULT_PERSONA_REPORT_PATH,
    live: bool = False,
    model: str | None = None,
) -> PersonaExtractionReport:
    anchors = read_anchor_sessions(anchors_path) if anchors_path.exists() else build_anchor_sessions()
    base_personas = build_base_personas(anchors)
    if live:
        base_personas = refine_personas_live(base_personas, model=model)
    personas = base_personas + build_controlled_variants(base_personas)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps([persona.model_dump() for persona in personas], indent=2))
    report = validate_personas(personas)
    report_path.write_text(report.model_dump_json(indent=2))
    if not report.valid:
        raise RuntimeError(f"Persona extraction validation failed: {report.errors}")
    return report


def build_base_personas(anchors: list[AnchorSession]) -> list[Persona]:
    anchors_by_id = {anchor.anchor_id: anchor for anchor in anchors}
    personas: list[Persona] = []
    for anchor_id in BASE_PERSONA_IDS:
        anchor = anchors_by_id.get(anchor_id)
        if anchor is None:
            raise ValueError(f"Missing anchor session for {anchor_id}")
        personas.append(_base_persona_from_anchor(anchor))
    return personas


def build_controlled_variants(base_personas: list[Persona]) -> list[Persona]:
    by_source = {persona.source_participant: persona for persona in base_personas}
    variants: list[Persona] = []
    for source_participant, axis, value, description in VARIANT_SPECS:
        base = by_source[source_participant]
        update: dict[str, Any] = {
            "persona_id": f"{source_participant}_variant_{axis}_{value}",
            "persona_type": "controlled_variant",
            "variant_axis": axis,
            "variant_description": description,
            "evidence_quotes": base.evidence_quotes[:2],
            "extraction_warnings": base.extraction_warnings + [f"Controlled variant modifies {axis} from base persona"],
        }
        update[axis] = value
        variants.append(base.model_copy(update=update))
    return variants


def validate_personas(personas: list[Persona]) -> PersonaExtractionReport:
    errors: list[str] = []
    warnings: list[str] = []
    base = [persona for persona in personas if persona.persona_type == "base"]
    variants = [persona for persona in personas if persona.persona_type == "controlled_variant"]
    source_participants = sorted({persona.source_participant for persona in base})

    if len(base) != 9:
        errors.append(f"Expected 9 base personas, found {len(base)}")
    if len(variants) != 11:
        errors.append(f"Expected 11 controlled variants, found {len(variants)}")
    expected_sources = set(BASE_PERSONA_IDS)
    if set(source_participants) != expected_sources:
        errors.append(f"Expected base sources {sorted(expected_sources)}, found {source_participants}")
    if len({persona.persona_id for persona in personas}) != len(personas):
        errors.append("Persona IDs must be unique")
    for persona in personas:
        if not persona.evidence_quotes:
            errors.append(f"{persona.persona_id} has no evidence quotes")
        if not persona.constraints_to_remember:
            warnings.append(f"{persona.persona_id} has no constraints_to_remember")
        if persona.persona_type == "controlled_variant" and not persona.variant_axis:
            errors.append(f"{persona.persona_id} is a variant without variant_axis")

    return PersonaExtractionReport(
        valid=not errors,
        total_personas=len(personas),
        base_personas=len(base),
        controlled_variants=len(variants),
        source_participants=source_participants,
        errors=errors,
        warnings=warnings,
    )


def validate_personas_file(path: Path) -> PersonaExtractionReport:
    payload = json.loads(path.read_text())
    personas = [Persona.model_validate(item) for item in payload]
    return validate_personas(personas)


def _base_persona_from_anchor(anchor: AnchorSession) -> Persona:
    warnings: list[str] = []
    background = anchor.background or ""
    user_context = _clean_user_context(anchor.user_context or {})
    global_context = _clean_global_context(anchor.user_global_context or {})

    evidence_quotes = _evidence_quotes(anchor)
    if not evidence_quotes:
        warnings.append("No direct evidence quotes extracted")
        evidence_quotes = [anchor.goal]

    return Persona(
        persona_id=f"{anchor.anchor_id}_base",
        persona_type="base",
        source_participant=anchor.anchor_id,
        source_anchor_id=anchor.anchor_id,
        goal=anchor.goal,
        user_description=_build_user_description(anchor),
        goal_domain_preferences=[anchor.domain],
        expertise_level=_infer_expertise(_anchor_text(anchor)),
        context_richness=_infer_context_richness(user_context, global_context),
        decision_style=_infer_decision_style(user_context, global_context),
        communication_style=_infer_communication_style(user_context, global_context),
        task_objectives=_infer_task_objectives(anchor),
        known_facts=_infer_known_facts(anchor),
        preferences=_infer_preferences(anchor),
        gaps_in_self_knowledge=_infer_gaps(anchor),
        constraints_to_remember=_infer_constraints(anchor),
        information_disclosure_policy=_infer_disclosure_policy(anchor),
        response_style_rules=_infer_response_style_rules(anchor),
        success_criteria=_infer_success_criteria(anchor),
        pushback_triggers=_infer_pushback_triggers(anchor),
        evidence_quotes=evidence_quotes,
        extraction_warnings=warnings + anchor.parse_warnings[:3],
    )


def _infer_expertise(background: str) -> str:
    lowered = background.lower()
    if any(phrase in lowered for phrase in ["never", "rarely", "first", "not familiar", "no experience", "current preparation level: none"]):
        return "novice"
    if any(phrase in lowered for phrase in ["strong idea", "rough idea", "basic logic", "some experience", "looked at"]):
        return "intermediate"
    return "intermediate"


def _infer_context_richness(*contexts: dict[str, Any]) -> str:
    values = [str(value) for context in contexts for value in context.values() if str(value).strip()]
    total_words = sum(len(_words(value)) for value in values)
    if len(values) >= 5 or total_words >= 180:
        return "high"
    if len(values) >= 2 or total_words >= 50:
        return "medium"
    return "low"


def _infer_decision_style(user_context: dict[str, Any], saved_drafts: dict[str, str]) -> str:
    text = " ".join(str(value) for value in list(user_context.values()) + list(saved_drafts.values())).lower()
    if any(marker in text for marker in ["i think", "not sure", "maybe", "could"]):
        return "collaborative"
    if len(saved_drafts) >= 4:
        return "opinionated"
    return "collaborative"


def _infer_communication_style(user_context: dict[str, Any], saved_drafts: dict[str, str]) -> str:
    values = [str(value) for value in list(user_context.values()) + list(saved_drafts.values()) if str(value).strip()]
    if not values:
        return "terse"
    avg_words = sum(len(_words(value)) for value in values) / len(values)
    if avg_words < 12:
        return "terse"
    if avg_words > 70:
        return "verbose"
    return "balanced"


def _infer_gaps(anchor: AnchorSession) -> list[str]:
    gaps: list[str] = []
    text = _anchor_text(anchor).lower()
    if "not sure" in text or "undecided" in text:
        gaps.append("has unresolved preferences or constraints")
    if "never" in (anchor.background or "").lower() or "first" in anchor.goal.lower():
        gaps.append("may not know the standard process for this goal")
    if not anchor.user_context and not anchor.user_global_context:
        gaps.append("may need elicitation before concrete planning")
    if not gaps:
        gaps.append("may need help prioritizing among plausible next steps")
    return gaps[:3]


def _build_user_description(anchor: AnchorSession) -> str:
    facts = _infer_known_facts(anchor)
    constraints = _infer_constraints(anchor)
    expertise = _infer_expertise(_anchor_text(anchor))
    pieces = [f"{_article_for(expertise).capitalize()} {expertise} user working on: {anchor.goal}."]
    if facts:
        pieces.append("Known context: " + "; ".join(facts[:3]) + ".")
    if constraints:
        pieces.append("Important constraints: " + "; ".join(constraints[:2]) + ".")
    pieces.append("They need a planning assistant to ask for missing details and turn the goal into concrete next steps.")
    return _shorten(" ".join(pieces), limit=650)


def _article_for(word: str) -> str:
    return "an" if word[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def _infer_task_objectives(anchor: AnchorSession) -> list[str]:
    goal = anchor.goal.lower()
    if "lsat" in goal or "exam" in goal or "bar" in goal or "gre" in goal:
        return [
            "choose a realistic preparation timeline",
            "identify missing baseline information",
            "turn study preparation into weekly actions",
        ]
    if "job" in goal or "offer" in goal or "portfolio" in goal:
        return [
            "clarify target opportunities",
            "organize application or outreach materials",
            "produce concrete next actions and tracking artifacts",
        ]
    if "reunion" in goal or "outing" in goal or "picnic" in goal or "game night" in goal:
        return [
            "coordinate people, time, and location constraints",
            "create a feasible event plan",
            "draft communication or logistics artifacts",
        ]
    if "youtube" in goal or "social media" in goal or "website" in goal:
        return [
            "clarify audience and positioning",
            "break the creative project into launch tasks",
            "produce reusable planning artifacts",
        ]
    if "move" in goal or "apartment" in goal or "sublease" in goal:
        return [
            "organize deadlines and logistics",
            "track documents, messages, and decisions",
            "produce a practical moving or admin checklist",
        ]
    return [
        "clarify the user's current state",
        "identify missing constraints",
        "produce concrete planning artifacts",
    ]


def _infer_known_facts(anchor: AnchorSession) -> list[str]:
    facts: list[str] = []
    if anchor.background:
        facts.extend(_sanitize_text(line) for line in anchor.background.splitlines() if line.strip())
    for quote in _persona_evidence_sources(anchor):
        if ":" in quote or quote.lower().startswith("resume/cv summary"):
            facts.append(quote)
    return _dedupe_preserve_order([fact for fact in facts if fact])[:6]


def _infer_preferences(anchor: AnchorSession) -> list[str]:
    preferences: list[str] = []
    for quote in _persona_evidence_sources(anchor):
        lowered = quote.lower()
        if any(marker in lowered for marker in ["prefer", "want", "like", "interested", "target", "location", "not sure"]):
            preferences.append(quote)
    if not preferences:
        preferences.append("prefers help that is specific to their stated context")
    return _dedupe_preserve_order(preferences)[:5]


def _infer_disclosure_policy(anchor: AnchorSession) -> list[str]:
    policies = [
        "Do not volunteer unstated details; reveal known facts only when the assistant asks relevant questions.",
        "If the assistant asks about information not present in the persona, say that the user does not know yet or has not decided.",
    ]
    if _infer_context_richness(_clean_user_context(anchor.user_context or {}), _clean_global_context(anchor.user_global_context or {})) == "high":
        policies.append("When asked directly, provide concrete constraints from known_facts and constraints_to_remember.")
    else:
        policies.append("Keep answers brief and let the assistant elicit missing planning context.")
    return policies


def _infer_response_style_rules(anchor: AnchorSession) -> list[str]:
    style = _infer_communication_style(_clean_user_context(anchor.user_context or {}), _clean_global_context(anchor.user_global_context or {}))
    if style == "terse":
        return [
            "Answer in one short sentence unless asked for specifics.",
            "Avoid bullet lists unless the assistant explicitly requests a list.",
            "Use plain, direct wording.",
        ]
    if style == "verbose":
        return [
            "Give context-rich answers when asked.",
            "Explain preferences and constraints briefly.",
            "Still keep each simulator turn under 80 tokens.",
        ]
    return [
        "Answer in one to three concise sentences.",
        "Provide specifics when asked, but do not front-load every detail.",
        "Use a collaborative tone.",
    ]


def _infer_success_criteria(anchor: AnchorSession) -> list[str]:
    outputs = _expected_outputs_for_goal(anchor.goal)
    return [
        f"receives a plan that is tailored to {anchor.goal}",
        "has clear next steps rather than generic advice",
        "gets tangible artifacts such as " + ", ".join(outputs[:3]),
    ]


def _infer_pushback_triggers(anchor: AnchorSession) -> list[str]:
    triggers = [
        "push back if the assistant contradicts constraints_to_remember",
        "push back if the assistant assumes facts not in known_facts",
        "push back if the plan is generic and does not ask for missing context",
    ]
    if "exam" in anchor.goal.lower() or "lsat" in anchor.goal.lower():
        triggers.append("push back if the study timeline ignores the exam date or current preparation level")
    if "job" in anchor.goal.lower():
        triggers.append("push back if advice ignores target role, location, or existing background")
    return triggers[:4]


def _expected_outputs_for_goal(goal: str) -> list[str]:
    lowered = goal.lower()
    if "lsat" in lowered or "exam" in lowered:
        return ["study schedule", "resource checklist", "progress tracker"]
    if "job" in lowered or "offer" in lowered:
        return ["application tracker", "outreach drafts", "interview prep plan"]
    if "reunion" in lowered or "outing" in lowered or "game night" in lowered:
        return ["itinerary", "invitation draft", "logistics checklist"]
    if "website" in lowered or "youtube" in lowered or "social media" in lowered:
        return ["content plan", "launch checklist", "audience notes"]
    if "move" in lowered or "apartment" in lowered or "sublease" in lowered:
        return ["moving checklist", "message templates", "timeline"]
    return ["checklist", "timeline", "decision aid"]


def _infer_constraints(anchor: AnchorSession) -> list[str]:
    constraints: list[str] = []
    for quote in _persona_evidence_sources(anchor):
        lowered_quote = quote.lower()
        if any(prefix in lowered_quote for prefix in ["job search location:", "target industry or job type:", "resume/cv summary:"]):
            constraints.append(_shorten(_sanitize_text(quote), limit=220))
            if len(constraints) >= 5:
                return _dedupe_preserve_order(constraints)[:5]
            continue
        for sentence in _split_sentences(quote):
            lowered = sentence.lower()
            if any(marker in lowered for marker in ["deadline", "date", "budget", "location", "time", "schedule", "prefer", "not sure", "only", "need", "want"]):
                constraints.append(_shorten(_sanitize_text(sentence.strip()), limit=220))
            if len(constraints) >= 5:
                return _dedupe_preserve_order(constraints)[:5]
    if anchor.background:
        constraints.append(_shorten(anchor.background.splitlines()[0], limit=220))
    if not constraints:
        constraints.append(f"Goal context: {anchor.goal}")
    return _dedupe_preserve_order(constraints)[:5]


def _evidence_quotes(anchor: AnchorSession) -> list[str]:
    quotes = _persona_evidence_sources(anchor)
    return [_shorten(quote) for quote in quotes[:6]]


def _anchor_text(anchor: AnchorSession) -> str:
    return " ".join(_persona_evidence_sources(anchor))


def _persona_evidence_sources(anchor: AnchorSession) -> list[str]:
    quotes: list[str] = []
    if anchor.background:
        quotes.extend(_sanitize_text(line.strip()) for line in anchor.background.splitlines() if line.strip())

    for key, value in _clean_global_context(anchor.user_global_context or {}).items():
        rendered = _render_context_fact(key, value)
        if rendered:
            quotes.append(rendered)

    for key, value in _clean_user_context(anchor.user_context or {}).items():
        rendered = _render_context_fact(key, value)
        if rendered:
            quotes.append(rendered)

    return _dedupe_preserve_order([quote for quote in quotes if quote])


def _clean_global_context(context: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in context.items():
        key_text = _sanitize_text(str(key))
        value_text = _sanitize_text(str(value))
        if not value_text:
            continue
        if _looks_like_resume_key(key_text) or _looks_like_resume_text(value_text):
            summary = _summarize_resume_context(value_text)
            if summary:
                cleaned[key_text] = summary
            continue
        cleaned[key_text] = _shorten(value_text, limit=180)
    return cleaned


def _clean_user_context(context: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in context.items():
        key_text = _sanitize_text(str(key))
        value_text = _sanitize_text(str(value))
        if not value_text or _looks_like_task_artifact(key_text, value_text):
            continue
        cleaned[key_text] = _shorten(value_text, limit=180)
    return cleaned


def _render_context_fact(key: str, value: str) -> str | None:
    if not value:
        return None
    if key.lower() in {"resume or cv", "resume", "cv"}:
        return value
    if len(value.split()) <= 18:
        return f"{key}: {value}"
    return f"{key}: {_shorten(value, limit=180)}"


def _looks_like_resume_key(key: str) -> bool:
    return key.lower() in {"resume or cv", "resume", "cv"}


def _looks_like_resume_text(text: str) -> bool:
    lowered = text.lower()
    markers = ["technical skills", "education", "experience", "linkedin.com", "operating systems", "frameworks"]
    return sum(marker in lowered for marker in markers) >= 3


def _summarize_resume_context(text: str) -> str:
    lowered = text.lower()
    facts: list[str] = []
    if "computer science" in lowered:
        facts.append("computer science background")
    if "machine learning" in lowered:
        facts.append("machine learning concentration or experience")
    if "software engineer intern" in lowered or "software engineering" in lowered:
        facts.append("software engineering internship experience")
    if "researcher" in lowered or "research" in lowered:
        facts.append("research experience")
    skills = []
    for skill in ["Python", "Java", "JavaScript", "SQL", "Flask", "PyTorch", "TensorFlow"]:
        if skill.lower() in lowered:
            skills.append(skill)
    if skills:
        facts.append("technical skills include " + ", ".join(skills[:5]))
    if not facts:
        return "Uploaded resume/CV available; use only task-relevant background details"
    return "Resume/CV summary: " + "; ".join(facts)


def _looks_like_task_artifact(key: str, value: str) -> bool:
    lowered_key = key.lower()
    lowered_value = value.lower()
    if re.match(r"^\d+-\d+-\d+-\d+-", key):
        return True
    artifact_markers = [
        "###",
        "**",
        "step 1",
        "step 2",
        "gpt response",
        "linkedin 1.",
        "create/update profile",
        "update profile",
        "job description link",
        "application link",
    ]
    if any(marker in lowered_value for marker in artifact_markers):
        return True
    if len(_words(value)) > 70:
        return True
    return any(marker in lowered_key for marker in ["identify key", "set up", "compile", "reach out", "schedule and conduct"])


def _sanitize_text(text: str) -> str:
    text = text.replace("\ufeff", "")
    text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email]", text)
    text = re.sub(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", "[phone]", text)
    text = _anonymize_institution_names(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _anonymize_institution_names(text: str) -> str:
    replacements = [
        (r"\bBarnard College of Columbia University\b", FAKE_UNIVERSITY_NAME),
        (r"\bBarnard College\b", FAKE_UNIVERSITY_NAME),
        (r"\bColumbia University\b", FAKE_UNIVERSITY_NAME),
        (r"Columbia University", FAKE_UNIVERSITY_NAME),
        (r"\bColumbia\b", FAKE_UNIVERSITY_NAME),
        (r"Columbia", FAKE_UNIVERSITY_NAME),
        (r"\bNew York University\b", FAKE_UNIVERSITY_NAME),
        (r"\bNYU\b", FAKE_UNIVERSITY_NAME),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text)


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"[\n.!?]+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _shorten(text: str, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
