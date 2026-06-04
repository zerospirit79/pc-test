"""Test result form (port of step-gui.sh)."""

from __future__ import annotations

import locale
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from pc_test.constants import TEST_BLOCKED, TEST_FAILED, TEST_PASSED, TEST_SKIPPED
from pc_test.context import RuntimeContext


def _utf8_lang() -> str:
    lang = os.environ.get("LANG", "ru_RU.UTF-8")
    if "UTF-8" not in lang.upper():
        lang = "ru_RU.UTF-8" if lang.lower().startswith("ru") else "en_US.UTF-8"
    return lang


def _gui_env() -> dict[str, str]:
    """UTF-8 locale for yad/tk dialogs.

    Root steps (collect, cpupower, …) set LC_ALL=C for command output; that locale
    must not leak into GUI subprocess argv encoding or yad fails on Cyrillic text.
    """
    lang = _utf8_lang()
    env = os.environ.copy()
    env["LANG"] = lang
    env["LC_ALL"] = lang
    env["LC_CTYPE"] = lang
    os.environ["LANG"] = lang
    os.environ["LC_ALL"] = lang
    os.environ["LC_CTYPE"] = lang
    for candidate in (lang, "C.UTF-8", "en_US.UTF-8"):
        try:
            locale.setlocale(locale.LC_ALL, candidate)
            break
        except locale.Error:
            continue
    return env


def _open_help_section(ctx: RuntimeContext, fragment: str) -> None:
    if not fragment or not ctx.helpfile or not Path(ctx.helpfile).is_file():
        return
    url = f"file://{ctx.helpfile}#{quote(fragment)}"
    stderr = open(ctx.xorglog, "a") if ctx.xorglog else subprocess.DEVNULL
    subprocess.run(["xdg-open", url], stderr=stderr, env=_gui_env(), check=False)


