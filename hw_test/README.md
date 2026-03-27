# HW-Test

Hardware compatibility testing tool for ALT Linux (based on Basalt SPo methodology).

## Features

- **Hardware Detection**: Automatic detection of CPU, memory, storage, network, GPU, audio, USB devices, webcams, fingerprint readers, and more
- **Express Tests**: Quick verification of boot time, system responsiveness, I/O performance, and network connectivity
- **System Check**: OS version verification, package manager health, available updates, disk space monitoring
- **Performance Benchmarks**: CPU, memory, disk I/O, and context switching benchmarks
- **Firmware Check**: BIOS/UEFI version detection, Secure Boot status, firmware updates via fwupd
- **Log Collection**: Comprehensive log gathering and archiving for troubleshooting

## Installation

### From source (development mode)

```bash
cd /workspace/hw_test
pip install -e .
```

### Build distribution

```bash
pip install build
python -m build
```

This creates source and wheel distributions in the `dist/` directory.

## Usage

### Basic usage

```bash
# Run all tests
sudo hw-test --start

# Run in batch mode (no interactive prompts)
sudo hw-test --start --batch

# Run specific steps only
sudo hw-test --start --steps hardware_detection,express_test

# Skip certain steps
sudo hw-test --start --skip performance,firmware_check

# Set custom test name
sudo hw-test --start --name "Workstation-001"

# Verbose output
sudo hw-test --start -v

# Custom output directory
sudo hw-test --start --output-dir /tmp/hw-results
```

### List available steps

```bash
hw-test --list-steps
```

### Show version

```bash
hw-test --version
```

## Available Test Steps

| Step | Description | Requires Root |
|------|-------------|---------------|
| `hardware_detection` | Detect all hardware components | Yes |
| `express_test` | Quick functionality tests | No |
| `system_check` | OS and package manager checks | Yes |
| `performance` | Performance benchmarks | No |
| `firmware_check` | BIOS/UEFI and firmware updates | Yes |
| `log_collection` | Collect logs and create archive | Yes |

## Architecture

```
hw_test/
├── __init__.py          # Package initialization, version
├── types.py             # Type definitions (TestConfig, HardwareInfo, StepResult)
├── cli.py               # Command-line interface
└── steps/
    ├── __init__.py      # Step registry and exports
    ├── base.py          # BaseHWStep abstract class
    ├── step_01_hardware_detection.py
    ├── step_02_express_test.py
    ├── step_03_system_check.py
    ├── step_04_performance.py
    ├── step_05_firmware_check.py
    └── step_06_log_collection.py
```

### Adding Custom Steps

1. Create a new file in `hw_test/steps/` (e.g., `step_07_custom.py`)
2. Inherit from `BaseHWStep`:

```python
from hw_test.steps.base import BaseHWStep
from hw_test.types import StepResult, TestStatus

class CustomStep(BaseHWStep):
    name = "Custom Test"
    description = "My custom test step"
    required_privileges = False
    
    def execute(self) -> StepResult:
        # Your test logic here
        return StepResult(
            step_name=self.name,
            status=TestStatus.PASSED,
            message="Custom test completed"
        )
```

3. Register in `hw_test/steps/__init__.py`

## Configuration

Default paths:
- Data directory: `/var/lib/hw-test`
- Log directory: `/var/lib/hw-test/logs`
- Config directory: `/etc/hw-test`

Environment variables:
- `HWTEST_DATA_DIR`: Override data directory
- `HWTEST_LOG_LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR)

## Output

Results are displayed in the console and logged. The `log_collection` step creates a compressed archive containing:
- System logs (syslog, messages, kern.log, etc.)
- Command outputs (dmesg, lspci, lsusb, etc.)
- Hardware information from sysfs
- Summary JSON file

Archive naming: `hw-test_<name>_<timestamp>.tar.gz`

## Requirements

- Python 3.8+
- psutil
- py-cpuinfo
- packaging

Optional dependencies (for full functionality):
- dmidecode
- fwupd
- ipmitool
- v4l2-ctl

## License

GPL-3.0

## Authors

Based on pc-test by Basalt SPo Team.
Rewritten in Python as hw-test.
