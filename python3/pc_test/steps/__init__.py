"""Step registry — import all step modules to register them."""

# Import side-effect: registers each step in REGISTRY
from pc_test.steps import (  # noqa: F401
    collect,
    config,
    cpupower,
    detect,
    diskperf,
    express,
    finalize,
    fwupd,
    glmark,
    install,
    prepare,
    syslogs,
    upgrade,
)
from pc_test.steps.base import REGISTRY, create_step, get_step_class, list_steps, register_step

__all__ = [
    "REGISTRY",
    "create_step",
    "get_step_class",
    "list_steps",
    "register_step",
]
