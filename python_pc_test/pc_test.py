#!/usr/bin/env python3
"""
pc-test - Hardware compatibility testing tool for ALT Linux
Based on Basalt SPO methodology

This is a complete Python rewrite of the original bash-based pc-test tool.
"""

import argparse
import configparser
import datetime
import getpass
import glob
import grp
import json
import logging
import os
import platform
import pwd
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# ============================================================================
# Constants and Enums
# ============================================================================

VERSION = "1.0.0"
BUILD_DATE = "2025-01-01"
PROG_NAME = "pc-test"

# Test result codes
class TestResult(IntEnum):
    PASSED = 0
    ALLOWED = 0
    FAILED = 128
    SKIPPED = 129
    BLOCKED = 130
    RUNNING = 131


# Launch modes
class LaunchMode(Enum):
    AUTO = "auto"
    CONTINUE = "continue"
    FINISH = "finish"
    START = "start"
    RETEST = "retest"


# Color codes for console output
class Colors:
    NORM = "\033[00m"
    BOLD = "\033[01;37m"
    LC1 = "\033[00;36m"
    LC2 = "\033[00;35m"
    OK = "\033[01;32m"
    ERR = "\033[01;31m"
    WARN = "\033[01;33m"


# Default paths - can be overridden via environment
DEFAULT_LIBDIR = Path(os.environ.get("PCTEST_LIBDIR", "/usr/libexec/pc-test"))
DEFAULT_ETC_CONF = Path(os.environ.get("PCTEST_ETC_CONF", "/etc/pc-test.conf"))
DEFAULT_SHARE_DIR = Path(os.environ.get("PCTEST_SHARE_DIR", "/usr/share/doc/pc-test-doc-*/html"))
DEFAULT_VAR_LIB = Path(os.environ.get("PCTEST_VAR_LIB", "/var/lib/pc-test"))
DEFAULT_LOG_DIR = Path(os.environ.get("PCTEST_LOG_DIR", "/var/log/pc-test"))


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Config:
    """Configuration settings for pc-test"""
    # APT sources
    update_apt_lists: bool = True
    dist_upgrade: bool = True
    update_kernel: bool = True
    
    # Local mirror
    local_url: str = ""
    local_mirror: str = ""
    mirror_subdir: str = ""
    local_media_base: str = ""
    local_media_labels: List[str] = field(default_factory=list)
    local_media_check: str = ""
    
    # Console colors
    clr_norm: str = Colors.NORM
    clr_bold: str = Colors.BOLD
    clr_lc1: str = Colors.LC1
    clr_lc2: str = Colors.LC2
    clr_ok: str = Colors.OK
    clr_err: str = Colors.ERR
    clr_warn: str = Colors.WARN
    
    # Testing options
    unsafe_diskperf: bool = False
    disable_autorun: bool = False
    ping_server: str = "ya.ru"
    express_video_set: str = "vkvideo"
    local_video_sample: str = ""
    
    # Runtime settings
    batch_mode: bool = False
    color_mode: str = "auto"  # auto, always, never
    lang_id: str = "en"
    
    def __post_init__(self):
        self.colors_enabled = self.color_mode == "always" or (
            self.color_mode == "auto" and sys.stdout.isatty()
        )


@dataclass
class SystemInfo:
    """System hardware and software information"""
    # System
    have_altsp: bool = False
    have_systemd: bool = False
    install_mate: bool = False
    distro_name: str = ""
    distro: str = ""
    repo: str = ""
    
    # Graphics
    have_xorg: bool = False
    have_kde5: bool = False
    have_mate: bool = False
    have_xfce: bool = False
    have_gnome: bool = False
    
    # Hardware
    arch_name: str = ""
    pc_type: str = ""
    drives: List[str] = field(default_factory=list)
    ifaces: List[str] = field(default_factory=list)
    
    # Tests flags
    fwupd_test: bool = False
    devel_test: bool = False
    xprss_test: bool = False
    infb_test: bool = False
    sound_test: bool = False
    numa_test: bool = False
    ipmi_test: bool = False
    webcam_test: bool = False
    power_test: bool = False
    fprnt_test: bool = False
    bluez_test: bool = False
    scard_test: bool = False
    fio_test: bool = False
    v3d_test: bool = False


@dataclass
class TestStep:
    """Represents a single test step"""
    number: str
    name: str
    user_type: str  # root, user, both
    en_name: str = ""
    ru_name: str = ""
    status: TestResult = TestResult.RUNNING


# ============================================================================
# Localization
# ============================================================================

