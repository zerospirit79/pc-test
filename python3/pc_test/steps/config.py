"""Test plan configuration step."""

from __future__ import annotations

import os

from pc_test.constants import TEST_ALLOWED, TEST_BLOCKED, TEST_SKIPPED
from pc_test.de_terminal import apply_graphical_session_env
from pc_test.gui import config_forms
from pc_test.steps.base import StepBase, register_step


@register_step
class ConfigStep(StepBase):
    STEP_ID = "config"
    number = "5.4"
    en_name = "Defining a Test Plan"
    ru_name = "Определение плана тестирования"

    def pre(self) -> int:
        ctx = self.ctx
        if ctx.batchmode:
            return TEST_SKIPPED
        if os.geteuid() != 0:
            apply_graphical_session_env()
        if (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and ctx.has_binary(
            "yad"
        ):
            return TEST_ALLOWED
        if ctx.has_binary("dialog"):
            return TEST_ALLOWED
        return TEST_BLOCKED

    def testcase(self) -> int:
        ctx = self.ctx
        if os.geteuid() == 0:
            return TEST_BLOCKED
        apply_graphical_session_env()
        wconf = False
        if (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and ctx.has_binary(
            "yad"
        ):
            config_forms.run_gui(ctx)
            wconf = True
        elif ctx.has_binary("dialog"):
            can_install_mate = ""
            if (
                ctx.have_altsp
                and not ctx.have_xorg
                and ctx.distro == "SRV"
                and ctx.repo in ("c10f1", "c10f2")
            ):
                can_install_mate = "1"
            config_forms.run_tui(ctx, can_install_mate=bool(can_install_mate))
            wconf = True
        if wconf:
            ctx.print_settings_ini("config.ini")
        return TEST_ALLOWED
