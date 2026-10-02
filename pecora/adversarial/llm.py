"""
Thin Claude wrapper for the adversarial agents.

Any callable with the signature llm(system: str, user: str) -> str works,
which lets tests (and cached demo runs) swap in a fake model.
"""

import json
import os
import re
import time

import anthropic

DEFAULT_MODEL = os.environ.get("PECORA_MODEL", "claude-sonnet-5")
_RETRYABLE = {429, 500, 502, 503, 529}


class ClaudeLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 max_tokens: int = 2000):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set. Export it or add it to .env.")
        self.client = anthropic.Anthropic(api_key=key)
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.calls = 0

    def __call__(self, system: str, user: str) -> str:
        for attempt in range(3):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                self.calls += 1
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