def _run_capture(
    ctx: RuntimeContext,
    cmd,
    *,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command and capture stdout; append stderr to xorg.log (Python 3.12-safe)."""
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=shell, env=_gui_env())
    if proc.stderr and ctx.xorglog:
        with open(ctx.xorglog, "a", encoding="utf-8") as lf:
            lf.write(proc.stderr)
    return proc


def _yad_major_version() -> int:
    try:
        out = subprocess.run(["yad", "--version"], capture_output=True, text=True, check=False)
        if out.stdout:
            return int(
                out.stdout.split(".")[0].split()[-1]
                if " " in out.stdout
                else out.stdout.split(".")[0]
            )
        return 0
    except (ValueError, OSError):
        return 0


def form_gui(ctx: RuntimeContext, fragment: str = "", title: Optional[str] = None) -> int:
    """Show methodology result form; returns TEST_* status code."""
    ctx.append_xorglog(
        f"*** forms.py::form_gui()\n*** fragment={fragment}\n*** number={ctx.number}\n"
    )
    title = title or ctx.nls_title(getattr(ctx, "en_name", ""), getattr(ctx, "ru_name", ""))
    tmpf = tempfile.NamedTemporaryFile(prefix=f"{ctx.progname}-", delete=False)
    tmp_path = tmpf.name
    tmpf.close()

    text = ctx.L(
        "L321",
        "Without closing windows of this program, perform testing according to "
        "section %s of the methodology, and indicate the result here.",
    )
    section = ctx.number or "0"
    try:
        msg = text % (section,)
    except TypeError:
        msg = text.replace("%s", section, 1)

    _open_help_section(ctx, fragment)

    l300 = ctx.L("L300", "Passed")
    l304 = ctx.L("L304", "Skipped")
    l306 = ctx.L("L306", "Blocked")
    l308 = ctx.L("L308", "Failed")

    yad_ver = _yad_major_version()
    if yad_ver >= 7:
        rc = _buttons_form(ctx, title, msg, tmp_path, l300, l304, l306, l308)
    elif shutil.which("yad"):
        rc = _select_form(ctx, title, msg, tmp_path, l300, l304, l306, l308)
    else:
        rc = TEST_BLOCKED
        try:
            rc = form_gui_tkinter(ctx, fragment, title)
        except Exception:
            rc = TEST_BLOCKED

    ctx.append_xorglog(f"*** rc={rc}\n")
    return rc


def _buttons_form(
    ctx: RuntimeContext,
    title: str,
    msg: str,
    tmp_path: str,
    l300: str,
    l304: str,
    l306: str,
    l308: str,
) -> int:
    ctx.append_xorglog("*** buttons_form()\n")
    l302 = ctx.L("L302", "Clear")
    l303 = ctx.L("L303", "Clear this form")
    l309 = ctx.L("L309", "The test was passed with errors or incompletely")
    l301 = ctx.L(
        "L301",
        "The test was successfully passed and the expected result was obtained.",
    )
    l305 = ctx.L("L305", "The test was not performed.")
    l307 = ctx.L("L307", "It is not possible to perform this test.")
    l320 = ctx.L("L320", "Comments")

    status_map = {0: TEST_PASSED, 2: TEST_SKIPPED, 3: TEST_BLOCKED, 4: TEST_FAILED}
    rc = TEST_FAILED
    while True:
        proc = _run_capture(
            ctx,
            [
                "yad",
                "--on-top",
                "--mouse",
                "--always-print-result",
                "--width=620",
                "--window-icon=utilities-system-monitor",
                "--separator=",
                "--item-separator=,",
                f"--title={title}",
                f"--text={msg}",
                f"--button={l300}!gtk-ok!{l301}",
                f"--button={l302}!view-refresh!{l303}",
                f"--button={l304}!system-run!{l305}",
                f"--button={l306}!list-remove!{l307}",
                f"--button={l308}!gtk-no!{l309}",
                "--form",
                f"--field={l320}:TXT",
            ],
        )
        yad_rc = proc.returncode
        if yad_rc in status_map:
            rc = status_map[yad_rc]
            if proc.stdout:
                Path(tmp_path).write_text(proc.stdout, encoding="utf-8")
            break
        if yad_rc in (1, 252):
            Path(tmp_path).unlink(missing_ok=True)
            continue
        break

    _save_comments(ctx, tmp_path)
    return rc


def _select_form(
    ctx: RuntimeContext,
    title: str,
    msg: str,
    tmp_path: str,
    l300: str,
    l304: str,
    l306: str,
    l308: str,
) -> int:
    ctx.append_xorglog("*** select_form()\n")
    l322 = ctx.L("L322", "Result")
    l320 = ctx.L("L320", "Comments")
    rc = TEST_FAILED
    while True:
        proc = _run_capture(
            ctx,
            [
                "yad",
                "--on-top",
                "--mouse",
                "--always-print-result",
                "--width=620",
                "--window-icon=utilities-system-monitor",
                "--separator=|",
                "--item-separator=,",
                f"--title={title}",
                f"--text={msg}",
                "--form",
                f"--field={l322}:CB",
                f"--field={l320}:TXT",
                f"{l300},{l304},{l306},{l308}",
            ],
        )
        if proc.returncode == 0:
            lines = (proc.stdout or "").splitlines()
            choice = lines[0].split("|")[0] if lines else ""
            comments = ""
            if lines:
                rest = lines[0]
                if "|" in rest:
                    comments = rest.split("|", 1)[1]
                elif len(lines) > 1:
                    comments = "\n".join(lines[1:])
            if choice == l300:
                rc = TEST_PASSED
            elif choice == l304:
                rc = TEST_SKIPPED
            elif choice == l306:
                rc = TEST_BLOCKED
            else:
                rc = TEST_FAILED
            if comments.strip():
                Path(f"comments-{ctx.number or 0}.txt").write_text(
                    comments + "\n", encoding="utf-8"
                )
            break
    Path(tmp_path).unlink(missing_ok=True)
    return rc


def _save_comments(ctx: RuntimeContext, tmp_path: str) -> None:
    p = Path(tmp_path)
    if p.is_file():
        text = p.read_text(encoding="utf-8").strip()
        if text:
            dest = Path(f"comments-{ctx.number or 0}.txt")
            p.rename(dest)
        else:
            p.unlink(missing_ok=True)


def form_gui_tkinter(ctx: RuntimeContext, fragment: str = "", title: Optional[str] = None) -> int:
    """Tkinter dialog (primary UI); returns TEST_BLOCKED if display unavailable."""
    import tkinter as tk
    from tkinter import scrolledtext, ttk

    title = title or "PC-Test"
    result = {"rc": TEST_FAILED}

    root = tk.Tk()
    root.title(title)
    root.geometry("620x400")

    text = ctx.L("L321", "Perform testing per section %s and record the result.")
    section = ctx.number or "0"
    try:
        text = text % (section,)
    except TypeError:
        text = text.replace("%s", section, 1)
    tk.Label(root, text=text, wraplength=580).pack(padx=10, pady=10)
    tk.Label(root, text=ctx.L("L320", "Comments")).pack(anchor="w", padx=10)
    comments = scrolledtext.ScrolledText(root, height=8, width=70)
    comments.pack(padx=10, pady=5)

    def set_rc(code: int) -> None:
        result["rc"] = code
        c = comments.get("1.0", "end").strip()
        if c:
            Path(f"comments-{ctx.number or 0}.txt").write_text(c + "\n", encoding="utf-8")
        root.destroy()

    btn_frame = ttk.Frame(root)
    btn_frame.pack(pady=10)
    for label, code in [
        (ctx.L("L300", "Passed"), TEST_PASSED),
        (ctx.L("L304", "Skipped"), TEST_SKIPPED),
        (ctx.L("L306", "Blocked"), TEST_BLOCKED),
        (ctx.L("L308", "Failed"), TEST_FAILED),
    ]:
        ttk.Button(btn_frame, text=label, command=lambda c=code: set_rc(c)).pack(
            side="left", padx=5
        )

    _open_help_section(ctx, fragment)
    root.mainloop()
    return result["rc"]
