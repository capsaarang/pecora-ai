"""Offline tests for the website's job runner (the pipeline is faked)."""

import json

from pecora.adversarial.llm import UsageLimitReached
from pecora.job import Job, run_job


def _status(job):
    with open(f"{job.dir}/status.json") as f:
        return json.load(f)


def test_successful_job_records_case_and_log(tmp_path):
    exported = []

    def fake_runner(ticker, year, log, **kw):
        log("[1/5] Loading filing...")
        return {"meta": {"ticker": ticker, "fiscal_year": year, "anonymized": True}, "summary": {"signal_score": 7}}

    job = Job("MDXG-2016-x", root=str(tmp_path), ticker="MDXG", year=2016)
    assert _status(job)["status"] == "running"
    run_job(job, "MDXG", 2016, runner=fake_runner, exporter=lambda *a: exported.append(a))

    s = _status(job)
    assert s["status"] == "done" and s["case_id"] == "MDXG_FY2016_anon" and s["summary"]["signal_score"] == 7
    assert exported and "[1/5] Loading filing..." in open(f"{job.dir}/log.txt").read()


def test_usage_limit_becomes_a_readable_error(tmp_path):
    def limited(**kw):
        raise UsageLimitReached("limit will reset at 5pm")

    job = Job("SMCI-2016-x", root=str(tmp_path))
    run_job(job, "SMCI", 2016, runner=limited, exporter=lambda *a: None)
    s = _status(job)
    assert s["status"] == "error" and "usage limit" in s["error"] and s["finished"]


def test_crash_records_the_exception(tmp_path):
    def broken(**kw):
        raise ValueError("No original 10-K for XYZ FY2016")

    job = Job("XYZ-2016-x", root=str(tmp_path))
    run_job(job, "XYZ", 2016, runner=broken, exporter=lambda *a: None)
    assert _status(job)["error"] == "ValueError: No original 10-K for XYZ FY2016"
