from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass
class ParsedDocx:
    goal: str | None = None
    background: str | None = None
    chatgpt_share_url: str | None = None
    rating_snippets: list[str] = field(default_factory=list)
    excerpt: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedLogRecord:
    task: str | None = None
    root_node: dict[str, Any] | None = None
    user_context: dict[str, Any] = field(default_factory=dict)
    user_global_context: dict[str, Any] = field(default_factory=dict)
    saved_draft_context: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def read_docx_paragraphs(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", WORD_NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", WORD_NS)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def parse_study_docx(path: Path) -> ParsedDocx:
    parsed = ParsedDocx()
    if not path.exists():
        parsed.warnings.append(f"DOCX not found: {path}")
        return parsed

    paragraphs = read_docx_paragraphs(path)
    parsed.excerpt = "\n".join(paragraphs[:30])
    raw_text = "\n".join(paragraphs)
    match = re.search(r"https://chatgpt\.com/share/[A-Za-z0-9-]+", raw_text)
    if match:
        parsed.chatgpt_share_url = match.group(0)
    else:
        parsed.warnings.append("No ChatGPT share URL found in DOCX")

    def section_after(label: str, stop_labels: tuple[str, ...]) -> list[str]:
        try:
            start = paragraphs.index(label) + 1
        except ValueError:
            return []
        end = len(paragraphs)
        for stop_label in stop_labels:
            try:
                candidate = paragraphs.index(stop_label, start)
            except ValueError:
                continue
            end = min(end, candidate)
        return paragraphs[start:end]

    goal_lines = section_after("Goal:", ("Background:", "Quality of the outputs/progress"))
    if goal_lines:
        parsed.goal = " ".join(goal_lines).strip()
    else:
        parsed.warnings.append("Goal section not found in DOCX")

    background_lines = section_after("Background:", ("Quality of the outputs/progress",))
    if background_lines:
        parsed.background = "\n".join(background_lines).strip()
    else:
        parsed.warnings.append("Background section not found in DOCX")

    if "Quality of the outputs/progress" in paragraphs:
        quality_index = paragraphs.index("Quality of the outputs/progress")
        parsed.rating_snippets = paragraphs[quality_index : quality_index + 24]
    else:
        parsed.warnings.append("Quality/rating section not found in DOCX")
    return parsed


def read_xlsx_rows(path: Path, sheet_name: str = "xl/worksheets/sheet1.xml") -> list[list[str]]:
    """Read basic XLSX cell values with stdlib XML support.

    This is intentionally small: enough for study metadata extraction without
    introducing openpyxl as a project dependency.
    """
    if not path.exists():
        return []
    with ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet = ET.fromstring(archive.read(sheet_name))

    rows: list[list[str]] = []
    for row in sheet.findall(".//a:row", XLSX_NS):
        values: list[str] = []
        for cell in row.findall("a:c", XLSX_NS):
            cell_type = cell.attrib.get("t")
            value_node = cell.find("a:v", XLSX_NS)
            if value_node is None or value_node.text is None:
                values.append("")
                continue
            value = value_node.text
            if cell_type == "s":
                value = shared_strings[int(value)]
            values.append(value)
        rows.append(values)
    return rows


def _read_shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings: list[str] = []
    for item in root.findall(".//a:si", XLSX_NS):
        strings.append("".join(node.text or "" for node in item.findall(".//a:t", XLSX_NS)))
    return strings


def parse_jumpstarter_log_record(path: Path, line_number: int | None) -> ParsedLogRecord:
    parsed = ParsedLogRecord()
    if line_number is None:
        parsed.warnings.append("No log line provided")
        return parsed
    if not path.exists():
        parsed.warnings.append(f"Log file not found: {path}")
        return parsed

    lines = path.read_text(errors="replace").splitlines()
    candidates: list[tuple[int, str]] = []
    for index in range(max(0, line_number - 4), min(len(lines), line_number + 8)):
        text = lines[index].strip()
        if text.startswith("{'task':") or text.startswith('{"task":'):
            candidates.append((index + 1, text))

    if not candidates:
        parsed.warnings.append(f"No serialized task record near line {line_number}")
        return parsed

    actual_line, payload = candidates[0]
    try:
        record = ast.literal_eval(payload)
    except (SyntaxError, ValueError) as exc:
        parsed.warnings.append(f"Could not parse log record at line {actual_line}: {exc}")
        return parsed

    parsed.task = record.get("task")
    parsed.root_node = record.get("root_node")
    parsed.user_context = _dict_or_empty(record.get("user_context"))
    parsed.user_global_context = _dict_or_empty(record.get("userGlobalContext"))
    if parsed.root_node:
        parsed.saved_draft_context = extract_saved_drafts(parsed.root_node)
    else:
        parsed.warnings.append("Log record missing root_node")
    if not parsed.user_context:
        parsed.warnings.append("Log record has no user_context entries")
    return parsed


def extract_saved_drafts(root_node: dict[str, Any]) -> dict[str, str]:
    drafts: dict[str, str] = {}

    def visit(node: dict[str, Any]) -> None:
        answer_draft = node.get("answer_draft") or {}
        name = answer_draft.get("answer_draft_name")
        value = answer_draft.get("answer_draft_input")
        if name and isinstance(value, str) and value.strip():
            drafts[name] = value.strip()
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child)

    visit(root_node)
    return drafts


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
