"""
Step 02: Express Testing
Performs quick functional tests of critical system components.
"""

import subprocess
import time
from typing import Dict, Any, List
from .base import BaseStep, StepResult, StepStatus


class ExpressTestStep(BaseStep):
    """Performs express testing of critical components."""
    
    def execute(self) -> StepResult:
        """Execute express tests."""
        self.logger.info("Starting express testing...")
        
        results = {
            "boot_time": self._check_boot_time(),
            "system_responsiveness": self._check_system_responsiveness(),
            "basic_io": self._check_basic_io(),
            "network_connectivity": self._check_network_connectivity(),
        }
        
        errors = []
        warnings = []
        
        # Analyze results
        if results["boot_time"].get("boot_seconds", 0) > 120:
            warnings.append("Boot time exceeds 2 minutes")
        
        if not results["network_connectivity"].get("reachable", False):
            errors.append("Network connectivity test failed")
        
        if results["basic_io"].get("write_speed_mb_s", 0) < 10:
            warnings.append("Low disk write speed detected")
        
        status = StepStatus.FAILED if errors else (StepStatus.WARNING if warnings else StepStatus.PASSED)
        
        return StepResult(
            step_name=self.name,
            status=status,
            message="Express testing completed",
            details=results,
            errors=errors,
            warnings=warnings
        )
    
    def _check_boot_time(self) -> Dict[str, Any]:
        """Check system boot time."""
        try:
            result = subprocess.run(
                ['systemd-analyze', 'blame'],
                capture_output=True, text=True, timeout=30
            )
            
            # Get total boot time
            result_total = subprocess.run(
                ['systemd-analyze'],
                capture_output=True, text=True, timeout=30
            )
            
            boot_info = {"raw_output": result_total.stdout}
            
            # Parse startup time in userspace and kernel
            import re
            kernel_match = re.search(r'kernel\s+in\s+(\d+(?:\.\d+)?)', result_total.stdout)
            userspace_match = re.search(r'userspace\s+in\s+(\d+(?:\.\d+)?)', result_total.stdout)
            
            if kernel_match:
                boot_info["kernel_seconds"] = float(kernel_match.group(1))
            if userspace_match:
                boot_info["userspace_seconds"] = float(userspace_match.group(1))
            
            boot_info["boot_seconds"] = boot_info.get("kernel_seconds", 0) + boot_info.get("userspace_seconds", 0)
            
            return boot_info
        except Exception as e:
            self.logger.error(f"Boot time check failed: {e}")
            return {"error": str(e)}
    
    def _check_system_responsiveness(self) -> Dict[str, Any]:
        """Check system responsiveness with simple commands."""
        start = time.time()
        
        try:
            # Test command execution latency
            for _ in range(5):
                subprocess.run(['echo', 'test'], capture_output=True, timeout=5)
            
            avg_latency = (time.time() - start) / 5
            
            return {
                "avg_command_latency_ms": round(avg_latency * 1000, 2),
                "status": "good" if avg_latency < 0.1 else "slow"
            }
        except Exception as e:
            self.logger.error(f"Responsiveness check failed: {e}")
            return {"error": str(e)}
    
    def _check_basic_io(self) -> Dict[str, Any]:
        """Perform basic I/O performance test."""
        try:
            import tempfile
            import os
            
            # Create a temporary file for testing
            with tempfile.NamedTemporaryFile(delete=False) as f:
                temp_path = f.name
                
                # Write test
                write_start = time.time()
                test_data = b'x' * 1024 * 1024  # 1MB
                for _ in range(10):  # Write 10MB
                    f.write(test_data)
                f.flush()
                os.fsync(f.fileno())
                write_time = time.time() - write_start
                
                # Read test
                f.seek(0)
                read_start = time.time()
                while f.read(1024 * 1024):  # Read in 1MB chunks
                    pass
                read_time = time.time() - read_start
            
            # Cleanup
            os.unlink(temp_path)
            
            write_speed = 10 / write_time  # MB/s
            read_speed = 10 / read_time  # MB/s
            
            return {
                "write_speed_mb_s": round(write_speed, 2),
                "read_speed_mb_s": round(read_speed, 2),
                "write_time_s": round(write_time, 2),
                "read_time_s": round(read_time, 2)
            }
        except Exception as e:
            self.logger.error(f"Basic I/O check failed: {e}")
            return {"error": str(e)}
    
    def _check_network_connectivity(self) -> Dict[str, Any]:
        """Check network connectivity."""
        connectivity_results = {
            "localhost": False,
            "gateway": False,
            "dns": False,
            "external": False
        }
        
        try:
            # Test localhost
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '2', '127.0.0.1'],
                capture_output=True, timeout=10
            )
            connectivity_results["localhost"] = (result.returncode == 0)
            
            # Try to get default gateway
            result = subprocess.run(
                ['ip', 'route', 'show', 'default'],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout:
                import re
                gateway_match = re.search(r'via\s+(\S+)', result.stdout)
                if gateway_match:
                    gateway_ip = gateway_match.group(1)
                    result = subprocess.run(
                        ['ping', '-c', '1', '-W', '2', gateway_ip],
                        capture_output=True, timeout=10
                    )
                    connectivity_results["gateway"] = (result.returncode == 0)
                    connectivity_results["gateway_ip"] = gateway_ip
            
            # Test DNS resolution
            result = subprocess.run(
                ['getent', 'hosts', 'localhost'],
                capture_output=True, timeout=10
            )
            connectivity_results["dns"] = (result.returncode == 0)
            
            # Test external connectivity (if network is available)
            result = subprocess.run(
                ['ip', 'route', 'get', '8.8.8.8'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and 'dev' in result.stdout:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '5', '8.8.8.8'],
                    capture_output=True, timeout=10
                )
                connectivity_results["external"] = (result.returncode == 0)
            
            connectivity_results["reachable"] = (
                connectivity_results["localhost"] and 
                (connectivity_results["gateway"] or connectivity_results["external"])
            )
            
        except Exception as e:
            self.logger.error(f"Network connectivity check failed: {e}")
            connectivity_results["error"] = str(e)
        
        return connectivity_results
