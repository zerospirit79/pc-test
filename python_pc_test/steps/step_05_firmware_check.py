"""
Step 05: Firmware/BIOS Update Check
Checks for firmware and BIOS updates availability.
"""

import subprocess
import os
from typing import Dict, Any, List
from .base import BaseStep, StepResult, StepStatus


class FirmwareCheckStep(BaseStep):
    """Checks for firmware and BIOS updates."""
    
    def execute(self) -> StepResult:
        """Execute firmware check."""
        self.logger.info("Starting firmware/BIOS check...")
        
        results = {
            "bios_info": self._get_bios_info(),
            "fwupd_available": self._check_fwupd(),
            "firmware_updates": self._check_firmware_updates(),
            "dmidecode_info": self._get_dmidecode_info(),
        }
        
        errors = []
        warnings = []
        
        # Analyze results
        if not results["bios_info"].get("version"):
            warnings.append("Could not determine BIOS version")
        
        if results["fwupd_available"].get("daemon_active", False):
            if results["firmware_updates"].get("updates_available", 0) > 0:
                warnings.append("Firmware updates available")
        
        status = StepStatus.FAILED if errors else (StepStatus.WARNING if warnings else StepStatus.PASSED)
        
        return StepResult(
            step_name=self.name,
            status=status,
            message="Firmware check completed",
            details=results,
            errors=errors,
            warnings=warnings
        )
    
    def _get_bios_info(self) -> Dict[str, Any]:
        """Get BIOS information from /sys/class/dmi."""
        bios_info = {}
        
        try:
            dmi_fields = {
                "bios_vendor": "/sys/class/dmi/id/bios_vendor",
                "bios_version": "/sys/class/dmi/id/bios_version",
                "bios_date": "/sys/class/dmi/id/bios_date",
                "board_name": "/sys/class/dmi/id/board_name",
                "board_vendor": "/sys/class/dmi/id/board_vendor",
                "product_name": "/sys/class/dmi/id/product_name",
                "product_family": "/sys/class/dmi/id/product_family",
                "chassis_type": "/sys/class/dmi/id/chassis_type",
            }
            
            for key, path in dmi_fields.items():
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        bios_info[key] = f.read().strip()
                else:
                    bios_info[key] = None
            
        except Exception as e:
            self.logger.error(f"BIOS info detection failed: {e}")
            bios_info["error"] = str(e)
        
        return bios_info
    
    def _check_fwupd(self) -> Dict[str, Any]:
        """Check if fwupd is available and active."""
        fwupd_info = {
            "installed": False,
            "daemon_active": False,
            "version": None
        }
        
        try:
            # Check if fwupdmgr is installed
            result = subprocess.run(
                ['which', 'fwupdmgr'],
                capture_output=True, timeout=10
            )
            fwupd_info["installed"] = (result.returncode == 0)
            
            if fwupd_info["installed"]:
                # Get version
                result = subprocess.run(
                    ['fwupdmgr', '--version'],
                    capture_output=True, text=True, timeout=10
                )
                if result.stdout:
                    lines = result.stdout.split('\n')
                    if lines:
                        fwupd_info["version"] = lines[0].strip()
                
                # Check daemon status
                result = subprocess.run(
                    ['systemctl', 'is-active', 'fwupd.service'],
                    capture_output=True, text=True, timeout=10
                )
                fwupd_info["daemon_active"] = (result.stdout.strip() == "active")
        
        except Exception as e:
            self.logger.error(f"fwupd check failed: {e}")
            fwupd_info["error"] = str(e)
        
        return fwupd_info
    
    def _check_firmware_updates(self) -> Dict[str, Any]:
        """Check for available firmware updates using fwupd."""
        update_info = {
            "updates_available": 0,
            "devices": [],
            "can_update": False
        }
        
        try:
            # Check if fwupdmgr is available
            result = subprocess.run(
                ['which', 'fwupdmgr'],
                capture_output=True, timeout=10
            )
            if result.returncode != 0:
                return update_info
            
            # Refresh metadata
            subprocess.run(
                ['fwupdmgr', 'refresh', '--force'],
                capture_output=True, timeout=60
            )
            
            # Get devices
            result = subprocess.run(
                ['fwupdmgr', 'get-devices'],
                capture_output=True, text=True, timeout=30
            )
            
            devices = []
            current_device = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('│') or line.startswith('├') or line.startswith('└'):
                    # Parse device info
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower().replace(' ', '_')
                        value = value.strip()
                        
                        if key == 'name':
                            if current_device:
                                devices.append(current_device)
                            current_device = {'name': value}
                        elif current_device:
                            current_device[key] = value
            
            if current_device:
                devices.append(current_device)
            
            update_info["devices"] = devices
            
            # Get updates
            result = subprocess.run(
                ['fwupdmgr', 'get-updates'],
                capture_output=True, text=True, timeout=60
            )
            
            # Count available updates
            update_lines = [l for l in result.stdout.split('\n') if 'Upgradable' in l or 'available' in l.lower()]
            update_info["updates_available"] = len(update_lines)
            update_info["can_update"] = (update_info["updates_available"] > 0)
            update_info["raw_output"] = result.stdout[:1000]  # Limit output size
        
        except Exception as e:
            self.logger.error(f"Firmware update check failed: {e}")
            update_info["error"] = str(e)
        
        return update_info
    
    def _get_dmidecode_info(self) -> Dict[str, Any]:
        """Get detailed system information using dmidecode."""
        dmi_info = {
            "available": False,
            "bios": {},
            "system": {},
            "memory": {}
        }
        
        try:
            # Check if dmidecode is available
            result = subprocess.run(
                ['which', 'dmidecode'],
                capture_output=True, timeout=10
            )
            if result.returncode != 0:
                return dmi_info
            
            dmi_info["available"] = True
            
            # Get BIOS information
            result = subprocess.run(
                ['dmidecode', '-t', 'bios'],
                capture_output=True, text=True, timeout=30
            )
            dmi_info["bios"]["raw"] = result.stdout[:500]  # Limit size
            
            # Get system information
            result = subprocess.run(
                ['dmidecode', '-t', 'system'],
                capture_output=True, text=True, timeout=30
            )
            dmi_info["system"]["raw"] = result.stdout[:500]
            
            # Get memory information
            result = subprocess.run(
                ['dmidecode', '-t', 'memory'],
                capture_output=True, text=True, timeout=30
            )
            dmi_info["memory"]["raw"] = result.stdout[:500]
            
            # Parse manufacturer
            import re
            manufacturer_match = re.search(r'Manufacturer:\s*(.+)', result.stdout)
            if manufacturer_match:
                dmi_info["system"]["manufacturer"] = manufacturer_match.group(1).strip()
            
            product_match = re.search(r'Product Name:\s*(.+)', result.stdout)
            if product_match:
                dmi_info["system"]["product"] = product_match.group(1).strip()
        
        except Exception as e:
            self.logger.error(f"dmidecode failed: {e}")
            dmi_info["error"] = str(e)
        
        return dmi_info
