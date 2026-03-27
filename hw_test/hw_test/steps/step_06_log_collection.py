"""Step 6: Log Collection."""

import subprocess
import os
import tarfile
import tempfile
import shutil
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from hw_test.types import StepResult, TestStatus, HardwareInfo, TestConfig
from hw_test.steps.base import BaseHWStep


class LogCollectionStep(BaseHWStep):
    """Collect system logs, hardware information, and create an archive."""
    
    name = "Log Collection"
    description = "Gather system logs, dmesg, hardware info, and create a compressed archive"
    required_privileges = True
    
    def __init__(self, config: TestConfig, hardware_info: Optional[HardwareInfo] = None):
        super().__init__(config, hardware_info)
        self.collected_files: List[str] = []
        self.archive_path: Optional[str] = None
    
    def _run_command(self, cmd: List[str], timeout: int = 60, output_file: Optional[str] = None) -> tuple[str, str, int]:
        """Run a command and return (stdout, stderr, returncode)."""
        try:
            if output_file:
                with open(output_file, 'w') as f:
                    result = subprocess.run(
                        cmd,
                        stdout=f,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=timeout
                    )
                    return "", result.stderr, result.returncode
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Command timed out: {' '.join(cmd)}")
            return "", "Timeout", -1
        except Exception as e:
            self.logger.debug(f"Command failed: {' '.join(cmd)} - {e}")
            return "", str(e), -1
    
    def _collect_command_output(self, cmd: List[str], filename: str, work_dir: str) -> bool:
        """Collect output of a command to a file."""
        filepath = os.path.join(work_dir, filename)
        
        try:
            stdout, stderr, rc = self._run_command(cmd, output_file=filepath)
            
            if rc == 0 or (stdout and len(stdout) > 0):
                self.collected_files.append(filepath)
                return True
            elif stderr:
                # Write error message to file
                with open(filepath, 'w') as f:
                    f.write(f"Command failed: {' '.join(cmd)}\n")
                    f.write(f"Error: {stderr}\n")
                self.collected_files.append(filepath)
                return True
                
        except Exception as e:
            self.logger.debug(f"Failed to collect {filename}: {e}")
        
        return False
    
    def _collect_file(self, src_path: str, work_dir: str, dest_name: Optional[str] = None) -> bool:
        """Copy a file to the collection directory."""
        if not os.path.exists(src_path):
            return False
        
        try:
            dest_name = dest_name or os.path.basename(src_path)
            dest_path = os.path.join(work_dir, dest_name)
            
            # Handle both files and directories
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path, ignore_dangling_symlinks=True)
            else:
                shutil.copy2(src_path, dest_path)
            
            self.collected_files.append(dest_path)
            return True
            
        except Exception as e:
            self.logger.debug(f"Failed to collect {src_path}: {e}")
            return False
    
    def _create_archive(self, work_dir: str, output_dir: str) -> Optional[str]:
        """Create a tar.gz archive of collected files."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = f"hw-test_{self.config.name}_{timestamp}.tar.gz"
            archive_path = os.path.join(output_dir, archive_name)
            
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            with tarfile.open(archive_path, "w:gz") as tar:
                for filepath in self.collected_files:
                    if os.path.exists(filepath):
                        # Add file with relative path
                        arcname = os.path.relpath(filepath, work_dir)
                        tar.add(filepath, arcname=arcname)
            
            self.archive_path = archive_path
            return archive_path
            
        except Exception as e:
            self.logger.error(f"Failed to create archive: {e}")
            return None
    
    def execute(self) -> StepResult:
        """Execute log collection."""
        errors = []
        warnings = []
        
        self.logger.info("Starting log collection...")
        
        # Create temporary working directory
        work_dir = None
        try:
            work_dir = tempfile.mkdtemp(prefix='hw-test-logs-')
            self.logger.debug(f"Working directory: {work_dir}")
            
            # Collect system logs
            log_files = [
                ('/var/log/syslog', 'syslog.log'),
                ('/var/log/messages', 'messages.log'),
                ('/var/log/kern.log', 'kern.log'),
                ('/var/log/dpkg.log', 'dpkg.log'),
                ('/var/log/apt/history.log', 'apt-history.log'),
                ('/var/log/apt/term.log', 'apt-term.log'),
                ('/var/log/boot.log', 'boot.log'),
                ('/var/log/faillog', 'faillog.txt'),
                ('/var/log/lastlog', 'lastlog.txt'),
            ]
            
            logs_collected = 0
            for src, dest in log_files:
                if self._collect_file(src, work_dir, dest):
                    logs_collected += 1
            
            self.logger.info(f"Collected {logs_collected} log files")
            
            # Collect command outputs
            commands = [
                (['dmesg'], 'dmesg.txt'),
                (['uname', '-a'], 'uname.txt'),
                (['hostnamectl'], 'hostnamectl.txt'),
                (['lscpu'], 'lscpu.txt'),
                (['lsblk', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE'], 'lsblk.txt'),
                (['df', '-h'], 'df.txt'),
                (['free', '-m'], 'free.txt'),
                (['ip', 'addr'], 'ip-addr.txt'),
                (['ip', 'route'], 'ip-route.txt'),
                (['ss', '-tulpn'], 'ss.txt'),
                (['lspci', '-nn'], 'lspci.txt'),
                (['lsusb'], 'lsusb.txt'),
                (['aplay', '-l'], 'audio-playback.txt'),
                (['arecord', '-l'], 'audio-capture.txt'),
                (['xrandr'], 'xrandr.txt'),
                (['env'], 'environment.txt'),
                (['ps', 'auxf'], 'processes.txt'),
                (['systemctl', 'list-units', '--state=failed'], 'failed-services.txt'),
                (['journalctl', '-p', 'err', '-n', '200', '--no-pager'], 'journal-errors.txt'),
                (['dmidecode', '-t', 'system'], 'dmidecode-system.txt'),
                (['dmidecode', '-t', 'bios'], 'dmidecode-bios.txt'),
                (['fwupdmgr', 'get-devices'], 'fwupd-devices.txt'),
            ]
            
            cmds_collected = 0
            for cmd, filename in commands:
                if self._collect_command_output(cmd, filename, work_dir):
                    cmds_collected += 1
            
            self.logger.info(f"Collected output from {cmds_collected} commands")
            
            # Collect hardware info from sysfs
            sysfs_dirs = [
                ('/sys/class/dmi/id', 'dmi-info'),
                ('/sys/class/net', 'net-devices'),
                ('/sys/block', 'block-devices'),
            ]
            
            for src, dest in sysfs_dirs:
                self._collect_file(src, work_dir, dest)
            
            # Create summary JSON
            summary = {
                'test_name': self.config.name,
                'collection_time': datetime.now().isoformat(),
                'logs_collected': logs_collected,
                'commands_collected': cmds_collected,
                'collected_files_count': len(self.collected_files),
                'hardware_summary': {}
            }
            
            # Add hardware summary if available
            if self.hardware_info:
                summary['hardware_summary'] = {
                    'cpu': self.hardware_info.cpu_model,
                    'cpu_cores': self.hardware_info.cpu_cores,
                    'memory_mb': self.hardware_info.total_memory_mb,
                    'disks_count': len(self.hardware_info.disk_info),
                    'network_interfaces': len(self.hardware_info.network_interfaces),
                    'gpus': len(self.hardware_info.gpu_info),
                }
            
            summary_path = os.path.join(work_dir, 'summary.json')
            with open(summary_path, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            self.collected_files.append(summary_path)
            
            # Create archive
            output_dir = self.config.data_dir
            archive_path = self._create_archive(work_dir, output_dir)
            
            if archive_path:
                status = TestStatus.PASSED
                message = f"Logs collected and archived to {archive_path}"
                
                result_details = {
                    'archive_path': archive_path,
                    'archive_size_bytes': os.path.getsize(archive_path),
                    'files_collected': len(self.collected_files),
                    'logs_count': logs_collected,
                    'commands_count': cmds_collected,
                    'summary': summary
                }
            else:
                status = TestStatus.WARNING
                message = "Logs collected but archive creation failed"
                warnings.append("Failed to create archive")
                result_details = {
                    'files_collected': len(self.collected_files),
                    'logs_count': logs_collected,
                    'commands_count': cmds_collected,
                    'summary': summary
                }
            
            return StepResult(
                step_name=self.name,
                status=status,
                message=message,
                details=result_details,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            self.logger.exception(f"Log collection failed: {e}")
            return StepResult(
                step_name=self.name,
                status=TestStatus.ERROR,
                message=f"Log collection failed: {str(e)}",
                errors=[str(e)]
            )
            
        finally:
            # Cleanup temporary directory
            if work_dir and os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup temp directory: {e}")
