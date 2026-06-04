"""Analyze dmesg, journal and systemd logs for critical issues and bottlenecks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

# Kernel messages that indicate serious failures (checked before generic errors).
DMESG_CRITICAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("kernel panic", re.compile(r"kernel panic", re.I)),
    ("oops", re.compile(r"\boops\b", re.I)),
    ("BUG", re.compile(r"\bBUG:", re.I)),
    ("MCE", re.compile(r"machine check", re.I)),
    ("hardware error", re.compile(r"hardware error", re.I)),
    ("page fault", re.compile(r"unable to handle kernel paging request", re.I)),
    ("I/O error", re.compile(r"\bI/O error\b", re.I)),
    ("AER", re.compile(r"AER: (Corrected error message|Multiple Corrected error) received", re.I)),
)

DMESG_ERROR_PATTERN = re.compile(r"(panic|fatal|fail|error|warning)", re.I)
DMESG_SKIP_SUBSTRINGS = (" Command line: ", " Kernel command line: ")

AER_PATTERN = re.compile(
    r"AER: (Corrected error message|Multiple Corrected error) received",
    re.I,
)

BLAME_LINE = re.compile(
    r"^\s*(?P<value>[\d.]+)\s*(?P<unit>ms|s|min|\+ms|\+s|\+min)\s+(?P<name>\S+)\s*$"
)
CHAIN_TIME = re.compile(r"@([\d.]+)(ms|s|min)\b")
CHAIN_START = re.compile(r"\+([\d.]+)(ms|s|min)\b")


@dataclass
class LogFinding:
    severity: str
    source: str
    message: str
    count: int = 1


@dataclass
class Bottleneck:
    source: str
    name: str
    time_ms: float


@dataclass
class LogAnalysisReport:
    findings: list[LogFinding] = field(default_factory=list)
    bottlenecks: list[Bottleneck] = field(default_factory=list)
    failed_units: list[str] = field(default_factory=list)
    aer_count: int = 0

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings) or bool(self.failed_units)


def _duration_to_ms(value: str, unit: str) -> float:
    amount = float(value)
    unit = unit.lstrip("+")
    if unit == "ms":
        return amount
    if unit == "min":
        return amount * 60_000.0
    return amount * 1000.0


def _merge_finding(findings: list[LogFinding], severity: str, source: str, message: str) -> None:
    key = message.strip()
    if not key:
        return
    for item in findings:
        if item.severity == severity and item.source == source and item.message == key:
            item.count += 1
            return
    findings.append(LogFinding(severity=severity, source=source, message=key))


def analyze_dmesg_lines(lines: Iterable[str]) -> tuple[list[LogFinding], int]:
    """Return findings and AER event count from dmesg text lines."""
    findings: list[LogFinding] = []
    aer_count = 0
    for line in lines:
        if any(skip in line for skip in DMESG_SKIP_SUBSTRINGS):
            continue
        if AER_PATTERN.search(line):
            aer_count += 1
        matched_critical = False
        for label, pattern in DMESG_CRITICAL_PATTERNS:
            if pattern.search(line):
                if label == "AER":
                    continue
                _merge_finding(findings, "critical", "dmesg", line.strip())
                matched_critical = True
                break
        if matched_critical:
            continue
        if DMESG_ERROR_PATTERN.search(line):
            _merge_finding(findings, "error", "dmesg", line.strip())
    return findings, aer_count


def analyze_journal_err_lines(lines: Iterable[str]) -> list[LogFinding]:
    findings: list[LogFinding] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        severity = "critical" if re.search(r"(panic|fatal|crit|emerg)", text, re.I) else "error"
        _merge_finding(findings, severity, "journal", text)
    return findings


def parse_systemctl_failed(text: str) -> list[str]:
    units: list[str] = []
    suffixes = (".service", ".target", ".socket", ".mount")
    for line in text.splitlines():
        stripped = line.strip().replace("●", " ")
        if not stripped or stripped.startswith("UNIT "):
            continue
        if " failed " not in stripped:
            continue
        for token in stripped.split():
            if token.endswith(suffixes):
                units.append(token)
                break
    return sorted(set(units))


def parse_systemd_blame(text: str, *, limit: int = 10, min_ms: float = 500.0) -> list[Bottleneck]:
    items: list[Bottleneck] = []
    for line in text.splitlines():
        match = BLAME_LINE.match(line)
        if not match:
            continue
        ms = _duration_to_ms(match.group("value"), match.group("unit"))
        if ms < min_ms:
            continue
        items.append(Bottleneck(source="systemd-blame", name=match.group("name"), time_ms=ms))
    items.sort(key=lambda item: item.time_ms, reverse=True)
    return items[:limit]


def parse_critical_chain(text: str, *, limit: int = 10, min_ms: float = 500.0) -> list[Bottleneck]:
    items: list[Bottleneck] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("The time"):
            continue
        start = CHAIN_START.search(stripped)
        active = CHAIN_TIME.search(stripped)
        ms = 0.0
        if start:
            ms = _duration_to_ms(start.group(1), start.group(2))
        elif active:
            ms = _duration_to_ms(active.group(1), active.group(2))
        if ms < min_ms:
            continue
        name = stripped.split()[0]
        items.append(Bottleneck(source="critical-chain", name=name, time_ms=ms))
    items.sort(key=lambda item: item.time_ms, reverse=True)
    return items[:limit]


def merge_reports(parts: Sequence[LogAnalysisReport]) -> LogAnalysisReport:
    merged = LogAnalysisReport()
    seen_bottleneck: set[tuple[str, str]] = set()
    for part in parts:
        merged.findings.extend(part.findings)
        merged.aer_count += part.aer_count
        for unit in part.failed_units:
            if unit not in merged.failed_units:
                merged.failed_units.append(unit)
        for bn in part.bottlenecks:
            key = (bn.source, bn.name)
            if key in seen_bottleneck:
                continue
            seen_bottleneck.add(key)
            merged.bottlenecks.append(bn)
    merged.bottlenecks.sort(key=lambda item: item.time_ms, reverse=True)
    return merged


def analyze_collected_logs(
    *,
    dmesg: str = "",
    journal_err: str = "",
    systemctl_failed: str = "",
    systemd_blame: str = "",
    critical_chain: str = "",
    bottleneck_limit: int = 10,
    bottleneck_min_ms: float = 500.0,
) -> LogAnalysisReport:
    """Build a combined report from captured log texts."""
    dmesg_findings, aer_count = analyze_dmesg_lines(dmesg.splitlines())
    report = LogAnalysisReport(
        findings=dmesg_findings + analyze_journal_err_lines(journal_err.splitlines()),
        aer_count=aer_count,
        failed_units=parse_systemctl_failed(systemctl_failed),
    )
    report.bottlenecks = parse_systemd_blame(
        systemd_blame,
        limit=bottleneck_limit,
        min_ms=bottleneck_min_ms,
    )
    report.bottlenecks.extend(
        parse_critical_chain(
            critical_chain,
            limit=bottleneck_limit,
            min_ms=bottleneck_min_ms,
        )
    )
    report.bottlenecks.sort(key=lambda item: item.time_ms, reverse=True)
    report.bottlenecks = report.bottlenecks[:bottleneck_limit]
    return report


def _format_ms(ms: float) -> str:
    if ms >= 1000.0:
        return f"{ms / 1000.0:.3f}s"
    return f"{ms:.0f}ms"


def format_report(report: LogAnalysisReport, *, lang: str = "ru") -> str:
    """Render human-readable log analysis for the workdir archive."""
    ru = lang == "ru"
    lines: list[str] = []
    title = "Анализ системных журналов" if ru else "System log analysis"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")

    if report.aer_count:
        label = "Сообщений PCIe AER" if ru else "PCIe AER messages"
        lines.append(f"{label}: {report.aer_count}")
        if report.aer_count > 9:
            hint = (
                "Рекомендуется pcie_aspm=off, pci=nomsi или pci=noaer"
                if ru
                else "Consider pcie_aspm=off, pci=nomsi or pci=noaer"
            )
            lines.append(f"  ! {hint}")
        lines.append("")

    if report.failed_units:
        label = "Сбойные unit-ы systemd" if ru else "Failed systemd units"
        lines.append(label + ":")
        for unit in report.failed_units:
            lines.append(f"  - {unit}")
        lines.append("")

    critical = [f for f in report.findings if f.severity == "critical"]
    errors = [f for f in report.findings if f.severity == "error"]
    if critical:
        label = "Критические сообщения" if ru else "Critical messages"
        lines.append(label + ":")
        for item in critical[:30]:
            suffix = f" (x{item.count})" if item.count > 1 else ""
            lines.append(f"  [{item.source}]{suffix} {item.message}")
        if len(critical) > 30:
            lines.append(f"  ... +{len(critical) - 30}")
        lines.append("")

    if errors:
        label = "Ошибки и предупреждения" if ru else "Errors and warnings"
        lines.append(label + ":")
        for item in errors[:40]:
            suffix = f" (x{item.count})" if item.count > 1 else ""
            lines.append(f"  [{item.source}]{suffix} {item.message}")
        if len(errors) > 40:
            lines.append(f"  ... +{len(errors) - 40}")
        lines.append("")

    if report.bottlenecks:
        label = "Узкие места загрузки (>500ms)" if ru else "Boot bottlenecks (>500ms)"
        lines.append(label + ":")
        for item in report.bottlenecks:
            lines.append(f"  {_format_ms(item.time_ms):>8}  [{item.source}] {item.name}")
        lines.append("")

    if not any((report.findings, report.bottlenecks, report.failed_units, report.aer_count)):
        lines.append("Замечаний не обнаружено." if ru else "No issues detected.")
    return "\n".join(lines).rstrip() + "\n"


def emit_report_to_log(
    ctx, report: LogAnalysisReport, *, outfile: str = "log-analysis.txt"
) -> None:
    """Write report file and append its contents to pc-test.log."""
    text = format_report(report, lang=getattr(ctx, "langid", "ru") or "ru")
    Path(outfile).write_text(text, encoding="utf-8")

    ctx.spawn(f": {outfile}")
    logfile = getattr(ctx, "logfile", "")
    if logfile and Path(logfile).is_file():
        with open(logfile, "a", encoding="utf-8", errors="replace") as lf:
            lf.write(text if text.endswith("\n") else text + "\n")

    ctx.spawn(": Log analysis summary")
    if report.failed_units:
        ctx.spawn(f": Failed systemd units: {len(report.failed_units)}")
    if report.aer_count > 9:
        ctx.spawn(f": PCIe AER messages: {report.aer_count}")
    critical = sum(1 for f in report.findings if f.severity == "critical")
    errors = sum(1 for f in report.findings if f.severity == "error")
    if critical:
        ctx.spawn(f": Critical log lines: {critical}")
    if errors:
        ctx.spawn(f": Error/warning log lines: {errors}")
    if report.bottlenecks:
        slowest = report.bottlenecks[0]
        ctx.spawn(
            f": Slowest boot step: {_format_ms(slowest.time_ms)} "
            f"({slowest.name}, {slowest.source})"
        )
    if not report.has_critical and not report.findings and not report.bottlenecks:
        ctx.spawn(": No critical issues in saved logs")
