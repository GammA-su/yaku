"""Local environment file loading."""
from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path = ".env", *, override: bool = False) -> dict[str, str]:
    """Load KEY=VALUE pairs from *path* into ``os.environ``.

    This intentionally implements the small subset Yaku needs instead of adding
    a runtime dependency: blank lines, comments, optional ``export``, and quoted
    values are supported. Existing environment variables win unless
    ``override`` is true.
    """
    env_path = Path(path)
    if not env_path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            continue

        value = _strip_inline_comment(value.strip())
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return loaded


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    for index, char in enumerate(value):
        if char in {"'", '"'}:
            quote = None if quote == char else char
        elif char == "#" and quote is None:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value
