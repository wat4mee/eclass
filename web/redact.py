"""Masks secrets in every log record of the process: passwords, eClass session cookies, tokens, API keys and
Fernet-encrypted values, in the message, its arguments and exception tracebacks.

install() puts the filter into the log record factory, so it applies to all loggers (Flask, werkzeug, gunicorn,
requests, the sync job) whatever handlers they use. The code must still never log a secret on purpose; this is
the safety net.
"""
import logging
import re

MASK = "[REDACTED]"

# key=value, key: value, "key": "value" for secret-looking keys (form data, URLs, JSON, dict reprs, headers)
_KEY_VALUE = re.compile(r"""(?ix)
    (?P<key>["']?(?:\w*(?:passw(?:or)?d|pwd|secret|token|api[_-]?key|cookie|credential|session)\w*
                   |\bpass\b|\bkey\b|\bauthorization\b|\bset-cookie\b)["']?)
    (?P<sep>\s*[=:]\s*)
    (?P<value>"[^"]*"|'[^']*'|[^\s&;,'"}]+)""")
_MOODLE_COOKIE = re.compile(r"(?i)\b(MoodleSession\w*)=([^;\s&]+)")
_BEARER = re.compile(r"(?i)\b(Bearer)\s+([A-Za-z0-9._~+/=-]{8,})")
_LITERALS = [
    re.compile(r"\bgAAAAA[A-Za-z0-9_\-=]{20,}"),                                           # Fernet tokens
    re.compile(r"\b(?:AIza[0-9A-Za-z_\-]{30,}|gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{20,})"),  # AI API keys
    re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{30,}"),                                       # Telegram bot tokens
]


def redact(text: str) -> str:
    if not text:
        return text
    # "Bearer <token>" and cookie pairs first: the key=value rule would only mask the word after "Authorization:"
    text = _BEARER.sub(lambda m: f"{m[1]} {MASK}", text)
    text = _MOODLE_COOKIE.sub(lambda m: f"{m[1]}={MASK}", text)
    text = _KEY_VALUE.sub(lambda m: f"{m['key']}{m['sep']}{MASK}", text)
    for pattern in _LITERALS:
        text = pattern.sub(MASK, text)
    return text


class RedactingFilter(logging.Filter):
    """Rewrites a record in place: formatted message and traceback are redacted, arguments are dropped."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a malformed format string must not hide the record
            message = str(record.msg)
        record.msg, record.args = redact(message), None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


_FILTER = RedactingFilter()
_installed = False


def install() -> None:
    """Redact every record created from now on (idempotent)."""
    global _installed
    if _installed:
        return
    make_record = logging.getLogRecordFactory()

    def redacting_factory(*args, **kwargs):
        record = make_record(*args, **kwargs)
        _FILTER.filter(record)
        return record
    logging.setLogRecordFactory(redacting_factory)
    _installed = True
