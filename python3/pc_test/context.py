"""Runtime context and helpers shared by pc-test steps."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pc_test import l10n
from pc_test.constants import (
    TEST_ALLOWED,
    TEST_BLOCKED,
    TEST_PASSED,
    TEST_RUNNING,
    TEST_SKIPPED,
)
from pc_test.internal_vars import SETTINGS_KEYS


def graphical_session(environ: os._Environ | None = None) -> bool:
    """True when an X11 or Wayland desktop session is active."""
    env = environ or os.environ
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


class FatalError(SystemExit):
    """Fatal error matching bash fatal()."""

    def __init__(self, code: int = 1) -> None:
        super().__init__(code)
        self.code = code


class RuntimeContext:
    """Global runtime state and shell-compatible helpers."""

    update_apt_lists: Optional[str] = "1"
    dist_upgrade: Optional[str] = "1"
    update_kernel: Optional[str] = "1"
    local_url: str = ""
    local_mirror: str = ""
    mirror_subdir: str = ""
    local_media_base: str = ""
    local_media_labels: List[str] = None  # type: ignore
    local_media_check: str = ""
    unsafe_diskperf: str = ""
    disable_autorun: str = ""
    ping_server: str = "ya.ru"
    express_video_set: str = "vkvideo"
    local_video_sample: str = ""

    batchmode: str = ""
    colormode: str = ""
    launchmode: str = ""
    repodate: str = ""
    compname: str = ""
    username: str = ""
    homedir: str = ""
    rundir: str = ""
    langid: str = "en"

    # system
    have_altsp: str = ""
    have_systemd: str = ""
    install_mate: str = ""
    distroname: str = ""
    distro: str = ""
    repo: str = ""

    # graphics
    have_xorg: str = ""
    have_kde5: str = ""
    have_mate: str = ""
    have_xfce: str = ""
    have_gnome: str = ""

    # hardware
    archname: str = ""
    pctype: str = ""
    drives: str = ""
    ifaces: str = ""

    # tests
    fwupd_test: str = ""
    devel_test: str = ""
    xprss_test: str = ""
    infb_test: str = ""
    sound_test: str = ""
    numa_test: str = ""
    ipmi_test: str = ""
    webcam_test: str = ""
    power_test: str = ""
    fprnt_test: str = ""
    bluez_test: str = ""
    scard_test: str = ""
    fio_test: str = ""
    v3d_test: str = ""

    retestno: str = ""
    usertype: str = ""
    testplan: str = "start.txt"
    desktop_icon_start: str = ""

    # paths (set by main)
    progname: str = "pc-test"
    libdir: str = ""
    workdir: str = ""
    logfile: str = ""
    xorglog: str = ""
    helpfile: str = ""
    scriptname: str = ""
    stepname: str = ""
    status: int = TEST_ALLOWED
    number: str = ""

    # console colors
    CLR_NORM: str = "\033[00m"
    CLR_BOLD: str = "\033[01;37m"
    CLR_LC1: str = "\033[00;36m"
    CLR_LC2: str = "\033[00;35m"
    CLR_OK: str = "\033[01;32m"
    CLR_ERR: str = "\033[01;31m"
    CLR_WARN: str = "\033[01;33m"

    def __init__(self) -> None:
        if self.local_media_labels is None:
            self.local_media_labels = []
        self._messages: Dict[str, str] = {}
        self._fatal: Dict[str, str] = {}

    def load_nls(self) -> None:
        self._messages = l10n.load_messages(self.langid, self.libdir)
        self._fatal = l10n.load_fatal(self.langid, self.libdir)

    def L(self, key: str, default: str = "") -> str:
        return l10n.msg(self._messages, key, default)

    def nls_title(self, en_name: str, ru_name: str) -> str:
        if self.langid == "ru":
            return ru_name
        return en_name

    def cmd_title(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{self.CLR_BOLD}{ts}{self.CLR_NORM}] "
        if text.startswith(": "):
            prefix = f"{self.CLR_ERR}:" if os.geteuid() == 0 else f"{self.CLR_OK}:"
            line += f"{prefix} {self.CLR_LC1}{text[2:]}{self.CLR_NORM}\n"
        else:
            prefix = f"{self.CLR_ERR}#" if os.geteuid() == 0 else f"{self.CLR_OK}$"
            line += f"{prefix} {self.CLR_LC1}{text}{self.CLR_NORM}\n"
        self._write_stderr(line)

    def spawn(self, *args: str, check: bool = False) -> int:
        if len(args) == 1 and args[0].startswith(": "):
            self.cmd_title(args[0])
            return 0
        cmd = list(args)
        self.cmd_title(" ".join(cmd))
        try:
            proc = subprocess.run(cmd, check=False)
            rc = proc.returncode
        except KeyboardInterrupt:
            self.fatal("F20", "Testing canceled.")
        except OSError:
            rc = 127
        if check and rc != 0:
            raise subprocess.CalledProcessError(rc, cmd)
        return rc

    def spawn2(self, *args: str) -> int:
        self.cmd_title(" ".join(args))
        try:
            return subprocess.run(args, check=False).returncode
        except KeyboardInterrupt:
            self.fatal("F20", "Testing canceled.")

    def spawn_capture(self, *args: str, text: bool = True) -> subprocess.CompletedProcess:
        self.cmd_title(" ".join(args))
        try:
            return subprocess.run(args, capture_output=True, text=text, check=False)
        except KeyboardInterrupt:
            self.fatal("F20", "Testing canceled.")

    def _write_stderr(self, text: str) -> None:
        sys.stderr.write(text)
        sys.stderr.flush()
        if self.logfile and Path(self.logfile).is_file():
            with open(self.logfile, "a", encoding="utf-8", errors="replace") as lf:
                lf.write(text)

    def _tee_log(self, text: str) -> None:
        sys.stderr.write(text)
        if self.logfile:
            with open(self.logfile, "a", encoding="utf-8", errors="replace") as lf:
                lf.write(text)

    def has_binary(self, name: str) -> bool:
        """Return True if executable exists (replaces bash builtin ``type -p``)."""
        if "/" in name:
            path = Path(name)
            return path.is_file() and os.access(path, os.X_OK)
        return shutil.which(name) is not None

    def is_pkg_installed(self, *pkgs: str) -> bool:
        return (
            subprocess.run(
                ["rpm", "-q", "--", *pkgs],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )

    def is_pkg_available(self, *pkgs: str) -> bool:
        return (
            subprocess.run(
                ["apt-cache", "show", "--", *pkgs],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )

    def in_array(self, needle: str, haystack: Sequence[str]) -> bool:
        return needle in haystack

    def bold(self, text: str) -> str:
        if not self.colormode:
            return text
        return f"{self.CLR_BOLD}{text}{self.CLR_NORM}"

    def fatal(self, fcode: str, fmt: str, *args: Any) -> None:
        key = fcode.lstrip("F")
        msg_fmt = self._fatal.get(f"F{key}", fmt)
        try:
            message = msg_fmt % args if args else msg_fmt
        except TypeError:
            message = msg_fmt
        ts = datetime.now().strftime("%H:%M:%S")
        line = (
            f"[{self.CLR_ERR}{ts}{self.CLR_NORM}] "
            f"{self.CLR_ERR}{self.progname} fatal[{key}]: {message}{self.CLR_NORM}\n"
        )
        self._write_stderr(line)
        raise FatalError(1)  # noqa: B904

    def _format_title_line(self, rc: int, no: str, text: str) -> str:
        """Return a colored result line without trailing newline."""
        n = self.CLR_NORM
        if rc == TEST_RUNNING:
            return (
                f"{self.CLR_WARN}Running{n}... "
                f"{self.CLR_WARN}{no}. {self.CLR_LC2}{text}{n}"
            )
        if rc == TEST_PASSED:
            accent, tag = self.CLR_OK, "PASSED  "
        elif rc == TEST_SKIPPED:
            accent, tag = self.CLR_WARN, "SKIPPED "
        elif rc == TEST_BLOCKED:
            accent, tag = self.CLR_ERR, "BLOCKED "
        else:
            accent, tag = self.CLR_ERR, "FAILED  "
        return f"[{accent}{tag}{n}] {accent}{no}. {n}{self.CLR_LC2}{text}{n}"

    def _write_result_line(self, line: str, *, log: bool) -> None:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
        if log and self.logfile and Path(self.logfile).is_file():
            with open(self.logfile, "a", encoding="utf-8", errors="replace") as lf:
                lf.write(line + "\n")

    def draw_title_line(self, rc: int, no: str, text: str, *, log: bool | None = None) -> None:
        if log is None:
            log = rc != TEST_RUNNING
        self._write_result_line(self._format_title_line(rc, no, text), log=log)

    def log_step_result(self, status: int) -> None:
        """Append step outcome lines to pc-test.log (and terminal)."""
        if not self.stepname:
            return
        from pc_test.steps import create_step

        step = create_step(self.stepname, self)
        step.show_results(status, log=True)
        self.draw_title_line(
            status,
            str(getattr(step, "number", self.number)),
            step.title(),
            log=True,
        )

    def write_config(self) -> None:
        sf = Path(self.workdir) / "STATE" / "settings.ini"
        sf.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for key in SETTINGS_KEYS:
            value = getattr(self, key, "")
            if value is None:
                value = ""
            if isinstance(value, list):
                value = " ".join(value)
            lines.append(f"{key}={shlex.quote(str(value))}\n")
        sf.write_text("".join(lines), encoding="utf-8")
        if os.geteuid() == 0 and self.username:
            subprocess.run(
                ["chown", f"{self.username}:{self.username}", str(sf)],
                check=False,
            )

    def print_settings_ini(self, outfile: str) -> None:
        self.write_config()
        src = Path(self.workdir) / "STATE" / "settings.ini"
        dst = Path(self.workdir) / outfile
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        for line in src.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip("'\"")
            print(f"{self.CLR_LC1}{k}{self.CLR_BOLD}={self.CLR_LC2}{v}{self.CLR_NORM}")

    def chown_workdir_for_user(self) -> None:
        """After root steps, ensure the test user owns workdir (autostart/continue)."""
        if os.geteuid() != 0 or not self.username:
            return
        wd = Path(self.workdir)
        subprocess.run(
            ["chown", "-R", f"{self.username}:{self.username}", str(wd)],
            check=False,
        )
        link = Path(self.homedir or "") / "PC-TEST"
        if link.is_symlink() and link.resolve() == wd.resolve():
            subprocess.run(
                ["chown", "-h", f"{self.username}:{self.username}", str(link)],
                check=False,
            )

    def break_step(self, status: int = TEST_PASSED) -> None:
        self.status = status
        os.chdir(self.workdir)
        if os.geteuid() == 0 and self.username:
            tmp_root = Path("TMP-ROOT")
            if tmp_root.is_dir():
                subprocess.run(
                    ["chown", "-R", f"{self.username}:{self.username}", str(tmp_root)],
                    check=False,
                )
                for p in tmp_root.iterdir():
                    dest = Path(self.workdir) / p.name
                    try:
                        p.rename(dest)
                    except OSError:
                        pass
                import shutil

                shutil.rmtree(tmp_root, ignore_errors=True)
        state = Path("STATE")
        if state.is_dir():
            (state / "STATUS").write_text(f"{status}\n", encoding="utf-8")
            if os.geteuid() == 0 and self.username:
                subprocess.run(
                    ["chown", f"{self.username}:{self.username}", "STATE/STATUS"],
                    check=False,
                )
        self.log_step_result(status)
        if not self.have_next_step():
            from pc_test.desktop import remove_desktop_file

            remove_desktop_file(self.progname, self.homedir or os.environ.get("HOME", ""))
        self.chown_workdir_for_user()

    def _plan_entries(self, content: str) -> list[str]:
        return [ln.strip() for ln in content.splitlines() if ln.strip() and "\t" in ln]

    def _step_from_plan_line(self, line: str) -> str:
        return line.split("\t", 1)[-1].strip()

    def have_next_step(self) -> bool:
        planfile = Path(self.workdir) / "STATE" / getattr(self, "testplan", "start.txt")
        statfile = Path(self.workdir) / "STATE" / "STATUS"
        stepfile = Path(self.workdir) / "STATE" / "STEP"
        if not planfile.is_file():
            return False
        content = planfile.read_text(encoding="utf-8")
        if not re.search(rf"\s{re.escape(self.stepname)}$", content, re.M):
            return False
        stepfile.unlink(missing_ok=True)
        status_val = getattr(self, "status", TEST_PASSED)
        if statfile.is_file() and statfile.stat().st_size:
            status_val = int(statfile.read_text().splitlines()[0] or "0")
            statfile.unlink()
        lines = self._plan_entries(content)
        remaining = [ln for ln in lines if not re.search(rf"\s{re.escape(self.stepname)}$", ln)]
        planfile.write_text(
            ("\n".join(remaining) + "\n") if remaining else "",
            encoding="utf-8",
        )
        if lines:
            results = Path(self.workdir) / "STATE" / "RESULTS"
            with open(results, "a", encoding="utf-8") as rf:
                rf.write(f"{status_val}\t{self.stepname}\n")
        if not remaining:
            return False
        next_step = self._step_from_plan_line(remaining[0])
        if not next_step:
            return False
        stepfile.write_text(f"{next_step}\n", encoding="utf-8")
        if os.geteuid() == 0 and self.username:
            subprocess.run(
                ["chown", f"{self.username}:{self.username}", str(stepfile)],
                check=False,
            )
        return True

    def stop_journald(self) -> None:
        self.spawn(
            "systemctl",
            "stop",
            "systemd-journald.socket",
            "systemd-journald-dev-log.socket",
            "systemd-journald-audit.socket",
            "systemd-journald.service",
        )
        shutil.rmtree("/var/log/journal", ignore_errors=True)

    def system_restart(self, rc: int = TEST_PASSED) -> None:
        from pc_test.desktop import copy_desktop_file

        tmp = Path(self.workdir) / "TMP-ROOT"
        if tmp.is_dir():
            (tmp / "REBOOT.txt").write_text("REBOOT\n", encoding="utf-8")
        self.break_step(rc)
        self.chown_workdir_for_user()
        if self.homedir and not self.disable_autorun:
            copy_desktop_file(self.progname, self.homedir, self.disable_autorun, force=True)
            desktop = Path(self.homedir) / ".config" / "autostart" / f"{self.progname}.desktop"
            if desktop.is_file() and self.username:
                subprocess.run(
                    ["chown", f"{self.username}:{self.username}", str(desktop)],
                    check=False,
                )
        if not self.batchmode:
            from pc_test.terminal import read_key

            msg = self.L("L052", "The update is complete. Press any key to reboot...")
            print(f"\n{msg}", flush=True)
            read_key()
        else:
            msg = self.L(
                "L053", "The update is complete. After %s seconds the system will reboot..."
            )
            print(f"\n{msg % 5}")
            time.sleep(5)
        msg = self.L("L054", "Rebooting the system...")
        line = f"[{self.CLR_BOLD}{datetime.now():%H:%M:%S}{self.CLR_NORM}] {self.CLR_ERR}{msg}{self.CLR_NORM}\n"
        self._tee_log(line)
        subprocess.run(["sync"], check=False)
        subprocess.run(["reboot"], check=False)
        sys.exit(0)

    def check_internet(self) -> bool:
        self.spawn(": Internet connection")
        proc = self.spawn_capture("mktemp", "-qt", f"{self.progname}-XXXXXXXX.tmp")
        if proc.returncode != 0:
            return False
        tmpf = proc.stdout.strip()
        ping = subprocess.run(
            ["ping", "-c4", "-W10", "--", self.ping_server],
            capture_output=True,
            text=True,
        )
        with open(tmpf, "w", encoding="utf-8") as f:
            f.write(ping.stdout or "")
        ok = ", 0% packet loss," in (ping.stdout or "")
        if self.logfile:
            with open(self.logfile, "a", encoding="utf-8") as lf:
                lf.write(ping.stdout or "")
        Path(tmpf).unlink(missing_ok=True)
        return ok

    def append_xorglog(self, text: str) -> None:
        if self.xorglog:
            with open(self.xorglog, "a", encoding="utf-8") as f:
                f.write(text)


_context: Optional[RuntimeContext] = None


def get_context() -> RuntimeContext:
    global _context
    if _context is None:
        _context = RuntimeContext()
    return _context


def set_context(ctx: RuntimeContext) -> None:
    global _context
    _context = ctx
