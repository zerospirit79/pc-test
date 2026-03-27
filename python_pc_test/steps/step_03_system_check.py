"""
Step 03: System Installation/Update Check
Verifies system installation status and available updates.
"""

import subprocess
import os
from typing import Dict, Any, List
from .base import BaseStep, StepResult, StepStatus


class SystemCheckStep(BaseStep):
    """Checks system installation and update status."""
    
    def execute(self) -> StepResult:
        """Execute system check."""
        self.logger.info("Starting system installation/update check...")
        
        results = {
            "os_info": self._get_os_info(),
            "package_manager": self._check_package_manager(),
            "updates_available": self._check_updates(),
            "system_integrity": self._check_system_integrity(),
            "disk_usage": self._check_disk_usage(),
        }
        
        errors = []
        warnings = []
        
        # Analyze results
        if not results["os_info"].get("name"):
            errors.append("Could not determine OS information")
        
        if results["disk_usage"].get("root_usage_percent", 0) > 90:
            errors.append("Root filesystem is over 90% full")
        elif results["disk_usage"].get("root_usage_percent", 0) > 80:
            warnings.append("Root filesystem is over 80% full")
        
        if results["updates_available"].get("count", 0) > 50:
            warnings.append("Large number of updates available (>50)")
        
        status = StepStatus.FAILED if errors else (StepStatus.WARNING if warnings else StepStatus.PASSED)
        
        return StepResult(
            step_name=self.name,
            status=status,
            message="System check completed",
            details=results,
            errors=errors,
            warnings=warnings
        )
    
    def _get_os_info(self) -> Dict[str, Any]:
        """Get operating system information."""
        os_info = {}
        
        try:
            # Try reading /etc/os-release
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os_info[key.lower()] = value.strip('"\'')
            
            # Get kernel version
            result = subprocess.run(
                ['uname', '-r'],
                capture_output=True, text=True, timeout=10
            )
            os_info["kernel"] = result.stdout.strip()
            
            # Get architecture
            result = subprocess.run(
                ['uname', '-m'],
                capture_output=True, text=True, timeout=10
            )
            os_info["architecture"] = result.stdout.strip()
            
        except Exception as e:
            self.logger.error(f"OS info detection failed: {e}")
            os_info["error"] = str(e)
        
        return os_info
    
    def _check_package_manager(self) -> Dict[str, Any]:
        """Check which package manager is available."""
        managers = {
            "apt": False,
            "dnf": False,
            "yum": False,
            "zypper": False,
            "pacman": False
        }
        
        for manager in managers.keys():
            result = subprocess.run(
                ['which', manager],
                capture_output=True, timeout=10
            )
            managers[manager] = (result.returncode == 0)
        
        # Detect active manager
        active = None
        if managers["apt"]:
            active = "apt"
        elif managers["dnf"]:
            active = "dnf"
        elif managers["yum"]:
            active = "yum"
        elif managers["zypper"]:
            active = "zypper"
        elif managers["pacman"]:
            active = "pacman"
        
        return {
            "available": managers,
            "active": active
        }
    
    def _check_updates(self) -> Dict[str, Any]:
        """Check for available updates."""
        update_info = {"count": 0, "packages": [], "security_updates": 0}
        
        try:
            # Check for apt-based systems
            result = subprocess.run(
                ['which', 'apt'],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                # Update package list (non-interactive)
                subprocess.run(
                    ['apt', 'update'],
                    capture_output=True, timeout=60
                )
                
                # Check upgradable packages
                result = subprocess.run(
                    ['apt', 'list', '--upgradable'],
                    capture_output=True, text=True, timeout=60
                )
                
                packages = []
                for line in result.stdout.split('\n')[1:]:  # Skip header
                    if line.strip():
                        parts = line.split('/')
                        if parts:
                            packages.append(parts[0])
                
                update_info["count"] = len(packages)
                update_info["packages"] = packages[:20]  # Limit to first 20
                
                # Check security updates
                result = subprocess.run(
                    ['apt', 'list', '--upgradable', '|', 'grep', 'security'],
                    shell=True, capture_output=True, text=True, timeout=60
                )
                update_info["security_updates"] = len(result.stdout.strip().split('\n'))
            
            # Check for dnf-based systems
            elif subprocess.run(['which', 'dnf'], capture_output=True, timeout=10).returncode == 0:
                result = subprocess.run(
                    ['dnf', 'check-update', '--quiet'],
                    capture_output=True, text=True, timeout=120
                )
                
                if result.returncode == 100:  # DNF returns 100 when updates are available
                    packages = [line.split()[0] for line in result.stdout.split('\n') if line.strip() and '.' in line]
                    update_info["count"] = len(packages)
                    update_info["packages"] = packages[:20]
        
        except Exception as e:
            self.logger.error(f"Update check failed: {e}")
            update_info["error"] = str(e)
        
        return update_info
    
    def _check_system_integrity(self) -> Dict[str, Any]:
        """Check system integrity."""
        integrity_info = {"status": "unknown", "checks": []}
        
        try:
            # Check if rpm database is valid (for RPM-based systems)
            result = subprocess.run(
                ['rpm', '--verify', '--all'],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                integrity_info["checks"].append({"name": "rpm_database", "status": "passed"})
            else:
                # Count verification failures
                failed_count = len([l for l in result.stdout.split('\n') if l.strip()])
                integrity_info["checks"].append({
                    "name": "rpm_database",
                    "status": "warning" if failed_count < 10 else "failed",
                    "details": f"{failed_count} files with verification issues"
                })
            
            # Check filesystem mounts
            result = subprocess.run(
                ['mount'],
                capture_output=True, text=True, timeout=10
            )
            mounts = result.stdout.split('\n')
            integrity_info["checks"].append({
                "name": "filesystem_mounts",
                "status": "passed",
                "details": f"{len([m for m in mounts if m.strip()])} mounts active"
            })
            
            integrity_info["status"] = "passed" if all(c.get("status") == "passed" for c in integrity_info["checks"]) else "warning"
            
        except Exception as e:
            self.logger.error(f"System integrity check failed: {e}")
            integrity_info["error"] = str(e)
            integrity_info["status"] = "unknown"
        
        return integrity_info
    
    def _check_disk_usage(self) -> Dict[str, Any]:
        """Check disk usage."""
        disk_usage = {"partitions": [], "root_usage_percent": 0}
        
        try:
            result = subprocess.run(
                ['df', '-h'],
                capture_output=True, text=True, timeout=10
            )
            
            for line in result.stdout.split('\n')[1:]:  # Skip header
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 5:
                        partition = {
                            "filesystem": parts[0],
                            "size": parts[1],
                            "used": parts[2],
                            "available": parts[3],
                            "use_percent": int(parts[4].replace('%', '')),
                            "mountpoint": parts[5]
                        }
                        disk_usage["partitions"].append(partition)
                        
                        if parts[5] == '/':
                            disk_usage["root_usage_percent"] = partition["use_percent"]
        
        except Exception as e:
            self.logger.error(f"Disk usage check failed: {e}")
            disk_usage["error"] = str(e)
        
        return disk_usage