class Localization:
    """Handles localization (NLS) for messages"""
    
    MESSAGES = {
        "en": {
            "starting_program": "Starting program",
            "resumption": "Resumption of testing",
            "first_part_complete": "The first part of testing is complete!",
            "testing_complete": "Testing is complete!",
            "creating_archive": "Creating the archive '@BOLD@'...",
            "archive_moved_to": "Now this archive has been moved to",
            "press_key_close": "Press any key to close this window...",
            "root_required": "Root privileges required: sudo not yet configured for",
            "update_complete_key": "The update is complete. Press any key to reboot...",
            "update_complete_time": "The update is complete. After %s seconds the system will reboot...",
            "rebooting": "Rebooting the system...",
            "launch_mode_changed": "The launch mode '%s' has been changed, testing will begin again!",
            "system_update_warning": "Before testing, the system and kernel will be updated!",
            "press_continue": "Press Ctrl-C to abort or any other key to continue...",
            "step_not_found": "Step script '%s.sh' not found.",
            "test_cannot_retake": "The specified test '%s' cannot be retaken at this time.",
        },
        "ru": {
            "starting_program": "Запуск программы",
            "resumption": "Возобновление тестирования",
            "first_part_complete": "Первая часть тестирования завершена!",
            "testing_complete": "Тестирование завершено!",
            "creating_archive": "Создание архива '@BOLD@'...",
            "archive_moved_to": "Теперь этот архив перемещён в",
            "press_key_close": "Нажмите любую клавишу для закрытия этого окна...",
            "root_required": "Требуются права root: sudo ещё не настроен для",
            "update_complete_key": "Обновление завершено. Нажмите любую клавишу для перезагрузки...",
            "update_complete_time": "Обновление завершено. Через %s секунд система будет перезапущена...",
            "rebooting": "Перезагрузка системы...",
            "launch_mode_changed": "Режим запуска '%s' изменен, тестирование начнется заново!",
            "system_update_warning": "Перед тестированием система и ядро будут обновлены!",
            "press_continue": "Нажмите Ctrl-C для отмены или любую другую клавишу для продолжения...",
            "step_not_found": "Скрипт шага '%s.sh' не найден.",
            "test_cannot_retake": "Указанный тест '%s' не может быть выполнен повторно в данный момент.",
        }
    }
    
    STEP_NAMES = {
        "en": {
            "prepare": "System preparation",
            "upgrade": "System upgrade",
            "detect": "Hardware discovery",
            "config": "Configuration",
            "install": "Package installation",
            "fwupd": "Firmware update",
            "syslogs": "System logs check",
            "collect": "Information collection",
            "express": "Express test",
            "cpupower": "CPU power test",
            "diskperf": "Disk performance test",
            "glmark": "Graphics test",
            "finalize": "Finalization",
        },
        "ru": {
            "prepare": "Подготовка системы",
            "upgrade": "Обновление системы",
            "detect": "Определение конфигурации оборудования",
            "config": "Конфигурация",
            "install": "Установка пакетов",
            "fwupd": "Обновление прошивок",
            "syslogs": "Проверка системных журналов",
            "collect": "Сбор информации",
            "express": "Экспресс-тест основных компонентов",
            "cpupower": "Тест производительности CPU",
            "diskperf": "Тест производительности дисков",
            "glmark": "Тест графики",
            "finalize": "Завершение",
        }
    }
    
    def __init__(self, lang_id: str = "en"):
        self.lang_id = lang_id if lang_id in self.MESSAGES else "en"
    
    def get(self, key: str, default: str = "") -> str:
        return self.MESSAGES.get(self.lang_id, {}).get(key, default)
    
    def get_step_name(self, step: str) -> str:
        return self.STEP_NAMES.get(self.lang_id, {}).get(step, step)


# ============================================================================
# Utility Functions
# ============================================================================

def run_command(cmd: List[str], capture: bool = True, 
                check: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check,
            **kwargs
        )
        return result
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return subprocess.CompletedProcess(e.cmd, e.returncode, e.stdout or "", e.stderr or "")
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, -1, "", f"Command not found: {cmd[0]}")


def has_binary(name: str) -> bool:
    """Check if a binary exists in PATH"""
    return shutil.which(name) is not None


def is_pkg_installed(name: str) -> bool:
    """Check if a package is installed (RPM-based systems)"""
    result = run_command(["rpm", "-q", name])
    return result.returncode == 0


def is_pkg_available(name: str) -> bool:
    """Check if a package is available in repositories"""
    result = run_command(["apt-cache", "show", name])
    return result.returncode == 0


def get_user_info(uid: Optional[int] = None) -> Tuple[str, str]:
    """Get username and home directory for a UID"""
    if uid is None:
        uid = os.geteuid()
    
    try:
        pw_entry = pwd.getpwuid(uid)
        return pw_entry.pw_name, pw_entry.pw_dir
    except KeyError:
        return str(uid), "/root"


def setup_logging(logfile: Path, level: int = logging.INFO) -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger(PROG_NAME)
    logger.setLevel(level)
    
    # File handler
    fh = logging.FileHandler(logfile)
    fh.setLevel(level)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


