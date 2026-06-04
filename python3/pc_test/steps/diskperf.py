"""Disk drives performance step."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import List

from pc_test.constants import TEST_FAILED, TEST_PASSED, TEST_SKIPPED
from pc_test.steps.base import StepBase, register_step

FS_MIN = 8589934592  # 8 GiB


def get_whole_disk(partdev: str) -> str:
    """Return whole-disk device for a partition."""
    number = subprocess.run(
        ["mountpoint", "-x", "--", partdev], capture_output=True, text=True
    ).stdout.strip()
    if not number:
        return partdev
    sysfs = Path(f"/sys/dev/block/{number}")
    try:
        sysfs = sysfs.resolve()
    except OSError:
        return partdev
    partn_file = sysfs / "partition"
    if not partn_file.is_file():
        return partdev
    partn = partn_file.read_text().strip()
    whole = ""
    if re.search(r"[0-9]p$", partdev):
        whole = re.sub(r"p" + re.escape(partn) + r"$", "", partdev)
    elif partdev.endswith(partn):
        whole = partdev[: -len(partn)]
    if whole and Path(whole).is_block_device():
        dev_name = Path(whole).name
        if (Path(f"/sys/block/{dev_name}") / Path(partdev).name / "dev").is_file():
            return whole
    return partdev


@register_step
class DiskperfStep(StepBase):
    STEP_ID = "diskperf"
    number = "11.1"
    en_name = "Checking Disk drives performance"
    ru_name = "Определение производительности дисковой подсистемы"

    def pre(self) -> int:
        if not self.ctx.fio_test or not self.ctx.drives:
            return TEST_SKIPPED
        return TEST_PASSED

    def testcase(self) -> int:
        ctx = self.ctx
        if ctx.username and ctx.langid != "en":
            os.environ["LANG"] = "C"
            os.environ["LC_ALL"] = "C"

        check_list: List[str] = []
        swaps: List[str] = []
        mounted: List[str] = []
        drives = ctx.drives.split()

        msg = ctx.L("L190", "Searching active SWAP devices")
        print(f"{msg}...")
        for devname in (
            subprocess.run(
                ["grep", "-sE", "^/dev/", "/proc/swaps"], capture_output=True, text=True
            ).stdout
            or ""
        ).splitlines():
            devname = devname.split()[0] if devname else ""
            if not devname or not Path(devname).exists():
                continue
            pdev = get_whole_disk(devname)
            if Path(pdev).name not in drives:
                continue
            if pdev in check_list:
                continue
            size = subprocess.run(
                ["blockdev", "--getsize64", devname], capture_output=True, text=True
            )
            try:
                sz = int((size.stdout or "0").strip())
            except ValueError:
                continue
            if sz < FS_MIN:
                continue
            check_list.append(pdev)
            swaps.append(Path(devname).name)

        msg = ctx.L("L192", "Searching for other mounted devices")
        print(f"{msg}...")
        mounts = (
            subprocess.run(
                ["grep", "-sE", "^/dev/", "/proc/mounts"], capture_output=True, text=True
            ).stdout
            or ""
        )
        for devname in mounts.splitlines():
            devname = devname.split()[0] if devname else ""
            if not devname or not Path(devname).exists():
                continue
            pdev = get_whole_disk(devname)
            if Path(pdev).name not in drives:
                continue
            if pdev in check_list:
                continue
            mnt = ""
            for ln in mounts.splitlines():
                if ln.startswith(devname + " "):
                    mnt = ln.split()[1]
            if not mnt:
                continue
            df = subprocess.run(["df", "-B1", "--", mnt], capture_output=True, text=True)
            avail = 0
            for ln in (df.stdout or "").splitlines():
                if ln.startswith(devname):
                    parts = ln.split()
                    if len(parts) >= 4:
                        avail = int(parts[3])
            if avail < FS_MIN:
                continue
            check_list.append(pdev)
            mounted.append(Path(devname).name)

        rc = 0
        tested = 0
        for devname in swaps:
            filename = f"/dev/{devname}"
            if ctx.spawn("swapoff", "-v", "--", filename) != 0:
                continue
            uuid = subprocess.run(
                ["blkid", "-c", "/dev/null", "-o", "value", "-s", "UUID", "--", filename],
                capture_output=True,
                text=True,
            ).stdout.strip()
            label = subprocess.run(
                ["blkid", "-c", "/dev/null", "-o", "value", "-s", "LABEL", "--", filename],
                capture_output=True,
                text=True,
            ).stdout.strip()
            ctx.spawn("wipefs", "-a", "--", filename)
            pdev = check_list[tested]
            if self._device_test(pdev, filename) != 0:
                rc = 1
            ctx.spawn("wipefs", "-a", "--", filename)
            args = ["mkswap", "-U", uuid, "--", filename]
            if label:
                args = ["mkswap", "-L", label, "-U", uuid, "--", filename]
            ctx.spawn(*args)
            ctx.spawn("swapon", "-v", "--", filename)
            tested += 1

        i = tested
        for devname in mounted:
            mnt_ln = subprocess.run(
                ["grep", "-sE", f"^/dev/{devname} ", "/proc/mounts"],
                capture_output=True,
                text=True,
            ).stdout
            filename = ""
            for ln in (mnt_ln or "").splitlines():
                filename = ln.split()[1]
            if not filename:
                msg = ctx.L("L194", "The device @BOLD@ will be skipped")
                print(msg.replace("@BOLD@", devname) + "...")
                i += 1
                continue
            filename = "/.TeSTfile-8G.fio" if filename == "/" else f"{filename}/.TeSTfile-8G.fio"
            pdev = check_list[i]
            if self._device_test(pdev, filename) != 0:
                rc = 1
            Path(filename).unlink(missing_ok=True)
            tested += 1
            i += 1

        for devname in drives:
            if f"/dev/{devname}" in check_list:
                continue
            msg = ctx.L("L194", "The device @BOLD@ will be skipped")
            print(msg.replace("@BOLD@", f"/dev/{devname}") + "...")
            if ctx.unsafe_diskperf:
                msg2 = ctx.L("L195", "Insecure testing will be implemented later!")
                print(f"{ctx.CLR_ERR}{msg2}{ctx.CLR_NORM}")

        if rc != 0:
            return TEST_FAILED
        if tested == 0:
            return TEST_SKIPPED
        return TEST_PASSED

    def _device_test(self, dev: str, filename: str) -> int:
        ctx = self.ctx
        msg = ctx.L("L196", "Testing the device @BOLD@...")
        print(msg.replace("@BOLD@", dev))
        datadir = Path(f"/var/lib/{ctx.progname}")
        fio_ini = datadir / "fio.ini"
        if not fio_ini.is_file():
            print(f"{ctx.CLR_ERR}Missing {fio_ini}{ctx.CLR_NORM}")
            return 1
        tests = sorted(datadir.glob("*.fio"))
        work = Path(ctx.workdir) / f"fio-{Path(dev).name}"
        work.mkdir(parents=True, exist_ok=True)
        (work / "test.ini").write_text(
            f"filename={filename}\n" + fio_ini.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        rc = 0
        direct = 1
        for testf in tests:
            name = testf.stem
            subprocess.run(["cp", "-Lf", str(testf), str(work)], check=False)
            proc = subprocess.run(
                ["fio", "--", f"{name}.fio"],
                capture_output=True,
                text=True,
                cwd=work,
            )
            log = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode != 0:
                log += f"\nFAILED: {proc.returncode}\n"
            (work / f"{name}.log").write_text(log, encoding="utf-8")
            if direct == 1 and log.splitlines() and log.splitlines()[-1].startswith("FAILED:"):
                retry_msg = ctx.L("L197", "Failure. Let's try again with direct=0")
                print(f"\n{retry_msg}...")
                ini = (work / "test.ini").read_text(encoding="utf-8")
                (work / "test.ini").write_text(
                    re.sub(r"^direct=1$", "direct=0", ini, flags=re.M),
                    encoding="utf-8",
                )
                proc = subprocess.run(
                    ["fio", "--", f"{name}.fio"],
                    capture_output=True,
                    text=True,
                    cwd=work,
                )
                log = (proc.stdout or "") + (proc.stderr or "")
                (work / f"{name}.log").write_text(log, encoding="utf-8")
                direct = 0
            last = (work / f"{name}.log").read_text(encoding="utf-8").splitlines()
            if last and re.search(r"^FAILED:", last[-1]):
                rc = 1
            (work / f"{name}.fio").unlink(missing_ok=True)
        return rc
