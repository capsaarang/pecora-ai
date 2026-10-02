"""
Tests for the screener: focus areas, finding parsing, and follow-up requests.
"""

import pytest
from pecora.retrieval.focus_areas import FOCUS_AREAS, get_all_queries, get_focus_area
from pecora.screen import Finding, _parse_findings, _extract_followup_request


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_finding(severity: str, focus_area: str = "risk_factors") -> Finding:
    return Finding(
        id="F1",
        severity=severity,
        section="Item 1A",
        title="Test finding",
        detail="Detail text.",
        flagged_text="some flagged text",
        recommendation="Monitor closely.",
        focus_area=focus_area,
    )


# ── Focus Areas ───────────────────────────────────────────────────────────────

class TestFocusAreas:
    def test_all_focus_areas_present(self):
        expected = {"risk_factors", "revenue", "debt", "litigation", "related_party", "forward_guidance"}
        assert set(FOCUS_AREAS.keys()) == expected

    def test_each_area_has_queries(self):
        for key, area in FOCUS_AREAS.items():
            assert len(area["queries"]) >= 3, f"{key} has too few queries"

    def test_each_area_has_instructions(self):
        for key, area in FOCUS_AREAS.items():
            assert len(area["audit_instructions"]) > 50, f"{key} missing audit instructions"

    def test_get_focus_area_valid(self):
        area = get_focus_area("revenue")
        assert area["label"] == "Revenue Anomalies"

    def test_get_focus_area_invalid(self):
        with pytest.raises(ValueError):
            get_focus_area("nonexistent_area")

    def test_get_all_queries_returns_pairs(self):
        pairs = get_all_queries(["risk_factors", "revenue"])
        assert all(isinstance(p, tuple) and len(p) == 2 for p in pairs)
        focus_keys = {p[0] for p in pairs}
        assert "risk_factors" in focus_keys
        assert "revenue" in focus_keys


# ── Scorer ────────────────────────────────────────────────────────────────────

class TestFindingParser:
    VALID_JSON = """
[
  {
    "id": "F1",
    "severity": "HIGH",
    "section": "Item 1A — Risk Factors",
    "title": "Revenue concentration in iPhone",
    "detail": "iPhone accounts for 52% of revenue, creating concentration risk.",
    "flagged_text": "iPhone net sales were $200.6 billion",
    "recommendation": "Assess product diversification strategy."
  },
  {
    "id": "F2",
    "severity": "MEDIUM",
    "section": "Item 7 — MD&A",
    "title": "Gross margin pressure noted",
    "detail": "Component costs rising, compressing margins.",
    "flagged_text": "gross margins may be under pressure",
    "recommendation": "Monitor supply chain cost trends."
  }
]
"""

    def test_parses_valid_json(self):
        findings = _parse_findings(self.VALID_JSON, "risk_factors")
        assert len(findings) == 2

    def test_finding_fields_populated(self):
        findings = _parse_findings(self.VALID_JSON, "risk_factors")
        f = findings[0]
        assert f.severity == "HIGH"
        assert f.title == "Revenue concentration in iPhone"
        assert f.focus_area == "risk_factors"
        assert f.flagged_text != ""

    def test_handles_json_with_markdown_fences(self):
        wrapped = f"```json\n{self.VALID_JSON}\n```"
        findings = _parse_findings(wrapped, "revenue")
        assert len(findings) == 2

    def test_returns_empty_on_invalid_json(self):
        findings = _parse_findings("This is not JSON at all.", "debt")
        assert findings == []

    def test_focus_area_set_on_all_findings(self):
        findings = _parse_findings(self.VALID_JSON, "litigation")
        for f in findings:
            assert f.focus_area == "litigation"


# ── Followup Extractor ────────────────────────────────────────────────────────

class TestFollowupExtractor:
    def test_extracts_followup_request(self):
        text = "Some analysis here.\nFOLLOWUP_REQUEST: debt covenants and credit facility terms"
        result = _extract_followup_request(text)
        assert result == "debt covenants and credit facility terms"

    def test_returns_none_when_absent(self):
        text = "Here are the findings in JSON format: [...]"
        result = _extract_followup_request(text)
        assert result is None

    def test_handles_extra_whitespace(self):
        text = "FOLLOWUP_REQUEST:   litigation settlement amounts in notes"
        result = _extract_followup_request(text)
        assert "litigation" in result
