"""Base class and registry for pc-test steps."""

from __future__ import annotations

from typing import Dict, Optional, Type

from pc_test.constants import TEST_ALLOWED, TEST_PASSED
from pc_test.context import RuntimeContext, get_context


class StepBase:
    """Python port of a bash step script (number, names, pre, testcase)."""

    STEP_ID: str = ""
    number: str = ""
    en_name: str = ""
    ru_name: str = ""

    def __init__(self, ctx: Optional[RuntimeContext] = None) -> None:
        self.ctx = ctx or get_context()

    def pre(self) -> int:
        return TEST_ALLOWED

    def testcase(self) -> int:
        return TEST_PASSED

    def reset_results(self) -> None:
        pass

    def show_results(self, rc: int, *, log: bool = True) -> None:
        pass

    def title(self) -> str:
        return self.ctx.nls_title(self.en_name, self.ru_name)


REGISTRY: Dict[str, Type[StepBase]] = {}


def register_step(cls: Type[StepBase]) -> Type[StepBase]:
    if not cls.STEP_ID:
        raise ValueError(f"STEP_ID not set on {cls.__name__}")
    REGISTRY[cls.STEP_ID] = cls
    return cls


def get_step_class(name: str) -> Type[StepBase]:
    if name not in REGISTRY:
        raise KeyError(f"Unknown step: {name}")
    return REGISTRY[name]


def create_step(name: str, ctx: Optional[RuntimeContext] = None) -> StepBase:
    return get_step_class(name)(ctx=ctx)


def list_steps() -> list[str]:
    return sorted(REGISTRY.keys())
