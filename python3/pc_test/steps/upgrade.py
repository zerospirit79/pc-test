"""System and kernel update step."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pc_test.constants import TEST_FAILED, TEST_PASSED
from pc_test.steps.base import StepBase, register_step

ALTSP_MIRRORS = [
    "http://update.altsp.su/pub/distributions/ALTLinux",
    "ftp://update.altsp.su/pub/distributions/ALTLinux",
    "rsync://update.altsp.su/ALTLinux",
]
APT_REPO_SET_BRANCHES = ("p9", "p10", "p11", "Sisyphus")
_REPO_SOURCE_MARKERS = {
    "p9": (r"p9/branch", r"\[p9\]"),
    "p10": (r"p10/branch", r"\[p10\]"),
    "p11": (r"p11/branch", r"\[p11\]"),
    "Sisyphus": (r"sisyphus", r"\[alt\]"),
    "c9f2": (r"CF2/branch",),
    "c10f2": (r"c10f2/branch",),
    "c10f1": (r"c10f/branch",),
    "c9f1": (r"c9f1/branch",),
}
_WRONG_REPO_MARKERS = (
    "not available as an update candidate",
    "нет доступных кандидатов на обновление",
    "unable to mark needed changes",
)
PUBLIC_MIRRORS = [
    "http://ftp.altlinux.org/pub/distributions/ALTLinux",
    "ftp://ftp.altlinux.org/pub/distributions/ALTLinux",
    "rsync://ftp.altlinux.org/ALTLinux",
    "http://mirror.yandex.ru/altlinux",
    "ftp://mirror.yandex.ru/altlinux",
    "rsync://mirror.yandex.ru/altlinux",
    "http://mirror.cs.msu.ru/alt",
    "rsync://mirror.cs.msu.ru/alt",
    "http://mirror.datacenter.by/pub/ALTLinux",
    "ftp://mirror.datacenter.by/pub/ALTLinux",
    "rsync://mirror.datacenter.by/ALTLinux",
    "http://ftp.heanet.ie/mirrors/ftp.altlinux.org",
    "ftp://ftp.heanet.ie/mirrors/ftp.altlinux.org",
    "rsync://ftp.heanet.ie/mirrors/ftp.altlinux.org",
    "http://distrib-coffee.ipsl.jussieu.fr/pub/linux/altlinux",
    "ftp://distrib-coffee.ipsl.jussieu.fr/pub/linux/altlinux",
    "rsync://distrib-coffee.ipsl.jussieu.fr/pub/linux/altlinux",
]


@register_step
class UpgradeStep(StepBase):
    STEP_ID = "upgrade"
    number = "5.2"
    en_name = "System and kernel update"
    ru_name = "Обновление системы и ядра"

    def testcase(self) -> int:
        ctx = self.ctx
        self._dist_changed = False
        self._kernel_changed = False
        rc = 0
        if ctx.update_apt_lists:
            self._setup_apt_sources()
        apt_repo = subprocess.run(["apt-repo"], capture_output=True, text=True)
        if ctx.logfile:
            with open(ctx.logfile, "a", encoding="utf-8") as lf:
                lf.write(apt_repo.stdout or "")
        ctx.spawn("apt-get", "update")

        for try_no in range(1, 4):
            if ctx.dist_upgrade:
                if self._dist_upgrade() != 0:
                    rc = 1
            if ctx.update_kernel:
                if self._update_kernel() != 0:
                    rc = 1
            if rc == 0:
                break
            msg = ctx.L("L100", "Try #%s/3 of a system update has been failed")
            line = f"{ctx.CLR_ERR}{msg % try_no}{ctx.CLR_NORM}...\n"
            if ctx.logfile:
                with open(ctx.logfile, "a", encoding="utf-8") as lf:
                    lf.write(line)
            if try_no == 3:
                break
            time.sleep(2)
            rc = 0

        if ctx.have_altsp:
            if ctx.repo in ("c10f1", "c10f2"):
                ctx.spawn("apt-mark", "manual", "update-kernel")
            elif ctx.update_apt_lists and ctx.repo == "c9f1":
                Path("/etc/apt/preferences").unlink(missing_ok=True)
                ctx.spawn("apt-get", "update")

        packages = []
        if not ctx.is_pkg_installed("inxi"):
            packages.append("inxi")
        if ctx.have_xorg and os.environ.get("DISPLAY") and ctx.is_pkg_available("yad"):
            if not ctx.is_pkg_installed("yad"):
                packages.append("yad")
        else:
            if not ctx.is_pkg_installed("dialog"):
                packages.append("dialog")
        if packages:
            if ctx.spawn("apt-get", "install", "-y", "--", *packages) != 0:
                rc = 1

        if rc != 0:
            final_rc = TEST_FAILED
            msg = ctx.L(
                "L104",
                "System/kernel update finished with errors (see log). Testing will continue.",
            )
            line = f"{ctx.CLR_ERR}{msg}{ctx.CLR_NORM}\n"
            print(line, end="", flush=True)
            if ctx.logfile:
                with open(ctx.logfile, "a", encoding="utf-8") as lf:
                    lf.write(line)
        else:
            final_rc = TEST_PASSED

        if ctx.have_altsp and ctx.has_binary("integalert"):
            ctx.spawn("integalert", "fix")

        # Methodology: reboot after system/kernel update before the next steps (5.3+).
        if (ctx.dist_upgrade or ctx.update_kernel) and final_rc == TEST_PASSED:
            ctx.system_restart(final_rc)
        return final_rc

    def _setup_apt_sources(self) -> None:
        ctx = self.ctx
        url = ""
        if ctx.local_url:
            url = ctx.local_url
        elif ctx.local_mirror:
            url = self._setup_network_mirror()
        elif ctx.local_media_labels:
            url = self._setup_external_media()
        elif ctx.repodate:
            url = self._archive_url()
        if self._special_altsp_cdrom_case(url):
            return
        arepo_lines = subprocess.run(["apt-repo"], capture_output=True, text=True).stdout or ""
        if self._should_rewrite_sources(arepo_lines, url):
            self._reset_branch_repositories(url)
        elif url:
            self._replace_mirror(url)

        if ctx.have_altsp and ctx.repo == "c9f1":
            Path("/etc/apt/preferences").write_text(
                "Package: *\nPin: release c=classic\nPin-Priority: 1001\n",
                encoding="utf-8",
            )

    def _archive_url(self) -> str:
        ctx = self.ctx
        base = "http://ftp.altlinux.org/pub/distributions/archive"
        if ctx.repo == "Sisyphus":
            url = f"{base}/sisyphus/date"
        elif ctx.repo in ("p9", "p10", "p11", "c9f2", "c10f2"):
            url = f"{base}/{ctx.repo}/date"
        else:
            return ""
        if url:
            self._write_sources(url)
        return url

    def _special_altsp_cdrom_case(self, url: str) -> bool:
        ctx = self.ctx
        if (
            ctx.have_altsp
            and ctx.repo == "c9f2"
            and not url
            and "rpm cdrom:"
            in (subprocess.run(["apt-repo"], capture_output=True, text=True).stdout or "")
        ):
            ctx.spawn("apt-repo", "rm", "all", "cdroms")
            ctx.spawn("apt-repo")
            ctx.spawn("apt-get", "update")
            ctx.spawn("apt-get", "dist-upgrade", "-y")
            ctx.spawn("rpm", "--eval", "%_priority_distbranch")
            ctx.spawn("rpm", "-q", "apt-conf-branch")
            return True
        return False

    def _setup_network_mirror(self) -> str:
        ctx = self.ctx
        dirp = ctx.local_mirror.split()[1] if ctx.local_mirror.split() else "/mnt/mirror"
        ctx.spawn("mkdir", "-p", "--", dirp)
        fstab = Path("/etc/fstab").read_text(encoding="utf-8")
        if ctx.local_mirror not in fstab:
            with open("/etc/fstab", "a", encoding="utf-8") as f:
                f.write(ctx.local_mirror + "\n")
        ctx.spawn("mount", "--", dirp)
        if ctx.mirror_subdir:
            dirp = f"{dirp}/{ctx.mirror_subdir}"
        if not Path(f"{dirp}/{ctx.repo}/noarch/base").is_dir():
            ctx.fatal("F11", "Couldn't connect to the server with a local mirror!")
        msg = ctx.L("L101", "Server with the local mirror is connected")
        print(f"{msg}: {ctx.CLR_BOLD}{ctx.repo}{ctx.CLR_NORM}\n")
        return dirp

    def _setup_external_media(self) -> str:
        ctx = self.ctx
        dirp = ""
        label_used = ""
        for label in ctx.local_media_labels:
            candidate = f"{ctx.local_media_base}/{label}"
            if subprocess.run(["mountpoint", "-q", "--", candidate], check=False).returncode == 0:
                check = candidate
                if ctx.local_media_check:
                    check = f"{check}/{ctx.local_media_check}"
                if Path(f"{check}/{ctx.repo}/noarch/base").is_dir():
                    dirp = check
                    label_used = label
                    break
        if not dirp:
            ctx.fatal("F10", "External media with the mirror is not connected!")
        msg = ctx.L("L102", "External media with the mirror is connected")
        print(f"{msg}: {ctx.CLR_BOLD}{label_used}{ctx.CLR_NORM}\n")
        return dirp

    def _apt_repo_list(self) -> str:
        proc = subprocess.run(["apt-repo"], capture_output=True, text=True)
        return proc.stdout or ""

    def _only_cdrom_sources(self, arepo_lines: str) -> bool:
        lines = [ln.strip() for ln in arepo_lines.splitlines() if ln.strip().startswith("rpm")]
        return bool(lines) and all("cdrom:" in ln for ln in lines)

    def _repo_in_sources(self, repo: str, arepo_lines: str) -> bool:
        for pat in _REPO_SOURCE_MARKERS.get(repo, (repo,)):
            if re.search(pat, arepo_lines, re.I):
                return True
        return False

    def _should_rewrite_sources(self, arepo_lines: str, url: str) -> bool:
        ctx = self.ctx
        if url and ctx.repodate:
            return False
        if not arepo_lines.strip():
            return True
        if self._only_cdrom_sources(arepo_lines):
            return True
        if ctx.repo and not self._repo_in_sources(ctx.repo, arepo_lines):
            return True
        return False

    def _reset_branch_repositories(self, url: str = "") -> None:
        ctx = self.ctx
        if not url and ctx.repo in APT_REPO_SET_BRANCHES:
            msg = ctx.L(
                "L103",
                "Configuring APT repositories for branch %s",
            )
            line = f"{msg % ctx.repo}\n"
            if ctx.logfile:
                with open(ctx.logfile, "a", encoding="utf-8") as lf:
                    lf.write(line)
            print(line, end="", flush=True)
            if (
                ctx.spawn("apt-repo", "rm", "all") == 0
                and ctx.spawn("apt-repo", "set", ctx.repo) == 0
            ):
                return
        self._write_sources(url)

    def _apt_up_to_date_summary(self, text: str) -> bool:
        low = text.lower()
        return any(
            m in low
            for m in (
                "0 upgraded",
                "0 будет обновлено",
                "0 newly installed",
                "0 новых установлено",
            )
        )

    def _apt_zero_packages_failed(self, text: str) -> bool:
        """apt reports a transaction error but 0 packages failed (already current)."""
        low = text.lower()
        if "не удалось обновить 0 пакетов" in low:
            return True
        return re.search(r"failed to update 0 packages?", low) is not None

    def _upgrade_output_indicates_wrong_repos(self, text: str) -> bool:
        low = text.lower()
        if self._apt_zero_packages_failed(text):
            return False
        if self._apt_up_to_date_summary(text) and any(
            m in low
            for m in (
                "not available as an update candidate",
                "нет доступных кандидатов на обновление",
            )
        ):
            return False
        if re.search(r"не удалось обновить ([1-9]\d*) пакет", low):
            return True
        if re.search(r"failed to update ([1-9]\d*) packages?", low):
            return True
        return any(m in low for m in _WRONG_REPO_MARKERS)

    def _apt_nothing_to_upgrade(self, text: str) -> bool:
        """System is already up to date (not a repository mismatch)."""
        if self._apt_zero_packages_failed(text):
            return True
        if self._upgrade_output_indicates_wrong_repos(text):
            return False
        low = text.lower()
        return self._apt_up_to_date_summary(text) or any(
            m in low
            for m in (
                "already the newest version",
                "уже установлена самая последняя версия",
            )
        )

    def _dist_upgrade_ok(self, returncode: int, combined: str) -> bool:
        return returncode == 0 or self._apt_nothing_to_upgrade(combined)

    def _dist_upgrade(self) -> int:
        returncode, combined = self._run_tee(["apt-get", "dist-upgrade", "-y"])
        if self._dist_upgrade_ok(returncode, combined):
            if returncode == 0 and not self._apt_nothing_to_upgrade(combined):
                self._dist_changed = True
            return 0
        if self._upgrade_output_indicates_wrong_repos(combined):
            self._reset_branch_repositories()
            self.ctx.spawn("apt-get", "update")
            returncode, combined = self._run_tee(["apt-get", "dist-upgrade", "-y"])
            if self._dist_upgrade_ok(returncode, combined):
                if returncode == 0 and not self._apt_nothing_to_upgrade(combined):
                    self._dist_changed = True
                return 0
        return returncode

    def _update_kernel(self) -> int:
        """Run update-kernel per methodology; use -f only when a new kernel is required."""
        returncode, combined = self._run_update_kernel(["update-kernel"])
        if self._update_kernel_ok(combined, returncode):
            if self._kernel_install_changed_system(combined) and not self._kernel_already_current(
                combined
            ):
                self._kernel_changed = True
            return 0
        if self._kernel_already_current(combined):
            return 0
        returncode, combined = self._run_update_kernel(["update-kernel", "-f"])
        if self._update_kernel_ok(combined, returncode):
            if self._kernel_install_changed_system(combined) and not self._kernel_already_current(
                combined
            ):
                self._kernel_changed = True
            return 0
        return returncode

    def _run_update_kernel(self, args: list[str]) -> tuple[int, str]:
        """Run update-kernel; auto-confirm module install prompts for pc-test runs."""
        return self._run_tee(args, stdin_reply="y\n" * 8)

    def _run_tee(
        self,
        args: list[str],
        *,
        stdin_reply: str | None = None,
    ) -> tuple[int, str]:
        """Run a command with live terminal output, log tee, and optional stdin."""
        ctx = self.ctx
        ctx.cmd_title(" ".join(args))
        chunks: list[str] = []
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if stdin_reply is not None else None,
                text=True,
                bufsize=1,
            )
            if stdin_reply is not None and proc.stdin is not None:
                proc.stdin.write(stdin_reply)
                proc.stdin.close()
            assert proc.stdout is not None
            for line in proc.stdout:
                chunks.append(line)
                sys.stderr.write(line)
                sys.stderr.flush()
                if ctx.logfile:
                    with open(ctx.logfile, "a", encoding="utf-8", errors="replace") as lf:
                        lf.write(line)
            return proc.wait(), "".join(chunks)
        except KeyboardInterrupt:
            ctx.fatal("F20", "Testing canceled.")

    def _kernel_already_current(self, text: str) -> bool:
        low = text.lower()
        return ("already installed on your system" in low) or (
            "latest available kernel" in low and "already installed" in low
        )

    def _kernel_install_changed_system(self, text: str) -> bool:
        """True if update-kernel installed or upgraded boot kernel packages."""
        low = text.lower()
        if self._kernel_already_current(text):
            return False
        for pkg in ("kernel-image", "kernel-modules"):
            if pkg not in low:
                continue
            if re.search(
                rf"(newly installed|новых установлено|upgraded,|будет обновлено).*{pkg}|"
                rf"{pkg}.*(newly installed|новых установлено|upgraded,|будет обновлено)",
                low,
            ):
                if "already the newest" in low or "уже установлена самая последняя" in low:
                    continue
                return True
        return False

    def _update_kernel_ok(self, combined: str, returncode: int) -> bool:
        """Success only when update-kernel exits 0 or reports nothing to do."""
        if returncode == 0:
            return True
        low = combined.lower()
        if "error while running transaction" in low or "failed to install kernel" in low:
            return False
        if any(
            m in low
            for m in (
                "nothing to do",
                "нечего",
                "no new kernel",
                "not needed",
                "не требуется",
                "everything is already installed",
                "no upgrade is possible",
                "всё уже установлено",
                "нечего обновлять",
            )
        ):
            return True
        if "latest available kernel" in low and "already installed" in low:
            return True
        if "is already installed on your system" in low:
            return True
        return False

    def _write_sources(self, url: str = "") -> None:
        ctx = self.ctx
        arepo = "1"
        archive = ""
        vendor = "cert8"
        first = "classic"
        branch = f"{ctx.repo}/branch"
        mirror = ""
        fmt = "rpm [{}] {} {}/{} {}\n"

        if url:
            if url.startswith("/"):
                url = f"file:{url}"
                branch = ctx.repo
                mirror = "1"
            elif ctx.repodate:
                branch = ctx.repodate.replace("-", "/")
                archive = "1"
        elif ctx.have_altsp:
            url = ALTSP_MIRRORS[0]
        else:
            url = PUBLIC_MIRRORS[0]

        arch = ctx.archname
        if ctx.repo == "Sisyphus":
            if arch in ("mipsel", "riscv64", "loongarch64"):
                if not mirror:
                    branch = f"ports/{arch}/{ctx.repo}"
                vendor = f"sisyphus-{arch}"
                archive = ""
            else:
                if not archive:
                    branch = ctx.repo
                vendor = "alt"
            arepo = ""
        elif ctx.repo in ("p10", "p11"):
            first = "classic gostcrypto"
            vendor = ctx.repo
        elif ctx.repo == "p9":
            if arch == "mipsel":
                if not mirror:
                    branch = f"ports/{arch}/{ctx.repo}"
                vendor = f"{ctx.repo}-{arch}"
                archive = ""
            else:
                vendor = ctx.repo
        elif ctx.repo == "c10f2":
            if not mirror and not archive:
                branch = "c10f2/branch"
            first = "classic gostcrypto"
        elif ctx.repo == "c10f1":
            if not mirror:
                branch = "c10f/branch"
            first = "classic gostcrypto"
            archive = ""
        elif ctx.repo == "c9f2":
            if not mirror and not archive:
                branch = "CF2/branch"
        elif ctx.repo == "c9f1":
            if not mirror:
                branch = "c9f1/branch"
            archive = ""

        ctx.spawn("apt-repo", "rm", "all")
        lines = [fmt.format(vendor, url, branch, arch, first)]
        if arch == "x86_64" and arepo:
            lines.append(fmt.format(vendor, url, branch, "x86_64-i586", "classic"))
        lines.append(fmt.format(vendor, url, branch, "noarch", "classic"))
        with open("/etc/apt/sources.list", "a", encoding="utf-8") as f:
            f.writelines(lines)

    def _replace_mirror(self, url: str) -> None:
        ctx = self.ctx
        mirror = url.startswith("/") or url.startswith("file:")
        proc = ctx.spawn_capture("mktemp", "-qt", f"{ctx.progname}-XXXXXXXX.tmp")
        tmpf = proc.stdout.strip()
        arepo_out = subprocess.run(["apt-repo"], capture_output=True, text=True).stdout or ""
        Path(tmpf).write_text(arepo_out, encoding="utf-8")
        ctx.spawn("apt-repo", "rm", "all")
        out_lines = []
        for line in arepo_out.splitlines():
            parts = line.split()
            if not parts:
                continue
            first, optional, addr, *junk = (
                parts[0],
                parts[1] if len(parts) > 1 else "",
                parts[2] if len(parts) > 2 else "",
                *parts[3:],
            )
            if optional.startswith("["):
                pass
            else:
                junk = [addr] + junk if addr else junk
                addr = optional
                optional = ""
            for u in ALTSP_MIRRORS + PUBLIC_MIRRORS:
                if addr.startswith(u):
                    addr = f"{url}{addr[len(u) :]}"
                    if mirror:
                        addr = f"file:{addr.replace('/branch/', '/')}"
                    break
            if mirror:
                junk_str = " ".join(junk).replace("branch/", "")
            else:
                junk_str = " ".join(junk)
            line_out = first
            if optional:
                line_out += f" {optional}"
            line_out += f" {addr} {junk_str}\n"
            out_lines.append(line_out)
        with open("/etc/apt/sources.list", "a", encoding="utf-8") as f:
            f.writelines(out_lines)
        Path(tmpf).unlink(missing_ok=True)
