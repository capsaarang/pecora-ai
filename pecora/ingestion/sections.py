"""Splits a 10-K into its standard Item sections by matching Item headers at line starts."""

import re
from dataclasses import dataclass


@dataclass
class Section:
    name: str
    item_number: str
    start_char: int
    end_char: int
    text: str

    def __repr__(self):
        return f"Section({self.item_number}: {self.name[:40]}, chars={len(self.text)})"


# Standard 10-K section patterns (Part I and Part II)
SECTION_PATTERNS = [
    ("Item 1",   "Business"),
    ("Item 1A",  "Risk Factors"),
    ("Item 1B",  "Unresolved Staff Comments"),
    ("Item 2",   "Properties"),
    ("Item 3",   "Legal Proceedings"),
    ("Item 4",   "Mine Safety Disclosures"),
    ("Item 5",   "Market for Registrant"),
    ("Item 6",   "Selected Financial Data"),
    ("Item 7",   "Management's Discussion and Analysis"),
    ("Item 7A",  "Quantitative and Qualitative Disclosures"),
    ("Item 8",   "Financial Statements"),
    ("Item 9",   "Changes in and Disagreements"),
    ("Item 9A",  "Controls and Procedures"),
    ("Item 9B",  "Other Information"),
    ("Item 10",  "Directors, Executive Officers"),
    ("Item 11",  "Executive Compensation"),
    ("Item 12",  "Security Ownership"),
    ("Item 13",  "Certain Relationships and Related Transactions"),
    ("Item 14",  "Principal Accountant Fees"),
    ("Item 15",  "Exhibits"),
]


def build_section_regex() -> re.Pattern:
    """Build a regex that matches any known Item header."""
    item_nums = [p[0].replace(" ", r"\s*") for p in SECTION_PATTERNS]
    pattern = r"(?im)^(?:" + "|".join(item_nums) + r")\b"
    return re.compile(pattern)


def _section(name: str, item_number: str, text: str, start: int, end: int) -> Section:
    """A section whose offsets point at its stripped text, so text[start_char:end_char] == section.text."""
    raw = text[start:end]
    body = raw.strip()
    first = start + len(raw) - len(raw.lstrip())
    return Section(name, item_number, first, first + len(body), body)


def detect_sections(text: str) -> list[Section]:
    """Labeled sections in document order; the whole text as one section if no header is found."""
    matches = list(build_section_regex().finditer(text))
    if not matches:
        return [_section("Full Document", "N/A", text, 0, len(text))]

    sections = []
    # Keep text before the first header: filings with nonstandard layouts (e.g. GE) put
    # most of the report there and list the Item headers only in a closing index
    if len(text[:matches[0].start()].strip()) > 200:
        sections.append(_section("Front Matter", "Front", text, 0, matches[0].start()))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        item = match.group(0).strip()
        sections.append(_section(_lookup_item_name(item), item, text, match.start(), end))
    return sections


def _lookup_item_name(item_header: str) -> str:
    """Map an item header string to its canonical name.

    Matches the item number exactly. A substring check would label
    "Item 1A" (and "Item 10".."Item 15") as "Item 1 - Business".
    """
    m = re.search(r"item\s*(\d+[a-c]?)", item_header, re.IGNORECASE)
    if not m:
        return "Unknown Section"
    number = m.group(1).upper()
    for item_num, name in SECTION_PATTERNS:
        if item_num.split()[1].upper() == number:
            return name
    return "Unknown Section"


def extract_notes(text: str) -> list[dict]:
    """Financial statement notes: [{'note_number', 'title', 'text'}]."""
    pattern = re.compile(
        r"(?im)^NOTE\s*(\d+)[.\s\-–—]+(.{0,80}?)$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    notes = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        notes.append({
            "note_number": m.group(1),
            "title": m.group(2).strip(),
            "text": text[start:end].strip(),
        })
    return notes
