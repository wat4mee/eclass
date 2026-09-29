"""LLM providers returning schema-constrained JSON, chained so a used-up free quota falls through.

AI_PROVIDER in .env:
    auto (default)  Groq gpt-oss-120b -> Groq qwen3.8-27b -> Groq gpt-oss-20b -> Gemini (if GEMINI_API_KEY)
                    -> Ollama (if running); every Groq model has its own daily free quota
    a list          e.g. "gemini,groq:openai/gpt-oss-120b,ollama"  (provider or provider:model)
API keys are sent only in headers and never appear in logs or exception messages.
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


class DailyLimitReached(AIError):
    """The provider's daily quota is exhausted; resume on a later run."""


class InvalidKey(AIError):
    """The API key was rejected (revoked, mistyped or pasted into the wrong slot)."""


class Busy(AIError):
    """This model cannot take the request right now (overloaded, per-minute limit, request too large)."""


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


class OpenAICompatProvider:
    """Chat-completions API with JSON-schema output (Groq, Gemini)."""
    name = "openai-compatible"
    url = ""
    key_env = ""
    tpm = 0                 # tokens per minute to pace for (0 = no pacing)
    max_wait = 120          # seconds; a longer retry-after means the daily quota is gone
    patient = True          # False (set by the chain): raise Busy instead of waiting, so the next model answers

    def __init__(self, model):
        self._key = os.getenv(self.key_env)
        if not self._key:
            raise AIError(f"{self.key_env} is not set in .env")
        self.model = model
        self._window = deque()  # (timestamp, tokens) of the last minute
        self._schema_mode = "json_schema"

    def _pace(self, estimate):
        """Sleep until `estimate` more tokens fit into the tokens-per-minute budget."""
        while self.tpm:
            now = time.monotonic()
            while self._window and now - self._window[0][0] > 60:
                self._window.popleft()
            if not self._window or sum(t for _, t in self._window) + estimate <= self.tpm:
                return
            time.sleep(60 - (now - self._window[0][0]) + 0.5)

    def _extra(self):
        return {}

    def _body(self, system, user, schema, max_tokens):
        if self._schema_mode == "json_schema":
            fmt = {"type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": schema}}
        else:  # provider rejected the schema: plain JSON mode, schema described in the prompt
            fmt = {"type": "json_object"}
            system += "\n\nReply with a single JSON object that follows this JSON Schema exactly:\n" + json.dumps(schema)
        return {"model": self.model, "max_completion_tokens": max_tokens, "response_format": fmt,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                **self._extra()}

    def _is_daily(self, message, wait):
        text = message.lower()
        return "per day" in text or "perday" in text or wait > self.max_wait

    def complete_json(self, system, user, schema, max_tokens):
        estimate = (len(system) + len(user)) // 3 + max_tokens
        retries = 0
        for _attempt in range(8):
            self._pace(estimate)
            try:
                resp = requests.post(self.url, json=self._body(system, user, schema, max_tokens), timeout=180,
                                     headers={"Authorization": f"Bearer {self._key}"})
            except requests.RequestException as exc:
                raise AIError(f"{self.name}: {type(exc).__name__}") from None
            message = _error_message(resp) if resp.status_code != 200 else ""
            if resp.status_code == 429:
                wait = _retry_after(resp, message)
                if self._is_daily(message, wait):
                    raise DailyLimitReached(f"{self.name} {self.model}: {message}")
                if not self.patient or "too large" in message.lower():  # waiting would not help this call
                    raise Busy(f"{self.name} {self.model}: {message}")
                time.sleep(wait + 1)
                continue
            if resp.status_code in (401, 403) or (resp.status_code == 400 and "api key" in message.lower()):
                raise InvalidKey(f"{self.name}: {self.key_env} rejected ({resp.status_code})")
            if resp.status_code == 400 and self._retry_400(resp, message) and retries < 2:
                retries += 1
                self._window.append((time.monotonic(), estimate))
                continue
            overloaded = resp.status_code in (500, 502, 503, 504)
            if overloaded and not self.patient:
                raise Busy(f"{self.name} {self.model}: {resp.status_code} {message}")
            if overloaded and retries < 2:  # last model in the chain: brief back-off
                retries += 1
                time.sleep(3 * retries)
                continue
            if resp.status_code != 200:
                raise AIError(f"{self.name} {resp.status_code}: {message}")
            data = resp.json()
            self._window.append((time.monotonic(), (data.get("usage") or {}).get("total_tokens", estimate)))
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise AIError(f"{self.name}: output truncated (max tokens too small)")
            content = choice["message"]["content"] or ""
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
            return unescape(json.loads(content))
        raise AIError(f"{self.name}: still failing after retries")

    def _retry_400(self, resp, message):
        return False


