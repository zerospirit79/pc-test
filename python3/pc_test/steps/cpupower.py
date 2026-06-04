"""CPU frequency and power modes step."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from pc_test.constants import TEST_BLOCKED, TEST_FAILED, TEST_PASSED
from pc_test.steps.base import StepBase, register_step

CPU_LEFT = Path("/sys/devices/system/cpu")


def _have_cpu_var(cpu: int, rel: str) -> bool:
    return (CPU_LEFT / f"cpu{cpu}" / rel).is_file()


def _read_cpu_var(cpu: int, rel: str) -> str:
    return (CPU_LEFT / f"cpu{cpu}" / rel).read_text().splitlines()[0].strip()


def _write_cpu(value: str, cpu: int, rel: str) -> None:
    try:
        (CPU_LEFT / f"cpu{cpu}" / rel).write_text(value)
    except OSError:
        pass


def _in_array(needle: str, haystack: str) -> bool:
    return needle in haystack.split()


def _read_freq(n_cores: int, cpu_idx: Optional[int] = None) -> List[int]:
    badv = 99999999999
    r = "cpufreq/cpuinfo_cur_freq"
    if not _have_cpu_var(0, r):
        r = "cpufreq/scaling_cur_freq"
    freqs = []
    if cpu_idx is not None:
        try:
            return [int(_read_cpu_var(cpu_idx, r))]
        except (ValueError, OSError):
            return [badv]
    for i in range(n_cores):
        try:
            freqs.append(int(_read_cpu_var(i, r)))
        except (ValueError, OSError):
            freqs.append(badv)
    return freqs


def _freq_min(values: List[int]) -> int:
    return min(values) if values else 0


def _freq_max(values: List[int]) -> int:
    return max(values) if values else 0


def _freq_avg(values: List[int], n_cores: int) -> int:
    return sum(values) // n_cores if n_cores else 0


@register_step
class CpupowerStep(StepBase):
    STEP_ID = "cpupower"
    number = "10.1"
    en_name = "Checking modes for changing processor frequency and power"
    ru_name = "Проверка режимов изменения частоты и мощности процессора"

    def testcase(self) -> int:
        ctx = self.ctx
        if ctx.username and ctx.langid != "en":
            os.environ["LANG"] = "C"
            os.environ["LC_ALL"] = "C"

        n = CPU_LEFT / "cpu0/cpufreq"
        minf = maxf = ""
        for attr in ("cpuinfo_min_freq", "scaling_min_freq"):
            if (n / attr).is_file():
                minf = (n / attr).read_text().split()[0]
                break
        for attr in ("cpuinfo_max_freq", "scaling_max_freq"):
            if (n / attr).is_file():
                maxf = (n / attr).read_text().split()[0]
                break
        if maxf and (n / "bios_limit").is_file():
            v = (n / "bios_limit").read_text().split()[0]
            if v and int(maxf) > int(v):
                maxf = v

        n_cores = int(
            subprocess.run(
                ["grep", "-scE", r"^processor\s", "/proc/cpuinfo"],
                capture_output=True,
                text=True,
            ).stdout
            or "0"
        )
        scaling = bool(
            n_cores
            and minf
            and maxf
            and int(minf) < int(maxf)
            and (n / "scaling_available_governors").is_file()
            and (n / "scaling_governor").is_file()
            and ((n / "cpuinfo_cur_freq").is_file() or (n / "scaling_cur_freq").is_file())
        )
        governors = ""
        have_pwsv = have_uspc = have_cons = have_ondm = ""
        if scaling:
            governors = (n / "scaling_available_governors").read_text().strip()
            have_pwsv = "1" if _in_array("powersave", governors) else ""
            have_uspc = "1" if _in_array("userspace", governors) else ""
            have_cons = "1" if _in_array("conservative", governors) else ""
            have_ondm = "1" if _in_array("ondemand", governors) else ""

        noturbo = ""
        if (CPU_LEFT / "intel_pstate/no_turbo").is_file():
            noturbo = (CPU_LEFT / "intel_pstate/no_turbo").read_text().strip()

        ctx.spawn("cpupower", "frequency-info")
        saved_bias: List[str] = []
        saved_governors: List[str] = []
        saved_min: List[str] = []
        saved_max: List[str] = []
        saved_speed: List[str] = []
        rc: Optional[int] = None
        i = 0
        o = "power/energy_perf_bias"

        if _have_cpu_var(0, o):
            while i < n_cores:
                if not _have_cpu_var(i, o):
                    break
                saved_bias.append(_read_cpu_var(i, o))
                i += 1
            i = 0

        if scaling:
            while i < n_cores:
                for rel, arr in (
                    ("cpufreq/scaling_governor", saved_governors),
                    ("cpufreq/scaling_min_freq", saved_min),
                    ("cpufreq/scaling_max_freq", saved_max),
                ):
                    if not _have_cpu_var(i, rel):
                        break
                    arr.append(_read_cpu_var(i, rel))
                try:
                    saved_speed.append(_read_cpu_var(i, "cpufreq/scaling_setspeed"))
                except (OSError, IndexError):
                    saved_speed.append("<unsupported>")
                i += 1
            i = 0

        if noturbo:
            try:
                (CPU_LEFT / "intel_pstate/no_turbo").write_text("1")
            except OSError:
                pass

        if saved_bias:
            while i < len(saved_bias):
                _write_cpu("15", i, o)
                i += 1
            i = 0

        if saved_max:
            while i < len(saved_max):
                gov = saved_governors[i]
                if have_pwsv and gov != "powersave":
                    _write_cpu("powersave", i, "cpufreq/scaling_governor")
                elif have_uspc and gov != "userspace":
                    _write_cpu("userspace", i, "cpufreq/scaling_governor")
                    gov = "SET-SPEED"
                elif have_cons and gov != "conservative":
                    _write_cpu("conservative", i, "cpufreq/scaling_governor")
                elif have_ondm and gov != "ondemand":
                    _write_cpu("ondemand", i, "cpufreq/scaling_governor")
                if saved_max[i] != maxf:
                    _write_cpu(maxf, i, "cpufreq/scaling_max_freq")
                if saved_min[i] != minf:
                    _write_cpu(minf, i, "cpufreq/scaling_min_freq")
                if gov == "SET-SPEED" and _have_cpu_var(i, "cpufreq/scaling_setspeed"):
                    _write_cpu(minf, i, "cpufreq/scaling_setspeed")
                i += 1
            i = 0

        if not scaling:
            ctx.spawn(": Scaling control unavailable on this hardware")
            rc = TEST_BLOCKED
        elif _have_cpu_var(0, "cpufreq/stats/time_in_state"):
            boundary = (int(maxf) - int(minf)) // (20 if have_pwsv or have_uspc else 5) + int(minf)
            for c in range(n_cores):
                _write_cpu("1", c, "cpufreq/stats/reset")
            time.sleep(15)
            good = 0
            for c in range(n_cores):
                states = (CPU_LEFT / f"cpu{c}/cpufreq/stats/time_in_state").read_text()
                top = sorted(
                    states.strip().splitlines(), key=lambda x: int(x.split()[1]), reverse=True
                )
                freq = int(top[0].split()[0]) if top else 0
                if freq > boundary:
                    good += 1
            if good == 0 or good != n_cores:
                rc = TEST_FAILED
        elif have_pwsv or have_uspc:
            boundary = (int(maxf) - int(minf)) // 20 + int(minf)
            time.sleep(15)
            freqs = _read_freq(n_cores)
            good = sum(1 for f in freqs if f <= boundary)
            if good != n_cores:
                rc = TEST_FAILED
        else:
            boundary = (int(maxf) - int(minf)) // 4 + int(minf)
            time.sleep(15)
            freqs = _read_freq(n_cores)
            avg = _freq_avg(freqs, n_cores)
            if avg > boundary:
                rc = TEST_FAILED

        for cmd in (
            ["cpupower", "monitor"],
            ["cpupower", "frequency-info", "-p"],
            ["cpupower", "frequency-info", "-m", "-f"],
        ):
            subprocess.run(cmd, check=False)
        subprocess.run(["env", "LANG=C", "LC_ALL=C", "lscpu", "--extended"], check=False)

        if saved_max:
            if _in_array("performance", governors):
                for c in range(len(saved_max)):
                    _write_cpu("performance", c, "cpufreq/scaling_governor")
            elif have_uspc:
                for c in range(len(saved_max)):
                    _write_cpu("userspace", c, "cpufreq/scaling_governor")
                    if _have_cpu_var(c, "cpufreq/scaling_setspeed"):
                        _write_cpu(maxf, c, "cpufreq/scaling_setspeed")

        if saved_bias:
            for c, val in enumerate(saved_bias):
                _write_cpu("0", c, o)

        if noturbo:
            try:
                (CPU_LEFT / "intel_pstate/no_turbo").write_text("0")
            except OSError:
                pass

        ctx.spawn2(
            "stress-ng",
            "--cpu",
            "0",
            "--numa",
            "0",
            "--cpu-method",
            "matrixprod",
            "--tz",
            "--metrics",
            "--timeout",
            "30",
        )
        ctx.spawn2(
            "stress-ng",
            "--cpu",
            "0",
            "--cpu-method",
            "matrixprod",
            "--tz",
            "--metrics",
            "--timeout",
            "20",
        )
        bg = subprocess.Popen(
            [
                "stress-ng",
                "--cpu",
                "0",
                "--cpu-method",
                "matrixprod",
                "--metrics",
                "--timeout",
                "10",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(5)
        ctx.spawn("cpupower", "monitor")
        if scaling and rc is None:
            freqs = _read_freq(n_cores, 0)
            avg = freqs[0] if len(freqs) == 1 else _freq_avg(_read_freq(n_cores), n_cores)
            threshold = int(maxf) - (int(maxf) - int(minf)) // 40
            if avg < threshold:
                rc = TEST_FAILED
        bg.wait()

        if noturbo:
            try:
                (CPU_LEFT / "intel_pstate/no_turbo").write_text(noturbo)
            except OSError:
                pass
        if saved_max:
            for c in range(len(saved_max)):
                _write_cpu(saved_governors[c], c, "cpufreq/scaling_governor")
                _write_cpu(saved_min[c], c, "cpufreq/scaling_min_freq")
                _write_cpu(saved_max[c], c, "cpufreq/scaling_max_freq")
                if saved_governors[c] == "userspace" and saved_speed[c] != "<unsupported>":
                    if _have_cpu_var(c, "cpufreq/scaling_setspeed"):
                        _write_cpu(saved_speed[c], c, "cpufreq/scaling_setspeed")
        if saved_bias:
            for c, val in enumerate(saved_bias):
                _write_cpu(val, c, o)

        ctx.spawn("cpupower", "frequency-info")
        return rc if rc is not None else TEST_PASSED
