#!/usr/bin/python3
# Copyright (C) 2024-2026, ALT Linux Team
"""DE-independent terminal launcher for pc-test."""

from __future__ import annotations

import shutil
import subprocess
import sys


def _installed(pkg: str) -> bool:
    return subprocess.run(["rpm", "-q", pkg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def main() -> int:
    cmd = ["pc-test", "--desktop-icon"]
    if _installed("gnome-shell") and _has("kgx"):
        subprocess.execvp("kgx", ["kgx", "-T", "PC Test", "-e", " ".join(cmd)])
    if (_installed("kde") or _installed("kde5") or _installed("plasma6-plasma5support-common")) and _has("konsole"):
        subprocess.execvp("konsole", ["konsole", "-T", "PC Test", "-e", "pc-test", "--desktop-icon"])
    if (_installed("mate-minimal") or _installed("mate-default") or _installed("mate-window-manager")) and _has("mate-terminal"):
        subprocess.execvp("mate-terminal", ["mate-terminal", "--window", "-t", "PC Test", "-e", "pc-test --desktop-icon"])
    if (_installed("xfce4-minimal") or _installed("xfce4-default")) and _has("xfce4-terminal"):
        subprocess.execvp("xfce4-terminal", ["xfce4-terminal", "-T", "PC Test", "-e", "pc-test --desktop-icon"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
