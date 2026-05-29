"""Logging setup for Yaku — console + rotating file, with API-key redaction."""
from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Sensitive-data redaction
# ---------------------------------------------------------------------------

_REDACT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(DeepL-Auth-Key\s+)\S+"),              r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)\S+"),                       r"\1[REDACTED]"),
    (re.compile(r"(Authorization[:\s]+)\S+", re.I),       r"\1[REDACTED]"),
    (re.compile(r"(api[_-]?key['\"]?\s*[:=]\s*['\"]?)\S+", re.I), r"\1[REDACTED]"),
]


def redact(text: str) -> str:
    """Remove API keys and auth tokens from *text*."""
    for pattern, replacement in _REDACT_RULES:
        text = pattern.sub(replacement, text)
    return text


class _SensitiveFilter(logging.Filter):
    """Log filter that scrubs API keys from every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            args = record.args if isinstance(record.args, tuple) else (record.args,)
            record.args = tuple(
                redact(str(a)) if isinstance(a, str) else a for a in args
            )
        return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(
    debug: bool = False,
    log_file: str = "out/yaku.log",
) -> None:
    """Configure the ``yaku`` logger with a console and rotating file handler.

    The file handler writes to *log_file* (max 5 MB, 2 backup files).
    Both handlers filter out API keys and auth tokens via :class:`_SensitiveFilter`.
    """
    level = logging.DEBUG if debug else logging.INFO

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    console.addFilter(_SensitiveFilter())

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    file_handler.addFilter(_SensitiveFilter())

    root = logging.getLogger("yaku")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"yaku.{name}")
