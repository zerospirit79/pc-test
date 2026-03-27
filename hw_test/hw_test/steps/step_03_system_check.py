"""Step 3: System Check."""

import subprocess
import os
import re
from typing import List, Dict, Any, Optional
from packaging import version

from hw_test.types import StepResult, TestStatus, HardwareInfo, TestConfig
from hw_test.steps.base import BaseHWStep


class SystemCheckStep(BaseHWStep):
    """Check OS integrity, package manager status, updates, and disk space."""
    
    name = "System Check"
    description = "Verify OS version, package manager health, available updates, and disk space"
    required_privileges = True
    
    def __init__(self, config: TestConfig, hardware_info: Optional[HardwareInfo] = None):
        super().__init__(config, hardware_info)
        self.check_results: Dict[str, Any] = {}
    
    def _run_command(self, cmd: List[str], timeout: int = 60) -> tuple[str, str, int]:
        """Run a command and return (stdout, stderr, returncode)."""
        try:
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
    
    def _check_os_version(self) -> Dict[str, Any]:
        """Check operating system version."""
        result = {'status': 'unknown', 'distribution': '', 'version': ''}
        
        # Try /etc/os-release
        if os.path.exists('/etc/os-release'):
            try:
                with open('/etc/os-release', 'r') as f:
                    content = f.read()
                    
                for line in content.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        value = value.strip('"\'')
                        
                        if key == 'NAME':
                            result['distribution'] = value
                        elif key == 'VERSION':
                            result['version'] = value
                        elif key == 'VERSION_ID':
                            result['version_id'] = value
                        elif key == 'PRETTY_NAME':
                            result['pretty_name'] = value
                
                if result['distribution']:
                    result['status'] = 'passed'
                    
            except Exception as e:
                result['error'] = str(e)
        
        # Alternative: lsb_release
        if not result.get('distribution'):
            stdout, _, rc = self._run_command(['lsb_release', '-a'])
            if rc == 0:
                for line in stdout.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip()
                        
                        if key == 'distributor id':
                            result['distribution'] = value
                        elif key == 'description':
                            result['version'] = value
                
                if result['distribution']:
                    result['status'] = 'passed'
        
        # Check if ALT Linux
        if result.get('distribution') and 'alt' in result['distribution'].lower():
            result['is_alt_linux'] = True
        else:
            result['is_alt_linux'] = False
            result['warning'] = "Not running on ALT Linux distribution"
        
        return result
    
    def _check_package_manager(self) -> Dict[str, Any]:
        """Check package manager (APT/DPKG for ALT Linux)."""
        result = {'status': 'unknown', 'manager': '', 'healthy': False}
        
        # Check for apt
        stdout, _, rc = self._run_command(['apt', '--version'])
        if rc == 0:
            result['manager'] = 'apt'
            result['apt_version'] = stdout.split('\n')[0].strip()
        
        # Check dpkg database integrity
        stdout, stderr, rc = self._run_command(['dpkg', '--audit'])
        if rc == 0:
            result['dpkg_healthy'] = True
            result['status'] = 'passed'
        else:
            result['dpkg_healthy'] = False
            result['dpkg_issues'] = stdout + stderr
            result['status'] = 'warning'
        
        # Check for broken packages
        stdout, _, rc = self._run_command(['apt', 'check'])
        if rc != 0:
            result['broken_packages'] = True
            result['status'] = 'warning'
        else:
            result['broken_packages'] = False
        
        return result
    
    def _check_updates(self) -> Dict[str, Any]:
        """Check for available updates."""
        result = {'status': 'passed', 'updates_available': 0, 'security_updates': 0}
        
        try:
            # Update package lists (quietly)
            self._run_command(['apt-get', 'update'], timeout=120)
            
            # Check upgradable packages
            stdout, _, rc = self._run_command(['apt', 'list', '--upgradable'])
            if rc == 0:
                lines = [l for l in stdout.split('\n') if l.strip() and not l.startswith('Listing')]
                result['updates_available'] = len(lines)
                
                if lines:
                    result['upgradable_packages'] = [l.split('/')[0] for l in lines[:10]]
                    
                    if result['updates_available'] > 50:
                        result['status'] = 'warning'
                        result['warning'] = "Large number of pending updates"
            
            # Check security updates
            stdout, _, rc = self._run_command([
                'apt', 'list', '--upgradable', 
                '-o', 'APT::Get::List-Cleanup=false'
            ])
            
            # Simple heuristic: count packages with security in name
            if stdout:
                security_count = sum(1 for line in stdout.split('\n') 
                                    if 'security' in line.lower())
                result['security_updates'] = security_count
                
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
        
        return result
    
    def _check_disk_space(self) -> Dict[str, Any]:
        """Check disk space usage."""
        result = {'status': 'passed', 'partitions': []}
        
        try:
            stdout, _, rc = self._run_command(['df', '-h', '-x', 'tmpfs', '-x', 'devtmpfs'])
            if rc == 0:
                lines = stdout.split('\n')[1:]  # Skip header
                
                for line in lines:
                    if not line.strip():
                        continue
                    
                    parts = line.split()
                    if len(parts) >= 5:
                        partition = {
                            'filesystem': parts[0],
                            'size': parts[1],
                            'used': parts[2],
                            'available': parts[3],
                            'use_percent': int(parts[4].replace('%', '')),
                            'mountpoint': parts[5]
                        }
                        result['partitions'].append(partition)
                        
                        # Check critical thresholds
                        if partition['use_percent'] > 95:
                            partition['status'] = 'critical'
                            result['status'] = 'failed'
                        elif partition['use_percent'] > 85:
                            partition['status'] = 'warning'
                            if result['status'] == 'passed':
                                result['status'] = 'warning'
                        else:
                            partition['status'] = 'ok'
                            
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
        
        return result
    
    def _check_system_integrity(self) -> Dict[str, Any]:
        """Basic system integrity checks."""
        result = {'status': 'passed', 'checks': []}
        
        # Check /var/log for recent errors
        check_items = [
            ('/var/log/syslog', 'syslog'),
            ('/var/log/messages', 'messages'),
            ('/var/log/apt/history.log', 'apt_history'),
        ]
        
        for log_path, log_name in check_items:
            check_result = {'name': log_name, 'exists': False, 'readable': False}
            
            if os.path.exists(log_path):
                check_result['exists'] = True
                if os.access(log_path, os.R_OK):
                    check_result['readable'] = True
                    
                    # Check file size
                    size = os.path.getsize(log_path)
                    check_result['size_bytes'] = size
                    
                    if size > 100 * 1024 * 1024:  # > 100MB
                        check_result['warning'] = "Log file is very large"
                        result['status'] = 'warning'
                else:
                    check_result['error'] = "Not readable"
            else:
                check_result['note'] = "Log file does not exist"
            
            result['checks'].append(check_result)
        
        # Check for core dumps
        try:
            core_files = []
            for root, dirs, files in os.walk('/var/crash', topdown=True):
                for f in files:
                    if f.endswith('.crash') or 'core' in f.lower():
                        core_files.append(os.path.join(root, f))
            
            if core_files:
                result['core_dumps'] = len(core_files)
                result['status'] = 'warning'
                result['warning'] = f"Found {len(core_files)} crash/core dump files"
            else:
                result['core_dumps'] = 0
                
        except Exception:
            pass
        
        return result
    
    def execute(self) -> StepResult:
        """Execute system checks."""
        errors = []
        warnings = []
        
        self.logger.info("Starting system checks...")
        
        try:
            # Run all checks
            self.check_results['os_version'] = self._check_os_version()
            self.check_results['package_manager'] = self._check_package_manager()
            self.check_results['updates'] = self._check_updates()
            self.check_results['disk_space'] = self._check_disk_space()
            self.check_results['integrity'] = self._check_system_integrity()
            
            # Aggregate results
            failed_checks = []
            warning_checks = []
            
            for check_name, check_result in self.check_results.items():
                if check_result.get('status') == 'failed':
                    failed_checks.append(check_name)
                elif check_result.get('status') == 'warning':
                    warning_checks.append(check_name)
            
            # Build summary
            summary = {
                'os': self.check_results['os_version'],
                'package_manager': self.check_results['package_manager'],
                'updates': self.check_results['updates'],
                'disk_space': self.check_results['disk_space'],
                'integrity': self.check_results['integrity'],
            }
            
            # Determine overall status
            if failed_checks:
                status = TestStatus.FAILED
                message = f"System checks failed: {', '.join(failed_checks)}"
                errors.extend([f"Check '{c}' failed" for c in failed_checks])
            elif warning_checks:
                status = TestStatus.WARNING
                message = f"System checks completed with warnings: {', '.join(warning_checks)}"
                warnings.extend([f"Check '{c}' has issues" for c in warning_checks])
            else:
                status = TestStatus.PASSED
                message = "All system checks passed"
            
            return StepResult(
                step_name=self.name,
                status=status,
                message=message,
                details=summary,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            self.logger.exception(f"System checks failed: {e}")
            return StepResult(
                step_name=self.name,
                status=TestStatus.ERROR,
                message=f"System checks failed: {str(e)}",
                errors=[str(e)]
            )
