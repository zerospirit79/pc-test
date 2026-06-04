"""Test plan configuration forms (config-form-gui.sh / config-form-tui.sh)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import List, Tuple

from pc_test import l10n
from pc_test.config_loader import load_config_files
from pc_test.context import FatalError, RuntimeContext, graphical_session
from pc_test.gui.forms import _run_capture


def _test_enabled(ctx: RuntimeContext, tag: str) -> bool:
    val = str(getattr(ctx, f"{tag}_test", "") or "").strip().strip("'\"")
    return val in ("1", "yes", "true", "on")


def sync_detected_hardware(ctx: RuntimeContext) -> None:
    """Apply flags saved by the detect step (and derived disk/GPU tests)."""
    wd = Path(ctx.workdir)
    settings = wd / "STATE" / "settings.ini"
    detect = wd / "detect.ini"
    if settings.is_file():
        load_config_files(ctx, settings)
    if detect.is_file():
        load_config_files(ctx, detect)

    if ctx.drives.strip() and not _test_enabled(ctx, "fio"):
        ctx.fio_test = "1"
    if ctx.have_xorg and graphical_session() and not _test_enabled(ctx, "v3d"):
        proc = subprocess.run(["inxi", "-G", "-c0"], capture_output=True, text=True)
        if re.search(r" Device-1: ", proc.stdout or ""):
            ctx.v3d_test = "1"
    if ctx.has_binary("fwupdmgr") and not _test_enabled(ctx, "fwupd"):
        ctx.fwupd_test = "1"


def _test_flags(ctx: RuntimeContext) -> tuple[List[Tuple[str, str, bool]], str]:
    sync_detected_hardware(ctx)
    mate_item, tests_list, _ = l10n.load_config_menu(ctx.langid, ctx.libdir)
    items = [(tag, label, _test_enabled(ctx, tag)) for tag, label in tests_list]
    return items, mate_item


def run_gui(ctx: RuntimeContext) -> None:
    """YAD checklist form for optional tests."""
    items, _ = _test_flags(ctx)
    title = ctx.nls_title("Defining a Test Plan", "Определение плана тестирования")
    argv = [
        "yad",
        "--borders=15",
        "--form",
        "--window-icon=utilities-system-monitor",
        "--separator= ",
        f"--title={title}",
    ]
    # YAD expects TRUE/FALSE immediately after each CHK field (not all fields, then all values).
    for _tag, label, enabled in items:
        argv.append(f"--field={label}:CHK")
        argv.append("TRUE" if enabled else "FALSE")

    proc = _run_capture(ctx, argv)
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        ctx.fatal("F20", "Testing canceled.")
    values = proc.stdout.split()
    for i, (tag, _label, _enabled) in enumerate(items):
        setattr(ctx, f"{tag}_test", "1" if i < len(values) and values[i] == "TRUE" else "")


def run_tui(ctx: RuntimeContext, can_install_mate: bool = False) -> None:
    """dialog checklist for optional tests."""
    items, mate_item = _test_flags(ctx)
    version = os.environ.get("PCTEST_VERSION", "")
    build = os.environ.get("PCTEST_BUILD_DATE", "")
    v = f"v{version}/{build}"
    title = ctx.nls_title("Defining a Test Plan", "Определение плана тестирования")
    _, _, tui_width = l10n.load_config_menu(ctx.langid, ctx.libdir)
    n = len(items)
    h = n // 2 + (1 if can_install_mate else 0)
    height = 6 + h

    cmd: List[str] = [
        "dialog",
        "--no-tags",
        "--shadow",
        "--backtitle",
        f"PC-Test {v}",
        "--title",
        f"[ {title} ]",
        "--checklist",
        '""',
        str(height),
        str(tui_width),
        str(h),
    ]
    if can_install_mate:
        cmd.extend(["mate", f'"{mate_item}"', "off"])
    for tag, label, enabled in items:
        cmd.extend([tag, f'"{label}"', "on" if enabled else "off"])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        ctx.fatal("F20", "Testing canceled.")
    os.system("clear")

    for tag, _label, _ in items:
        setattr(ctx, f"{tag}_test", "")
    ctx.install_mate = ""
    for tag in proc.stdout.split():
        if tag == "mate":
            ctx.install_mate = "1"
        else:
            setattr(ctx, f"{tag}_test", "1")


def run_config_form(ctx: RuntimeContext) -> None:
    """Choose GUI or TUI based on environment."""
    sync_detected_hardware(ctx)
    if graphical_session() and ctx.has_binary("yad"):
        run_gui(ctx)
    elif ctx.has_binary("dialog"):
        run_tui(ctx)
    else:
        raise FatalError(1)
