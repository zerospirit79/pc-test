"""Installed paths (libexec vs usrmerge /usr/lib/pc-test)."""

from __future__ import annotations

from pathlib import Path

PROGNAME = "pc-test"


def libexec_dir() -> Path:
    """Directory with l10n/, launcher.py, resume.py (not the Python package)."""
    for candidate in (
        Path(f"/usr/libexec/{PROGNAME}"),
        Path(f"/usr/lib/{PROGNAME}"),
    ):
        if (candidate / "l10n").is_dir():
            return candidate
    dev = Path(__file__).resolve().parent.parent.parent / "usr" / "libexec" / PROGNAME
    if (dev / "l10n").is_dir():
        return dev
    return Path(f"/usr/libexec/{PROGNAME}")
