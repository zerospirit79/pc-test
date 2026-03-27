"""Step 5: Firmware Check."""

import subprocess
import os
from typing import List, Dict, Any, Optional

from hw_test.types import StepResult, TestStatus, HardwareInfo, TestConfig
from hw_test.steps.base import BaseHWStep


class FirmwareCheckStep(BaseHWStep):
    """Check BIOS/UEFI version and available firmware updates via fwupd."""
    
    name = "Firmware Check"
    description = "Verify BIOS/UEFI version and check for firmware updates using fwupd"
    required_privileges = True
    
    def __init__(self, config: TestConfig, hardware_info: Optional[HardwareInfo] = None):
        super().__init__(config, hardware_info)
        self.firmware_results: Dict[str, Any] = {}
    
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
    
    def _detect_bios_info(self) -> Dict[str, Any]:
        """Detect BIOS/UEFI information from DMI."""
        result = {
            'status': 'unknown',
            'vendor': '',
            'version': '',
            'date': '',
            'bios_revision': '',
            'firmware_type': 'unknown'
        }
        
        # Read from sysfs
        dmi_files = {
            '/sys/class/dmi/id/bios_vendor': 'vendor',
            '/sys/class/dmi/id/bios_version': 'version',
            '/sys/class/dmi/id/bios_date': 'date',
            '/sys/class/dmi/id/bios_revision': 'bios_revision',
        }
        
        for file_path, key in dmi_files.items():
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        value = f.read().strip()
                        if value:
                            result[key] = value
            except (FileNotFoundError, PermissionError) as e:
                self.logger.debug(f"Cannot read {file_path}: {e}")
        
        # Determine firmware type
        if os.path.exists('/sys/firmware/efi'):
            result['firmware_type'] = 'UEFI'
            result['status'] = 'passed'
        elif result['vendor']:
            result['firmware_type'] = 'Legacy BIOS'
            result['status'] = 'passed'
        else:
            result['status'] = 'warning'
            result['warning'] = 'Could not detect BIOS/UEFI information'
        
        # Additional info via dmidecode if available
        stdout, _, rc = self._run_command(['dmidecode', '-t', 'bios'])
        if rc == 0:
            result['dmidecode_available'] = True
            
            # Parse relevant info
            for line in stdout.split('\n'):
                if 'Runtime Size:' in line or 'ROM Size:' in line:
                    if 'rom_size' not in result:
                        result['rom_size'] = line.strip()
                elif 'Characteristics:' in line:
                    result['has_characteristics'] = True
        else:
            result['dmidecode_available'] = False
        
        return result
    
    def _check_fwupd(self) -> Dict[str, Any]:
        """Check fwupd daemon and available updates."""
        result = {
            'status': 'skipped',
            'available': False,
            'daemon_running': False,
            'devices': [],
            'updates_available': 0
        }
        
        # Check if fwupd is installed
        stdout, _, rc = self._run_command(['fwupdmgr', '--version'])
        if rc != 0:
            result['available'] = False
            result['warning'] = 'fwupd is not installed'
            return result
        
        result['available'] = True
        result['fwupd_version'] = stdout.split('\n')[0].strip() if stdout else 'unknown'
        
        # Check if daemon is running
        stdout, _, rc = self._run_command(['systemctl', 'is-active', 'fwupd.service'])
        if rc == 0 and stdout.strip() == 'active':
            result['daemon_running'] = True
        else:
            result['daemon_running'] = False
            result['warning'] = 'fwupd daemon is not running'
            result['status'] = 'warning'
        
        # Get device list
        stdout, stderr, rc = self._run_command(['fwupdmgr', 'get-devices'])
        if rc == 0 and stdout:
            result['devices_raw'] = stdout
            
            # Parse devices (simplified parsing)
            current_device = {}
            lines = stdout.split('\n')
            
            for line in lines:
                line_stripped = line.strip()
                
                if '│' in line:
                    # Device header
                    if '●' in line or '○' in line:
                        if current_device:
                            result['devices'].append(current_device)
                        
                        # Extract device name
                        name_parts = line.split('│')
                        for part in name_parts:
                            if '●' in part or '○' in part:
                                current_device = {
                                    'name': part.replace('●', '').replace('○', '').strip(),
                                    'status': 'updateable' if '●' in part else 'not_updateable',
                                    'components': []
                                }
                                break
                    elif current_device and ': ' in line_stripped:
                        # Component info
                        key, value = line_stripped.split(':', 1)
                        current_device.setdefault('components', []).append({
                            'key': key.strip(),
                            'value': value.strip()
                        })
            
            if current_device:
                result['devices'].append(current_device)
            
            # Count updateable devices
            result['updateable_devices'] = sum(
                1 for d in result['devices'] 
                if d.get('status') == 'updateable'
            )
            
        # Check for available updates
        stdout, stderr, rc = self._run_command(['fwupdmgr', 'get-updates'], timeout=120)
        if rc == 0:
            if 'No updates available' in stdout or not stdout.strip():
                result['updates_available'] = 0
            else:
                # Count update sections
                result['updates_raw'] = stdout
                result['updates_available'] = stdout.count('╞') + stdout.count('│')
                
                if result['updates_available'] > 0:
                    result['status'] = 'warning'
                    result['warning'] = f"{result['updates_available']} firmware updates available"
        else:
            # Daemon might not be running or no internet
            if 'failed' in stderr.lower() or 'error' in stderr.lower():
                result['update_check_error'] = stderr.strip()[:200]
        
        return result
    
    def _check_secure_boot(self) -> Dict[str, Any]:
        """Check Secure Boot status."""
        result = {
            'status': 'unknown',
            'enabled': False,
            'mode': 'unknown'
        }
        
        # Check via mokutil
        stdout, _, rc = self._run_command(['mokutil', '--sb-state'])
        if rc == 0:
            if 'SecureBoot enabled' in stdout:
                result['enabled'] = True
                result['mode'] = 'enabled'
                result['status'] = 'passed'
            elif 'SecureBoot disabled' in stdout:
                result['enabled'] = False
                result['mode'] = 'disabled'
                result['status'] = 'passed'
                result['info'] = 'Secure Boot is disabled'
        
        # Alternative: check via efivarfs
        if result['status'] == 'unknown' and os.path.exists('/sys/firmware/efi/efivars'):
            try:
                secure_boot_var = '/sys/firmware/efi/efivars/SecureBoot-*/data'
                import glob
                secure_boot_files = glob.glob(secure_boot_var)
                
                if secure_boot_files:
                    with open(secure_boot_files[0], 'rb') as f:
                        data = f.read()
                        # Last byte indicates status (0x01 = enabled, 0x00 = disabled)
                        if len(data) >= 5:
                            status_byte = data[-1]
                            result['enabled'] = (status_byte == 1)
                            result['mode'] = 'enabled' if status_byte == 1 else 'disabled'
                            result['status'] = 'passed'
            except Exception as e:
                self.logger.debug(f"Could not read Secure Boot status: {e}")
        
        return result
    
    def execute(self) -> StepResult:
        """Execute firmware checks."""
        errors = []
        warnings = []
        
        self.logger.info("Starting firmware checks...")
        
        try:
            # Run all checks
            self.firmware_results['bios'] = self._detect_bios_info()
            self.firmware_results['fwupd'] = self._check_fwupd()
            self.firmware_results['secure_boot'] = self._check_secure_boot()
            
            # Aggregate results
            failed_checks = []
            warning_checks = []
            
            for check_name, check_result in self.firmware_results.items():
                if check_result.get('status') == 'failed':
                    failed_checks.append(check_name)
                elif check_result.get('status') == 'warning':
                    warning_checks.append(check_name)
            
            # Build summary
            summary = {
                'bios_info': self.firmware_results['bios'],
                'fwupd': self.firmware_results['fwupd'],
                'secure_boot': self.firmware_results['secure_boot'],
            }
            
            # Add human-readable summary
            bios = self.firmware_results['bios']
            summary['summary'] = {
                'firmware_type': bios.get('firmware_type', 'unknown'),
                'bios_vendor': bios.get('vendor', 'unknown'),
                'bios_version': bios.get('version', 'unknown'),
                'fwupd_available': self.firmware_results['fwupd'].get('available', False),
                'updates_pending': self.firmware_results['fwupd'].get('updates_available', 0),
                'secure_boot_enabled': self.firmware_results['secure_boot'].get('enabled', False),
            }
            
            # Determine overall status
            if failed_checks:
                status = TestStatus.FAILED
                message = f"Firmware checks failed: {', '.join(failed_checks)}"
                errors.extend([f"Check '{c}' failed" for c in failed_checks])
            elif warning_checks:
                status = TestStatus.WARNING
                message = f"Firmware checks completed with warnings: {', '.join(warning_checks)}"
                warnings.extend([
                    check_result.get('warning', f"Check '{c}' has issues")
                    for c, check_result in self.firmware_results.items()
                    if check_result.get('warning')
                ])
            else:
                status = TestStatus.PASSED
                message = "All firmware checks passed"
            
            return StepResult(
                step_name=self.name,
                status=status,
                message=message,
                details=summary,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            self.logger.exception(f"Firmware checks failed: {e}")
            return StepResult(
                step_name=self.name,
                status=TestStatus.ERROR,
                message=f"Firmware checks failed: {str(e)}",
                errors=[str(e)]
            )
