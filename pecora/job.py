"""
One analysis job, started by the website's Run tab (or by hand).

Usage:
    python -m pecora.job --id MDXG-2016-20261028T204500 --ticker MDXG --year 2016 [--max-findings 5] [--no-anonymize]

Writes outputs/jobs/<id>/status.json and outputs/jobs/<id>/log.txt as it goes, so the site can show
progress and pick a job back up after a page reload. On success the run is exported to web/data,
where the site lists it straight away.
"""

import argparse
import json
import os
import traceback
from datetime import datetime

from dotenv import load_dotenv

from .adversarial.llm import UsageLimitReached
from .export import case_id, export

JOBS_DIR = os.path.join("outputs", "jobs")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Job:
    def __init__(self, job_id: str, root: str = JOBS_DIR, **fields):
        self.dir = os.path.join(root, job_id)
        os.makedirs(self.dir, exist_ok=True)
        self.status = {"id": job_id, "status": "running", "started": _now(), "finished": None,
                       "case_id": None, "error": None, "pid": os.getpid(), **fields}
        self._save()

    def _save(self) -> None:
        tmp = os.path.join(self.dir, "status.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.status, f, indent=1)
        os.replace(tmp, os.path.join(self.dir, "status.json"))  # readers never see a half-written file

    def log(self, *parts) -> None:
        line = " ".join(str(p) for p in parts)
        print(line, flush=True)
        with open(os.path.join(self.dir, "log.txt"), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def finish(self, **fields) -> None:
        self.status.update(finished=_now(), **fields)
        self._save()


def run_job(job: Job, ticker: str, year: int, max_findings: int = 5, anonymize: bool = True,
            runner=None, exporter=export, output_dir: str = "outputs/adversarial", data_dir: str = "web/data") -> None:
    if runner is None:
        from .adversarial.run import run_adversarial as runner
    try:
        result = runner(ticker=ticker, year=year, anonymize=anonymize, max_findings=max_findings,
                        output_dir=output_dir, log=job.log)
        exporter(output_dir, data_dir)
        job.finish(status="done", case_id=case_id(result["meta"]), summary=result["summary"])
    except UsageLimitReached as e:
        job.log(f"Stopped: {e}")
        job.finish(status="error", error=f"Claude usage limit reached. Try again after it resets. ({e})")
    except Exception as e:
        job.log(traceback.format_exc())
        job.finish(status="error", error=f"{type(e).__name__}: {e}")


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description="Run one Pecora.ai analysis job")
    p.add_argument("--id", required=True)
    p.add_argument("--ticker", required=True)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--max-findings", type=int, default=5)
    p.add_argument("--no-anonymize", action="store_true")
    args = p.parse_args()
    ticker = args.ticker.upper()
    job = Job(args.id, ticker=ticker, year=args.year, max_findings=args.max_findings,
              anonymize=not args.no_anonymize)
    run_job(job, ticker, args.year, args.max_findings, not args.no_anonymize)


if __name__ == "__main__":
    main()