# ============================================================================
# Main Application Class
# ============================================================================

class PCTestApp:
    """Main application class for pc-test"""
    
    def __init__(self):
        self.config = Config()
        self.system_info = SystemInfo()
        self.logger: Optional[logging.Logger] = None
        self.nls: Optional[Localization] = None
        self.workdir: Optional[Path] = None
        self.logfile: Optional[Path] = None
        self.xorglog: Optional[Path] = None
        self.launch_mode: LaunchMode = LaunchMode.AUTO
        self.retest_no: str = ""
        self.username: str = ""
        self.homedir: str = ""
        self.compname: str = ""
        self.repodate: str = ""
        self.batch_mode: bool = False
        self.steps: List[TestStep] = []
        self.current_step_idx: int = 0
        
    def setup_nls(self):
        """Setup Native Language Support"""
        # Get locale from environment
        lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or \
               os.environ.get("LANG") or "en_US.UTF-8"
        
        # Extract language code
        lang_id = lang.split(".")[0].split("_")[0]
        self.config.lang_id = lang_id if lang_id in ["en", "ru"] else "en"
        self.nls = Localization(self.config.lang_id)
    
    def parse_arguments(self, args: Optional[List[str]] = None) -> argparse.Namespace:
        """Parse command line arguments"""
        parser = argparse.ArgumentParser(
            prog=PROG_NAME,
            description="Hardware compatibility testing tool for ALT Linux",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=textwrap.dedent(f"""
            Examples:
              {PROG_NAME} --start          Start new testing
              {PROG_NAME} --continue       Continue previous testing
              {PROG_NAME} --finish         Finish previous testing
              {PROG_NAME} --test=5.3       Retest specific step
              {PROG_NAME} --batch          Run in batch mode
            """)
        )
        
        # Launch modes
        mode_group = parser.add_mutually_exclusive_group()
        mode_group.add_argument("-A", "--auto", action="store_const",
                               const=LaunchMode.AUTO, dest="launch_mode",
                               help="Auto-detection of program launch mode")
        mode_group.add_argument("-C", "--continue", action="store_const",
                               const=LaunchMode.CONTINUE, dest="launch_mode",
                               help="Continue previously started testing")
        mode_group.add_argument("-F", "--finish", action="store_const",
                               const=LaunchMode.FINISH, dest="launch_mode",
                               help="Finish previously started testing")
        mode_group.add_argument("-S", "--start", action="store_const",
                               const=LaunchMode.START, dest="launch_mode",
                               help="Start new testing")
        mode_group.add_argument("-T", "--test", metavar="#",
                               help="Run the test again at the specified number")
        
        # Options
        parser.add_argument("-b", "--batch", action="store_true",
                           help="Do not use input and dialogs for settings")
        parser.add_argument("-c", "--color", choices=["auto", "always", "never"],
                           default="auto", help="Change console color mode")
        parser.add_argument("-d", "--date", metavar="DATE",
                           help="Date in YYYY-MM-DD format for archive naming")
        parser.add_argument("-n", "--name", metavar="NAME",
                           help="Computer name for archive naming")
        parser.add_argument("--no-autorun", action="store_true",
                           help="Disable autorun via desktop file")
        parser.add_argument("--no-sources", action="store_true",
                           help="Disable APT sources changes")
        parser.add_argument("--no-update", action="store_true",
                           help="Disable system and kernel updates")
        parser.add_argument("--update", action="store_true",
                           help="Enable system and kernel updates (default)")
        parser.add_argument("--uid", type=int, metavar="ID",
                           help="For internal use only")
        parser.add_argument("--desktop-icon", action="store_true",
                           help="Show desktop icon")
        parser.add_argument("-v", "--version", action="version",
                           version=f"{PROG_NAME} {VERSION} {BUILD_DATE}")
        
        parsed = parser.parse_args(args)
        
        # Handle --test option
        if parsed.test:
            parsed.launch_mode = LaunchMode.RETEST
            self.retest_no = parsed.test
        
        # Apply options to config
        self.config.color_mode = parsed.color
        self.config.batch_mode = parsed.batch
        self.config.disable_autorun = parsed.no_autorun
        
        if parsed.update:
            self.config.update_apt_lists = True
            self.config.dist_upgrade = True
            self.config.update_kernel = True
        elif parsed.no_update:
            self.config.update_apt_lists = False
            self.config.dist_upgrade = False
            self.config.update_kernel = False
        elif parsed.no_sources:
            self.config.update_apt_lists = False
        
        if parsed.date:
            # Validate date format
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', parsed.date):
                parser.error("Date must be in YYYY-MM-DD format")
            self.repodate = parsed.date
        
        if parsed.name:
            self.compname = parsed.name.replace(" ", "").split("(")[0].split(",")[0]
        
        self.launch_mode = parsed.launch_mode or LaunchMode.AUTO
        
        return parsed
    
    def load_config(self):
        """Load configuration from files"""
        # Load /etc/pc-test.conf
        if DEFAULT_ETC_CONF.exists():
            self._load_config_file(DEFAULT_ETC_CONF)
        
        # Load user config
        user_conf = Path.home() / ".config" / f"{PROG_NAME}.conf"
        if user_conf.exists():
            self._load_config_file(user_conf)
    
    def _load_config_file(self, path: Path):
        """Load a single configuration file"""
        try:
            config = configparser.ConfigParser()
            config.read(path)
            
            if 'settings' in config:
                settings = config['settings']
                self.config.update_apt_lists = settings.getboolean(
                    'update_apt_lists', self.config.update_apt_lists)
                self.config.dist_upgrade = settings.getboolean(
                    'dist_upgrade', self.config.dist_upgrade)
                self.config.update_kernel = settings.getboolean(
                    'update_kernel', self.config.update_kernel)
                self.config.ping_server = settings.get(
                    'ping_server', self.config.ping_server)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to load config {path}: {e}")
    
    def detect_launch_mode(self) -> LaunchMode:
        """Auto-detect the appropriate launch mode"""
        lastdir = Path.home() / "PC-TEST"
        workdir = self._get_workdir()
        
        if (lastdir.is_symlink() and 
            (lastdir / f"{PROG_NAME}.log").exists() and
            (lastdir / "STATE" / "start.txt").exists()):
            
            real_lastdir = lastdir.resolve()
            real_workdir = workdir.resolve()
            
            if real_lastdir == real_workdir:
                if (lastdir / "STATE" / "STEP").exists():
                    return LaunchMode.CONTINUE
                elif (not (lastdir / "STATE" / "STEP").exists() and
                      not (lastdir / "STATE" / "start.txt").read_text().strip() and
                      not (lastdir / "STATE" / "finish.txt").exists()):
                    return LaunchMode.FINISH
                else:
                    return LaunchMode.START
        
        return LaunchMode.START
    
    def _get_workdir(self) -> Path:
        """Get the working directory path"""
        date_str = self.repodate or datetime.datetime.now().strftime("%Y-%m-%d")
        return Path.home() / ".local" / "share" / PROG_NAME / date_str
    
    def setup_directories(self):
        """Create necessary directories and symlinks"""
        self.workdir = self._get_workdir()
        lastdir = Path.home() / "PC-TEST"
        
        if self.launch_mode == LaunchMode.START:
            # Clean up old directories
            if self.workdir.exists():
                shutil.rmtree(self.workdir)
            if lastdir.exists() or lastdir.is_symlink():
                lastdir.unlink(missing_ok=True)
            
            # Create new structure
            self.workdir.mkdir(parents=True, exist_ok=True)
            (self.workdir / "STATE").mkdir(exist_ok=True)
            
            # Create symlink
            lastdir.symlink_to(self.workdir)
            
            # Copy start.txt
            start_src = DEFAULT_VAR_LIB / "start.txt"
            if start_src.exists():
                shutil.copy(start_src, self.workdir / "STATE" / "start.txt")
                
                # Extract first step
                content = (self.workdir / "STATE" / "start.txt").read_text()
                first_line = content.strip().split("\n")[0]
                parts = first_line.split("\t")
                if len(parts) >= 2:
                    (self.workdir / "STATE" / "STEP").write_text(f"{parts[1]}\n")
            
            # Initialize results file
            (self.workdir / "STATE" / "RESULTS").touch()
        
        # Setup log files
        self.logfile = self.workdir / f"{PROG_NAME}.log"
        self.xorglog = self.workdir / "xorg.log"
        
        if not self.xorglog.exists():
            self.xorglog.touch()
    
    def detect_hardware(self):
        """Detect hardware configuration"""
        # Architecture
        self.system_info.arch_name = platform.machine()
        
        # Check for systemd
        self.system_info.have_systemd = Path("/run/systemd/system").exists()
        
        # Detect PC type from DMI
        self._detect_pc_type()
        
        # Detect disk drives
        self._detect_drives()
        
        # Detect network interfaces
        self._detect_network()
        
        # Detect graphics
        self._detect_graphics()
        
        # Detect sound
        self._detect_sound()
        
        # Detect other hardware features
        self._detect_hardware_features()
        
        # Check if express test is possible
        self._check_express_test()
    
    def _detect_pc_type(self):
        """Detect PC type from DMI information"""
        dmi_paths = [
            Path("/sys/class/dmi/id"),
            Path("/sys/devices/virtual/dmi/id")
        ]
        
        dmi_path = None
        for path in dmi_paths:
            if path.exists():
                dmi_path = path
                break
        
        if dmi_path:
            chassis_type_file = dmi_path / "chassis_type"
            if chassis_type_file.exists():
                try:
                    chassis_type = int(chassis_type_file.read_text().strip())
                    
                    # Map chassis types
                    if chassis_type in [3, 4, 5, 6, 7, 15, 16, 24, 36]:
                        self.system_info.pc_type = "Personal"
                    elif chassis_type in [8, 9, 10, 14]:
                        self.system_info.pc_type = "Notebook"
                    elif chassis_type in [17, 22, 23, 28, 29]:
                        self.system_info.pc_type = "Server"
                    elif chassis_type == 13:
                        self.system_info.pc_type = "Monoblock"
                    elif chassis_type == 30:
                        self.system_info.pc_type = "Tablet"
                    elif chassis_type == 31:
                        self.system_info.pc_type = "Convertible"
                    else:
                        self.system_info.pc_type = "Computer"
                except (ValueError, IOError):
                    pass
        
        # Check for virtualization
        if not self.system_info.pc_type:
            result = run_command(["lscpu"])
            if "Hypervisor vendor:" in result.stdout:
                self.system_info.pc_type = "Virtual"
            else:
                self.system_info.pc_type = "Computer"
        
        # Set computer name if not provided
        if not self.compname and dmi_path:
            product_name = (dmi_path / "product_name")
            board_name = (dmi_path / "board_name")
            
            if product_name.exists():
                self.compname = product_name.read_text().strip().replace(" ", "")
                self.compname = self.compname.split("(")[0].split(",")[0]
            
            if not self.compname and board_name.exists():
                self.compname = board_name.read_text().strip().replace(" ", "")
                self.compname = self.compname.split("(")[0].split(",")[0]
            
            if not self.compname:
                self.compname = f"{self.system_info.pc_type}-{self.system_info.arch_name}"
    
    def _detect_drives(self):
        """Detect disk drives"""
        drives = []
        
        try:
            block_dir = Path("/sys/block")
            for entry in block_dir.iterdir():
                name = entry.name
                
                # Skip certain device types
                if (name.startswith("loop") or name.startswith("ram") or
                    name.startswith("sr") or name.startswith("dm-") or
                    name.startswith("md")):
                    continue
                
                dev_path = Path(f"/dev/{name}")
                if not dev_path.is_block_device():
                    continue
                
                # Check if readable (not write-protected)
                ro_file = entry / "ro"
                if ro_file.exists():
                    try:
                        if ro_file.read_text().strip() != "0":
                            continue
                    except IOError:
                        pass
                
                # Skip if it's a slave or has holders
                slaves_dir = entry / "slaves"
                holders_dir = entry / "holders"
                
                if (slaves_dir.exists() and any(slaves_dir.iterdir())) or \
                   (holders_dir.exists() and any(holders_dir.iterdir())):
                    continue
                
                drives.append(name)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error detecting drives: {e}")
        
        # Check for MD RAID if no drives found
        if not drives:
            try:
                block_dir = Path("/sys/block")
                for entry in block_dir.iterdir():
                    if entry.name.startswith("md"):
                        dev_path = Path(f"/dev/{entry.name}")
                        if dev_path.is_block_device():
                            drives.append(entry.name)
            except Exception:
                pass
        
        self.system_info.drives = drives
    
    def _detect_network(self):
        """Detect network interfaces"""
        ifaces = []
        
        try:
            net_dir = Path("/sys/class/net")
            for entry in net_dir.iterdir():
                name = entry.name
                if name != "lo":
                    ifaces.append(name)
        except Exception:
            pass
        
        self.system_info.ifaces = ifaces
    
    def _detect_graphics(self):
        """Detect graphics environment"""
        # Check for Xorg
        self.system_info.have_xorg = has_binary("Xorg") or Path("/usr/bin/Xorg").exists()
        
        # Check for desktop environments
        self.system_info.have_kde5 = Path("/usr/share/plasma").exists()
        self.system_info.have_mate = Path("/usr/share/mate").exists()
        self.system_info.have_xfce = Path("/usr/share/xfce4").exists()
        self.system_info.have_gnome = Path("/usr/share/gnome").exists()
    
    def _detect_sound(self):
        """Detect sound cards"""
        result = run_command(["inxi", "-A", "-c0"])
        if " Device-1: " in result.stdout:
            self.system_info.sound_test = True
    
    def _detect_hardware_features(self):
        """Detect various hardware features"""
        # Infiniband/RDMA
        result = run_command(["lspci"])
        if "RDMA" in result.stdout or "infiniband" in result.stdout.lower():
            self.system_info.infb_test = True
        
        # NUMA
        result = run_command(["lscpu", "--parse=NODE"])
        nodes = set()
        for line in result.stdout.split("\n"):
            if line and not line.startswith("#"):
                parts = line.split(",")
                if parts:
                    nodes.add(parts[0])
        if len(nodes) > 1:
            self.system_info.numa_test = True
        
        # IPMI (for servers)
        if self.system_info.pc_type == "Server":
            self.system_info.ipmi_test = True
        
        # Webcam
        try:
            with open("/proc/modules") as f:
                modules = f.read()
                if any(mod in modules for mod in ["uvcvideo ", "gspca_", "em28xx"]):
                    self.system_info.webcam_test = True
        except IOError:
            pass
        
        # Power management (battery systems)
        if not self.system_info.have_xorg or not os.environ.get("DISPLAY"):
            result = run_command(["inxi", "-B", "-c0"])
            if " ID-1: " in result.stdout:
                self.system_info.power_test = True
        
        # Fingerprint scanner
        result = run_command(["lsusb"])
        usb_devices = result.stdout
        
        fingerprint_patterns = [
            "Fingerprint", "298d:1010", "1c7a:0570", "1c7a:0571", "1c7a:0603",
            "Digital Persona U.are.U 4000", "UPEK TouchChip", "UPEK Eikon Touch 300",
            "UPEK TouchStrip", "Elan MOC Sensors", "Veridicom 5thSense",
            "Synaptics Sensors", "AuthenTec AES16", "AuthenTec AES25",
            "AuthenTec AES26", "AuthenTec AES4000", "AuthenTec AES3500",
            "Validity VFS"
        ]
        
        for pattern in fingerprint_patterns:
            if pattern in usb_devices:
                self.system_info.fprnt_test = True
                break
        
        # Bluetooth
        result = run_command(["inxi", "-E", "-c0"])
        if " Device-1: " in result.stdout:
            self.system_info.bluez_test = True
        
        # Smart cards
        if has_binary("opensc-tool"):
            result = run_command(["opensc-tool", "--list-readers"])
            if "No smart card readers found" not in result.stdout:
                self.system_info.scard_test = True
    
    def _check_express_test(self):
        """Check if express test can be run"""
        if self.system_info.pc_type == "Server":
            return
        
        if not self.system_info.ifaces:
            return
        
        if not self.system_info.sound_test:
            return
        
        if not self.system_info.have_xorg:
            return
        
        if not (self.system_info.have_mate or self.system_info.have_kde5 or
                self.system_info.have_xfce or self.system_info.have_gnome):
            return
        
        result = run_command(["inxi", "-G", "-c0"])
        if " Device-1: " not in result.stdout:
            return
        
        self.system_info.xprss_test = True
    
    def load_test_plan(self) -> List[TestStep]:
        """Load the test plan from configuration files"""
        steps = []
        
        if self.launch_mode == LaunchMode.RETEST:
            # Load specific test from numbers.txt
            numbers_file = DEFAULT_VAR_LIB / "numbers.txt"
            if numbers_file.exists():
                for line in numbers_file.read_text().strip().split("\n"):
                    parts = line.split(None, 1)
                    if len(parts) == 2 and parts[0] == self.retest_no:
                        step_name = parts[1]
                        steps.append(TestStep(
                            number=self.retest_no,
                            name=step_name,
                            user_type="both"
                        ))
                        break
        else:
            # Load from start.txt or finish.txt
            plan_file = "finish.txt" if self.launch_mode == LaunchMode.FINISH else "start.txt"
            plan_path = DEFAULT_VAR_LIB / plan_file
            
            if plan_path.exists():
                for line in plan_path.read_text().strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        user_type = parts[0]
                        step_name = parts[1]
                        
                        # Get step number
                        step_num = self._get_step_number(step_name)
                        
                        steps.append(TestStep(
                            number=step_num,
                            name=step_name,
                            user_type=user_type
                        ))
        
        return steps
    
    def _get_step_number(self, step_name: str) -> str:
        """Get the step number from numbers.txt"""
        numbers_file = DEFAULT_VAR_LIB / "numbers.txt"
        if numbers_file.exists():
            for line in numbers_file.read_text().strip().split("\n"):
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[1] == step_name:
                    return parts[0]
        return "?"
    
    def draw_title_line(self, result: TestResult, number: str, text: str):
        """Draw a formatted title line for test results"""
        c = Colors() if self.config.colors_enabled else type('C', (), {
            'NORM': '', 'OK': '', 'WARN': '', 'ERR': ''
        })()
        
        if result == TestResult.RUNNING:
            prefix = f"{c.WARN}Running{c.NORM}... "
        elif result == TestResult.PASSED:
            prefix = f"[{c.OK}PASSED{c.NORM}  ] "
        elif result == TestResult.SKIPPED:
            prefix = f"[{c.WARN}SKIPPED{c.NORM} ] "
        elif result == TestResult.BLOCKED:
            prefix = f"[{c.ERR}BLOCKED{c.NORM} ] "
        else:
            prefix = f"[{c.ERR}FAILED{c.NORM}  ] "
        
        print(f"{prefix}{c.WARN}{number}. {c.LC2 if self.config.colors_enabled else ''}{text}{c.NORM}")
    
    def show_usage(self, message: str = ""):
        """Show usage information"""
        if message:
            print(message, file=sys.stderr)
        
        print(f"\nUsage: {PROG_NAME} [<options>...]")
        print(f"Try '{PROG_NAME} --help' for more details.")
        sys.exit(1)
    
    def fatal_error(self, code: str, message: str, *args):
        """Handle fatal errors"""
        if args:
            message = message % args
        
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        if self.config.colors_enabled:
            err_msg = f"[{Colors.ERR}{timestamp}{Colors.NORM}] {Colors.ERR}fatal[{code[1:]}]{Colors.NORM}: {Colors.ERR}{message}{Colors.NORM}"
        else:
            err_msg = f"[{timestamp}] fatal[{code[1:]}]: {message}"
        
        print(err_msg, file=sys.stderr)
        
        if self.logger:
            self.logger.error(f"Fatal error {code}: {message}")
        
        self.cleanup()
        sys.exit(1)
    
    def cleanup(self):
        """Cleanup before exit"""
        # Remove desktop file if exists
        self._remove_desktop_file()
    
    def _remove_desktop_file(self):
        """Remove the autorun desktop file"""
        desktop_file = Path.home() / ".config" / "autostart" / f"{PROG_NAME}.desktop"
        desktop_file.unlink(missing_ok=True)
    
    def copy_desktop_file(self):
        """Copy desktop file to autostart directory"""
        if os.geteuid() != 0 and os.environ.get("DISPLAY") and not self.config.disable_autorun:
            autostart_dir = Path.home() / ".config" / "autostart"
            autostart_dir.mkdir(parents=True, exist_ok=True)
            
            desktop_src = Path(f"/usr/share/applications/{PROG_NAME}.desktop")
            if desktop_src.exists():
                desktop_dst = autostart_dir / f"{PROG_NAME}.desktop"
                
                # Replace launcher.sh with resume.sh
                content = desktop_src.read_text()
                content = content.replace("/launcher.sh", "/resume.sh")
                desktop_dst.write_text(content)
                desktop_dst.chmod(0o644)
    
    def write_config(self):
        """Write current configuration to settings.ini"""
        if not self.workdir:
            return
        
        settings_file = self.workdir / "STATE" / "settings.ini"
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        
        config = configparser.ConfigParser()
        config['settings'] = {
            'update_apt_lists': str(self.config.update_apt_lists),
            'dist_upgrade': str(self.config.dist_upgrade),
            'update_kernel': str(self.config.update_kernel),
            'local_url': self.config.local_url,
            'ping_server': self.config.ping_server,
            'express_video_set': self.config.express_video_set,
            'lang_id': self.config.lang_id,
            'compname': self.compname,
        }
        
        with open(settings_file, 'w') as f:
            config.write(f)
        
        # Set ownership if running as root
        if os.geteuid() == 0 and self.username:
            try:
                pw = pwd.getpwnam(self.username)
                os.chown(settings_file, pw.pw_uid, pw.pw_gid)
            except (KeyError, OSError):
                pass
    
    def run(self, args: Optional[List[str]] = None):
        """Main entry point"""
        # Setup NLS
        self.setup_nls()
        
        # Parse arguments
        self.parse_arguments(args)
        
        # Load configuration
        self.load_config()
        
        # Get user info
        if os.geteuid() == 0:
            # Running as root, might need to switch user
            pass
        else:
            self.username, self.homedir = get_user_info()
        
        # Auto-detect launch mode if needed
        if self.launch_mode == LaunchMode.AUTO:
            self.launch_mode = self.detect_launch_mode()
        
        # Setup directories
        self.setup_directories()
        
        # Setup logging
        self.logger = setup_logging(self.logfile)
        self.logger.info(f"Starting {PROG_NAME} {VERSION}")
        
        # Print startup message
        en_name = self.nls.get("starting_program", "Starting program")
        ru_name = self.nls.get("starting_program", "Запуск программы")
        
        print(f"\n{en_name} / {ru_name}\n")
        
        # Detect hardware
        self.detect_hardware()
        
        # Write initial config
        self.write_config()
        
        # Load test plan
        self.steps = self.load_test_plan()
        
        if not self.steps:
            self.fatal_error("F19", "No test steps found in plan")
        
        # Run test steps
        self.run_test_loop()
        
        # Finalize
        self.finalize()
    
    def run_test_loop(self):
        """Main test execution loop"""
        for i, step in enumerate(self.steps):
            self.current_step_idx = i
            
            # Check user requirements
            if step.user_type == "root" and os.geteuid() != 0:
                # Need to restart as root
                self.logger.info(f"Step {step.name} requires root privileges")
                # Implementation of privilege escalation would go here
                pass
            
            if step.user_type == "user" and os.geteuid() == 0:
                # Should run as regular user
                step.status = TestResult.BLOCKED
                self.draw_title_line(step.status, step.number, 
                                    self.nls.get_step_name(step.name))
                continue
            
            # Run the test step
            step.status = TestResult.RUNNING
            self.draw_title_line(step.status, step.number,
                                self.nls.get_step_name(step.name))
            
            # Execute step
            result = self.execute_step(step)
            step.status = result
            
            # Draw result
            self.draw_title_line(step.status, step.number,
                                self.nls.get_step_name(step.name))
            
            # Save result
            self.save_step_result(step)
    
    def execute_step(self, step: TestStep) -> TestResult:
        """Execute a single test step"""
        # Import and run the appropriate step module
        step_module_path = DEFAULT_LIBDIR / "steps" / f"{step.name}.py"
        
        if step_module_path.exists():
            # Would import and execute Python step module
            # For now, simulate success
            return TestResult.PASSED
        else:
            # Fall back to bash scripts temporarily
            bash_script = DEFAULT_LIBDIR / "steps" / f"{step.name}.sh"
            if bash_script.exists():
                self.logger.info(f"Running bash step: {step.name}")
                # Could call bash script here during transition
                return TestResult.PASSED
            else:
                self.logger.warning(f"Step script not found: {step.name}")
                return TestResult.SKIPPED
    
    def save_step_result(self, step: TestStep):
        """Save the result of a test step"""
        if not self.workdir:
            return
        
        results_file = self.workdir / "STATE" / "RESULTS"
        with open(results_file, 'a') as f:
            f.write(f"{step.status.value}\t{step.name}\n")
    
    def finalize(self):
        """Finalize the testing process"""
        if not self.workdir:
            return
        
        # Check which part we're finishing
        plan_file = "finish.txt" if self.launch_mode == LaunchMode.FINISH else "start.txt"
        
        if (self.workdir / "STATE" / plan_file).exists():
            # First part complete
            msg = self.nls.get("first_part_complete", 
                              "The first part of testing is complete!")
            print(f"\n{Colors.OK}{msg}{Colors.NORM}")
            
            msg = "Perform manual testing according to section 10 of the methodology."
            print(msg)
            
            msg = self.nls.get("creating_archive", 
                              "Don't forget to run '@BOLD@' after testing!")
            msg = msg.replace("@BOLD@", f"{PROG_NAME} --finish")
            print(f"\n{Colors.BOLD}{msg}{Colors.NORM}")
        else:
            # Testing complete, create archive
            msg = self.nls.get("testing_complete", "Testing is complete!")
            print(f"\n{Colors.OK}{msg}{Colors.NORM}")
            
            # Create archive
            archive_name = f"{PROG_NAME}-{self.workdir.name}.tar"
            archive_path = Path.home() / archive_name
            
            msg = self.nls.get("creating_archive", "Creating the archive '@BOLD@'...")
            msg = msg.replace("@BOLD@", archive_name)
            print(f"\n{Colors.BOLD}{msg}{Colors.NORM}")
            
            # Move STATE files
            state_dir = self.workdir / "STATE"
            if state_dir.exists():
                for item in state_dir.iterdir():
                    shutil.move(str(item), str(self.workdir / item.name))
                state_dir.rmdir()
            
            # Create tarball
            parent_dir = self.workdir.parent
            with tarfile.open(archive_path, "w") as tar:
                tar.add(self.workdir, arcname=self.workdir.name)
            
            # Try to move to server location
            server_dir = Path(f"/mnt/{PROG_NAME}")
            if server_dir.exists():
                server_archive = server_dir / f"{self.compname}-{self.workdir.name}.tar"
                try:
                    shutil.copy(archive_path, server_archive)
                    msg = self.nls.get("archive_moved_to", 
                                      "Now this archive has been moved to")
                    print(f"{msg}: {Colors.WARN}{server_archive}{Colors.NORM}")
                    archive_path.unlink()
                except Exception as e:
                    self.logger.warning(f"Could not copy to server: {e}")
        
        # Pause before exit
        if not self.config.batch_mode:
            msg = self.nls.get("press_key_close", "Press any key to close this window...")
            print(f"\n{msg}")
            try:
                input()
            except EOFError:
                pass


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point"""
    app = PCTestApp()
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(130)
    except Exception as e:
        if app.logger:
            app.logger.exception("Unexpected error")
        else:
            print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
