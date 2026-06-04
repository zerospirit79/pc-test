"""Graphics performance step."""

from __future__ import annotations

from pc_test.constants import TEST_ALLOWED, TEST_PASSED, TEST_SKIPPED
from pc_test.context import graphical_session
from pc_test.steps.base import StepBase, register_step


@register_step
class GlmarkStep(StepBase):
    STEP_ID = "glmark"
    number = "11.2"
    en_name = "Checking 2D/3D-Video performance"
    ru_name = "Определение производительности видеоподсистемы"

    def pre(self) -> int:
        if not self.ctx.v3d_test:
            return TEST_SKIPPED
        if not graphical_session():
            return TEST_SKIPPED
        return TEST_ALLOWED

    def testcase(self) -> int:
        import subprocess

        with open("glmark2.log", "w", encoding="utf-8") as logf:
            subprocess.run(["glmark2"], stdout=logf, stderr=subprocess.STDOUT, check=False)
        return TEST_PASSED
