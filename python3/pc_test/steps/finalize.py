"""Final kernel message check step."""

from __future__ import annotations

import gzip
import os
import subprocess
from pathlib import Path

from pc_test.constants import TEST_FAILED, TEST_PASSED
from pc_test.log_analysis import analyze_collected_logs, emit_report_to_log
from pc_test.steps.base import StepBase, register_step


@register_step
class FinalizeStep(StepBase):
    STEP_ID = "finalize"
    number = "10.11"
    en_name = "Final check of kernel messages"
    ru_name = "Контрольная проверка сообщений ядра"

    def testcase(self) -> int:
        ctx = self.ctx
        if ctx.username and ctx.langid != "en":
            os.environ["LANG"] = "C"
            os.environ["LC_ALL"] = "C"

        proc = subprocess.run(
            ["dmesg", "-H", "-P", "-T", "--color=always"], capture_output=True, text=True
        )
        with gzip.open("dmesg_final.gz", "wt", encoding="utf-8") as gz:
            gz.write(proc.stdout or "")

        if ctx.xorglog and Path(ctx.xorglog).is_file() and Path(ctx.xorglog).stat().st_size == 0:
            Path(ctx.xorglog).unlink(missing_ok=True)

        dmesg = subprocess.run(["dmesg"], capture_output=True, text=True).stdout or ""
        report = analyze_collected_logs(dmesg=dmesg)
        emit_report_to_log(ctx, report, outfile="log-analysis-final.txt")

        if report.aer_count > 9:
            return TEST_FAILED
        return TEST_PASSED
