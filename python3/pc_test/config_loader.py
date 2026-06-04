"""Load /etc/pc-test.conf and user overrides."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any


def _apply_line(ctx: Any, line: str) -> None:
    line = line.strip()
    if not line or line.startswith("#"):
        return
    if "=" not in line:
        return
    key, _, raw = line.partition("=")
    key = key.strip()
    raw = raw.strip()
    if not key or not hasattr(ctx, key):
        return
    if raw.startswith("(") and raw.endswith(")"):
        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            value = raw
    else:
        value = raw.strip("'\"")
    setattr(ctx, key, value)


def load_config_files(ctx: Any, *paths: Path) -> None:
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            _apply_line(ctx, line)


def detect_langid() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        if val:
            base = val.split(".")[0].split("_")[0]
            if base:
                return base
    return "en"
