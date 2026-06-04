"""Installing additional software step."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pc_test.constants import TEST_PASSED
from pc_test.context import graphical_session
from pc_test.steps.base import StepBase, register_step


@register_step
class InstallStep(StepBase):
    STEP_ID = "install"
    number = "5.5"
    en_name = "Installing additional software"
    ru_name = "Установка дополнительных программ"

    def testcase(self) -> int:
        ctx = self.ctx
        wconf = False
        deinstall: list[str] = []
        packages = [
            "hdparm",
            "system-report",
            "rfkill",
            "acpica",
            "dmidecode",
            "lsblk",
            "smartmontools",
            "stress-ng",
            "cpupower",
        ]
        if ctx.devel_test:
            packages.extend(["sos", "eject"])
        if ctx.ifaces:
            packages.extend(["iputils", "iperf3"])

        if ctx.install_mate:
            mate_pkgs = ["mate-default", "lightdm-gtk-greeter", "fonts-ttf-dejavu"]
            if ctx.xprss_test or ctx.helpfile:
                mate_pkgs.append("firefox-esr")
            for pkg in mate_pkgs:
                if not ctx.is_pkg_available(pkg):
                    ctx.install_mate = ""
                    wconf = True
                    break
            if ctx.install_mate:
                for pkg in mate_pkgs + ["yad"]:
                    if not ctx.is_pkg_installed(pkg):
                        packages.append(pkg)
                ctx.have_xorg = "1"
                ctx.have_mate = "1"
                wconf = True

        if ctx.fwupd_test and ctx.is_pkg_available("fwupd") and not ctx.is_pkg_installed("fwupd"):
            packages.append("fwupd")

        if not ctx.is_pkg_installed("lsscsi") and ctx.is_pkg_available("lsscsi"):
            packages.append("lsscsi")

        if ctx.infb_test and ctx.is_pkg_available("libibverbs-utils"):
            if not ctx.is_pkg_installed("libibverbs-utils"):
                packages.append("libibverbs-utils")

        if ctx.sound_test or ctx.webcam_test:
            for pkg in ("alsa-utils", "aplay", "pulseaudio-daemon", "pulseaudio-utils"):
                if ctx.is_pkg_available(pkg) and not ctx.is_pkg_installed(pkg):
                    packages.append(pkg)

        if ctx.power_test and ctx.is_pkg_available("upower"):
            if not ctx.have_xorg and not ctx.is_pkg_installed("upower"):
                packages.append("upower")

        if ctx.numa_test:
            numa_list = ["htop", "numactl", "squashfs-tools"]
            ok = all(ctx.is_pkg_installed(p) or ctx.is_pkg_available(p) for p in numa_list)
            if not ok:
                ctx.numa_test = "1"
            else:
                for pkg in numa_list:
                    if not ctx.is_pkg_installed(pkg):
                        packages.append(pkg)

        if ctx.ipmi_test and ctx.is_pkg_available("ipmitool"):
            if not ctx.is_pkg_installed("ipmitool"):
                packages.append("ipmitool")

        if not ctx.have_xorg or (
            not ctx.install_mate and not graphical_session()
        ):
            ctx.webcam_test = ""
            ctx.v3d_test = ""
            wconf = True
        else:
            if not ctx.is_pkg_installed("xrandr"):
                packages.append("xrandr")
            if not ctx.has_binary("glxinfo"):
                packages.append("/usr/bin/glxinfo")
            if ctx.webcam_test or ctx.sound_test:
                if ctx.have_kde5 and ctx.distro == "KWS":
                    pkg = "kamoso"
                elif ctx.distro == "SRV":
                    pkg = "vlc"
                else:
                    pkg = "cheese"
                for p in (pkg, "icon-theme-adwaita", "sound-theme-freedesktop"):
                    if ctx.is_pkg_available(p) and not ctx.is_pkg_installed(p):
                        packages.append(p)
            if ctx.v3d_test and ctx.is_pkg_available("glmark2"):
                if not ctx.is_pkg_installed("glmark2"):
                    packages.append("glmark2")

        if ctx.xprss_test and ctx.have_xorg:
            for pkg in (
                "yad",
                "notify-send",
                "xdg-utils",
                "pulseaudio-utils",
                "icon-theme-adwaita",
                "sound-theme-freedesktop",
            ):
                if ctx.is_pkg_available(pkg) and not ctx.is_pkg_installed(pkg):
                    packages.append(pkg)

        if ctx.fprnt_test and ctx.is_pkg_available("fprintd"):
            if not ctx.is_pkg_installed("fprintd"):
                packages.append("fprintd")

        if ctx.bluez_test and ctx.is_pkg_available("bluez"):
            if not ctx.is_pkg_installed("bluez"):
                packages.append("bluez")

        if ctx.scard_test:
            scard_list = [
                "pcsc-lite-ccid",
                "libpcsclite",
                "pcsc-tools",
                "opensc",
                "pcsc-lite",
            ]
            for pkg in scard_list:
                if not ctx.is_pkg_installed(pkg) and not ctx.is_pkg_available(pkg):
                    ctx.scard_test = ""
                    wconf = True
                    break
            if ctx.scard_test:
                for pkg in scard_list:
                    if not ctx.is_pkg_installed(pkg) and ctx.is_pkg_available(pkg):
                        packages.append(pkg)
                for pkg in ("openct", "pcsc-lite-openct", "libopenct"):
                    if ctx.is_pkg_installed(pkg):
                        deinstall.append(pkg)

        if ctx.fio_test and ctx.is_pkg_available("fio"):
            if not ctx.is_pkg_installed("fio"):
                packages.append("fio")

        if ctx.have_mate or ctx.have_kde5 or ctx.have_xfce or ctx.have_gnome:
            if ctx.is_pkg_installed("acpid-events-power"):
                deinstall.append("acpid-events-power")

        if deinstall:
            ctx.spawn("apt-get", "remove", "--purge", "-y", "--", *deinstall)
        ctx.spawn("remove-old-kernels", "-f")
        ctx.spawn("apt-get", "autoremove", "--purge", "-y")
        ctx.spawn("apt-get", "install", "-y", "--", *packages)
        ctx.spawn("apt-get", "autoremove", "--purge", "-y")
        ctx.spawn("apt-get", "clean")

        if ctx.has_binary("systemctl") and ctx.has_binary("journalctl"):
            if not ctx.have_systemd:
                wconf = True
            ctx.have_systemd = "1"

        if ctx.infb_test and ctx.is_pkg_installed("libibverbs-utils"):
            modules = [
                "ib_ipoib",
                "rdma_ucm",
                "ib_uverbs",
                "ib_umad",
                "rdma_cm",
                "ib_cm",
                "ib_mad",
                "iw_cm",
            ]
            mod_path = Path("/etc/modules")
            existing = mod_path.read_text(encoding="utf-8") if mod_path.is_file() else ""
            for mod in modules:
                proc = subprocess.run(["modinfo", mod], capture_output=True, check=False)
                if proc.returncode == 0 and mod not in existing:
                    with open(mod_path, "a", encoding="utf-8") as f:
                        f.write(mod + "\n")

        if ctx.ipmi_test and ctx.has_binary("ipmitool"):
            with open("/etc/modules", "a", encoding="utf-8") as f:
                f.write("ipmi_msghandler\nipmi_devintf\nipmi_si\n")

        if ctx.fprnt_test and ctx.have_systemd and ctx.is_pkg_installed("fprintd"):
            ctx.spawn("systemctl", "enable", "fprintd")
        if ctx.bluez_test and ctx.have_systemd and ctx.is_pkg_installed("bluez"):
            ctx.spawn("systemctl", "enable", "bluetooth")
        if ctx.scard_test and ctx.have_systemd and ctx.is_pkg_installed("pcsc-lite"):
            ctx.spawn("systemctl", "enable", "pcscd.service", "pcscd.socket")
        if ctx.install_mate and ctx.have_systemd:
            ctx.spawn("systemctl", "enable", "lightdm")
            ctx.spawn("systemctl", "set-default", "graphical.target")
        if ctx.have_altsp and ctx.has_binary("integalert"):
            ctx.spawn("integalert", "fix")
        if ctx.have_systemd:
            ctx.stop_journald()

        if wconf:
            ctx.print_settings_ini("install.ini")
        ctx.system_restart()
        return TEST_PASSED
