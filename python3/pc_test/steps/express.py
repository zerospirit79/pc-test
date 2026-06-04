"""Express test of main components step."""

from __future__ import annotations

import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from pc_test.constants import (
    TEST_ALLOWED,
    TEST_BLOCKED,
    TEST_FAILED,
    TEST_PASSED,
    TEST_SKIPPED,
)
from pc_test.context import graphical_session
from pc_test.de_terminal import prepare_user_session_env
from pc_test.gui import forms
from pc_test.steps.base import StepBase, register_step

EXPRESS_FILES = [
    "express.step",
    "EXPRESS-AUTOTEST",
    "POWEROFF-STARTED",
    "REBOOT-STARTED",
    "HIBERNATE-STARTED",
    "SUSPEND-STARTED",
    "POWEROFF-FINISHED",
    "REBOOT-FINISHED",
    "HIBERNATE-FINISHED",
    "SUSPEND-FINISHED",
    "POWEROFF-FAILED",
    "REBOOT-FAILED",
    "HIBERNATE-FAILED",
    "SUSPEND-FAILED",
    "NETWORK-FAILED",
    "WIFI-FAILED",
    "WIFI-PASSED",
    "h.dmesg.gz",
    "s.dmesg.gz",
    "h.status",
    "s.status",
]


def express_video_url(ctx) -> str:
    url = ctx.local_video_sample
    homedir = ctx.homedir or os.path.expanduser("~")
    for idx in (
        Path(homedir) / f".config/{ctx.progname}-{ctx.express_video_set}.txt",
        Path(f"/etc/{ctx.progname}-{ctx.express_video_set}.txt"),
        Path(f"/var/lib/{ctx.progname}/{ctx.express_video_set}.txt"),
    ):
        vbase_candidates = (
            Path(homedir) / f".config/{ctx.progname}-RVSETS.txt",
            Path(f"/etc/{ctx.progname}-RVSETS.txt"),
            Path(f"/var/lib/{ctx.progname}/rvsets.txt"),
        )
        if not idx.is_file():
            continue
        vsamples = [ln.strip() for ln in idx.read_text().splitlines() if ln.strip()]
        vbase = next((p for p in vbase_candidates if p.is_file()), None)
        if not vsamples or not vbase:
            continue
        pick = vsamples[random.randint(0, len(vsamples) - 1)]
        for ln in vbase.read_text().splitlines():
            if re.match(rf"^{re.escape(ctx.express_video_set)}\s+", ln):
                url = re.sub(rf"^{re.escape(ctx.express_video_set)}\s+", "", ln).strip()
                url = url.replace("@VURL@", pick)
                return url
    return url or "https://ya.ru/video/preview/14399646464678007768"


