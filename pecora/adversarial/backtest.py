"""
Backtest: target (later restated) vs control (clean peer), same settings.

Usage:
    python -m pecora.adversarial.backtest --target SMCI:2016 --control NTAP:2016
    python -m pecora.adversarial.backtest --target SMCI:2016 --target SMCI:2015 --control NTAP:2016

The claim being tested: the adversarial signal is meaningfully higher for the
target BEFORE its problems went public, and stays low for the control.
"""

import argparse
import json
import os

from .run import DEFAULT_FOCUS, run_adversarial


def _parse_case(s: str) -> tuple[str, int]:
    ticker, year = s.split(":")
    return ticker.upper(), int(year)


def main():
    p = argparse.ArgumentParser(description="Pecora.ai backtest: target vs control")
    p.add_argument("--target", action="append", required=True, help="TICKER:YEAR (repeatable)")
    p.add_argument("--control", action="append", required=True, help="TICKER:YEAR (repeatable)")
    p.add_argument("--no-anonymize", action="store_true")
    p.add_argument("--mask-years", action="store_true")
    p.add_argument("--max-findings", type=int, default=5)
    p.add_argument("--output-dir", default="outputs/adversarial")
    args = p.parse_args()

    settings = dict(anonymize=not args.no_anonymize, mask_years=args.mask_years,
                    max_findings=args.max_findings, focus_areas=DEFAULT_FOCUS,
                    output_dir=args.output_dir)

    rows = []
    for role, cases in (("target", args.target), ("control", args.control)):
        for case in cases:
            ticker, year = _parse_case(case)
            print(f"\n{'=' * 60}\n  {role.upper()}: {ticker} FY{year}\n{'=' * 60}")
            r = run_adversarial(ticker=ticker, year=year, **settings)
            s = r["summary"]
            rows.append({"role": role, "ticker": ticker, "fiscal_year": year,
                         "signal_score": s["signal_score"],
                         "upheld": s["verdicts"].get("UPHELD", 0),
                         "dismissed": s["verdicts"].get("DISMISSED", 0),
                         "inconclusive": s["verdicts"].get("INCONCLUSIVE", 0),
                         "citation_integrity": s["citation_integrity"],
                         "result_file": r["path"]})

    print(f"\n{'=' * 60}\n  BACKTEST RESULTS\n{'=' * 60}")
    print(f"  {'role':8s} {'case':12s} {'signal':>6s} {'upheld':>7s} {'dismiss':>8s} {'cite%':>6s}")
    for r in rows:
        cite = f"{r['citation_integrity'] * 100:.0f}" if r["citation_integrity"] is not None else "-"
        print(f"  {r['role']:8s} {r['ticker'] + ' FY' + str(r['fiscal_year']):12s} "
              f"{r['signal_score']:>6d} {r['upheld']:>7d} {r['dismissed']:>8d} {cite:>6s}")

    targets = [r["signal_score"] for r in rows if r["role"] == "target"]
    controls = [r["signal_score"] for r in rows if r["role"] == "control"]
    gap = round(sum(targets) / len(targets) - sum(controls) / len(controls), 1)
    print(f"\n  Signal gap (target avg - control avg): {gap:+}")

    os.makedirs(args.output_dir, exist_ok=True)
    name = "backtest_" + "_".join(c.replace(":", "") for c in args.target + args.control) + ".json"
    path = os.path.join(args.output_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"settings": settings, "rows": rows, "signal_gap": gap}, f, indent=2)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    main()
