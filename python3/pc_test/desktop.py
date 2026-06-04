"""Desktop autostart helpers."""

from __future__ import annotations

import os
from pathlib import Path

from pc_test.context import graphical_session


def _autostart_desktop_text(progname: str) -> str:
    """Autostart entry with the real install path (usrmerge: /usr/lib/pc-test)."""
    resume = libexec_dir() / "resume.py"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={progname} resume\n"
        "Comment=Resume PC Test after reboot\n"
        "Icon=utilities-system-monitor\n"
        f"Exec={resume}\n"
        "Terminal=false\n"
        "Hidden=false\n"
        "NoDisplay=false\n"
        "OnlyShowIn=KDE;GNOME;XFCE;MATE;\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=10\n"
        "X-KDE-StartupCondition=desktop\n"
        "X-KDE-autostart-after=panel\n"
        "Categories=System;Utility;\n"
    )


def _read_autostart_template(progname: str) -> str:
    path = Path(f"/usr/share/applications/{progname}-autostart.desktop")
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lib = str(libexec_dir())
    if text:
        return text.replace("@pc_test_libdir@", lib)
    return _autostart_desktop_text(progname)


def copy_desktop_file(
    progname: str, homedir: str, disable_autorun: str, *, force: bool = False
) -> None:
    if disable_autorun or not homedir:
        return
    if not force and (os.geteuid() == 0 or not graphical_session()):
        return
    autostart = Path(homedir) / ".config" / "autostart"
    autostart.mkdir(parents=True, mode=0o700, exist_ok=True)
    dst = autostart / f"{progname}.desktop"
    dst.write_text(_read_autostart_template(progname), encoding="utf-8")
    dst.chmod(0o644)


def remove_desktop_file(progname: str, homedir: str) -> None:
    path = Path(homedir) / ".config" / "autostart" / f"{progname}.desktop"
    path.unlink(missing_ok=True)
