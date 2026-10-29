"""Offline test for the website exporter."""

import json

from pecora.export import export


def _run(path, run_at, ticker="MDXG", bundled=True):
    run = {"meta": {"ticker": ticker, "fiscal_year": 2016, "anonymized": True, "run_at": run_at,
                    "anonymization": {"aliases": ["MIMEDX GROUP, INC."], "people": [], "products": [], "leaks": {}}},
           "summary": {"signal_score": 10, "verdicts": {"UPHELD": 1}},
           "screen": {"findings": [{}, {}], "failed_areas": {}},
           "debates": [{"finding": {"title": "t"}, "verdict": "UPHELD", "extra": "dropped"}]}
    if bundled:
        run["filing"] = {"text": "x", "sections": []}
    path.write_text(json.dumps(run))


def test_export_keeps_newest_bundled_run_per_filing(tmp_path):
    src, out = tmp_path / "runs", tmp_path / "web"
    src.mkdir()
    _run(src / "old.json", "2026-10-01T10:00:00")
    _run(src / "new.json", "2026-10-02T10:00:00")
    _run(src / "nobundle.json", "2026-10-03T10:00:00", ticker="SMCI", bundled=False)
    (src / "backtest.json").write_text(json.dumps({"rows": []}))

    index = export(str(src), str(out))

    assert [c["id"] for c in index] == ["MDXG_FY2016_anon"]
    case = json.loads((out / "cases" / "MDXG_FY2016_anon.json").read_text())
    assert case["meta"]["source_file"] == "new.json"
    assert case["meta"]["company_name"] == "MIMEDX GROUP, INC."  # fallback from the anonymizer's aliases
    assert "extra" not in case["debates"][0] and case["screen"]["findings"] == 2
