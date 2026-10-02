"""
10-K Section Detector

Identifies standard SEC 10-K sections in raw document text using
regex pattern matching against known Item headers.
"""

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


def detect_sections(text: str) -> list[Section]:
    """
    Split a 10-K document into labeled sections.

    Args:
        text: Full document text

    Returns:
        List of Section objects with name, item number, and text content
    """
    regex = build_section_regex()
    matches = list(regex.finditer(text))

    if not matches:
        # Fallback: return whole document as one section
        return [Section(
            name="Full Document",
            item_number="N/A",
            start_char=0,
            end_char=len(text),
            text=text,
        )]

    sections = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()

        # Identify which item this is
        matched_item = match.group(0).strip()
        item_name = _lookup_item_name(matched_item)

        sections.append(Section(
            name=item_name,
            item_number=matched_item,
            start_char=start,
            end_char=end,
            text=section_text,
        ))

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
    """
    Extract financial statement notes (Note 1, Note 2, etc.).

    Returns list of {'note_number': str, 'text': str}
    """
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
