"""Load localized strings from pc-test l10n shell files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple


def _expand_shell_refs(text: str, table: Dict[str, str]) -> str:
    for _ in range(20):
        m = re.search(r"\$([A-Z][A-Z0-9_]*)", text)
        if not m:
            break
        ref = m.group(1)
        if ref not in table:
            break
        text = text[: m.start()] + table[ref] + text[m.end() :]
    return text


def _assign_message(table: Dict[str, str], key: str, val: str) -> None:
    """Append to an existing key like bash messages.sh (L321=$L321 more text)."""
    val = val.replace("\\'", "'")
    self_ref = f"${key}"
    if key in table and val.startswith(self_ref):
        suffix = val[len(self_ref) :].lstrip()
        table[key] = f"{table[key]} {suffix}".strip() if suffix else table[key]
    else:
        table[key] = val


def load_messages(langid: str, libdir: str) -> Dict[str, str]:
    path = Path(libdir) / "l10n" / langid / "messages.sh"
    if not path.is_file():
        path = Path(libdir) / "l10n" / "en" / "messages.sh"
    table: Dict[str, str] = {}
    if not path.is_file():
        return table
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^(L[0-9]+)=\"(.*)\"$", line.strip())
        if m:
            _assign_message(table, m.group(1), m.group(2))
    for key in list(table):
        table[key] = _expand_shell_refs(table[key], table)
    return table


def load_fatal(langid: str, libdir: str) -> Dict[str, str]:
    defaults = {
        "F01": "%s fatal[%s]",
        "F02": "Unexpected error: %s",
        "F03": "Invalid command-line usage. Try '%s -h' for more details.",
        "F04": "First you need to disable %s!",
        "F05": "Use pcie_aspm=off, pci=nomsi or pci=noaer boot options!",
        "F06": "ALT Linux or compatible distro is required!",
        "F07": "Unsupported distro: %s",
        "F08": "Unsupported certified distro: %s",
        "F09": "Unsupported distro version: %s",
        "F10": "External media with the mirror is not connected!",
        "F11": "Couldn't connect to the server with a local mirror!",
        "F12": "Invalid color mode: '%s'.",
        "F13": "Unsupported option: '%s'.",
        "F14": "To many argument(s): %s",
        "F15": "The program launch mode already specified: '%s'.",
        "F16": "You must be root for using --uid=<UID>.",
        "F17": "Invalid user ID: '%s'.",
        "F18": "The specified test '%s' cannot be retaken at this time.",
        "F19": "Step module '%s' not found.",
        "F20": "Testing canceled.",
        "F21": "Couldn't configure sudo.",
    }
    path = Path(libdir) / "l10n" / langid / "fatal.sh"
    if not path.is_file():
        return defaults
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^#?(F[0-9]+)=\"(.*)\"$", line.strip())
        if m:
            defaults[m.group(1)] = m.group(2).replace("\\'", "'")
    return defaults


def load_config_menu(langid: str, libdir: str) -> Tuple[str, List[Tuple[str, str]], int]:
    path = Path(libdir) / "l10n" / langid / "config.sh"
    if not path.is_file():
        path = Path(libdir) / "l10n" / "en" / "config.sh"
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    mate_m = re.search(r'mate_item="([^"]*)"', text)
    mate_item = mate_m.group(1) if mate_m else "Installing MATE in ALT SP Server 10"
    width_m = re.search(r"tui_form_width=(\d+)", text)
    tui_width = int(width_m.group(1)) if width_m else 51
    tests_list: List[Tuple[str, str]] = []
    block_m = re.search(r"tests_list=\(\s*(.*?)\s*\)", text, re.DOTALL)
    if block_m:
        entries = re.findall(r'(\w+)\s+"([^"]*)"', block_m.group(1))
        tests_list = [(tag, label) for tag, label in entries]
    if not tests_list:
        tests_list = [
            ("fwupd", "Hardware components firmware update"),
            ("devel", "Additional diagnostics for developers"),
            ("xprss", "Express test of main components"),
            ("infb", "Testing Infiniband/RDMA"),
            ("sound", "Testing Sound Card"),
            ("numa", "Testing NUMA Technology"),
            ("ipmi", "Testing IMPI Management"),
            ("webcam", "Testing internal Web-camera"),
            ("power", "Testing Console Power Management"),
            ("fprnt", "Testing Fingerprint Scanner"),
            ("bluez", "Testing Bluetooth interface"),
            ("scard", "Testing Smart-cards interface"),
            ("fio", "Checking Disk drives performance"),
            ("v3d", "Checking 2D/3D-Video performance"),
        ]
    return mate_item, tests_list, tui_width


def msg(table: Dict[str, str], key: str, default: str = "") -> str:
    return table.get(key, default or key)
