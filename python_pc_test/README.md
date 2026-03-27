# pc-test Python Implementation

This directory contains a complete Python rewrite of the `pc-test` hardware compatibility testing tool for ALT Linux, based on the Basalt SPO methodology.

## Overview

The original `pc-test` tool was written in Bash and located in `/usr/bin/pc-test` with supporting libraries in `/usr/libexec/pc-test/`. This Python implementation provides:

- **Full compatibility** with the original command-line interface
- **Improved maintainability** through object-oriented design
- **Better error handling** and logging
- **Type hints** for improved code quality
- **Localization support** (English and Russian)

## Files

- `pc_test.py` - Main application script (executable)
- `pc_test_lib/` - Library modules (for future expansion)
- `var/lib/pc-test/` - Test configuration files (copied from original)

## Usage

```bash
# Show help
python3 pc_test.py --help

# Show version
python3 pc_test.py --version

# Start new testing
python3 pc_test.py --start

# Continue previous testing
python3 pc_test.py --continue

# Finish previous testing
python3 pc_test.py --finish

# Run specific test
python3 pc_test.py --test=5.3

# Batch mode (no interaction)
python3 pc_test.py --start --batch

# With custom date and name
python3 pc_test.py --start --date=2025-01-01 --name=MyPC
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `-A, --auto` | Auto-detection of program launch mode (default) |
| `-C, --continue` | Continue previously started testing |
| `-F, --finish` | Finish previously started testing |
| `-S, --start` | Start new testing |
| `-T, --test=#` | Run the test again at the specified number |
| `-b, --batch` | Do not use input and dialogs for settings |
| `-c, --color=<M>` | Change console color mode (auto/always/never) |
| `-d, --date=<F>` | Date in YYYY-MM-DD format for archive naming |
| `-n, --name=<N>` | Computer name for archive naming |
| `--no-autorun` | Disable autorun via desktop file |
| `--no-sources` | Disable APT sources changes |
| `--no-update` | Disable system and kernel updates |
| `--update` | Enable system and kernel updates (default) |
| `--uid=<ID>` | For internal use only |
| `-v, --version` | Show version information |
| `-h, --help` | Show help message |

## Architecture

### Main Classes

- **PCTestApp**: Main application class that orchestrates the testing process
- **Config**: Configuration settings dataclass
- **SystemInfo**: Hardware and software information dataclass
- **TestStep**: Represents a single test step
- **Localization**: Handles multi-language support (NLS)

### Test Steps

The following test steps are supported (matching the original implementation):

1. `prepare` - System preparation
2. `upgrade` - System upgrade
3. `detect` - Hardware discovery
4. `config` - Configuration
5. `install` - Package installation
6. `fwupd` - Firmware update
7. `syslogs` - System logs check
8. `collect` - Information collection
9. `express` - Express test of main components
10. `cpupower` - CPU power test
11. `diskperf` - Disk performance test
12. `glmark` - Graphics test
13. `finalize` - Finalization

### Hardware Detection

The Python implementation includes comprehensive hardware detection:

- **PC Type**: Desktop, Notebook, Server, Tablet, Convertible, Virtual, etc.
- **Disk Drives**: Physical drives (excluding loop, RAM, CD-ROM devices)
- **Network Interfaces**: All non-loopback interfaces
- **Graphics**: Xorg server and desktop environment detection
- **Sound Cards**: Via inxi utility
- **Additional Features**:
  - Infiniband/RDMA
  - NUMA topology
  - IPMI (for servers)
  - Webcams
  - Power management (battery systems)
  - Fingerprint scanners
  - Bluetooth
  - Smart cards

## Configuration

Configuration can be set via:

1. **Command-line arguments** (highest priority)
2. **User config**: `~/.config/pc-test.conf`
3. **System config**: `/etc/pc-test.conf`
4. **Default values** (lowest priority)

### Environment Variables

- `PCTEST_LIBDIR` - Path to library directory
- `PCTEST_ETC_CONF` - Path to system configuration
- `PCTEST_VAR_LIB` - Path to variable data
- `PCTEST_LOG_DIR` - Path to log directory

## Test Results

Test results are stored in:
- `~/PC-TEST/` - Symlink to current test directory
- `~/.local/share/pc-test/<date>/` - Actual test data

Results include:
- `pc-test.log` - Full execution log
- `xorg.log` - X server errors
- `STATE/RESULTS` - Step-by-step results
- `settings.ini` - Configuration used
- Final tarball archive

## Migration Notes

### From Bash to Python

Key differences and improvements:

1. **Error Handling**: Python exceptions vs Bash exit codes
2. **Data Structures**: Dataclasses vs shell variables
3. **Logging**: Python logging module vs printf/tee
4. **Configuration**: configparser vs shell sourcing
5. **Hardware Detection**: subprocess calls with better error handling

### Compatibility

The Python implementation maintains compatibility with:
- Original command-line syntax
- Configuration file formats
- Test plan files (start.txt, finish.txt, numbers.txt)
- Result file formats
- Directory structure

## Development

### Requirements

- Python 3.7+
- Standard library only (no external dependencies)
- Optional: inxi, lspci, lsusb utilities for hardware detection

### Testing

```bash
# Run with batch mode for automated testing
python3 pc_test.py --start --batch --name=TestPC

# Check syntax
python3 -m py_compile pc_test.py

# Run with different locales
LANG=ru_RU.UTF-8 python3 pc_test.py --help
LANG=en_US.UTF-8 python3 pc_test.py --help
```

## License

GNU General Public License version 3 or later (same as original)

## Copyright

Copyright (C) 2024-2025, ALT Linux Team