class GroqProvider(OpenAICompatProvider):
    name = "groq"
    url = "https://api.groq.com/openai/v1/chat/completions"
    key_env = "GROQ_API_KEY"

    def __init__(self, model=None):
        super().__init__(model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
        self.tpm = int(os.getenv("GROQ_TPM", "8000"))  # free tier: 8K tokens/minute per model

    def _extra(self):
        if self.model.startswith("openai/gpt-oss"):
            return {"reasoning_effort": "low", "include_reasoning": False}
        return {}

    def _retry_400(self, resp, message):
        # strict-mode decoding occasionally gives up; an identical retry usually succeeds
        return _error_code(resp) == "json_validate_failed"


class GeminiProvider(OpenAICompatProvider):
    name = "gemini"
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    key_env = "GEMINI_API_KEY"

    def __init__(self, model=None):
        super().__init__(model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))

    def _extra(self):
        return {"reasoning_effort": "low"}

    def _retry_400(self, resp, message):
        # some schema features are not accepted: fall back to JSON mode once
        if self._schema_mode == "json_schema" and ("schema" in message.lower() or "response_format" in message):
            self._schema_mode = "json_object"
            return True
        return False


class OllamaProvider:
    name = "ollama"

    def __init__(self, model=None):
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3:14b")
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


class ChainProvider:
    """Uses the first provider whose daily quota is not used up; name/model tell who answered last."""

    def __init__(self, providers):
        self.providers = providers
        self.name, self.model = providers[0].name, providers[0].model

    def complete_json(self, system, user, schema, max_tokens):
        last = None
        for provider in list(self.providers):
            provider.patient = provider is self.providers[-1]  # only the last one waits out a busy spell
            try:
                result = provider.complete_json(system, user, schema, max_tokens)
            except (DailyLimitReached, InvalidKey) as exc:  # done for today / bad key: drop it
                last = exc
                self.providers.remove(provider)
                continue
            except Busy as exc:  # overloaded or rate limited: the next one answers this call
                last = exc
                continue
            self.name, self.model = provider.name, provider.model
            return result
        if self.providers:  # the ones left were only busy: a retry can still succeed
            raise last if isinstance(last, Busy) else Busy(str(last))
        raise last or DailyLimitReached("no AI provider left")


PROVIDERS = {"groq": GroqProvider, "gemini": GeminiProvider, "ollama": OllamaProvider}
AUTO_CHAIN = ["groq:openai/gpt-oss-120b", "groq:qwen/qwen3.8-27b", "groq:openai/gpt-oss-20b", "gemini", "ollama"]


def get_provider():
    load_dotenv()
    setting = os.getenv("AI_PROVIDER", "auto").strip().lower()
    auto = setting in ("auto", "")
    items = AUTO_CHAIN if auto else [s.strip() for s in setting.split(",") if s.strip()]
    if setting == "groq":  # the Groq models only, each with its own daily quota
        items = [s for s in AUTO_CHAIN if s.startswith("groq")]
    providers, problems = [], []
    for item in items:
        name, _, model = item.partition(":")
        if name not in PROVIDERS:
            raise AIError(f"unknown AI provider {name!r}; use {sorted(PROVIDERS)} or auto")
        try:
            providers.append(PROVIDERS[name](model or None))
        except AIError as exc:  # missing key / server not running: skip it
            problems.append(str(exc))
    if not providers:
        raise AIError("no AI provider available: " + "; ".join(problems))
    return ChainProvider(providers)


def _error_body(resp):
    try:
        body = resp.json()
    except ValueError:
        return {"message": resp.text[:200]}
    if isinstance(body, list):
        body = body[0] if body else {}
    err = body.get("error", {}) if isinstance(body, dict) else {}
    return err if isinstance(err, dict) else {"message": str(err)}


def _retry_after(resp, message):
    """Seconds to wait: the retry-after header, or Gemini's "Please retry in 41.9s" in the message."""
    if resp.headers.get("retry-after"):
        return float(resp.headers["retry-after"])
    match = re.search(r"retry in ([\d.]+)s", message)
    return float(match.group(1)) if match else 20.0


def _error_code(resp):
    return _error_body(resp).get("code")


def _error_message(resp):
    return str(_error_body(resp).get("message", ""))[:500]
