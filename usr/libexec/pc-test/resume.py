#!/usr/bin/python3
# Copyright (C) 2024-2026, ALT Linux Team
"""Autorun helper to resume pc-test in a graphical session."""

from __future__ import annotations

import os
from pathlib import Path


def _log(msg: str) -> None:
    try:
        logdir = Path(os.environ.get("HOME", "")) / ".local/share/pc-test"
        logdir.mkdir(parents=True, exist_ok=True)
        with open(logdir / "resume.log", "a", encoding="utf-8") as lf:
            lf.write(msg + "\n")
    except OSError:
        pass


def _state_ready(lastdir: Path, progname: str) -> bool:
    return (
        lastdir.is_symlink()
        and (lastdir / f"{progname}.log").is_file()
        and (lastdir / f"{progname}.log").stat().st_size > 0
        and (lastdir / "STATE" / "STEP").is_file()
        and (lastdir / "STATE" / "STEP").stat().st_size > 0
        and (lastdir / "STATE" / "start.txt").is_file()
    )


def main() -> int:
    progname = "pc-test"
    home = Path(os.environ.get("HOME", ""))
    lastdir = home / "PC-TEST"
    desktopfile = home / ".config" / "autostart" / f"{progname}.desktop"
    cmd = [progname, "--desktop-icon", "--continue"]

    from pc_test.de_terminal import launch_in_terminal, wait_for_display

    if not _state_ready(lastdir, progname):
        _log("resume: state not ready, removing autostart")
        desktopfile.unlink(missing_ok=True)
        return 1

    if not wait_for_display(120):
        _log("resume: DISPLAY not set after 120s")
        return 1

    settings_path = lastdir / "STATE" / "settings.ini"
    try:
        launch_in_terminal(cmd, settings_path, delay=5)
    except SystemExit:
        _log("resume: no suitable terminal emulator found")
        desktopfile.unlink(missing_ok=True)
        return 1
    except OSError as exc:
        _log(f"resume: launch failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
