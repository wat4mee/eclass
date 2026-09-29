"""LLM providers returning schema-constrained JSON, chained so a used-up free quota falls through.

AI_PROVIDER in .env:
    auto (default)  Groq gpt-oss-120b -> Groq qwen3.8-27b -> Groq gpt-oss-20b -> Gemini (if GEMINI_API_KEY)
                    -> Ollama (if running); every Groq model has its own daily free quota
    a list          e.g. "gemini,groq:openai/gpt-oss-120b,ollama"  (provider or provider:model)
AI_FALLBACK in .env (optional, same format): models tried last, after every AI_PROVIDER model failed, hit its
limit or was too slow. Time limits: AI_TIMEOUT per request (study packs), AI_CHAT_TIMEOUT per request and
AI_CHAT_BUDGET for a whole chat answer (see eclass/config.py).
API keys are sent only in headers and never appear in logs or exception messages.
"""
import json
import os
import re
import time
from collections import deque

import requests
from dotenv import load_dotenv

from eclass import config, latex


class AIError(RuntimeError):
    pass


class DailyLimitReached(AIError):
    """The provider's daily quota is exhausted; resume on a later run."""


class InvalidKey(AIError):
    """The API key was rejected (revoked, mistyped or pasted into the wrong slot)."""


class Busy(AIError):
    """This model cannot take the request right now (overloaded, per-minute limit, request too large)."""


class AITimeout(Busy):
    """No answer in time: the model is too slow or unreachable, or the caller's time budget is spent."""


def _time_left(deadline, need=3.0):
    """Seconds left before `deadline` (time.monotonic()), or AITimeout when fewer than `need` remain."""
    if deadline is None:
        return None
    left = deadline - time.monotonic()
    if left < need:
        raise AITimeout("time budget used up")
    return left


_ESCAPED_UNICODE = re.compile(r"\\u([0-9a-fA-F]{4})")


def unescape(value):
    """Undo escaping mistakes the models make inside JSON strings: double escaping (bo\\u2018lgan, bo\\'yicha)
    and single backslashes in LaTeX that decoded into control characters (\\frac -> form feed + "rac")."""
    if isinstance(value, str):
        value = _ESCAPED_UNICODE.sub(lambda m: chr(int(m.group(1), 16)), value)
        return latex.repair(value.replace("\\'", "'").replace('\\"', '"'))
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
    deadline = None         # time.monotonic() by which the caller needs the answer (set by the chain)

    def __init__(self, model, timeout=None):
        self._key = os.getenv(self.key_env)
        if not self._key:
            raise AIError(f"{self.key_env} is not set in .env")
        self.model = model
        self.timeout = timeout or config.AI_TIMEOUT  # seconds per HTTP request
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
            self._sleep(60 - (now - self._window[0][0]) + 0.5)

    def _sleep(self, seconds):
        """Wait, unless that would miss the caller's deadline: then let the next model answer instead."""
        left = _time_left(self.deadline)
        if left is not None and seconds > left - 3:
            raise Busy(f"{self.name} {self.model}: would have to wait {seconds:.0f} s")
        time.sleep(seconds)

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
            left = _time_left(self.deadline)
            timeout = min(self.timeout, left) if left is not None else self.timeout
            try:
                resp = requests.post(self.url, json=self._body(system, user, schema, max_tokens), timeout=timeout,
                                     headers={"Authorization": f"Bearer {self._key}"})
            except (requests.Timeout, requests.ConnectionError) as exc:  # slow or unreachable: try the next model
                raise AITimeout(f"{self.name} {self.model}: {type(exc).__name__} after {timeout:.0f} s") from None
            except requests.RequestException as exc:
                raise AIError(f"{self.name}: {type(exc).__name__}") from None
            message = _error_message(resp) if resp.status_code != 200 else ""
            if resp.status_code == 429:
                wait = _retry_after(resp, message)
                if self._is_daily(message, wait):
                    raise DailyLimitReached(f"{self.name} {self.model}: {message}")
                if not self.patient or "too large" in message.lower():  # waiting would not help this call
                    raise Busy(f"{self.name} {self.model}: {message}")
                self._sleep(wait + 1)
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
                self._sleep(3 * retries)
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

    def __init__(self, model=None, timeout=None):
        super().__init__(model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), timeout)
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

    def __init__(self, model=None, timeout=None):
        super().__init__(model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"), timeout)

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
    deadline = None

    def __init__(self, model=None, timeout=None):
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3:14b")
        self.timeout = timeout or config.OLLAMA_TIMEOUT
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
        left = _time_left(self.deadline)
        timeout = min(self.timeout, left) if left is not None else self.timeout
        try:
            resp = requests.post(self.url, json=body, timeout=timeout)
        except requests.Timeout:
            raise AITimeout(f"ollama {self.model}: no answer after {timeout:.0f} s") from None
        except requests.RequestException as exc:
            raise AIError(f"ollama not reachable at {self.url}: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise AIError(f"ollama {resp.status_code}: {_error_message(resp)}")
        return unescape(json.loads(resp.json()["message"]["content"]))


class ChainProvider:
    """Uses the first provider whose daily quota is not used up; name/model tell who answered last."""

    def __init__(self, providers, deadline=None):
        self.providers = providers
        self.deadline = deadline  # time.monotonic() by which every call must be answered (chat), or None
        self.name, self.model = providers[0].name, providers[0].model

    def complete_json(self, system, user, schema, max_tokens):
        last = None
        for provider in list(self.providers):
            _time_left(self.deadline)
            provider.deadline = self.deadline
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


def _items(setting):
    return [s.strip() for s in setting.lower().split(",") if s.strip()]


def get_provider(timeout=None, deadline=None):
    """The configured provider chain. `timeout`: seconds per HTTP request (default AI_TIMEOUT);
    `deadline`: time.monotonic() by which each call must be answered, whatever model ends up answering."""
    load_dotenv()
    setting = os.getenv("AI_PROVIDER", "auto").strip().lower()
    auto = setting in ("auto", "")
    items = AUTO_CHAIN if auto else _items(setting)
    if setting == "groq":  # the Groq models only, each with its own daily quota
        items = [s for s in AUTO_CHAIN if s.startswith("groq")]
    items = items + [s for s in _items(os.getenv("AI_FALLBACK", "")) if s not in items]
    providers, problems = [], []
    for item in items:
        name, _, model = item.partition(":")
        if name not in PROVIDERS:
            raise AIError(f"unknown AI provider {name!r}; use {sorted(PROVIDERS)} or auto")
        try:
            providers.append(PROVIDERS[name](model or None, timeout))
        except AIError as exc:  # missing key / server not running: skip it
            problems.append(str(exc))
    if not providers:
        raise AIError("no AI provider available: " + "; ".join(problems))
    return ChainProvider(providers, deadline)


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
