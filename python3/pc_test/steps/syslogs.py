"""Collecting system logs step."""

from __future__ import annotations

import gzip
import os
import re
import subprocess

from pc_test.constants import TEST_PASSED
from pc_test.log_analysis import analyze_collected_logs, emit_report_to_log
from pc_test.steps.base import StepBase, register_step


@register_step
class SyslogsStep(StepBase):
    STEP_ID = "syslogs"
    number = "7"
    en_name = "Checking and saving logs"
    ru_name = "Проверка и сохранение журналов"

    def testcase(self) -> int:
        ctx = self.ctx
        if ctx.username and ctx.langid != "en":
            os.environ["LANG"] = "C"
            os.environ["LC_ALL"] = "C"

        filt = re.compile(r"(panic|fatal|fail|error|warning)", re.I)
        dmesg = subprocess.run(["dmesg"], capture_output=True, text=True).stdout or ""
        filtered = []
        for ln in dmesg.splitlines():
            if not filt.search(ln):
                continue
            if " Command line: " in ln or " Kernel command line: " in ln:
                continue
            filtered.append(ln)
        with gzip.open("dmesg_err.gz", "wt", encoding="utf-8") as gz:
            gz.write("\n".join(filtered))

        proc = subprocess.run(
            ["dmesg", "-H", "-P", "--color=always"], capture_output=True, text=True
        )
        with gzip.open("dmesg.gz", "wt", encoding="utf-8") as gz:
            gz.write(proc.stdout or "")

        journal_err = ""
        systemctl_failed = ""
        systemd_blame = ""
        critical_chain = ""

        if not ctx.have_systemd:
            report = analyze_collected_logs(dmesg=dmesg)
            emit_report_to_log(ctx, report)
            return TEST_PASSED

        for cmd, outfile in (
            (["systemctl", "--failed"], "systemctl_err.gz"),
            (["journalctl", "-b"], "journal.gz"),
            (["journalctl", "-p", "err", "-b"], "journal_err.gz"),
        ):
            out = subprocess.run(cmd, capture_output=True, text=True)
            with gzip.open(outfile, "wt", encoding="utf-8") as gz:
                gz.write(out.stdout or "")
            if cmd[0] == "systemctl":
                systemctl_failed = out.stdout or ""
            elif "-p" in cmd:
                journal_err = out.stdout or ""

        if ctx.devel_test and ctx.has_binary("systemd-analyze"):
            for args, name in (
                (["systemd-analyze", "--no-pager", "critical-chain"], "critical-chain.txt"),
                (["systemd-analyze", "--no-pager", "blame"], "systemd-blame.txt"),
            ):
                out = subprocess.run(args, capture_output=True, text=True)
                if out.returncode == 0:
                    open(name, "w", encoding="utf-8").write(out.stdout or "")
                    if "blame" in name:
                        systemd_blame = out.stdout or ""
                    else:
                        critical_chain = out.stdout or ""

        report = analyze_collected_logs(
            dmesg=dmesg,
            journal_err=journal_err,
            systemctl_failed=systemctl_failed,
            systemd_blame=systemd_blame,
            critical_chain=critical_chain,
        )
        emit_report_to_log(ctx, report)
        return TEST_PASSED