@register_step
class ExpressStep(StepBase):
    STEP_ID = "express"
    number = "9"
    en_name = "Express test of main components"
    ru_name = "Экспресс-тест основных компонентов"

    def pre(self) -> int:
        ctx = self.ctx
        prepare_user_session_env(ctx)
        if not Path("express.step").is_file():
            Path("./EXPRESS-AUTOTEST").unlink(missing_ok=True)
        ctx.spawn(": Checking the test plan...")
        if not ctx.xprss_test:
            return TEST_SKIPPED
        ctx.spawn(": Checking for a Xorg server...")
        if not ctx.have_xorg:
            return TEST_SKIPPED
        ctx.spawn(": Checking for Network interfaces...")
        if not ctx.ifaces:
            return TEST_SKIPPED
        ctx.spawn(": Checking for a Desktop Environment...")
        if not (ctx.have_mate or ctx.have_kde5 or ctx.have_xfce or ctx.have_gnome):
            return TEST_SKIPPED
        ctx.spawn(": Checking XDG_CURRENT_DESKTOP...")
        if os.environ.get("XDG_CURRENT_DESKTOP") not in ("KDE", "MATE", "XFCE", "GNOME"):
            return TEST_SKIPPED
        ctx.spawn(": Checking for a Graphics card...")
        if Path("inxi-G.txt").is_file():
            if " Device-1: " not in Path("inxi-G.txt").read_text():
                return TEST_SKIPPED
        elif ctx.spawn("grep", "-qs", " Device-1: ", "inxi-G.txt") != 0:
            return TEST_SKIPPED
        ctx.spawn(": Checking DISPLAY...")
        if not graphical_session():
            return TEST_BLOCKED
        st = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if not st:
            if os.environ.get("WAYLAND_DISPLAY"):
                st = "wayland"
            elif os.environ.get("DISPLAY"):
                st = "x11"
        ctx.spawn(": Checking XDG_SESSION_TYPE...")
        if st not in ("x11", "wayland", "xorg"):
            return TEST_BLOCKED
        ctx.spawn(": Checking for a systemd...")
        if not ctx.have_systemd:
            return TEST_BLOCKED
        for p in ("yad", "xdg-open", "pactl", "paplay"):
            ctx.spawn(f": Checking for a binary: {p}...")
            if not ctx.has_binary(p):
                ctx.spawn(f": Required program not found: {p}")
                return TEST_BLOCKED
        ctx.spawn(": Checking for a binary: notify-send...")
        if not ctx.has_binary("notify-send"):
            ctx.spawn(": notify-send not found, desktop notifications will be unavailable")
        sound = "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga"
        if not Path(sound).is_file():
            ctx.spawn(f": Required sound file not found: {sound}")
            return TEST_BLOCKED
        icons = (
            "/usr/share/icons/Adwaita/32x32/legacy/audio-volume-muted.png",
            "/usr/share/icons/Adwaita/symbolic/status/audio-volume-muted-symbolic.svg",
        )
        if not any(Path(i).is_file() for i in icons):
            ctx.spawn(": Adwaita audio icon not found (install icon-theme-adwaita)")
            return TEST_BLOCKED
        for p in range(50):
            ctx.spawn(": Waiting for a network connection...")
            route = subprocess.run(["ip", "route"], capture_output=True, text=True).stdout or ""
            if re.search(r"^default via ", route, re.M):
                ctx.spawn(f": Network connection established, counter={p}")
                return TEST_ALLOWED
            time.sleep(0.3)
        ctx.spawn(": Network unreachable, the express test is blocked")
        return TEST_BLOCKED

    def testcase(self) -> int:
        ctx = self.ctx
        if os.geteuid() == 0:
            return TEST_BLOCKED
        ctx.en_name = self.en_name
        ctx.ru_name = self.ru_name
        prepare_user_session_env(ctx)
        mode = self._choice_mode()
        if mode == "failed":
            return TEST_BLOCKED
        if mode == "autotest":
            rc = self._autotest()
            if rc != TEST_PASSED:
                return rc
        else:
            subprocess.run(
                ["xdg-open", express_video_url(ctx)],
                stderr=open(ctx.xorglog, "a") if ctx.xorglog else subprocess.DEVNULL,
                env=forms._gui_env(),
                check=False,
            )
            rc = forms.form_gui(ctx, "_экспресс_тест_основных_компонентов", self.title())
            if rc != TEST_PASSED:
                return rc
        return TEST_PASSED

    def reset_results(self) -> None:
        files = [Path(f"./{f}") for f in EXPRESS_FILES if Path(f"./{f}").is_file()]
        if files:
            subprocess.run(["rm", "-f", *[str(f) for f in files]], check=False)

    def show_results(self, rc: int, *, log: bool = True) -> None:
        autotest = Path("./EXPRESS-AUTOTEST")
        if rc == TEST_BLOCKED or not autotest.is_file():
            return
        if autotest.read_text().strip() != "0":
            return
        self._express_show_results(rc, log=log)

    def _express_show_results(self, overall_rc: int, *, log: bool = True) -> None:
        ctx = self.ctx
        num = ctx.number or "9"

        def po_rc():
            if not Path("./POWEROFF-STARTED").is_file():
                return TEST_SKIPPED
            return TEST_PASSED if Path("./POWEROFF-FINISHED").is_file() else TEST_FAILED

        def settings_rc():
            return TEST_BLOCKED if not Path("./REBOOT-STARTED").is_file() else TEST_PASSED

        def sleep_rc(prefix: str):
            if not Path(f"./{prefix}-STARTED").is_file():
                return TEST_SKIPPED
            return TEST_PASSED if Path(f"./{prefix}-FINISHED").is_file() else TEST_FAILED

        ctx.draw_title_line(po_rc(), f"{num}.1", ctx.L("L259", "Power OFF"), log=log)
        ctx.draw_title_line(settings_rc(), f"{num}.2", ctx.L("L263", "Settings"), log=log)
        ctx.draw_title_line(sleep_rc("HIBERNATE"), f"{num}.3", ctx.L("L257", "Hibernate"), log=log)
        ctx.draw_title_line(sleep_rc("SUSPEND"), f"{num}.4", ctx.L("L258", "Suspend"), log=log)
        net = (
            TEST_FAILED
            if Path("./NETWORK-FAILED").is_file()
            else (TEST_SKIPPED if not Path("./POWEROFF-STARTED").is_file() else TEST_PASSED)
        )
        ctx.draw_title_line(net, f"{num}.5", ctx.L("L264", "Network"), log=log)
        wifi = (
            TEST_FAILED
            if Path("./WIFI-FAILED").is_file()
            else (TEST_PASSED if Path("./WIFI-PASSED").is_file() else TEST_SKIPPED)
        )
        ctx.draw_title_line(wifi, f"{num}.6", ctx.L("L265", "WiFi"), log=log)
        reboot = (
            TEST_FAILED
            if Path("./REBOOT-FAILED").is_file()
            else (TEST_SKIPPED if not Path("./REBOOT-STARTED").is_file() else TEST_PASSED)
        )
        ctx.draw_title_line(reboot, f"{num}.7", ctx.L("L266", "Reboot"), log=log)

    def _choice_mode(self) -> str:
        """Return 'autotest', 'manual', or 'failed' for express testing mode."""
        ctx = self.ctx
        prepare_user_session_env(ctx)
        autotest = Path("./EXPRESS-AUTOTEST")
        if autotest.is_file():
            val = autotest.read_text().strip()
            if val == "0":
                return "autotest"
            if val == "1":
                return "manual"
            return "failed"
        msg = ctx.L(
            "L260",
            "Before express testing, the computer will be turned off. "
            "To switch to manual testing, press Cancel or Esc.",
        )
        fld = ctx.L(
            "L261",
            "Don't forget to turn on the video recording and show a close-up "
            "of the computer model, ports for external monitors and audio devices.",
        )
        img = "/usr/share/icons/Adwaita/symbolic/actions/system-shutdown-symbolic.svg"
        if not Path(img).is_file():
            img = "/usr/share/icons/Adwaita/48x48/legacy/system-shutdown.png"
        args = [
            "yad",
            "--width=620",
            "--height=150",
            "--borders=10",
            "--center",
            "--on-top",
            "--window-icon=utilities-system-monitor",
            f"--title={self.title()}",
            f"--text={msg}",
            "--form",
            f"--field={fld}:LBL",
        ]
        if Path(img).is_file():
            args.insert(-2, f"--image={img}")
        if ctx.batchmode:
            args.extend(["--timeout-indicator=bottom", "--timeout=15"])
        proc = subprocess.run(
            args,
            stderr=open(ctx.xorglog, "a") if ctx.xorglog else subprocess.DEVNULL,
            env=forms._gui_env(),
        )
        yad_rc = proc.returncode
        if ctx.xorglog:
            with open(ctx.xorglog, "a", encoding="utf-8") as lf:
                lf.write(f"*** express _choice_mode yad_rc={yad_rc}\n")
        if yad_rc == 0 or (yad_rc == 70 and ctx.batchmode):
            autotest.write_text("0\n")
            return "autotest"
        if yad_rc in (1, 252):
            autotest.write_text("1\n")
            return "manual"
        return "failed"

    def _autotest(self) -> int:
        sfile = Path("express.step")
        stepno = int(sfile.read_text().splitlines()[0]) if sfile.is_file() else 1
        rc = TEST_PASSED
        brpid = ""

        if 2 <= stepno <= 5:
            init_rc = self._autotest_init()
            if init_rc != TEST_PASSED:
                rc = init_rc
                stepno = 7

        while stepno < 7:
            sfile.write_text(f"{stepno}\n")
            if stepno == 1:
                po = self._try_poweroff()
                if po != TEST_PASSED:
                    rc = po
                    break
            elif stepno == 2:
                self._show_settings()
            elif stepno == 3:
                self._try_hibernate()
            elif stepno == 4:
                self._try_suspend()
            elif stepno == 5:
                brpid = self._additional_hw(brpid)
            else:
                self._try_reboot()
            stepno += 1

        if rc == TEST_PASSED:
            if any(
                Path(f"./{m}").is_file()
                for m in (
                    "POWEROFF-FAILED",
                    "HIBERNATE-FAILED",
                    "SUSPEND-FAILED",
                    "NETWORK-FAILED",
                    "WIFI-FAILED",
                    "REBOOT-FAILED",
                )
            ):
                rc = TEST_FAILED
            elif (
                not Path("./SUSPEND-STARTED").is_file()
                and not Path("./HIBERNATE-STARTED").is_file()
            ):
                rc = TEST_SKIPPED

        self._express_show_results(rc, log=False)
        sfile.unlink(missing_ok=True)
        return rc

    def _save_date(self, name: str) -> None:
        Path(f"./{name}").write_text(
            subprocess.run(
                ["env", "LANG=C", "LC_ALL=C", "date"], capture_output=True, text=True
            ).stdout
        )

    def _try_poweroff(self) -> int:
        ctx = self.ctx
        if Path("./POWEROFF-STARTED").is_file():
            self._save_date("POWEROFF-FINISHED")
            self._autotest_init()
            return TEST_PASSED
        subprocess.run(["notify-send", self.title(), ctx.L("L259", "Power OFF")], check=False)
        time.sleep(5)
        self._save_date("POWEROFF-STARTED")
        session = subprocess.run(["loginctl", "session-status"], capture_output=True, text=True)
        sid = (session.stdout or "").splitlines()[0].split()[0] if session.stdout else ""
        if ctx.spawn("systemctl", "-i", "poweroff") == 0:
            ctx.spawn("loginctl", "terminate-session", sid)
            sys.exit(0)
        self._save_date("POWEROFF-FAILED")
        return TEST_PASSED

    def _autotest_init(self) -> int:
        ctx = self.ctx
        url = express_video_url(ctx)
        browser = ""
        if ctx.has_binary("xdg-settings"):
            b = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True
            ).stdout.strip()
            desktop = Path(f"/usr/share/applications/{b}")
            if desktop.is_file():
                for ln in desktop.read_text().splitlines():
                    if ln.startswith("Exec="):
                        browser = ln[5:].split()[0]
                        break
                if browser and not (Path(browser).is_file() or ctx.has_binary(browser)):
                    browser = ""
        if not browser:
            for i in (
                "firefox",
                "chromium",
                "chromium-gost",
                "yandex-browser-stable",
                "yandex-browser",
            ):
                if ctx.has_binary(i):
                    browser = i
                    break
        if not browser:
            return TEST_BLOCKED
        cmd = [browser]
        if browser == "firefox":
            cmd = ["firefox", "--new-tab"]
        subprocess.run(
            ["notify-send", self.title(), ctx.L("L254", "Start playing the video...")], check=False
        )
        subprocess.Popen(
            cmd + [url], stderr=open(ctx.xorglog, "a") if ctx.xorglog else subprocess.DEVNULL
        )
        self._set_audio_volume(50)
        time.sleep(15)
        return TEST_PASSED

    def _set_audio_volume(self, volume: int) -> None:
        ctx = self.ctx
        if volume == 0:
            ctx.spawn("pactl", "set-sink-mute", "0", "1")
        else:
            ctx.spawn("pactl", "set-sink-mute", "0", "0")
            sound = "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga"
            if ctx.spawn("pactl", "set-sink-volume", "0", f"{volume}%") == 0:
                for _ in range(5):
                    ctx.spawn("paplay", sound)

    def _kde_display_settings_cmd(self) -> list[str] | None:
        ctx = self.ctx
        for prog in ("systemsettings", "systemsettings6", "systemsettings5"):
            if ctx.has_binary(prog):
                return [prog, "kcm_kscreen"]
        return None

    def _show_settings(self) -> None:
        ctx = self.ctx
        de = os.environ.get("XDG_CURRENT_DESKTOP", "")
        subprocess.run(["xrandr", "--listactivemonitors"], check=False)
        cmd: list[str] | None = None
        if de == "GNOME" and ctx.has_binary("gnome-control-center"):
            cmd = ["gnome-control-center", "display"]
        elif de == "KDE":
            cmd = self._kde_display_settings_cmd()
        elif de == "MATE" and ctx.has_binary("mate-display-properties"):
            cmd = ["mate-display-properties"]
        elif de == "XFCE" and ctx.has_binary("xfce4-display-settings"):
            cmd = ["xfce4-display-settings"]
        if cmd:
            proc = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
            time.sleep(15)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        time.sleep(30)
        primary = ""
        for ln in subprocess.run(["xrandr"], capture_output=True, text=True).stdout.splitlines():
            if " connected primary " in ln:
                primary = ln.split()[0]
                break
        sound = "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga"
        if primary:
            for br in (0.25, 0.33, 0.5, 0.75, 1.5, 1.25, 1):
                if ctx.spawn("xrandr", "--output", primary, "--brightness", str(br)) == 0:
                    ctx.spawn("paplay", sound)
                time.sleep(2)
        self._set_audio_volume(0)
        time.sleep(15)
        self._set_audio_volume(75)
        time.sleep(15)
        self._set_audio_volume(25)
        time.sleep(15)

    def _try_hibernate(self) -> None:
        self._try_sleep("hibernate", "HIBERNATE", "L257")

    def _try_suspend(self) -> None:
        self._try_sleep("suspend", "SUSPEND", "L258")

    def _try_sleep(self, target: str, prefix: str, msg_key: str) -> None:
        ctx = self.ctx
        masked = subprocess.run(
            ["systemctl", "status", f"{target}.target"], capture_output=True, text=True
        )
        if re.search(r"^\s+Loaded: masked ", masked.stdout or "", re.M):
            return
        started = Path(f"./{prefix}-STARTED")
        if started.is_file():
            self._save_date(f"{prefix}-FAILED")
            time.sleep(45)
            return
        subprocess.run(["notify-send", self.title(), ctx.L(msg_key, target)], check=False)
        time.sleep(5)
        self._save_date(f"{prefix}-STARTED")
        if ctx.spawn("systemctl", "-i", target) != 0:
            self._save_date(f"{prefix}-FAILED")
            time.sleep(40)
            return
        time.sleep(30)
        self._save_date(f"{prefix}-FINISHED")
        svc = f"systemd-{target}.service"
        subprocess.run(
            ["systemctl", "status", svc], stdout=open(f"{target[0]}.status", "w"), check=False
        )
        subprocess.run(
            ["sudo", "dmesg", "-H", "-P", "--color=always"],
            stdout=open(f"{target[0]}.dmesg.gz", "wb"),
            check=False,
        )
        subprocess.run(["notify-send", self.title(), ctx.L("L267", "Click Play")], check=False)

    def _additional_hw(self, brpid: str) -> str:
        ctx = self.ctx
        eth, wifi = self._has_dualnet()
        if ctx.has_binary("nmcli") and eth and wifi:
            subprocess.run(["notify-send", self.title(), ctx.L("L265", "WiFi")], check=False)
            ctx.spawn("nmcli", "c", "down", eth)
            ctx.spawn("nmcli", "c", "up", wifi)
            time.sleep(20)
            if ctx.check_internet():
                self._save_date("WIFI-PASSED")
            else:
                self._save_date("WIFI-FAILED")
            ctx.spawn("nmcli", "c", "up", eth)
            time.sleep(10)
        else:
            time.sleep(20)
        if not ctx.check_internet():
            self._save_date("NETWORK-FAILED")
        t = 40
        l256 = ctx.L("L256", "Manual mode %s sec")
        try:
            notify_text = l256 % (t,)
        except TypeError:
            notify_text = l256.replace("%s", str(t), 1)
        subprocess.run(
            ["notify-send", self.title(), notify_text],
            check=False,
        )
        time.sleep(t)
        return brpid

    def _has_dualnet(self) -> tuple[str, str]:
        proc = subprocess.run(
            ["env", "LANG=C", "LC_ALL=C", "nmcli", "-c", "no", "-f", "TYPE,ACTIVE,UUID", "c"],
            capture_output=True,
            text=True,
        )
        eth = wifi = ""
        for ln in (proc.stdout or "").splitlines():
            parts = ln.split()
            if len(parts) < 3 or parts[1] != "yes":
                continue
            if parts[0] == "wifi":
                wifi = parts[2]
            elif parts[0] == "ethernet":
                eth = parts[2]
        return eth, wifi

    def _try_reboot(self) -> None:
        ctx = self.ctx
        if Path("./REBOOT-STARTED").is_file():
            self._save_date("REBOOT-FINISHED")
            return
        subprocess.run(["notify-send", self.title(), ctx.L("L266", "Reboot")], check=False)
        time.sleep(5)
        self._save_date("REBOOT-STARTED")
        os.execvp("systemctl", ["systemctl", "-i", "reboot"])
