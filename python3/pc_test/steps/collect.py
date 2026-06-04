"""Collecting hardware information step."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from pc_test.constants import TEST_PASSED
from pc_test.context import graphical_session
from pc_test.steps.base import StepBase, register_step


@register_step
class CollectStep(StepBase):
    STEP_ID = "collect"
    number = "8"
    en_name = "Collecting information about hardware"
    ru_name = "Сбор информации о системе и оборудовании"

    def testcase(self) -> int:
        ctx = self.ctx
        if ctx.username and ctx.langid != "en":
            os.environ["LANG"] = "C"
            os.environ["LC_ALL"] = "C"

        self._run_version()
        self._run_inxi()
        self._run_sosreport()
        self._run_sysreport()
        self._run_make_initrd_bugreport()
        self._run_acpi_lspci_dmidecode()
        self._run_storage_tools()
        self._run_xorg_info()
        self._run_elbrus_cdrom()
        self._run_audio_dumps()
        return TEST_PASSED

    def _run_version(self) -> None:
        ctx = self.ctx
        proc = subprocess.run([ctx.progname, "--version"], capture_output=True, text=True)
        Path("version.txt").write_text(proc.stdout or "", encoding="utf-8")
        if ctx.logfile:
            with open(ctx.logfile, "a", encoding="utf-8") as lf:
                lf.write(proc.stdout or "")

    def _run_inxi(self) -> None:
        ctx = self.ctx
        for args, name, tee in (
            (["inxi", "-v8", "-c2"], "inxi.txt", bool(ctx.colormode)),
            (["inxi", "-CM", "-c0"], "inxi-CM.txt", False),
            (["inxi", "-m", "-c0"], "inxi-m.txt", False),
            (["inxi", "-D", "-c0"], "inxi-D.txt", False),
            (["inxi", "-G", "-c0"], "inxi-G.txt", False),
        ):
            proc = subprocess.run(args, capture_output=True, text=True)
            out = proc.stdout or ""
            if tee and ctx.logfile:
                with open(ctx.logfile, "a", encoding="utf-8") as lf:
                    lf.write(out)
            Path(name).write_text(out, encoding="utf-8")

    def _sos_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONWARNINGS", "ignore::UserWarning")
        return env

    def _run_sosreport(self) -> None:
        ctx = self.ctx
        if not (ctx.devel_test and ctx.is_pkg_installed("sos")):
            return
        ver = subprocess.run(
            ["rpm", "-q", "sos", "--qf", "%{VERSION}"], capture_output=True, text=True
        ).stdout.strip()
        for _pat in ("/var/tmp/sosreport*",):
            for p in Path("/var/tmp").glob("sosreport*"):
                p.unlink(missing_ok=True)
        cmp_proc = subprocess.run(["rpmvercmp", ver, "4.6.0"], capture_output=True, text=True)
        old = (cmp_proc.stdout or "").strip() == "-1"
        if old:
            ctx.cmd_title("sosreport --batch --quiet --all-logs --no-report")
            subprocess.run(
                ["sosreport", "--batch", "--quiet", "--all-logs", "--no-report"],
                env=self._sos_env(),
                check=False,
            )
            self._mv_glob("/var/tmp/sosreport*.tar.xz", "sosreport.tar.xz")
            self._mv_glob("/var/tmp/sosreport*.tar.xz.md5", "sosreport.tar.xz.md5")
        else:
            env = self._sos_env()
            env["TMPDIR"] = "/var/tmp"
            ctx.cmd_title("sos report --batch --quiet --all-logs --no-report")
            subprocess.run(
                ["sos", "report", "--batch", "--quiet", "--all-logs", "--no-report"],
                env=env,
                check=False,
            )
            self._mv_glob("/var/tmp/sosreport*.tar.xz", "sosreport.tar.xz")
            self._mv_glob("/var/tmp/sosreport*.tar.xz.sha256", "sosreport.tar.xz.sha256")

    def _mv_glob(self, pattern: str, dest: str) -> None:
        import glob

        for src in glob.glob(pattern):
            try:
                shutil.move(src, dest)
            except OSError:
                pass

    def _run_sysreport(self) -> None:
        ctx = self.ctx
        os.chdir("/var/tmp")
        for p in Path(".").glob("sysreport*"):
            p.unlink(missing_ok=True)
        if ctx.spawn("timeout", "-s", "KILL", "60s", "system-report") != 0:
            for p in Path(".").glob("sysreport*"):
                p.unlink(missing_ok=True)
            ctx.spawn("timeout", "-s", "KILL", "60s", "system-report", "--no-save-ddcprobe")
        os.chdir(ctx.workdir)
        self._mv_glob("/var/tmp/sysreport*.tar.xz", "sysreport.tar.xz")

    def _run_make_initrd_bugreport(self) -> None:
        ctx = self.ctx
        if not (ctx.devel_test and ctx.has_binary("make-initrd")):
            return
        os.chdir("/var/tmp")
        for p in Path(".").glob("*bugreport*"):
            p.unlink(missing_ok=True)
        if ctx.spawn("make-initrd", "bug-report") == 0:
            self._mv_glob("/var/tmp/make-initrd-bugreport-*.tar.bz2", "bugreport.tar.bz2")
        os.chdir(ctx.workdir)

    def _run_acpi_lspci_dmidecode(self) -> None:
        ctx = self.ctx
        subprocess.run(["acpidump"], stdout=open("acpi.dat", "w"), check=False)
        for args, name, tee in (
            (["lspci", "-nnk"], "lspci.txt", True),
            (["dmidecode"], "dmidecode.txt", False),
            (["dmidecode", "--type", "19"], "mem-info.txt", True),
            (["lsusb"], "lsusb.txt", True),
            (["lsusb", "-t"], "lsusb_hierarchy.txt", True),
        ):
            proc = subprocess.run(args, capture_output=True, text=True)
            out = proc.stdout or ""
            Path(name).write_text(out, encoding="utf-8")
            if tee and ctx.logfile:
                with open(ctx.logfile, "a", encoding="utf-8") as lf:
                    lf.write(out)
        proc = subprocess.run(
            ["env", "LANG=C", "LC_ALL=C", "lscpu"], capture_output=True, text=True
        )
        Path("lscpu.txt").write_text(proc.stdout or "", encoding="utf-8")
        proc = subprocess.run(["lsblk", "-ft"], capture_output=True, text=True)
        Path("lsblk.txt").write_text(proc.stdout or "", encoding="utf-8")

    def _run_storage_tools(self) -> None:
        ctx = self.ctx
        if ctx.has_binary("lsscsi"):
            proc = subprocess.run(["lsscsi", "-v"], capture_output=True, text=True)
            if proc.stdout:
                Path("lsscsi.txt").write_text(proc.stdout, encoding="utf-8")
            elif Path("lsscsi.txt").exists():
                Path("lsscsi.txt").unlink()
        for dev in (ctx.drives or "").split():
            if re.match(r"md\d+", dev):
                continue
            subprocess.run(
                ["smartctl", "-a", "--", f"/dev/{dev}"],
                stdout=open(f"smartctl-{dev}.txt", "w"),
                check=False,
            )
            subprocess.run(["sync"], check=False)
            try:
                Path("/proc/sys/vm/drop_caches").write_text("3")
            except OSError:
                pass
            proc = subprocess.run(
                ["hdparm", "-t", "--direct", "--", f"/dev/{dev}"],
                capture_output=True,
                text=True,
            )
            Path(f"hdparm-{dev}.txt").write_text(proc.stdout or "", encoding="utf-8")
        proc = subprocess.run(["rfkill", "--output-all"], capture_output=True, text=True)
        if proc.stdout:
            Path("rfkill.txt").write_text(proc.stdout, encoding="utf-8")
        elif Path("rfkill.txt").exists():
            Path("rfkill.txt").unlink()
        proc = subprocess.run(["uname", "-a"], capture_output=True, text=True)
        Path("uname.txt").write_text(proc.stdout or "", encoding="utf-8")

    def _run_xorg_info(self) -> None:
        ctx = self.ctx
        if not (ctx.have_xorg and graphical_session()):
            return
        env = os.environ.copy()
        if ctx.rundir:
            env["XDG_RUNTIME_DIR"] = ctx.rundir
        subprocess.run(["xrandr"], stdout=open("xrandr.txt", "w"), check=False)
        proc = subprocess.run(
            ["env", "LANG=C", "LC_ALL=C", "glxinfo"], env=env, capture_output=True, text=True
        )
        Path("glxinfo.txt").write_text(proc.stdout or "", encoding="utf-8")
        for ln in (proc.stdout or "").splitlines():
            if "direct rendering" in ln and ctx.logfile:
                with open(ctx.logfile, "a", encoding="utf-8") as lf:
                    lf.write(ln + "\n")
        if ctx.devel_test:
            for cmd, name in (("es2_info", "es2_info.txt"), ("eglinfo", "eglinfo.txt")):
                if ctx.has_binary(cmd):
                    subprocess.run(
                        ["env", "LANG=C", "LC_ALL=C", cmd],
                        env=env,
                        stdout=open(name, "w"),
                        check=False,
                    )

    def _run_elbrus_cdrom(self) -> None:
        ctx = self.ctx
        if Path("/proc/bootdata").is_file():
            out = subprocess.run(
                ["grep", "cache", "/proc/bootdata"], capture_output=True, text=True
            )
            Path("e2k_cache.txt").write_text(out.stdout or "", encoding="utf-8")
        info = Path("/proc/sys/dev/cdrom/info")
        if info.is_file():
            text = info.read_text()
            if re.search(r"^drive name:\s+", text, re.M):
                Path("dvd-info.txt").write_text(text, encoding="utf-8")
                if ctx.devel_test:
                    for flag, name in (("-vr", "eject-vr.txt"), ("-vt", "eject-vt.txt")):
                        proc = subprocess.run(["eject", flag[1:]], capture_output=True, text=True)
                        Path(name).write_text(proc.stdout or "", encoding="utf-8")
                        if flag == "-vr":
                            import time

                            time.sleep(2)

    def _run_audio_dumps(self) -> None:
        ctx = self.ctx
        if ctx.devel_test and ctx.has_binary("pactl"):
            if not ctx.username:
                subprocess.run(
                    ["env", "LANG=C", "LC_ALL=C", "pactl", "list", "sinks"],
                    stdout=open("pa-sinks.log", "w"),
                    check=False,
                )
            else:
                subprocess.run(
                    ["su", "-", "-c", "env LANG=C LC_ALL=C pactl list sinks", ctx.username],
                    stdout=open("pa-sinks.log", "w"),
                    check=False,
                )
        if ctx.devel_test and ctx.has_binary("pw-dump"):
            env = os.environ.copy()
            if ctx.rundir:
                env["XDG_RUNTIME_DIR"] = ctx.rundir
            env["LANG"] = "C"
            env["LC_ALL"] = "C"
            subprocess.run(
                ["pw-dump", "--color=never"],
                env=env,
                stdout=open("pw-dump.json", "w"),
                stderr=subprocess.DEVNULL,
                check=False,
            )
