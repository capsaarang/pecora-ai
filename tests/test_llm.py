"""Offline tests for the Claude CLI transport (subprocess is faked; no subscription usage)."""

import json
from types import SimpleNamespace

import pytest

from pecora.adversarial import llm as llm_mod
from pecora.adversarial.llm import (CLIError, ClaudeCLI, TruncatedResponse, UsageLimitReached,
                                    flatten_messages, make_llm)


def _result(text="{}", is_error=False, **extra):
    return json.dumps({"type": "result", "is_error": is_error, "result": text,
                       "usage": {"input_tokens": 3, "cache_creation_input_tokens": 800,
                                 "cache_read_input_tokens": 50, "output_tokens": 20}, **extra})


@pytest.fixture
def cli(monkeypatch):
    """A ClaudeCLI whose subprocess replies come from the `replies` list, recording each call."""
    monkeypatch.setattr(llm_mod.shutil, "which", lambda b: f"/usr/bin/{b}")
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    calls, replies = [], []

    def fake_run(cmd, input, env, cwd, **kw):
        calls.append({"cmd": cmd, "input": input, "env": env, "cwd": cwd})
        return SimpleNamespace(stdout=replies.pop(0), stderr="", returncode=0)

    monkeypatch.setattr(llm_mod.subprocess, "run", fake_run)
    c = ClaudeCLI(max_tokens=1234)
    c.fake_calls, c.fake_replies = calls, replies
    return c


def test_success_returns_text_and_counts_tokens(cli):
    cli.fake_replies.append(_result('{"verdict": "UPHELD"}'))
    assert cli("system", "user") == '{"verdict": "UPHELD"}'
    assert cli.calls == 1 and cli.input_tokens == 853 and cli.output_tokens == 20


def test_call_is_isolated_from_user_setup_and_api_billing(cli, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    cli.fake_replies.append(_result())
    cli("the system prompt", "user")
    call = cli.fake_calls[0]
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in call["cmd"]
    assert call["cmd"][call["cmd"].index("--tools") + 1] == ""
    assert call["cmd"][call["cmd"].index("--setting-sources") + 1] == ""
    assert call["cmd"][call["cmd"].index("--system-prompt") + 1] == "the system prompt"
    assert "ANTHROPIC_API_KEY" not in call["env"]
    assert call["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "1234"
    assert call["cwd"] == cli.workdir


def test_cut_off_reply_raises_truncated(cli):
    cli.fake_replies.append(_result("API Error: exceeded", is_error=True, api_error="max_output_tokens"))
    with pytest.raises(TruncatedResponse):
        cli("s", "u")


def test_usage_limit_is_not_retried(cli):
    cli.fake_replies.append(_result("Claude usage limit reached. Your limit will reset at 5pm", is_error=True))
    with pytest.raises(UsageLimitReached):
        cli("s", "u")
    assert len(cli.fake_calls) == 1


def test_transient_error_retried_then_succeeds(cli):
    cli.fake_replies += [_result("API Error: Overloaded", is_error=True, api_error_status=529),
                         _result("ok")]
    assert cli("s", "u") == "ok" and len(cli.fake_calls) == 2


def test_unreadable_output_retried_then_raises(cli):
    cli.fake_replies += ["not json", "still not json", "nope"]
    with pytest.raises(CLIError):
        cli("s", "u")
    assert len(cli.fake_calls) == 3


def test_other_errors_raise_without_retry(cli):
    cli.fake_replies.append(_result("Invalid model name", is_error=True))
    with pytest.raises(CLIError):
        cli("s", "u")
    assert len(cli.fake_calls) == 1


def test_flatten_keeps_the_conversation_in_order():
    msgs = [{"role": "user", "content": "first ask"}, {"role": "assistant", "content": "FOLLOWUP_REQUEST: x"},
            {"role": "user", "content": "here is more context"}]
    text = flatten_messages(msgs)
    assert text.index("first ask") < text.index("FOLLOWUP_REQUEST") < text.index("here is more context")
    assert text.endswith("here is more context")
    assert flatten_messages(msgs[:1]) == "first ask"


def test_make_llm_rejects_unknown_provider():
    with pytest.raises(ValueError):
        make_llm("openai")


def test_make_llm_fails_closed_when_cli_missing(monkeypatch):
    monkeypatch.setattr(llm_mod.shutil, "which", lambda b: None)
    with pytest.raises(ValueError, match="not found"):
        make_llm("cli")
