"""Hardware firmware update step."""

from __future__ import annotations

import os

from pc_test.constants import TEST_ALLOWED, TEST_BLOCKED, TEST_FAILED, TEST_SKIPPED
from pc_test.steps.base import StepBase, register_step


@register_step
class FwupdStep(StepBase):
    STEP_ID = "fwupd"
    number = "6"
    en_name = "Checking the ability to hardware components firmware updating"
    ru_name = "Проверка возможности обновления прошивки компонентов оборудования"

    def pre(self) -> int:
        ctx = self.ctx
        if not ctx.fwupd_test:
            return TEST_SKIPPED
        if not ctx.has_binary("fwupdmgr"):
            return TEST_BLOCKED
        return TEST_ALLOWED

    def testcase(self) -> int:
        ctx = self.ctx
        if ctx.username and ctx.langid != "en":
            os.environ["LANG"] = "C"
            os.environ["LC_ALL"] = "C"

        rc = TEST_ALLOWED
        print("===[ Devices list:")
        if ctx.spawn("fwupdmgr", "get-devices") != 0:
            rc = TEST_BLOCKED
        print("===]\n")

        print("===[ Updates list:")
        if ctx.spawn("fwupdmgr", "get-updates", "-y") != 0:
            rc = TEST_BLOCKED
        print("===]\n")

        if rc == TEST_ALLOWED:
            print("===[ Update process:")
            if ctx.spawn("fwupdmgr", "update") != 0:
                rc = TEST_FAILED
            print("===]\n")
            if ctx.have_systemd:
                ctx.stop_journald()
            ctx.system_restart(rc)
        return rc
