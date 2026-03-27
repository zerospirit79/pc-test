"""
Step 06: Log Collection
Collects system logs and diagnostic information.
"""

import subprocess
import os
import shutil
import tarfile
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path
from .base import BaseStep, StepResult, StepStatus


class LogCollectionStep(BaseStep):
    """Collects system logs and diagnostics."""
    
    def __init__(self, config: Dict[str, Any], logger: Any):
        super().__init__(config, logger)
        self.log_dir = config.get('log_dir', '/var/log')
        self.output_dir = config.get('output_dir', '/tmp/pc-test-logs')
        self.archive_path = None
    
    def execute(self) -> StepResult:
        """Execute log collection."""
        self.logger.info("Starting log collection...")
        
        try:
            # Create output directory
            os.makedirs(self.output_dir, exist_ok=True)
            
            collected_logs = {
                "system_logs": self._collect_system_logs(),
                "dmesg": self._collect_dmesg(),
                "hardware_info": self._collect_hardware_info(),
                "network_config": self._collect_network_config(),
                "package_info": self._collect_package_info(),
            }
            
            # Create archive
            self.archive_path = self._create_archive()
            
            errors = []
            for key, value in collected_logs.items():
                if isinstance(value, dict) and value.get("error"):
                    errors.append(f"{key}: {value['error']}")
                elif isinstance(value, str) and value.startswith("Error"):
                    errors.append(f"{key}: {value}")
            
            status = StepStatus.FAILED if errors else StepStatus.PASSED
            
            return StepResult(
                step_name=self.name,
                status=status,
                message="Log collection completed",
                details={
                    "collected_logs": collected_logs,
                    "archive_path": self.archive_path,
                    "output_dir": self.output_dir
                },
                errors=errors
            )
        
        except Exception as e:
            self.logger.exception(f"Log collection failed")
            return StepResult(
                step_name=self.name,
                status=StepStatus.FAILED,
                message=f"Log collection failed: {str(e)}",
                errors=[str(e)]
            )
    
    def teardown(self) -> None:
        """Cleanup temporary files if needed."""
        pass  # Keep logs for user to retrieve
    
    def _collect_system_logs(self) -> Dict[str, Any]:
        """Collect system logs from /var/log."""
        result = {"files": [], "size_bytes": 0}
        
        try:
            log_files = [
                'syslog', 'messages', 'kern.log', 'auth.log',
                'boot.log', 'Xorg.0.log', 'alternatives.log',
                'dpkg.log', 'apt/history.log', 'apt/term.log'
            ]
            
            for log_file in log_files:
                full_path = os.path.join(self.log_dir, log_file)
                if os.path.exists(full_path):
                    size = os.path.getsize(full_path)
                    dest_path = os.path.join(self.output_dir, f"log_{log_file.replace('/', '_')}")
                    
                    # Copy file
                    shutil.copy2(full_path, dest_path)
                    
                    result["files"].append({
                        "name": log_file,
                        "size_bytes": size,
                        "copied_to": dest_path
                    })
                    result["size_bytes"] += size
            
            # Collect journalctl logs if available
            result = subprocess.run(
                ['which', 'journalctl'],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                journal_path = os.path.join(self.output_dir, 'journal.txt')
                with open(journal_path, 'w') as f:
                    subprocess.run(
                        ['journalctl', '--no-pager', '-n', '1000'],
                        stdout=f, stderr=subprocess.DEVNULL, timeout=60
                    )
                result["files"].append({
                    "name": "journal.txt",
                    "size_bytes": os.path.getsize(journal_path),
                    "copied_to": journal_path
                })
        
        except Exception as e:
            self.logger.error(f"System log collection failed: {e}")
            result["error"] = str(e)
        
        return result
    
    def _collect_dmesg(self) -> Dict[str, Any]:
        """Collect dmesg output."""
        result = {"output": "", "size_bytes": 0}
        
        try:
            output_path = os.path.join(self.output_dir, 'dmesg.txt')
            
            proc_result = subprocess.run(
                ['dmesg'],
                capture_output=True, text=True, timeout=30
            )
            
            with open(output_path, 'w') as f:
                f.write(proc_result.stdout)
            
            result["output"] = output_path
            result["size_bytes"] = os.path.getsize(output_path)
        
        except Exception as e:
            self.logger.error(f"dmesg collection failed: {e}")
            result["error"] = str(e)
        
        return result
    
    def _collect_hardware_info(self) -> Dict[str, Any]:
        """Collect hardware information."""
        result = {"files": []}
        
        commands = {
            'lspci.txt': ['lspci', '-vvv'],
            'lsusb.txt': ['lsusb', '-v'],
            'lscpu.txt': ['lscpu'],
            'lsblk.txt': ['lsblk', '-a'],
            'lsmem.txt': ['lsmem'],
            'numactl.txt': ['numactl', '--hardware'],
            'cpuinfo.txt': ['cat', '/proc/cpuinfo'],
            'meminfo.txt': ['cat', '/proc/meminfo'],
            'interrupts.txt': ['cat', '/proc/interrupts'],
        }
        
        for filename, cmd in commands.items():
            try:
                output_path = os.path.join(self.output_dir, filename)
                
                proc_result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=30
                )
                
                with open(output_path, 'w') as f:
                    f.write(proc_result.stdout)
                
                result["files"].append({
                    "name": filename,
                    "size_bytes": os.path.getsize(output_path),
                    "command": ' '.join(cmd)
                })
            except Exception as e:
                self.logger.error(f"Failed to collect {filename}: {e}")
                result["files"].append({
                    "name": filename,
                    "error": str(e)
                })
        
        return result
    
    def _collect_network_config(self) -> Dict[str, Any]:
        """Collect network configuration."""
        result = {"files": []}
        
        commands = {
            'ip_addr.txt': ['ip', 'addr'],
            'ip_route.txt': ['ip', 'route'],
            'ip_link.txt': ['ip', 'link'],
            'netstat.txt': ['ss', '-tulpn'],
            'resolv_conf.txt': ['cat', '/etc/resolv.conf'],
            'hosts.txt': ['cat', '/etc/hosts'],
            'network_interfaces.txt': ['cat', '/etc/network/interfaces'],
        }
        
        for filename, cmd in commands.items():
            try:
                output_path = os.path.join(self.output_dir, filename)
                
                proc_result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=30
                )
                
                with open(output_path, 'w') as f:
                    f.write(proc_result.stdout)
                
                result["files"].append({
                    "name": filename,
                    "size_bytes": os.path.getsize(output_path)
                })
            except Exception as e:
                self.logger.error(f"Failed to collect {filename}: {e}")
        
        return result
    
    def _collect_package_info(self) -> Dict[str, Any]:
        """Collect package manager information."""
        result = {"files": [], "package_manager": None}
        
        try:
            # Detect package manager
            for pm in ['apt', 'dnf', 'yum', 'zypper', 'pacman']:
                proc_result = subprocess.run(
                    ['which', pm],
                    capture_output=True, timeout=10
                )
                if proc_result.returncode == 0:
                    result["package_manager"] = pm
                    
                    if pm == 'apt':
                        # List installed packages
                        output_path = os.path.join(self.output_dir, 'installed_packages.txt')
                        with open(output_path, 'w') as f:
                            subprocess.run(
                                ['dpkg', '--list'],
                                stdout=f, stderr=subprocess.DEVNULL, timeout=60
                            )
                        result["files"].append({
                            "name": "installed_packages.txt",
                            "size_bytes": os.path.getsize(output_path)
                        })
                        
                        # List upgradable packages
                        output_path = os.path.join(self.output_dir, 'upgradable_packages.txt')
                        with open(output_path, 'w') as f:
                            subprocess.run(
                                ['apt', 'list', '--upgradable'],
                                stdout=f, stderr=subprocess.DEVNULL, timeout=60
                            )
                        result["files"].append({
                            "name": "upgradable_packages.txt",
                            "size_bytes": os.path.getsize(output_path)
                        })
                    
                    elif pm in ['dnf', 'yum']:
                        output_path = os.path.join(self.output_dir, 'installed_packages.txt')
                        with open(output_path, 'w') as f:
                            subprocess.run(
                                [pm, 'list', 'installed'],
                                stdout=f, stderr=subprocess.DEVNULL, timeout=120
                            )
                        result["files"].append({
                            "name": "installed_packages.txt",
                            "size_bytes": os.path.getsize(output_path)
                        })
                    
                    break
        
        except Exception as e:
            self.logger.error(f"Package info collection failed: {e}")
            result["error"] = str(e)
        
        return result
    
    def _create_archive(self) -> str:
        """Create tar.gz archive of collected logs."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = f"pc-test-logs-{timestamp}.tar.gz"
            archive_path = os.path.join(self.output_dir, archive_name)
            
            with tarfile.open(archive_path, "w:gz") as tar:
                for item in os.listdir(self.output_dir):
                    item_path = os.path.join(self.output_dir, item)
                    if item_path != archive_path:  # Don't include the archive itself
                        tar.add(item_path, arcname=item)
            
            self.logger.info(f"Created archive: {archive_path}")
            return archive_path
        
        except Exception as e:
            self.logger.error(f"Failed to create archive: {e}")
            raise
