"""Launch pc-test in a desktop environment terminal (kgx, konsole, …)."""

from __future__ import annotations

import os
import pwd
import re
import shutil
import subprocess
import time
from pathlib import Path


def _installed(pkg: str) -> bool:
    return (
        subprocess.run(
            ["rpm", "-q", pkg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _setting_bool(path: Path | None, key: str) -> bool:
    if path is None or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(rf"^{re.escape(key)}=(.+)$", text, re.M)
    if not m:
        return False
    return m.group(1).strip().strip("'\"") in ("1", "yes", "true", "on")


def _try_kgx(cmd: list[str]) -> bool:
    if not shutil.which("kgx"):
        return False
    os.execvp("kgx", ["kgx", "-T", "PC Test", "-e", " ".join(cmd)])
    return True  # unreachable


def _try_konsole(cmd: list[str]) -> bool:
    if not shutil.which("konsole"):
        return False
    # Plasma 6 / konsole: pass command and args after -e (ALT Workstation K)
    argv = ["konsole", "--title", "PC Test", "-e", *cmd]
    os.execvp("konsole", argv)
    return True


def _try_mate_terminal(cmd: list[str]) -> bool:
    if not shutil.which("mate-terminal"):
        return False
    os.execvp(
        "mate-terminal",
        ["mate-terminal", "--window", "-t", "PC Test", "-e", " ".join(cmd)],
    )
    return True


def _try_xfce_terminal(cmd: list[str]) -> bool:
    if not shutil.which("xfce4-terminal"):
        return False
    os.execvp(
        "xfce4-terminal",
        ["xfce4-terminal", "-T", "PC Test", "-e", " ".join(cmd)],
    )
    return True


def _try_gnome_terminal(cmd: list[str]) -> bool:
    if not shutil.which("gnome-terminal"):
        return False
    os.execvp(
        "gnome-terminal",
        ["gnome-terminal", "--", *cmd],
    )
    return True


def _try_xterm(cmd: list[str]) -> bool:
    if not shutil.which("xterm"):
        return False
    os.execvp("xterm", ["xterm", "-T", "PC Test", "-e", " ".join(cmd)])
    return True


def _have_kde_plasma() -> bool:
    return any(
        _installed(pkg)
        for pkg in (
            "kde",
            "kde5",
            "plasma6-plasma5support-common",
            "plasma6-workspace",
            "plasma6-workspace-common",
            "plasma-desktop",
        )
    )


def launch_in_terminal(
    cmd: list[str], settings_ini: Path | None = None, *, delay: int = 8
) -> None:
    """Open a terminal running cmd; prefers DE flags from settings.ini, then auto-detect."""
    if _setting_bool(settings_ini, "have_kde5") or _have_kde_plasma():
        delay = max(delay, 12)
    time.sleep(delay)
    for key, val in _session_env_for_uid(os.getuid()).items():
        if val:
            os.environ.setdefault(key, val)

    if _setting_bool(settings_ini, "have_kde5") and _try_konsole(cmd):
        pass
    elif _setting_bool(settings_ini, "have_gnome") and _try_kgx(cmd):
        pass
    elif _setting_bool(settings_ini, "have_mate") and _try_mate_terminal(cmd):
        pass
    elif _setting_bool(settings_ini, "have_xfce") and _try_xfce_terminal(cmd):
        pass
    elif _have_kde_plasma() and _try_konsole(cmd):
        pass
    elif _installed("gnome-shell") and _try_kgx(cmd):
        pass
    elif (
        _installed("mate-minimal")
        or _installed("mate-default")
        or _installed("mate-window-manager")
    ) and _try_mate_terminal(cmd):
        pass
    elif (_installed("xfce4-minimal") or _installed("xfce4-default")) and _try_xfce_terminal(cmd):
        pass
    elif _try_kgx(cmd):
        pass
    elif _try_konsole(cmd):
        pass
    elif _try_gnome_terminal(cmd):
        pass
    elif _try_mate_terminal(cmd):
        pass
    elif _try_xfce_terminal(cmd):
        pass
    elif _try_xterm(cmd):
        pass
    else:
        raise SystemExit(1)


def _graphical_session_ready() -> bool:
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return True
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    return session in ("wayland", "x11", "xorg")


def wait_for_display(timeout: int = 120) -> bool:
    """Wait until a graphical session is up (X11 or Wayland, e.g. Plasma on K Workstation)."""
    if _graphical_session_ready():
        return True
    for _ in range(timeout):
        if _graphical_session_ready():
            return True
        time.sleep(1)
    return False


_GRAPHICAL_ENV_KEYS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "XDG_SESSION_TYPE",
    "XDG_CURRENT_DESKTOP",
    "DESKTOP_SESSION",
    "KDE_FULL_SESSION",
)

_DE_PROCNAMES = (
    "plasmashell",
    "gnome-shell",
    "xfce4-session",
    "mate-session",
    "cinnamon-session",
)


def _environ_from_pid(pid: int) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if b"=" not in item:
            continue
        key, _, value = item.partition(b"=")
        try:
            out[key.decode()] = value.decode(errors="replace")
        except UnicodeDecodeError:
            continue
    return out


def _graphical_env_for_uid(uid: int) -> dict[str, str]:
    """Read DISPLAY/Wayland variables from the user's running desktop session."""
    for name in _DE_PROCNAMES:
        proc = subprocess.run(
            ["pgrep", "-u", str(uid), "-x", name],
            capture_output=True,
            text=True,
            check=False,
        )
        for pid_s in (proc.stdout or "").split():
            try:
                pid = int(pid_s)
            except ValueError:
                continue
            proc_env = _environ_from_pid(pid)
            if proc_env.get("DISPLAY") or proc_env.get("WAYLAND_DISPLAY"):
                return {k: proc_env[k] for k in _GRAPHICAL_ENV_KEYS if proc_env.get(k)}
    return {}


def apply_graphical_session_env(uid: int | None = None) -> None:
    """Merge DISPLAY/Wayland variables from the user's desktop into the current process."""
    if uid is None:
        uid = os.getuid()
    for key, value in _session_env_for_uid(uid).items():
        if value:
            os.environ[key] = value


def prepare_user_session_env(ctx, uid: int | None = None) -> None:
    """Apply desktop session env and infer missing DE variables from settings.ini."""
    import pwd

    if uid is None:
        if getattr(ctx, "username", None):
            try:
                uid = pwd.getpwnam(ctx.username).pw_uid
            except KeyError:
                uid = os.getuid()
        else:
            uid = os.getuid()
    apply_graphical_session_env(uid)
    if not os.environ.get("XDG_CURRENT_DESKTOP"):
        if getattr(ctx, "have_kde5", None):
            os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
        elif getattr(ctx, "have_mate", None):
            os.environ["XDG_CURRENT_DESKTOP"] = "MATE"
        elif getattr(ctx, "have_xfce", None):
            os.environ["XDG_CURRENT_DESKTOP"] = "XFCE"
        elif getattr(ctx, "have_gnome", None):
            os.environ["XDG_CURRENT_DESKTOP"] = "GNOME"
    if not os.environ.get("XDG_SESSION_TYPE"):
        if os.environ.get("WAYLAND_DISPLAY"):
            os.environ["XDG_SESSION_TYPE"] = "wayland"
        elif os.environ.get("DISPLAY"):
            os.environ["XDG_SESSION_TYPE"] = "x11"


def _session_env_for_uid(uid: int, base: dict[str, str] | None = None) -> dict[str, str]:
    """Graphical session variables for a logged-in user (root handoff / resume)."""
    src = dict(base if base is not None else os.environ)
    env: dict[str, str] = {}
    for key in _GRAPHICAL_ENV_KEYS:
        if src.get(key):
            env[key] = src[key]
    graphical = _graphical_env_for_uid(uid)
    for key, value in graphical.items():
        env.setdefault(key, value)
    runtime = Path(f"/run/user/{uid}")
    if runtime.is_dir():
        env["XDG_RUNTIME_DIR"] = str(runtime)
        bus = runtime / "bus"
        if bus.exists():
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
    return env


def _terminal_argv_for_cmd(cmd: list[str], settings_ini: Path | None) -> list[str] | None:
    if _setting_bool(settings_ini, "have_kde5") and shutil.which("konsole"):
        return ["konsole", "--title", "PC Test", "-e", *cmd]
    if _setting_bool(settings_ini, "have_gnome") and shutil.which("kgx"):
        return ["kgx", "-T", "PC Test", "-e", " ".join(cmd)]
    if _setting_bool(settings_ini, "have_mate") and shutil.which("mate-terminal"):
        return [
            "mate-terminal",
            "--window",
            "-t",
            "PC Test",
            "-e",
            " ".join(cmd),
        ]
    if _setting_bool(settings_ini, "have_xfce") and shutil.which("xfce4-terminal"):
        return ["xfce4-terminal", "-T", "PC Test", "-e", " ".join(cmd)]
    if _have_kde_plasma() and shutil.which("konsole"):
        return ["konsole", "--title", "PC Test", "-e", *cmd]
    if shutil.which("kgx"):
        return ["kgx", "-T", "PC Test", "-e", " ".join(cmd)]
    if shutil.which("konsole"):
        return ["konsole", "--title", "PC Test", "-e", *cmd]
    if shutil.which("gnome-terminal"):
        return ["gnome-terminal", "--", *cmd]
    if shutil.which("xterm"):
        return ["xterm", "-T", "PC Test", "-e", " ".join(cmd)]
    return None


def spawn_continue_in_user_session(
    username: str,
    settings_ini: Path | None = None,
    progname: str = "pc-test",
) -> bool:
    """From root (or resume): open a terminal as the test user running pc-test --continue."""
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        return False
    cmd = [progname, "--desktop-icon", "--continue"]
    term = _terminal_argv_for_cmd(cmd, settings_ini)
    if not term:
        return False
    env = _session_env_for_uid(pw.pw_uid)
    if not env.get("XDG_CURRENT_DESKTOP") and settings_ini and settings_ini.is_file():
        text = settings_ini.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^have_kde5=1", text, re.M):
            env["XDG_CURRENT_DESKTOP"] = "KDE"
        elif re.search(r"^have_mate=1", text, re.M):
            env["XDG_CURRENT_DESKTOP"] = "MATE"
        elif re.search(r"^have_xfce=1", text, re.M):
            env["XDG_CURRENT_DESKTOP"] = "XFCE"
        elif re.search(r"^have_gnome=1", text, re.M):
            env["XDG_CURRENT_DESKTOP"] = "GNOME"
    if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
        return False
    env_args = [f"{key}={val}" for key, val in env.items()]
    # runuser avoids sudo SETENV (NOPASSWD rules often forbid sudo -E / env preservation)
    if os.geteuid() == 0 and shutil.which("runuser"):
        argv = ["runuser", "-u", username, "--", "env", *env_args, *term]
    else:
        argv = ["sudo", "-u", username, "-H", "env", *env_args, *term]
    subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True
