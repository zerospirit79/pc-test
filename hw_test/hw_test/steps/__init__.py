"""Steps package for HW-Test."""

from hw_test.steps.base import BaseHWStep
from hw_test.steps.step_01_hardware_detection import HardwareDetectionStep
from hw_test.steps.step_02_express_test import ExpressTestStep
from hw_test.steps.step_03_system_check import SystemCheckStep
from hw_test.steps.step_04_performance import PerformanceStep
from hw_test.steps.step_05_firmware_check import FirmwareCheckStep
from hw_test.steps.step_06_log_collection import LogCollectionStep

__all__ = [
    'BaseHWStep',
    'HardwareDetectionStep',
    'ExpressTestStep',
    'SystemCheckStep',
    'PerformanceStep',
    'FirmwareCheckStep',
    'LogCollectionStep',
]

# Registry of all available steps
AVAILABLE_STEPS = {
    'hardware_detection': HardwareDetectionStep,
    'express_test': ExpressTestStep,
    'system_check': SystemCheckStep,
    'performance': PerformanceStep,
    'firmware_check': FirmwareCheckStep,
    'log_collection': LogCollectionStep,
}

# Default step execution order
DEFAULT_STEP_ORDER = [
    'hardware_detection',
    'express_test',
    'system_check',
    'performance',
    'firmware_check',
    'log_collection',
]


def get_step_class(step_name: str):
    """Get a step class by name."""
    return AVAILABLE_STEPS.get(step_name)


def get_available_steps() -> list[str]:
    """Get list of available step names."""
    return list(AVAILABLE_STEPS.keys())
