"""Command-line interface."""

from __future__ import annotations

import argparse
import datetime
import os
import pwd
import re
import subprocess
from pathlib import Path

from pc_test.config_loader import detect_langid
from pc_test.context import RuntimeContext
from pc_test.version import PCTEST_BUILD_DATE, PCTEST_VERSION


def build_parser(progname: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=progname, add_help=False)
    p.add_argument("-A", "--auto", action="store_const", dest="launchmode", const="auto")
    p.add_argument("-C", "--continue", action="store_const", dest="launchmode", const="continue")
    p.add_argument("-F", "--finish", action="store_const", dest="launchmode", const="finish")
    p.add_argument("-S", "--start", action="store_const", dest="launchmode", const="start")
    p.add_argument("-T", "--test", dest="retestno", metavar="N")
    p.add_argument("-b", "--batch", action="store_true", dest="batchmode")
    p.add_argument("-c", "--color", choices=("always", "never", "auto"), default="auto")
    p.add_argument("-d", "--date", dest="repodate")
    p.add_argument("-n", "--name", dest="compname")
    p.add_argument("--update", action="store_true")
    p.add_argument("--no-sources", action="store_true")
    p.add_argument("--no-update", action="store_true")
    p.add_argument("--no-autorun", action="store_true", dest="disable_autorun_flag")
    p.add_argument("--uid", dest="uid")
    p.add_argument("--desktop-icon", action="store_true", dest="desktop_icon_start")
    p.add_argument("-v", "--version", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    return p


def show_help(ctx: RuntimeContext) -> None:
    path = Path(ctx.libdir) / "l10n" / ctx.langid / "help.msg"
    if not path.is_file():
        path = Path(ctx.libdir) / "l10n" / "en" / "help.msg"
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    print(text.replace("@PROG@", ctx.progname))
    raise SystemExit(0)


def show_version(progname: str) -> None:
    print(f"{progname} {PCTEST_VERSION} {PCTEST_BUILD_DATE}")
    raise SystemExit(0)


def parse_args(ctx: RuntimeContext, argv: list[str]) -> None:
    parser = build_parser(ctx.progname)
    args, extra = parser.parse_known_args(argv)
    if args.version:
        show_version(ctx.progname)
    if args.help:
        show_help(ctx)
    if extra:
        ctx.fatal("F14", "To many argument(s): %s", " ".join(extra))

    if args.retestno:
        if getattr(ctx, "launchmode", None) and ctx.launchmode not in ("", "auto"):
            ctx.fatal("F15", "The program launch mode already specified: '%s'.", ctx.launchmode)
        ctx.launchmode = "retest"
        ctx.retestno = str(args.retestno)
    elif args.launchmode:
        if getattr(ctx, "_launch_set", False):
            ctx.fatal("F15", "The program launch mode already specified: '%s'.", ctx.launchmode)
        ctx.launchmode = args.launchmode
    else:
        ctx.launchmode = ctx.launchmode or "auto"

    if args.batchmode:
        ctx.batchmode = "1"
    ctx.colormode = args.color
    if args.repodate:
        if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", args.repodate):
            ctx.fatal("F12", "Invalid date: '%s'.", args.repodate)
        ctx.repodate = args.repodate
    if args.compname:
        ctx.compname = re.sub(r"[\(\),].*$", "", args.compname.replace(" ", ""))
    if args.update:
        ctx.update_apt_lists = ctx.dist_upgrade = ctx.update_kernel = "1"
    if args.no_sources:
        ctx.update_apt_lists = ""
    if args.no_update:
        ctx.update_apt_lists = ctx.dist_upgrade = ctx.update_kernel = ""
    if args.disable_autorun_flag:
        ctx.disable_autorun = "1"
    if args.desktop_icon_start:
        ctx.desktop_icon_start = "1"
    if args.uid is not None:
        _configure_sudo_uid(ctx, args.uid)
        ctx.launchmode = "continue"

    ctx.langid = detect_langid()
    lib = Path(ctx.libdir) / "l10n" / ctx.langid / "help.msg"
    if not lib.is_file():
        ctx.langid = "en"


def _configure_sudo_uid(ctx: RuntimeContext, user_id: str) -> None:
    if os.geteuid() != 0:
        ctx.fatal("F16", "You must be root for using --uid=<UID>.")
    try:
        if user_id.isdigit():
            pw = pwd.getpwuid(int(user_id))
        else:
            pw = pwd.getpwnam(user_id)
    except (KeyError, ValueError):
        ctx.fatal("F17", "Invalid user ID: '%s'.", user_id)
    if pw.pw_uid == 0:
        ctx.fatal("F17", "Invalid user ID: '%s'.", user_id)
    ctx.username = pw.pw_name
    ctx.homedir = pw.pw_dir
    sudoers = Path("/etc/sudoers")
    marker = f"NOPASSWD: {ctx.scriptname}"
    if sudoers.is_file() and marker not in sudoers.read_text(encoding="utf-8", errors="replace"):
        dmesg = subprocess.run(["which", "dmesg"], capture_output=True, text=True)
        dmesg_path = (dmesg.stdout or "").strip() or "/usr/bin/dmesg"
        with open(sudoers, "a", encoding="utf-8") as f:
            f.write(
                f"\n# Allow {ctx.username} to execute {ctx.progname} and dmesg\n"
                f"{ctx.username} ALL=(ALL:ALL) NOPASSWD: {ctx.scriptname},{dmesg_path}\n"
            )
        flag = Path(ctx.homedir) / ".local/share" / ctx.progname / "sudo.UID"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(datetime.datetime.now().isoformat(), encoding="utf-8")
        os.chown(flag, pw.pw_uid, pw.pw_gid)
        log = Path(f"/var/log/{ctx.progname}.log")
        with open(log, "a", encoding="utf-8") as lf:
            lf.write(f"[{datetime.datetime.now():%F %T}] Sudo configured: {flag}\n")
