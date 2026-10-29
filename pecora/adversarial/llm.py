"""
Thin Claude wrappers for the screener and the adversarial agents.

Two transports with the same interface (llm(system, user) and llm.chat(system, messages)):
  - ClaudeCLI (default): the local Claude Code CLI, on the user's Claude subscription
  - ClaudeLLM: the Anthropic API, billed per token

make_llm() picks one from PECORA_LLM ("cli" or "api"). Any callable with the signature
llm(system: str, user: str) -> str also works, which lets tests swap in a fake model.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

import anthropic

DEFAULT_MODEL = os.environ.get("PECORA_MODEL", "claude-sonnet-5")
DEFAULT_CLI_MODEL = os.environ.get("PECORA_CLI_MODEL", "claude-sonnet-5-5")
DEFAULT_CLI_EFFORT = os.environ.get("PECORA_CLI_EFFORT", "medium")
# Thinking blocks share this budget with the visible reply, so leave plenty of room
DEFAULT_MAX_TOKENS = 8000
_RETRYABLE = {429, 500, 502, 503, 529}


class TruncatedResponse(RuntimeError):
    """The reply hit max_tokens. Its JSON is incomplete, so retrying the same call won't help."""


class UsageLimitReached(RuntimeError):
    """The Claude subscription's usage limit was hit. Retrying now won't help; wait for the reset."""


class CLIError(RuntimeError):
    """The Claude CLI failed for a reason that is not a rate limit or a cut-off reply."""


def make_llm(provider: str | None = None):
    """The configured LLM. No silent fallback: a missing CLI never quietly switches to paid API calls."""
    provider = (provider or os.environ.get("PECORA_LLM", "cli")).lower()
    if provider == "cli":
        return ClaudeCLI()
    if provider == "api":
        return ClaudeLLM()
    raise ValueError(f"PECORA_LLM must be 'cli' or 'api', not {provider!r}")


def flatten_messages(messages: list[dict]) -> str:
    """One prompt from a multi-turn conversation; `claude -p` takes a single message."""
    if len(messages) == 1:
        return messages[0]["content"]
    earlier = "\n\n".join(f"<{m['role']}>\n{m['content']}\n</{m['role']}>" for m in messages[:-1])
    return (f"The conversation so far:\n\n{earlier}\n\n"
            f"Now respond to this latest user message:\n\n{messages[-1]['content']}")


class ClaudeCLI:
    """
    Claude through `claude -p`, billed to the user's Claude subscription instead of API credits.

    Each call is isolated from the user's own Claude Code setup: no tools, no MCP servers
    (without --strict-mcp-config every call carried ~127k tokens of tool definitions), no
    skills, no user or project settings or hooks, no saved session, and an empty working
    directory. API keys are removed from the subprocess environment so a call can never
    fall back to paid API billing.
    """

    _STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")

    def __init__(self, model: str | None = None, effort: str | None = DEFAULT_CLI_EFFORT,
                 max_tokens: int = DEFAULT_MAX_TOKENS, timeout: int = 900, binary: str = "claude"):
        self.cli = shutil.which(binary)
        if not self.cli:
            raise ValueError(f"Claude Code CLI '{binary}' not found on PATH. Install it and run "
                             "`claude` once to log in, or set PECORA_LLM=api to use an API key.")
        self.model = model or DEFAULT_CLI_MODEL
        self.effort = effort
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.workdir = tempfile.mkdtemp(prefix="pecora-claude-")
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self._lock = threading.Lock()  # agents run in parallel threads

    def __call__(self, system: str, user: str) -> str:
        return self.chat(system, [{"role": "user", "content": user}])

    def _command(self, system: str) -> list[str]:
        cmd = [self.cli, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
               "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "",
               "--model", self.model, "--system-prompt", system]
        if self.effort:
            cmd += ["--effort", self.effort]
        return cmd

    def _env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in self._STRIP_ENV}
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(self.max_tokens)
        return env

    def chat(self, system: str, messages: list[dict]) -> str:
        """One call. Retries transient errors; raises on a cut-off reply or a usage limit."""
        for attempt in range(3):
            proc = subprocess.run(self._command(system), input=flatten_messages(messages),
                                  capture_output=True, text=True, env=self._env(),
                                  cwd=self.workdir, timeout=self.timeout)
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                detail = (proc.stderr or proc.stdout or "").strip()[:300]
                if attempt == 2:
                    raise CLIError(f"unreadable CLI output (exit {proc.returncode}): {detail}")
                time.sleep(2 * (2 ** attempt))
                continue

            usage = data.get("usage") or {}
            with self._lock:
                self.calls += 1
                self.input_tokens += sum(int(usage.get(k) or 0) for k in (
                    "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                self.output_tokens += int(usage.get("output_tokens") or 0)

            if not data.get("is_error"):
                return data.get("result") or ""
            message = str(data.get("result") or "")[:500]
            if data.get("api_error") == "max_output_tokens":
                raise TruncatedResponse(f"reply cut off at max_tokens={self.max_tokens}")
            if re.search(r"usage limit|limit reached|limit will reset", message, re.I):
                raise UsageLimitReached(message)
            if data.get("api_error_status") not in _RETRYABLE and not re.search(
                    r"overloaded|rate limit|timeout|temporarily", message, re.I):
                raise CLIError(message)
            if attempt == 2:
                raise CLIError(f"still failing after 3 attempts: {message}")
            time.sleep(5 * (2 ** attempt))
        raise RuntimeError("unreachable")


class ClaudeLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set. Export it or add it to .env.")
        self.client = anthropic.Anthropic(api_key=key)
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.calls = 0

    def __call__(self, system: str, user: str) -> str:
        return self.chat(system, [{"role": "user", "content": user}])

    def chat(self, system: str, messages: list[dict]) -> str:
        """Multi-turn call. Retries rate limits and server errors; raises if the reply was cut off."""
        for attempt in range(3):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=messages,
                )
                self.calls += 1
                if resp.stop_reason == "max_tokens":
                    raise TruncatedResponse(f"reply cut off at max_tokens={self.max_tokens}")
                return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            except anthropic.APIStatusError as e:
                if e.status_code not in _RETRYABLE or attempt == 2:
                    raise
            except anthropic.APIConnectionError:
                if attempt == 2:
                    raise
            time.sleep(2 * (2 ** attempt))
        raise RuntimeError("unreachable")


def parse_json_object(text: str) -> dict:
    """Parse a JSON object from model output, tolerating fences and preamble."""
    clean = re.sub(r"```(?:json)?", "", text).strip()
    try:
        obj = json.loads(clean)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start, end = clean.find("{"), clean.rfind("}")
    if start != -1 and end > start:
        obj = json.loads(clean[start:end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"Could not parse JSON object from model output: {text[:200]!r}")
