"""pc-test main entry and test runner loop."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import date
from pathlib import Path

from pc_test import cli
from pc_test.config_loader import load_config_files
from pc_test.constants import (
    TEST_ALLOWED,
    TEST_PASSED,
    TEST_RUNNING,
)
from pc_test.context import FatalError, RuntimeContext, get_context, graphical_session, set_context
from pc_test.desktop import copy_desktop_file, remove_desktop_file
from pc_test.paths import PROGNAME, libexec_dir
from pc_test.steps import create_step, list_steps
from pc_test.terminal import read_key
from pc_test.version import PCTEST_VERSION


def _resolve_install_paths(ctx: RuntimeContext) -> None:
    """Set progname, scriptname and libdir (l10n/assets under %_libexecdir)."""
    ctx.progname = PROGNAME
    ctx.scriptname = str(Path("/usr/bin") / PROGNAME)
    for candidate in (Path(sys.argv[0]).resolve(), Path("/usr/bin/pc-test")):
        if candidate.name == PROGNAME and candidate.is_file():
            ctx.scriptname = str(candidate)
            break
    ctx.libdir = str(libexec_dir())


def setup_console(ctx: RuntimeContext) -> None:
    if ctx.colormode == "always":
        ctx.colormode = "1"
    elif ctx.colormode == "never":
        ctx.colormode = ""
    elif not sys.stdout.isatty():
        ctx.colormode = ""
    else:
        ctx.colormode = "1"
    if not ctx.colormode:
        for name in (
            "CLR_NORM",
            "CLR_BOLD",
            "CLR_LC1",
            "CLR_LC2",
            "CLR_OK",
            "CLR_ERR",
            "CLR_WARN",
        ):
            setattr(ctx, name, "")


def pause_before_exit(ctx: RuntimeContext) -> None:
    if ctx.batchmode:
        time.sleep(5)
        return
    if getattr(ctx, "desktop_icon_start", None) and not graphical_session():
        return
    if not sys.stdin.isatty() and not getattr(ctx, "desktop_icon_start", None):
        return
    msg = ctx.L("L050", "Press any key to close this window...")
    print(f"\n{msg}", flush=True)
    read_key()


def _restart_extra_args(ctx: RuntimeContext) -> str:
    if ctx.update_apt_lists and ctx.dist_upgrade and ctx.update_kernel:
        return " --update"
    if not (ctx.update_apt_lists or ctx.dist_upgrade or ctx.update_kernel):
        return " --no-update"
    if not ctx.update_apt_lists:
        return " --no-sources"
    return ""


def restart_as_root(ctx: RuntimeContext) -> None:
    """Re-exec pc-test as root (never returns on success)."""
    import pwd

    uid = os.getuid()
    try:
        user = pwd.getpwuid(uid).pw_name
    except KeyError:
        user = os.environ.get("USER", str(uid))
    home = ctx.homedir or pwd.getpwuid(uid).pw_dir
    add = _restart_extra_args(ctx)
    flag = Path(home) / ".local/share" / ctx.progname / "sudo.UID"
    icon = " --desktop-icon" if getattr(ctx, "desktop_icon_start", None) else ""
    shell_cmd = f"{ctx.scriptname} --uid={uid}{add}{icon} --continue"

    if flag.is_file():
        sudo_argv = ["sudo", ctx.scriptname, f"--uid={uid}", "--continue"]
        if getattr(ctx, "desktop_icon_start", None):
            sudo_argv.append("--desktop-icon")
        if add.strip():
            sudo_argv.extend(add.split())
        try:
            os.execvp("sudo", sudo_argv)
        except OSError as exc:
            ctx.fatal("F21", "Couldn't run sudo: %s", exc)

    msg = ctx.L("L051", "Root privileges required: sudo not yet configured for")
    print(f"\n{ctx.CLR_WARN}{msg} '{user}'!{ctx.CLR_NORM}", flush=True)
    print(
        f"{ctx.CLR_WARN}Enter root password once to configure sudo for pc-test.{ctx.CLR_NORM}\n",
        flush=True,
    )

    for try_no in range(1, 4):
        try:
            os.execvpe("su", ["su", "-", "-c", shell_cmd], os.environ)
        except OSError:
            pass
        if try_no == 3:
            ctx.fatal("F21", "Couldn't configure sudo.")
        print(f"{ctx.CLR_ERR}su failed (attempt {try_no}/3).{ctx.CLR_NORM}\n", flush=True)


def _workdir_has_retest_data(workdir: Path) -> bool:
    return (workdir / "RESULTS").is_file() or (workdir / "STATE" / "RESULTS").is_file()


def _workdir_has_retest_settings(workdir: Path) -> bool:
    return (workdir / "settings.ini").is_file() or (workdir / "STATE" / "settings.ini").is_file()


def resolve_launch_mode(ctx: RuntimeContext) -> None:
    home = ctx.homedir or os.environ.get("HOME", "")
    lastdir = Path(home) / "PC-TEST"
    workdir = (
        Path(home) / ".local/share" / ctx.progname / (ctx.repodate or date.today().isoformat())
    )

    if ctx.launchmode == "auto":
        if (
            lastdir.is_symlink()
            and (lastdir / f"{ctx.progname}.log").is_file()
            and (lastdir / "STATE" / "start.txt").is_file()
            and lastdir.resolve() == workdir.resolve()
        ):
            if (lastdir / "STATE" / "STEP").is_file() and (
                lastdir / "STATE" / "STEP"
            ).stat().st_size:
                ctx.launchmode = "continue"
            elif (
                not (lastdir / "STATE" / "STEP").exists()
                and not (lastdir / "STATE" / "start.txt").read_text().strip()
                and not (lastdir / "STATE" / "finish.txt").exists()
            ):
                ctx.launchmode = "finish"
            else:
                ctx.launchmode = "start"
        else:
            ctx.launchmode = "start"
        return

    if ctx.launchmode == "continue":
        if (
            lastdir.is_symlink()
            and (lastdir / f"{ctx.progname}.log").is_file()
            and (lastdir / "STATE" / "start.txt").is_file()
        ):
            step_path = lastdir / "STATE" / "STEP"
            start_empty = not (lastdir / "STATE" / "start.txt").read_text().strip()
            finish_staged = (lastdir / "STATE" / "finish.txt").exists()
            if step_path.is_file() and step_path.stat().st_size:
                ctx.workdir = str(lastdir.resolve())
            elif start_empty and not finish_staged:
                ctx.workdir = str(lastdir.resolve())
            else:
                ctx.usertype = "continue"
                ctx.launchmode = "start"
        else:
            ctx.usertype = "continue"
            ctx.launchmode = "start"
        return

    if ctx.launchmode == "finish":
        start = lastdir / "STATE" / "start.txt" if lastdir.is_symlink() else None
        if (
            lastdir.is_symlink()
            and (lastdir / f"{ctx.progname}.log").is_file()
            and start
            and start.is_file()
            and not start.read_text().strip()
        ):
            ctx.workdir = str(lastdir.resolve())
        elif lastdir.is_symlink() and start and start.is_file() and start.read_text().strip():
            ctx.fatal(
                "F18",
                "The first test plan is not complete yet. Use '%s --continue' to resume.",
                ctx.progname,
            )
        else:
            ctx.usertype = "finish"
            ctx.launchmode = "start"
        return

    if ctx.launchmode == "retest":
        numbers = Path(f"/var/lib/{ctx.progname}/numbers.txt")
        wd = lastdir.resolve() if lastdir.is_symlink() else None
        if (
            wd
            and (wd / f"{ctx.progname}.log").is_file()
            and numbers.is_file()
            and re.search(rf"^{re.escape(ctx.retestno)}\s", numbers.read_text(), re.M)
            and _workdir_has_retest_data(wd)
            and _workdir_has_retest_settings(wd)
        ):
            ctx.workdir = str(wd)
        else:
            ctx.fatal(
                "F18", "The specified test '%s' cannot be retaken at this time.", ctx.retestno
            )


def start_new_run(ctx: RuntimeContext, argv: list[str]) -> None:
    home = ctx.homedir or os.environ.get("HOME", "")
    lastdir = Path(home) / "PC-TEST"
    workdir = Path(
        ctx.workdir
        or (
            Path(home) / ".local/share" / ctx.progname / (ctx.repodate or date.today().isoformat())
        )
    )
    ctx.workdir = str(workdir)

    if getattr(ctx, "usertype", None):
        msg = ctx.L("L001", "The launch mode '%s' has been changed, testing will begin again!")
        print(f"{ctx.CLR_WARN}{msg % ctx.usertype}{ctx.CLR_NORM}")

    if ctx.dist_upgrade or ctx.update_kernel:
        msg = ctx.L("L002", "Before testing, the system and kernel will be updated!")
        print(f"{ctx.CLR_ERR}{msg}{ctx.CLR_NORM}")
        if not ctx.batchmode:
            step = ctx.L("L003", "Press Ctrl-C to abort or any other key to continue...")
            print(step, flush=True)
            if not read_key(abort_on_ctrl_c=True):
                ctx.fatal("F20", "Testing canceled.")
        print(flush=True)

    if workdir.exists():
        shutil.rmtree(workdir)
    if lastdir.exists() or lastdir.is_symlink():
        lastdir.unlink(missing_ok=True)
    (workdir / "STATE").mkdir(parents=True)
    lastdir.symlink_to(workdir)
    shutil.copy(f"/var/lib/{ctx.progname}/start.txt", workdir / "STATE" / "start.txt")
    first = (workdir / "STATE" / "start.txt").read_text(encoding="utf-8").splitlines()[0]
    (workdir / "STATE" / "STEP").write_text(first.split("\t")[-1] + "\n", encoding="utf-8")
    (workdir / "STATE" / "RESULTS").write_text("", encoding="utf-8")
    ctx.logfile = str(workdir / f"{ctx.progname}.log")
    ctx.xorglog = str(workdir / "xorg.log")
    title = f"{ctx.progname} {' '.join(argv)}"
    with open(ctx.logfile, "w", encoding="utf-8") as lf:
        print(f"[{time.strftime('%H:%M:%S')}] {title}", file=lf)
        Path(ctx.xorglog).write_text("", encoding="utf-8")
    step = create_step((workdir / "STATE" / "STEP").read_text().strip(), ctx)
    ctx.draw_title_line(TEST_PASSED, step.number, step.title())
    copy_desktop_file(ctx.progname, home, ctx.disable_autorun)
    ctx.write_config()


def _step_role(ctx: RuntimeContext, stepname: str) -> str:
    plan = Path(ctx.workdir) / "STATE" / ctx.testplan
    if not plan.is_file():
        return ""
    for line in plan.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(stepname):
            return line.split("\t", 1)[0]
    return ""


def _user_has_graphical_session(username: str) -> bool:
    import pwd

    from pc_test.de_terminal import _session_env_for_uid

    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        return False
    env = _session_env_for_uid(pw.pw_uid)
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def _ensure_express_packages(ctx: RuntimeContext) -> None:
    """Install express-test packages while still root (before user handoff)."""
    if not (ctx.xprss_test and ctx.have_xorg) or os.geteuid() != 0:
        return
    missing = [
        pkg
        for pkg in (
            "yad",
            "notify-send",
            "xdg-utils",
            "pulseaudio-utils",
            "icon-theme-adwaita",
            "sound-theme-freedesktop",
        )
        if ctx.is_pkg_available(pkg) and not ctx.is_pkg_installed(pkg)
    ]
    if missing:
        ctx.spawn("apt-get", "install", "-y", "--", *missing)


def _switch_to_user_in_process(ctx: RuntimeContext, next_step: str = "") -> bool:
    """Drop root privileges and continue testing in the same terminal."""
    if os.geteuid() != 0:
        return True
    if not ctx.username:
        return False
    import pwd

    try:
        pw = pwd.getpwnam(ctx.username)
    except KeyError:
        return False
    if pw.pw_uid == 0:
        return False

    from pc_test.de_terminal import prepare_user_session_env, wait_for_display

    prepare_user_session_env(ctx, pw.pw_uid)
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        if next_step == "express" and wait_for_display(120):
            prepare_user_session_env(ctx, pw.pw_uid)
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False

    ctx.chown_workdir_for_user()
    try:
        os.initgroups(ctx.username, pw.pw_gid)
    except (AttributeError, PermissionError, OSError):
        try:
            os.setgroups([])
        except OSError:
            pass
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
    os.environ["HOME"] = pw.pw_dir
    os.environ["USER"] = ctx.username
    os.environ["LOGNAME"] = ctx.username
    return True


def _handoff_user_message(ctx: RuntimeContext, next_step: str) -> str:
    if ctx.langid == "ru":
        if next_step == "config":
            return "Запуск шага 5.4 «Определение плана тестирования»..."
        if next_step == "express":
            return "Запуск шага 9 «Экспресс-тест»..."
        return "Переключение на пользовательскую сессию..."
    if next_step == "config":
        return "Starting step 5.4 (test plan configuration)..."
    if next_step == "express":
        return "Starting step 9 (express test)..."
    return "Switching to user session..."


def _handoff_to_user_session(ctx: RuntimeContext) -> None:
    next_step = ""
    stepfile = Path(ctx.workdir) / "STATE" / "STEP"
    if stepfile.is_file():
        next_step = stepfile.read_text(encoding="utf-8").splitlines()[0].strip()

    if next_step == "express":
        _ensure_express_packages(ctx)

    if _switch_to_user_in_process(ctx, next_step):
        print(
            f"\n{ctx.CLR_OK}{_handoff_user_message(ctx, next_step)}{ctx.CLR_NORM}\n",
            flush=True,
        )
        return

    if (
        not ctx.disable_autorun
        and ctx.username
        and os.geteuid() == 0
        and _user_has_graphical_session(ctx.username)
    ):
        from pc_test.de_terminal import spawn_continue_in_user_session

        settings = Path(ctx.workdir) / "STATE" / "settings.ini"
        if spawn_continue_in_user_session(
            ctx.username,
            settings if settings.is_file() else None,
            ctx.progname,
        ):
            if ctx.langid == "ru":
                if next_step == "config":
                    msg = (
                        "Открыто второе окно для шага 5.4 «Определение плана тестирования». "
                        "Продолжайте в нём; окно с обновлением (root) можно закрыть."
                    )
                elif next_step == "express":
                    msg = (
                        "Открыто окно терминала для шага 9 «Экспресс-тест». "
                        "Продолжайте там; окно root можно закрыть."
                    )
                else:
                    msg = (
                        "Открыто второе окно терминала для продолжения тестирования. "
                        "Продолжайте там; это окно root можно закрыть."
                    )
            else:
                if next_step == "config":
                    msg = (
                        "A second terminal was opened for step 5.4 (test plan). "
                        "Continue there; you may close this root window."
                    )
                elif next_step == "express":
                    msg = (
                        "A terminal was opened for step 9 (express test). "
                        "Continue there; you may close this root window."
                    )
                else:
                    msg = (
                        "A second terminal was opened to continue testing. "
                        "Continue there; you may close this root window."
                    )
            print(f"\n{ctx.CLR_OK}{msg}{ctx.CLR_NORM}\n", flush=True)
            raise SystemExit(0)
    if ctx.langid == "ru":
        msg = "Продолжите тестирование от пользователя: pc-test --continue"
        if next_step == "config":
            msg = "Шаг 5.4 (план тестирования): pc-test --continue"
        elif next_step == "express":
            msg = "Шаг 9 (экспресс-тест): pc-test --continue"
    else:
        msg = "Continue testing as user: pc-test --continue"
        if next_step == "config":
            msg = "Step 5.4 (test plan): pc-test --continue"
        elif next_step == "express":
            msg = "Step 9 (express test): pc-test --continue"
    print(f"\n{ctx.CLR_OK}{msg}{ctx.CLR_NORM}\n", flush=True)
    raise SystemExit(0)


def _express_retry_prompt(ctx: RuntimeContext, status: int) -> None:
    if ctx.langid == "ru":
        print(
            f"\n{ctx.CLR_WARN}Экспресс-тест не завершён (код {status}). "
            f"Дальнейшие шаги приостановлены.{ctx.CLR_NORM}"
        )
        print(
            "Устраните проблему и нажмите любую клавишу для повтора "
            "(Ctrl-C — выход из тестирования).",
            flush=True,
        )
    else:
        print(
            f"\n{ctx.CLR_WARN}Express test is not complete (status {status}). "
            f"Further steps are paused.{ctx.CLR_NORM}"
        )
        print(
            "Fix the issue and press any key to retry (Ctrl-C to abort testing).",
            flush=True,
        )
    if not read_key(abort_on_ctrl_c=True):
        ctx.fatal("F20", "Testing canceled.")


def _write_step_status(ctx: RuntimeContext, status: int) -> None:
    """Record step result for have_next_step() (user steps have no TMP-ROOT finalize)."""
    state = Path(ctx.workdir) / "STATE"
    state.mkdir(parents=True, exist_ok=True)
    (state / "STATUS").write_text(f"{status}\n", encoding="utf-8")


def _chown_state_for_user(ctx: RuntimeContext, *names: str) -> None:
    """Give the test user ownership of STATE files created while running as root."""
    if os.geteuid() != 0 or not ctx.username:
        return
    state = Path(ctx.workdir) / "STATE"
    if not state.is_dir():
        return
    paths = [str(state / name) for name in names if (state / name).exists()]
    if paths:
        subprocess.run(
            ["chown", f"{ctx.username}:{ctx.username}", *paths],
            check=False,
        )


def _finalize_root_step(ctx: RuntimeContext, status: int) -> None:
    """After a root step run via sudo --uid, save artifacts and chown to the user."""
    if os.geteuid() != 0 or not ctx.username:
        return
    tmp = Path(ctx.workdir) / "TMP-ROOT"
    if tmp.is_dir():
        subprocess.run(
            ["chown", "-R", f"{ctx.username}:{ctx.username}", str(tmp)],
            check=False,
        )
        for item in tmp.iterdir():
            dest = Path(ctx.workdir) / item.name
            try:
                shutil.move(str(item), str(dest))
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)
    state = Path(ctx.workdir) / "STATE"
    if state.is_dir():
        (state / "STATUS").write_text(f"{status}\n", encoding="utf-8")
        _chown_state_for_user(ctx, "STATUS", "NUMBER", "finish.txt", "STEP")
    ctx.chown_workdir_for_user()


def _finish_plan_entries(content: str) -> list[str]:
    return [ln.strip() for ln in content.splitlines() if ln.strip() and "\t" in ln]


def _stage_finish_plan(ctx: RuntimeContext) -> bool:
    """Install finish.txt and set STEP to the first finish-plan step."""
    src = Path(f"/var/lib/{ctx.progname}/finish.txt")
    if not src.is_file():
        return False
    content = src.read_text(encoding="utf-8")
    entries = _finish_plan_entries(content)
    if not entries:
        return False
    state = Path(ctx.workdir) / "STATE"
    state.mkdir(parents=True, exist_ok=True)
    step = entries[0].split("\t", 1)[-1].strip()
    if not step:
        return False
    (state / "finish.txt").write_text(content, encoding="utf-8")
    (state / "STEP").write_text(f"{step}\n", encoding="utf-8")
    _chown_state_for_user(ctx, "finish.txt", "STEP")
    return True


def run_main_loop(ctx: RuntimeContext) -> None:
    os.chdir(ctx.workdir)
    ctx.testplan = "start.txt"

    while True:
        os.chdir(ctx.workdir)
        Path("REBOOT.txt").unlink(missing_ok=True)
        plan_name = "finish.txt" if (Path("STATE") / "finish.txt").is_file() else "start.txt"
        ctx.testplan = plan_name
        settings = Path("STATE") / "settings.ini"
        if settings.is_file():
            load_config_files(ctx, settings)
        stepfile = Path("STATE") / "STEP"
        if not stepfile.is_file() or not stepfile.stat().st_size:
            break
        ctx.stepname = stepfile.read_text(encoding="utf-8").splitlines()[0].strip()
        if not ctx.stepname:
            break
        if ctx.stepname not in list_steps():
            ctx.fatal("F19", "Step module '%s' not found.", ctx.stepname)

        plan = Path("STATE") / plan_name
        usertype = ""
        for line in plan.read_text(encoding="utf-8").splitlines():
            if line.endswith(ctx.stepname):
                usertype = line.split("\t")[0]
                break
        if not usertype:
            break

        step = create_step(ctx.stepname, ctx)
        ctx.number = getattr(step, "number", "5")
        ctx.en_name = step.en_name
        ctx.ru_name = step.ru_name
        ctx.status = TEST_ALLOWED

        if usertype == "root" and os.geteuid() != 0:
            restart_as_root(ctx)
            ctx.fatal("F21", "Couldn't restart as root.")

        if usertype in ("user", "both") and os.geteuid() == 0:
            _handoff_to_user_session(ctx)

        if usertype in ("user", "both") and os.geteuid() != 0:
            from pc_test.de_terminal import prepare_user_session_env

            prepare_user_session_env(ctx)

        Path("STATE/NUMBER").write_text(f"{ctx.number}\n", encoding="utf-8")
        Path("STATE/STATUS").unlink(missing_ok=True)
        status = step.pre()
        if status == TEST_ALLOWED:
            if os.geteuid() == 0 and ctx.username:
                tmp = Path("TMP-ROOT")
                tmp.mkdir(exist_ok=True)
                os.chdir(tmp)
            print()
            ctx.draw_title_line(TEST_RUNNING, str(ctx.number), step.title() + "...")
            try:
                status = step.testcase()
            except FatalError:
                raise
            except Exception as exc:
                import traceback

                tb = traceback.format_exc()
                if ctx.logfile:
                    with open(ctx.logfile, "a", encoding="utf-8") as lf:
                        lf.write(tb)
                ctx.fatal("F02", "Unexpected error: %s", f"{exc} [{step.STEP_ID}]")
            os.chdir(ctx.workdir)
            _finalize_root_step(ctx, status)
        else:
            state = Path("STATE")
            state.mkdir(exist_ok=True)
            (state / "STATUS").write_text(f"{status}\n", encoding="utf-8")
            if os.geteuid() == 0 and ctx.username:
                subprocess.run(
                    ["chown", f"{ctx.username}:{ctx.username}", "STATE/STATUS"],
                    cwd=ctx.workdir,
                    check=False,
                )
        ctx.status = status
        if os.geteuid() != 0:
            _write_step_status(ctx, status)

        ctx.log_step_result(status)

        if (
            ctx.stepname == "express"
            and plan_name == "start.txt"
            and ctx.xprss_test
            and status != TEST_PASSED
        ):
            if ctx.batchmode:
                break
            _express_retry_prompt(ctx, status)
            continue

        if not ctx.have_next_step():
            break

        # One sudo session: keep running root steps; return to user only before user/both steps
        if os.geteuid() == 0 and ctx.username:
            next_step = (
                (Path(ctx.workdir) / "STATE" / "STEP")
                .read_text(encoding="utf-8")
                .splitlines()[0]
                .strip()
            )
            next_role = _step_role(ctx, next_step)
            if next_role in ("user", "both"):
                _handoff_to_user_session(ctx)
                continue

    Path("REBOOT.txt").unlink(missing_ok=True)
    remove_desktop_file(ctx.progname, ctx.homedir or os.environ.get("HOME", ""))


def show_results(ctx: RuntimeContext, *, log: bool = False) -> None:
    results = Path(ctx.workdir) / "STATE" / "RESULTS"
    if not results.is_file():
        return
    for line in results.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        rc_s, step_id = parts
        try:
            rc = int(rc_s)
        except ValueError:
            rc = 0
        step = create_step(step_id, ctx)
        step.show_results(rc, log=log)
        ctx.draw_title_line(rc, step.number, step.title(), log=log)


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    ctx = RuntimeContext()
    _resolve_install_paths(ctx)
    set_context(ctx)

    import pwd

    if not ctx.username:
        pw = pwd.getpwuid(os.getuid())
        ctx.username = pw.pw_name
        ctx.homedir = pw.pw_dir

    load_config_files(ctx, Path(f"/etc/{ctx.progname}.conf"))
    cli.parse_args(ctx, argv)
    home = ctx.homedir or os.environ.get("HOME", "")
    load_config_files(ctx, Path(home) / ".config" / f"{ctx.progname}.conf")
    ctx.load_nls()
    setup_console(ctx)

    ctx.helpfile = f"/usr/share/doc/{ctx.progname}-doc-{PCTEST_VERSION}/html/{ctx.progname}.html"
    if not Path(ctx.helpfile).is_file():
        ctx.helpfile = ""

    resolve_launch_mode(ctx)
    if not ctx.workdir:
        ctx.workdir = str(
            Path(home) / ".local/share" / ctx.progname / (ctx.repodate or date.today().isoformat())
        )
    ctx.logfile = str(Path(ctx.workdir) / f"{ctx.progname}.log")
    ctx.xorglog = str(Path(ctx.workdir) / "xorg.log")

    if ctx.launchmode == "start":
        start_new_run(ctx, argv)
    elif ctx.launchmode == "retest":
        _setup_retest(ctx, argv)
    elif ctx.launchmode == "finish":
        _setup_finish(ctx, argv)

    if ctx.launchmode != "start":
        settings = Path(ctx.workdir) / "STATE" / "settings.ini"
        if settings.is_file():
            load_config_files(ctx, settings)
        ctx.load_nls()

    if os.geteuid() != 0 or not ctx.username:
        if ctx.launchmode != "start":
            os.chdir(ctx.workdir)
            show_results(ctx)
            step_name = (
                Path(ctx.workdir).joinpath("STATE/STEP").read_text().strip()
                if (Path(ctx.workdir) / "STATE/STEP").is_file()
                else "prepare"
            )
            create_step(step_name, ctx)
            num = "5"
            num_file = Path(ctx.workdir) / "STATE/NUMBER"
            if num_file.is_file():
                num = num_file.read_text().strip() + ".1"
            resume_title = (
                "Возобновление тестирования" if ctx.langid == "ru" else "Resumption of testing"
            )
            ctx.draw_title_line(TEST_PASSED, num, resume_title)
            with open(ctx.logfile, "a", encoding="utf-8"):
                pass
        if graphical_session():
            for proc in (
                "DiscoverNotifier",
                "apt-indicator-checker",
                "apt-indicator",
                "discover",
            ):
                subprocess.run(["killall", "-TERM", proc], stderr=subprocess.DEVNULL, check=False)

    run_main_loop(ctx)
    _final_message(ctx)
    pause_before_exit(ctx)


def _setup_retest(ctx: RuntimeContext, argv: list[str]) -> None:
    numbers = Path(f"/var/lib/{ctx.progname}/numbers.txt")
    stepname = ""
    for line in numbers.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{ctx.retestno}\t") or line.startswith(f"{ctx.retestno} "):
            stepname = line.split(None, 1)[-1].strip()
            break
    if not stepname:
        ctx.fatal("F18", "The specified test '%s' cannot be retaken at this time.", ctx.retestno)

    wd = Path(ctx.workdir)
    state = wd / "STATE"
    state.mkdir(exist_ok=True)

    settings = wd / "settings.ini"
    if settings.is_file():
        load_config_files(ctx, settings)
        dest = state / "settings.ini"
        if dest.is_file():
            dest.unlink()
        shutil.move(str(settings), str(dest))
    elif (state / "settings.ini").is_file():
        load_config_files(ctx, state / "settings.ini")
    else:
        ctx.fatal("F18", "The specified test '%s' cannot be retaken at this time.", ctx.retestno)

    results = wd / "RESULTS"
    if results.is_file():
        dest = state / "RESULTS"
        if dest.is_file():
            dest.unlink()
        shutil.move(str(results), str(dest))
    elif not (state / "RESULTS").is_file():
        (state / "RESULTS").write_text("", encoding="utf-8")

    (state / "start.txt").write_text("", encoding="utf-8")
    finish_lines = []
    for name in ("start.txt", "finish.txt"):
        p = Path(f"/var/lib/{ctx.progname}") / name
        if p.is_file():
            for ln in p.read_text(encoding="utf-8").splitlines():
                if ln.endswith(stepname):
                    finish_lines.append(ln)
    (state / "finish.txt").write_text("\n".join(finish_lines) + "\n", encoding="utf-8")
    (state / "STEP").write_text(stepname + "\n", encoding="utf-8")
    (state / "NUMBER").write_text(f"{ctx.retestno}\n", encoding="utf-8")
    step = create_step(stepname, ctx)
    step.reset_results()
    copy_desktop_file(ctx.progname, ctx.homedir or os.environ.get("HOME", ""), ctx.disable_autorun)


def _setup_finish(ctx: RuntimeContext, argv: list[str]) -> None:
    state = Path(ctx.workdir) / "STATE"
    state.mkdir(parents=True, exist_ok=True)
    src = Path(f"/var/lib/{ctx.progname}/finish.txt")
    dst = state / "finish.txt"
    if not src.is_file():
        ctx.fatal("F19", "Step module '%s' not found.", "finish.txt")
    expected = src.read_text(encoding="utf-8")
    try:
        if not _stage_finish_plan(ctx):
            ctx.fatal("F19", "Step module '%s' not found.", "finish.txt")
    except PermissionError:
        if not dst.is_file() or dst.read_text(encoding="utf-8") != expected:
            ctx.fatal(
                "F21",
                "Cannot update finish plan (permission denied). Run: sudo chown -R %s '%s'",
                ctx.username,
                ctx.workdir,
            )
        entries = _finish_plan_entries(expected)
        if not entries:
            ctx.fatal("F19", "Step module '%s' not found.", "finish.txt")
        step = entries[0].split("\t", 1)[-1].strip()
        step_path = state / "STEP"
        try:
            step_path.write_text(f"{step}\n", encoding="utf-8")
        except PermissionError:
            ctx.fatal(
                "F21",
                "Cannot update finish plan (permission denied). Run: sudo chown -R %s '%s'",
                ctx.username,
                ctx.workdir,
            )
    copy_desktop_file(ctx.progname, ctx.homedir or os.environ.get("HOME", ""), ctx.disable_autorun)


def _plan_entries(content: str) -> list[str]:
    return [ln.strip() for ln in content.splitlines() if ln.strip() and "\t" in ln]


def _start_plan_remaining(ctx: RuntimeContext) -> list[str]:
    planfile = Path(ctx.workdir) / "STATE" / "start.txt"
    if not planfile.is_file():
        return []
    return _plan_entries(planfile.read_text(encoding="utf-8"))


def _current_step_name(ctx: RuntimeContext) -> str:
    stepfile = Path(ctx.workdir) / "STATE" / "STEP"
    if not stepfile.is_file() or not stepfile.stat().st_size:
        return ""
    return stepfile.read_text(encoding="utf-8").splitlines()[0].strip()


def _express_pause_message(ctx: RuntimeContext) -> None:
    cmd = ctx.bold(f"{ctx.progname} --continue")
    if ctx.langid == "ru":
        print(
            f"\n{ctx.CLR_WARN}Шаг 9 «Экспресс-тест» не завершён. "
            f"Дальнейшие шаги (cpupower и др.) приостановлены.{ctx.CLR_NORM}"
        )
        print(f"Продолжите тестирование командой: {cmd}\n")
    else:
        print(
            f"\n{ctx.CLR_WARN}Step 9 (express test) is not complete. "
            f"Further steps (cpupower, etc.) are paused.{ctx.CLR_NORM}"
        )
        print(f"Continue testing with: {cmd}\n")


def _final_message(ctx: RuntimeContext) -> None:
    remaining = _start_plan_remaining(ctx)
    if ctx.testplan == "start.txt" and remaining:
        if _current_step_name(ctx) == "express" or any(ln.endswith("express") for ln in remaining):
            _express_pause_message(ctx)
        else:
            cmd = ctx.bold(f"{ctx.progname} --continue")
            if ctx.langid == "ru":
                print(f"\n{ctx.CLR_WARN}Тестирование приостановлено.{ctx.CLR_NORM}")
                print(f"Продолжите командой: {cmd}\n")
            else:
                print(f"\n{ctx.CLR_WARN}Testing paused.{ctx.CLR_NORM}")
                print(f"Continue with: {cmd}\n")
        return

    if ctx.testplan == "start.txt":
        print(
            f"\n{ctx.CLR_OK}{ctx.L('L004', 'The first part of testing is complete!')}{ctx.CLR_NORM}"
        )
        print(ctx.L("L005", "Perform manual testing according to section 10 of the methodology."))
        msg = ctx.L("L006", "Don't forget to run '%s' after testing!")
        print(msg.replace("@BOLD@", ctx.bold(f"{ctx.progname} --finish")))
        return

    stepname = f"{ctx.progname}-{Path(ctx.workdir).name}.tar"
    print(f"\n{ctx.CLR_OK}{ctx.L('L007', 'Testing is complete!')}{ctx.CLR_NORM}")
    print(ctx.L("L008", "Creating the archive '%s'...").replace("@BOLD@", ctx.bold(stepname)))
    wd = Path(ctx.workdir)
    shutil.move(wd / "STATE/RESULTS", wd / "RESULTS")
    shutil.move(wd / "STATE/settings.ini", wd / "settings.ini")
    shutil.rmtree(wd / "STATE", ignore_errors=True)
    home = Path(ctx.homedir or os.environ.get("HOME", ""))
    archive = home / stepname
    with tarfile.open(archive, "w") as tar:
        tar.add(wd, arcname=wd.name)
    mnt = Path(f"/mnt/{ctx.progname}")
    if mnt.is_dir() and ctx.compname:
        dest = mnt / f"{ctx.compname}-{wd.name}.tar"
        try:
            shutil.copy2(archive, dest)
            print(
                ctx.L("L009", "Now this archive has been moved to")
                + f": '{ctx.CLR_WARN}{dest}{ctx.CLR_NORM}'."
            )
            archive.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        try:
            get_context().fatal("F20", "Testing canceled.")
        except Exception:
            print("\nTesting canceled.", file=sys.stderr)
            raise SystemExit(130) from None
    except FatalError as e:
        raise SystemExit(e.code if hasattr(e, "code") else 1) from e
