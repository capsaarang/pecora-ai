"""
Export case bundles for the website.

Usage:
    python -m pecora.export                 # outputs/adversarial -> web/data
    python -m pecora.export --out web/data

Keeps the newest bundled run per filing (ticker, fiscal year, anonymized or not). Runs saved
before case bundles existed have no filing text and are skipped. Writes one JSON per case
under cases/ and an index.json the site lists them from.
"""

import argparse
import glob
import json
import os

_DEBATE_KEYS = ("finding", "evidence", "auditor", "defender", "adjudication", "citations",
                "verdict", "raw_confidence", "final_confidence", "flags", "error")


def case_id(meta: dict) -> str:
    fy = f"FY{meta['fiscal_year']}" if meta.get("fiscal_year") else "local"
    return f"{meta['ticker']}_{fy}{'_anon' if meta.get('anonymized') else ''}"


def company_name(meta: dict) -> str:
    """Older runs did not save the name; the anonymizer's first alias is the EDGAR name."""
    return meta.get("company_name") or (meta.get("anonymization", {}).get("aliases") or [meta["ticker"]])[0]


def export(src: str = "outputs/adversarial", out: str = "web/data") -> list[dict]:
    newest: dict[str, tuple[str, dict]] = {}
    for path in glob.glob(os.path.join(src, "*.json")):
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        if "filing" not in run or "meta" not in run:
            continue  # backtest summaries and pre-bundle runs
        cid = case_id(run["meta"])
        if cid not in newest or run["meta"]["run_at"] > newest[cid][1]["meta"]["run_at"]:
            newest[cid] = (path, run)

    os.makedirs(os.path.join(out, "cases"), exist_ok=True)
    index = []
    for cid, (path, run) in sorted(newest.items()):
        meta = {**run["meta"], "company_name": company_name(run["meta"]), "source_file": os.path.basename(path)}
        case = {"id": cid, "meta": meta, "summary": run["summary"], "bundle": run.get("bundle", {}),
                "screen": {"findings": len(run.get("screen", {}).get("findings", [])),
                           "failed_areas": run.get("screen", {}).get("failed_areas", {})},
                "debates": [{k: d.get(k) for k in _DEBATE_KEYS} for d in run["debates"]],
                "filing": run["filing"]}
        with open(os.path.join(out, "cases", f"{cid}.json"), "w", encoding="utf-8") as f:
            json.dump(case, f)
        index.append({"id": cid, "ticker": meta["ticker"], "company_name": meta["company_name"],
                      "fiscal_year": meta.get("fiscal_year"), "filing_date": meta.get("filing_date"),
                      "anonymized": meta.get("anonymized", False), "signal_score": run["summary"]["signal_score"],
                      "verdicts": run["summary"]["verdicts"], "debated": len(run["debates"]),
                      "screened": case["screen"]["findings"]})
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)
    return index


def main():
    p = argparse.ArgumentParser(description="Export Pecora.ai case bundles for the website")
    p.add_argument("--src", default="outputs/adversarial")
    p.add_argument("--out", default="web/data")
    args = p.parse_args()
    index = export(args.src, args.out)
    print(f"Exported {len(index)} case(s) to {args.out}: {', '.join(c['id'] for c in index) or 'none'}")


if __name__ == "__main__":
    main()
