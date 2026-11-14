"""
Case files for the app: the built-in sample case plus saved runs.

The sample case is fictional and always labeled as sample data. Saved runs come
from outputs/adversarial, written by pecora.adversarial.run and backtest.
"""

import glob
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE_PATH = os.path.join(ROOT, "data", "demo", "sample_case.json")
VIDEO_PATH = os.path.join(ROOT, "assets", "pecora-demo.mp4")
RESULTS_DIR = os.path.join(ROOT, "outputs", "adversarial")
DEMO_ID = "demo"

_RUN_CMD = re.compile(r"^\s*(?:analy[sz]e\s+|run\s+|review\s+)?\$?([A-Za-z][A-Za-z.]{0,5})\s+(?:FY\s?)?((?:19|20)\d{2})\s*$",
                      re.IGNORECASE)


def load_sample() -> dict:
    with open(SAMPLE_PATH, encoding="utf-8") as f:
        case = json.load(f)
    case["id"] = DEMO_ID
    return case


def list_cases(results_dir: str = RESULTS_DIR) -> list[dict]:
    """Saved runs, newest first. Each item: {id, path, kind, label, meta, summary}."""
    items = []
    for path in glob.glob(os.path.join(results_dir, "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if "rows" in data:
            label = "Backtest: " + " vs ".join(f"{r['ticker']} {r['fiscal_year']}" for r in data["rows"])
            items.append({"id": path, "path": path, "kind": "backtest", "label": label, "data": data,
                          "mtime": os.path.getmtime(path)})
        elif "debates" in data:
            m = data.get("meta", {})
            fy = f"FY{m['fiscal_year']}" if m.get("fiscal_year") else ""
            label = f"{m.get('ticker', 'Case')} {fy}".strip()
            if not m.get("anonymized", True):
                label += " (names shown)"
            items.append({"id": path, "path": path, "kind": "case", "label": label, "data": data,
                          "mtime": os.path.getmtime(path)})
    return sorted(items, key=lambda x: x["mtime"], reverse=True)


def load_case(case_id: str) -> dict | None:
    if case_id == DEMO_ID:
        return load_sample()
    try:
        with open(case_id, encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    case["id"] = case_id
    return case


def parse_run_command(text: str) -> tuple[str, int] | None:
    """'SMCI 2016', 'analyze smci FY2016' -> ('SMCI', 2016). Anything else -> None."""
    m = _RUN_CMD.match(text or "")
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2))


def find_demo_answer(case: dict, question: str) -> dict | None:
    """Canned answers for the sample case, so the demo works with no model call."""
    q = re.sub(r"\W+", " ", question.lower()).strip()
    for item in case.get("demo_qa", []):
        if re.sub(r"\W+", " ", item["question"].lower()).strip() == q:
            return {"answer": item["answer"], "citations": item["citations"], "answerable": True, "error": ""}
    return None
