"""LLM providers returning schema-constrained JSON: Groq (free tier) and local Ollama.

Select with AI_PROVIDER=groq|ollama in .env. API keys are sent only in headers
and never appear in logs or exception messages.
"""
import json
import os
import re
import time
from collections import deque

import requests
from dotenv import load_dotenv


class AIError(RuntimeError):
    pass


_ESCAPED_UNICODE = re.compile(r"\\u([0-9a-fA-F]{4})")


def unescape(value):
    """Undo double escaping the models sometimes emit inside JSON strings (e.g. bo\\u2018lgan, bo\\'yicha)."""
    if isinstance(value, str):
        value = _ESCAPED_UNICODE.sub(lambda m: chr(int(m.group(1), 16)), value)
        return value.replace("\\'", "'").replace('\\"', '"')
    if isinstance(value, list):
        return [unescape(v) for v in value]
    if isinstance(value, dict):
        return {k: unescape(v) for k, v in value.items()}
    return value


class DailyLimitReached(AIError):
    """The provider's daily quota is exhausted; resume on a later run."""


class GroqProvider:
    name = "groq"
    URL = "https://api.groq.com/openai/v1/chat/completions"
    MAX_WAIT = 120  # seconds; a longer retry-after means the daily quota is gone

    def __init__(self):
        self._key = os.getenv("GROQ_API_KEY")
        if not self._key:
            raise AIError("GROQ_API_KEY is not set in .env")
        self.model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.tpm = int(os.getenv("GROQ_TPM", "8000"))  # free tier: 8K tokens/minute
        self._window = deque()  # (timestamp, tokens) of the last minute

    def _pace(self, estimate):
        """Sleep until `estimate` more tokens fit into the tokens-per-minute budget."""
        while True:
            now = time.monotonic()
            while self._window and now - self._window[0][0] > 60:
                self._window.popleft()
            used = sum(t for _, t in self._window)
            if not self._window or used + estimate <= self.tpm:
                return
            time.sleep(60 - (now - self._window[0][0]) + 0.5)

    def complete_json(self, system, user, schema, max_tokens):
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            },
            "max_completion_tokens": max_tokens,
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
            body["include_reasoning"] = False
        estimate = (len(system) + len(user)) // 3 + max_tokens
        json_failures = 0
        for _attempt in range(8):
            self._pace(estimate)
            try:
                resp = requests.post(self.URL, json=body, timeout=180,
                                     headers={"Authorization": f"Bearer {self._key}"})
            except requests.RequestException as exc:
                raise AIError(f"groq: {type(exc).__name__}") from None
            if resp.status_code == 429:
                message = _error_message(resp)
                wait = float(resp.headers.get("retry-after", 30))
                if "per day" in message.lower() or wait > self.MAX_WAIT:
                    raise DailyLimitReached(f"groq: {message}")
                time.sleep(wait + 1)
                continue
            if resp.status_code == 400 and _error_code(resp) == "json_validate_failed" and json_failures < 2:
                # strict-mode decoding occasionally gives up; an identical retry usually succeeds
                json_failures += 1
                self._window.append((time.monotonic(), estimate))
                continue
            if resp.status_code != 200:
                raise AIError(f"groq {resp.status_code}: {_error_message(resp)}")
            data = resp.json()
            usage = data.get("usage", {})
            self._window.append((time.monotonic(), usage.get("total_tokens", estimate)))
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise AIError("groq: output truncated (max_completion_tokens too small)")
            return unescape(json.loads(choice["message"]["content"]))
        raise AIError("groq: still rate limited after retries")


class OllamaProvider:
    name = "ollama"

    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "qwen3:14b")
        base = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.url = base + "/api/chat"
        try:  # fail once up front instead of once per file
            requests.get(base + "/api/tags", timeout=3).raise_for_status()
        except requests.RequestException:
            raise AIError(f"ollama is not running at {base}") from None

    def complete_json(self, system, user, schema, max_tokens):
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "options": {"num_ctx": 16384, "num_predict": max_tokens},
        }
        try:
            resp = requests.post(self.url, json=body, timeout=900)
        except requests.RequestException as exc:
            raise AIError(f"ollama not reachable at {self.url}: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise AIError(f"ollama {resp.status_code}: {_error_message(resp)}")
        return unescape(json.loads(resp.json()["message"]["content"]))


PROVIDERS = {"groq": GroqProvider, "ollama": OllamaProvider}


def get_provider():
    load_dotenv()
    name = os.getenv("AI_PROVIDER", "groq").strip().lower()
    if name not in PROVIDERS:
        raise AIError(f"unknown AI_PROVIDER={name!r}; use one of {sorted(PROVIDERS)}")
    return PROVIDERS[name]()


def _error_code(resp):
    try:
        err = resp.json().get("error", {})
        return err.get("code") if isinstance(err, dict) else None
    except ValueError:
        return None


def _error_message(resp):
    try:
        err = resp.json().get("error", {})
        return err.get("message", "") if isinstance(err, dict) else str(err)
    except ValueError:
        return resp.text[:200]
