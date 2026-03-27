"""Type definitions and constants for HW-Test."""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


class TestStatus(Enum):
    """Status of a test step."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    ERROR = "error"


class TestResult(Enum):
    """Result type for hardware tests."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class HardwareInfo:
    """Information about detected hardware."""
    cpu_model: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    cpu_freq_mhz: float = 0.0
    total_memory_mb: int = 0
    available_memory_mb: int = 0
    disk_info: List[Dict[str, Any]] = field(default_factory=list)
    network_interfaces: List[Dict[str, Any]] = field(default_factory=list)
    gpu_info: List[Dict[str, Any]] = field(default_factory=list)
    audio_devices: List[Dict[str, Any]] = field(default_factory=list)
    usb_devices: List[Dict[str, Any]] = field(default_factory=list)
    numa_nodes: int = 1
    bios_vendor: str = ""
    bios_version: str = ""
    system_manufacturer: str = ""
    system_product: str = ""
    ipmi_detected: bool = False
    webcams: List[Dict[str, Any]] = field(default_factory=list)
    fingerprint_readers: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StepResult:
    """Result of a test step execution."""
    step_name: str
    status: TestStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TestConfig:
    """Configuration for HW-Test execution."""
    name: str = "default"
    batch_mode: bool = False
    verbose: bool = False
    log_dir: str = "/var/lib/hw-test/logs"
    data_dir: str = "/var/lib/hw-test"
    config_dir: str = "/etc/hw-test"
    steps_to_run: List[str] = field(default_factory=list)
    skip_steps: List[str] = field(default_factory=list)
    timeout_seconds: int = 3600
    language: str = "ru"  # 'en' or 'ru'
