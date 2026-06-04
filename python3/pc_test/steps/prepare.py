"""Preparing for a system update step."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pc_test.constants import TEST_PASSED
from pc_test.steps.base import StepBase, register_step


def _run_text(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return (proc.stdout or "").strip()
    except OSError:
        return ""


def _sysfs_first_line(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[0].strip() if lines else ""
    except OSError:
        return ""


@register_step
class PrepareStep(StepBase):
    STEP_ID = "prepare"
    number = "5.1"
    en_name = "Preparing for a system update"
    ru_name = "Подготовка к обновлению системы"

    def testcase(self) -> int:
        ctx = self.ctx

        if _sysfs_first_line(Path("/sys/kernel/security/evm")) == "1":
            ctx.fatal("F04", "First you need to disable %s!", "IMA/EVM")

        # sysfs nodes may exist without the LSM being active (common on ALT)
        if Path("/sys/kernel/security/apparmor").is_dir() and ctx.has_binary("aa-enabled"):
            if _run_text(["aa-enabled"]) == "Yes":
                ctx.fatal("F04", "First you need to disable %s!", "AppArmor")

        if Path("/sys/kernel/security/selinux").is_dir() or Path("/sys/fs/selinux").is_dir():
            mode = ""
            if ctx.has_binary("getenforce"):
                mode = _run_text(["getenforce"]).lower()
            elif ctx.has_binary("sestatus"):
                for ln in _run_text(["sestatus"]).splitlines():
                    if ln.startswith("Current mode:"):
                        mode = ln.split(":", 1)[1].strip().lower()
                        break
            if mode == "enforcing":
                ctx.fatal("F04", "First you need to disable %s!", "SELinux")

        aer_pat = r"AER: (Corrected error message|Multiple Corrected error) received"
        dmesg = _run_text(["dmesg"]) if ctx.has_binary("dmesg") else ""
        if dmesg and len(re.findall(aer_pat, dmesg)) > 9:
            ctx.fatal("F05", "Use pcie_aspm=off, pci=nomsi or pci=noaer boot options!")

        ctx.archname = _run_text(["uname", "-m"])

        r = Path("/etc/os-release")
        if not r.is_file():
            ctx.fatal("F06", "ALT Linux or compatible distro is required!")
        text = r.read_text(encoding="utf-8", errors="replace")
        if "ID=altlinux" not in text and 'ID="altlinux"' not in text:
            ctx.fatal("F06", "ALT Linux or compatible distro is required!")

        def _field(key: str) -> str:
            m = re.search(rf"^{key}=(.*)$", text, re.M)
            if not m:
                return ""
            return m.group(1).strip().strip('"')

        n = _field("NAME").lower()
        p = _field("PRETTY_NAME")
        v = _field("VERSION_ID")
        ctx.repo = ""

        if n == "myoffice plus":
            ctx.distro, ctx.repo = "WS", "p10"
        elif n == "alt tonk":
            ctx.distro = "WS"
        else:
            ctx.distro = self._detect_distro(n, p)
            if ctx.distro is None:
                ctx.fatal("F07", "Unsupported distro: %s", p or n)

        sp_markers = ("alt 8 sp", "alt sp", "(cliff)")
        pl = p.lower()
        if any(m in n or m in pl for m in sp_markers):
            if ctx.distro in ("WS", "SRV"):
                ctx.have_altsp = "1"

        if not ctx.repo and ctx.have_altsp:
            if v == "10.2" or v.startswith("10.2."):
                ctx.repo = "c10f2"
            else:
                repo_map = {
                    "8.2": "c9f1",
                    "8.4": "c9f2",
                    "10": "c10f1",
                }
                if v not in repo_map:
                    ctx.fatal("F08", "Unsupported certified distro: %s", p)
                ctx.repo = repo_map[v]
        elif not ctx.repo:
            if re.match(r"^(9|9\..*|p9|p9-mipsel)$", v):
                ctx.repo = "p9"
            elif re.match(r"^(10|10\..*|p10)$", v):
                ctx.repo = "p10"
            elif re.match(r"^(11|11\..*|p11)$", v):
                ctx.repo = "p11"
            else:
                ctx.fatal("F09", "Unsupported distro version: %s", p or v)

        ctx.distroname = p

        if ctx.has_binary("systemctl") and ctx.has_binary("journalctl"):
            ctx.have_systemd = "1"

        if (
            Path("/usr/bin/Xorg").is_file()
            or Path("/usr/bin/Xwayland").is_file()
            or ctx.is_pkg_installed("wayland")
        ):
            ctx.have_xorg = "1"
        for pkg, attr in (
            ("gnome-shell", "have_gnome"),
            (
                (
                    "kde",
                    "kde5",
                    "plasma6-plasma5support-common",
                    "plasma6-workspace",
                    "plasma6-workspace-common",
                    "kde6-runtime",
                ),
                "have_kde5",
            ),
            (("mate-minimal", "mate-default", "mate-window-manager"), "have_mate"),
            (("xfce4-minimal", "xfce4-default"), "have_xfce"),
        ):
            if isinstance(pkg, tuple):
                if any(ctx.is_pkg_installed(p) for p in pkg):
                    setattr(ctx, attr, "1")
                    ctx.have_xorg = "1"
            elif ctx.is_pkg_installed(pkg):
                setattr(ctx, attr, "1")
                ctx.have_xorg = "1"

        ctx.write_config()
        return TEST_PASSED

    @staticmethod
    def _detect_distro(n: str, p: str) -> str | None:
        pl = p.lower()
        if "sisyphus" in n or "regular" in pl:
            return "REG"
        if "starter" in n or "starter" in pl:
            return "SKIT"
        if "simply" in n or "simply" in pl:
            return "SL"
        if "workstation k" in pl or "k workstation" in pl:
            return "KWS"
        if "workstation" in n or "workstation" in pl:
            return "WS"
        if "education" in n or "education" in pl:
            return "EDU"
        if "server-v" in n or "virtualization" in pl:
            return "ASV"
        if "server" in n or "server" in pl:
            return "SRV"
        return None
