"""Hardware auto-detection step."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from pc_test.constants import TEST_PASSED
from pc_test.steps.base import StepBase, register_step


@register_step
class DetectStep(StepBase):
    STEP_ID = "detect"
    number = "5.3"
    en_name = "Automatic hardware discovery"
    ru_name = "Определение конфигурации оборудования"

    def testcase(self) -> int:
        ctx = self.ctx
        i = 0
        tmpf = Path("/sys/class/dmi/id")
        if not tmpf.is_dir():
            tmpf = Path("/sys/devices/virtual/dmi/id")

        chassis = tmpf / "chassis_type"
        if chassis.is_file():
            try:
                i = int(chassis.read_text().split()[0])
            except (ValueError, OSError):
                i = 0

        pctype_map = {
            (3, 4, 5, 6, 7, 15, 16, 24, 36): "Personal",
            (8, 9, 10, 14): "Notebook",
            (17, 22, 23, 28, 29): "Server",
            (13,): "Monoblock",
            (30,): "Tablet",
            (31,): "Convertible",
        }
        ctx.pctype = "Computer"
        for types, name in pctype_map.items():
            if i in types:
                ctx.pctype = name
                break
        else:
            lscpu = subprocess.run(["lscpu"], capture_output=True, text=True)
            if "Hypervisor vendor:" in (lscpu.stdout or ""):
                ctx.pctype = "Virtual"

        if not ctx.compname:
            for attr in ("product_name", "board_name"):
                p = tmpf / attr
                if p.is_file():
                    name = re.sub(
                        r"[\(\),].*$", "", p.read_text().splitlines()[0].replace(" ", "")
                    )
                    if name:
                        ctx.compname = name
                        break
            if not ctx.compname:
                altsp = "-cert" if ctx.have_altsp else ""
                ctx.compname = f"{ctx.pctype}-{ctx.archname}{altsp}-{ctx.distro}{ctx.repo}"

        proc = ctx.spawn_capture("mktemp", "-qt", f"{ctx.progname}-XXXXXXXX.tmp")
        tmp_path = proc.stdout.strip() if proc.returncode == 0 else "/tmp/pc-test-detect.tmp"

        drives: list[str] = []
        block = Path("/sys/block")
        if block.is_dir():
            for dev in block.iterdir():
                name = dev.name
                if re.match(r"loop\d+|ram\d+|sr\d+|dm-\d+|md\d+", name):
                    continue
                if not Path(f"/dev/{name}").is_block_device():
                    continue
                ro = dev / "ro"
                if ro.is_file() and ro.read_text().strip() != "0":
                    continue
                slaves = dev / "slaves"
                if slaves.is_dir() and any(slaves.iterdir()):
                    continue
                holders = dev / "holders"
                if holders.is_dir() and any(holders.iterdir()):
                    continue
                drives.append(name)

        if not drives:
            for dev in block.iterdir() if block.is_dir() else []:
                if re.match(r"md\d+", dev.name) and Path(f"/dev/{dev.name}").is_block_device():
                    drives.append(dev.name)

        ctx.drives = " ".join(drives)

        lspci_out = subprocess.run(["lspci"], capture_output=True, text=True).stdout or ""
        Path(tmp_path).write_text(lspci_out, encoding="utf-8")
        if re.search(r"\bRDMA\b", lspci_out, re.I) or re.search(r"infiniband", lspci_out, re.I):
            ctx.infb_test = "1"

        if self._detect_sound_card():
            ctx.sound_test = "1"

        lscpu_nodes = subprocess.run(["lscpu", "--parse=NODE"], capture_output=True, text=True)
        nodes = {
            ln.split(",")[0]
            for ln in (lscpu_nodes.stdout or "").splitlines()
            if ln and ln[0].isdigit()
        }
        if len(nodes) > 1:
            ctx.numa_test = "1"

        if ctx.pctype == "Server":
            ctx.ipmi_test = "1"

        modules = Path("/proc/modules")
        if modules.is_file():
            modtext = modules.read_text()
            if re.search(r"^(uvcvideo |gspca_|em28xx)", modtext, re.M):
                ctx.webcam_test = "1"

        if not ctx.have_xorg or not os.environ.get("DISPLAY"):
            inxi_b = subprocess.run(["inxi", "-B", "-c0"], capture_output=True, text=True)
            if re.search(r" ID-1: ", inxi_b.stdout or ""):
                ctx.power_test = "1"

        fp_patterns = [
            r"\bFingerprint\b",
            r"^298d:1010 ",
            r"^1c7a:(0570|0571|0603) ",
            r" Digital Persona U\.are\.U 4000",
            r" UPEK TouchChip/Eikon Touch 300",
            r" UPEK TouchStrip",
            r" Elan MOC Sensors",
            r" Veridicom 5thSense",
            r" Synaptics Sensors",
            r" AuthenTec AES16",
            r" AuthenTec AES25",
            r" AuthenTec AES26",
            r" AuthenTec AES4000",
            r" AuthenTec AES3500",
            r" Validity VFS",
        ]
        usb_cut = subprocess.run(["lsusb"], capture_output=True, text=True)
        cut_lines = []
        for ln in (usb_cut.stdout or "").splitlines():
            parts = ln.split(None, 5)
            if len(parts) < 6:
                continue
            rest = parts[5]
            if rest.startswith("1d6b:000"):
                continue
            cut_lines.append(rest)
        usb_text = "\n".join(cut_lines)
        if any(re.search(p, usb_text) for p in fp_patterns):
            ctx.fprnt_test = "1"

        inxi_e = subprocess.run(["inxi", "-E", "-c0"], capture_output=True, text=True)
        if re.search(r" Device-1: ", inxi_e.stdout or ""):
            ctx.bluez_test = "1"

        if ctx.has_binary("opensc-tool"):
            osc = subprocess.run(["opensc-tool", "--list-readers"], capture_output=True, text=True)
            if "No smart card readers found" not in (osc.stdout or ""):
                ctx.scard_test = "1"

        ifaces: list[str] = []
        net = Path("/sys/class/net")
        if net.is_dir():
            for iface in net.iterdir():
                if iface.name != "lo":
                    ifaces.append(iface.name)
        ctx.ifaces = " ".join(ifaces)

        if self._cando_express_test():
            ctx.xprss_test = "1"
        else:
            ctx.spawn(": We cannot run an express test...")

        if ctx.drives.strip():
            ctx.fio_test = "1"
        if ctx.have_xorg and os.environ.get("DISPLAY"):
            inxi_g = subprocess.run(["inxi", "-G", "-c0"], capture_output=True, text=True)
            if re.search(r" Device-1: ", inxi_g.stdout or ""):
                ctx.v3d_test = "1"
        if ctx.has_binary("fwupdmgr"):
            ctx.fwupd_test = "1"

        Path(tmp_path).unlink(missing_ok=True)
        ctx.print_settings_ini("detect.ini")
        return TEST_PASSED

    def _pactl_env(self) -> dict[str, str] | None:
        """Use the test user's PipeWire/Pulse session when detect runs via sudo."""
        ctx = self.ctx
        if os.geteuid() != 0 or not ctx.username:
            return None
        try:
            import pwd

            from pc_test.de_terminal import _session_env_for_uid

            pw = pwd.getpwnam(ctx.username)
            env = _session_env_for_uid(pw.pw_uid)
            return env if env else None
        except (ImportError, KeyError, OSError):
            return None

    def _detect_sound_card(self) -> bool:
        ctx = self.ctx
        inxi_a = subprocess.run(["inxi", "-A", "-c0"], capture_output=True, text=True)
        if re.search(r" Device-1: ", inxi_a.stdout or ""):
            return True
        # PipeWire/Pulse without a PCI audio device (common on VMs, ALT Workstation K)
        if ctx.has_binary("pactl"):
            pactl_env = self._pactl_env()
            sinks = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                env=pactl_env,
            )
            if sinks.returncode == 0 and (sinks.stdout or "").strip():
                return True
            if (
                subprocess.run(
                    ["pactl", "info"],
                    capture_output=True,
                    env=pactl_env,
                ).returncode
                == 0
            ):
                return True
        cards = Path("/proc/asound/cards")
        if cards.is_file():
            text = cards.read_text(encoding="utf-8", errors="replace")
            if text.strip() and "no soundcards" not in text.lower():
                return True
        return False

    def _cando_express_test(self) -> bool:
        ctx = self.ctx
        ctx.spawn(": Checking for a Server...")
        if ctx.pctype == "Server":
            return False
        ctx.spawn(": Checking for Network interfaces...")
        if not ctx.ifaces:
            return False
        ctx.spawn(": Checking for Sound cards...")
        if not ctx.sound_test:
            return False
        ctx.spawn(": Checking for a Xorg server...")
        if not ctx.have_xorg:
            return False
        ctx.spawn(": Checking for a Desktop Environment...")
        if not (ctx.have_mate or ctx.have_kde5 or ctx.have_xfce or ctx.have_gnome):
            return False
        ctx.spawn(": Checking for a Graphics card...")
        inxi_g = subprocess.run(["inxi", "-G", "-c0"], capture_output=True, text=True)
        if not re.search(r" Device-1: ", inxi_g.stdout or ""):
            return False
        ctx.spawn(": So, we can run an express test...")
        return True
