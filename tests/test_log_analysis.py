"""Tests for log_analysis."""

import unittest

from pc_test.log_analysis import (
    analyze_collected_logs,
    analyze_dmesg_lines,
    parse_systemctl_failed,
    parse_systemd_blame,
)


class LogAnalysisTests(unittest.TestCase):
    def test_analyze_dmesg_critical_and_aer(self):
        text = [
            "[    1.000000] kernel panic - not syncing",
            "[    2.000000] AER: Multiple Corrected error received",
            "[    3.000000] Command line: BOOT_IMAGE=linux ro",
        ]
        findings, aer_count = analyze_dmesg_lines(text)
        self.assertEqual(aer_count, 1)
        self.assertTrue(
            any(f.severity == "critical" and "kernel panic" in f.message for f in findings)
        )

    def test_parse_systemctl_failed(self):
        text = """
  UNIT                         LOAD   ACTIVE SUB    DESCRIPTION
● pcscd.service                loaded failed failed PC/SC Smart Card Daemon
"""
        self.assertEqual(parse_systemctl_failed(text), ["pcscd.service"])

    def test_parse_systemd_blame(self):
        text = """
  1.234s dev-sda1.device
  600ms NetworkManager.service
  50ms systemd-journald.service
"""
        items = parse_systemd_blame(text, limit=5, min_ms=500.0)
        names = [item.name for item in items]
        self.assertIn("dev-sda1.device", names)
        self.assertIn("NetworkManager.service", names)
        self.assertNotIn("systemd-journald.service", names)

    def test_analyze_collected_logs_merge(self):
        report = analyze_collected_logs(
            dmesg="[    0.0] something error happened\n",
            journal_err="Fatal error in service\n",
            systemctl_failed="● bad.service loaded failed failed Bad\n",
            systemd_blame="  2.000s slow.service\n",
        )
        self.assertEqual(report.failed_units, ["bad.service"])
        self.assertTrue(report.bottlenecks)
        self.assertEqual(report.bottlenecks[0].name, "slow.service")

    def test_emit_report_to_log_appends_full_report(self):
        import tempfile
        from pathlib import Path

        from pc_test.log_analysis import emit_report_to_log, format_report

        class Ctx:
            logfile = ""
            langid = "ru"

            def __init__(self, logpath: Path) -> None:
                self.logfile = str(logpath)
                self._lines: list[str] = []

            def spawn(self, *args: str) -> int:
                if len(args) == 1 and args[0].startswith(": "):
                    self._lines.append(args[0][2:])
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            logpath = Path(tmp) / "pc-test.log"
            logpath.write_text("", encoding="utf-8")
            ctx = Ctx(logpath)
            report = analyze_collected_logs(
                systemctl_failed="● bad.service loaded failed failed Bad\n",
            )
            import os

            prev = os.getcwd()
            os.chdir(tmp)
            try:
                emit_report_to_log(ctx, report, outfile="log-analysis-final.txt")
            finally:
                os.chdir(prev)
            report_text = format_report(report, lang="ru")
            self.assertTrue((Path(tmp) / "log-analysis-final.txt").is_file())
            self.assertIn(report_text, logpath.read_text(encoding="utf-8"))
            self.assertTrue(any("log-analysis-final.txt" in line for line in ctx._lines))
            self.assertIn("Log analysis summary", ctx._lines)


if __name__ == "__main__":
    unittest.main()
