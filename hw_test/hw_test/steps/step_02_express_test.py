"""Step 2: Express Tests."""

import time
import subprocess
import tempfile
import os
from typing import List, Dict, Any, Optional

from hw_test.types import StepResult, TestStatus, HardwareInfo, TestConfig
from hw_test.steps.base import BaseHWStep


class ExpressTestStep(BaseHWStep):
    """Run quick express tests to verify basic system functionality."""
    
    name = "Express Tests"
    description = "Quick tests for boot time, responsiveness, I/O, and network connectivity"
    required_privileges = False
    
    def __init__(self, config: TestConfig, hardware_info: Optional[HardwareInfo] = None):
        super().__init__(config, hardware_info)
        self.test_results: Dict[str, Any] = {}
    
    def _run_command(self, cmd: List[str], timeout: int = 30) -> tuple[str, str, int]:
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
    
    def _test_boot_time(self) -> Dict[str, Any]:
        """Check system boot time."""
        result = {'status': 'skipped', 'boot_time_sec': None}
        
        try:
            stdout, _, rc = self._run_command(['systemctl', 'show', '-p', 'UserspaceTimestamp', 'Manager'])
            if rc == 0 and '=' in stdout:
                # Parse userspace timestamp
                pass
            
            # Alternative: use systemd-analyze
            stdout, _, rc = self._run_command(['systemd-analyze'])
            if rc == 0:
                for line in stdout.split('\n'):
                    if 'startup' in line.lower() or 'kernel' in line.lower():
                        result['raw_output'] = line.strip()
                        # Try to extract numeric values
                        import re
                        matches = re.findall(r'([\d.]+)\s*(?:ms|s|min)', line, re.IGNORECASE)
                        if matches:
                            result['boot_time_sec'] = sum(float(m) for m in matches[:2])
                            result['status'] = 'passed'
                            break
                
                if result.get('status') != 'passed' and stdout.strip():
                    result['status'] = 'passed'
                    result['raw_output'] = stdout.strip()[:200]
                    
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
        
        return result
    
    def _test_responsiveness(self) -> Dict[str, Any]:
        """Test basic system responsiveness."""
        result = {'status': 'passed', 'latency_ms': []}
        
        try:
            latencies = []
            
            # Measure fork/exec latency
            for i in range(5):
                start = time.perf_counter()
                proc = subprocess.run(['true'], capture_output=True, timeout=5)
                elapsed = (time.perf_counter() - start) * 1000  # ms
                if proc.returncode == 0:
                    latencies.append(elapsed)
            
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                max_latency = max(latencies)
                result['avg_latency_ms'] = round(avg_latency, 2)
                result['max_latency_ms'] = round(max_latency, 2)
                
                if avg_latency > 100:  # More than 100ms is concerning
                    result['status'] = 'warning'
                elif avg_latency > 500:
                    result['status'] = 'failed'
                    
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
        
        return result
    
    def _test_io_performance(self) -> Dict[str, Any]:
        """Quick I/O performance test."""
        result = {'status': 'passed', 'write_speed_mbs': None, 'read_speed_mbs': None}
        
        try:
            with tempfile.NamedTemporaryFile(delete=False) as f:
                test_file = f.name
            
            # Write test (1MB)
            data = b'x' * (1024 * 1024)  # 1MB
            start = time.perf_counter()
            with open(test_file, 'wb') as f:
                f.write(data)
            write_time = time.perf_counter() - start
            write_speed = (1 / write_time) if write_time > 0 else 0
            result['write_speed_mbs'] = round(write_speed, 2)
            
            # Read test
            start = time.perf_counter()
            with open(test_file, 'rb') as f:
                _ = f.read()
            read_time = time.perf_counter() - start
            read_speed = (1 / read_time) if read_time > 0 else 0
            result['read_speed_mbs'] = round(read_speed, 2)
            
            # Cleanup
            os.unlink(test_file)
            
            # Check thresholds
            if write_speed < 1:  # Less than 1 MB/s is very slow
                result['status'] = 'warning'
            elif write_speed < 0.1:
                result['status'] = 'failed'
                
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
            if 'test_file' in locals():
                try:
                    os.unlink(test_file)
                except:
                    pass
        
        return result
    
    def _test_network_connectivity(self) -> Dict[str, Any]:
        """Test basic network connectivity."""
        result = {'status': 'passed', 'hosts_tested': []}
        
        hosts_to_test = [
            ('127.0.0.1', 'localhost'),
            ('8.8.8.8', 'google-dns'),
        ]
        
        for host_ip, host_name in hosts_to_test:
            host_result = {'ip': host_ip, 'name': host_name, 'reachable': False, 'time_ms': None}
            
            try:
                start = time.perf_counter()
                stdout, _, rc = self._run_command(
                    ['ping', '-c', '1', '-W', '2', host_ip],
                    timeout=5
                )
                elapsed = (time.perf_counter() - start) * 1000
                
                if rc == 0:
                    host_result['reachable'] = True
                    host_result['time_ms'] = round(elapsed, 2)
                    
                    # Extract ping time from output
                    import re
                    match = re.search(r'time=([\d.]+)\s*ms', stdout)
                    if match:
                        host_result['ping_time_ms'] = float(match.group(1))
                        
            except Exception as e:
                host_result['error'] = str(e)
            
            result['hosts_tested'].append(host_result)
        
        # Determine overall status
        reachable_count = sum(1 for h in result['hosts_tested'] if h['reachable'])
        if reachable_count == 0:
            result['status'] = 'failed'
        elif reachable_count < len(hosts_to_test):
            result['status'] = 'warning'
        
        result['reachable_hosts'] = reachable_count
        result['total_hosts'] = len(hosts_to_test)
        
        return result
    
    def _test_memory_basic(self) -> Dict[str, Any]:
        """Basic memory availability test."""
        result = {'status': 'passed'}
        
        try:
            import psutil
            mem = psutil.virtual_memory()
            
            result['total_mb'] = round(mem.total / (1024 * 1024), 2)
            result['available_mb'] = round(mem.available / (1024 * 1024), 2)
            result['used_percent'] = mem.percent
            
            if mem.percent > 95:
                result['status'] = 'warning'
            elif mem.percent > 99:
                result['status'] = 'failed'
                
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
        
        return result
    
    def execute(self) -> StepResult:
        """Execute express tests."""
        errors = []
        warnings = []
        
        self.logger.info("Starting express tests...")
        
        try:
            # Run all tests
            self.test_results['boot_time'] = self._test_boot_time()
            self.test_results['responsiveness'] = self._test_responsiveness()
            self.test_results['io_performance'] = self._test_io_performance()
            self.test_results['network'] = self._test_network_connectivity()
            self.test_results['memory'] = self._test_memory_basic()
            
            # Aggregate results
            failed_tests = []
            warning_tests = []
            
            for test_name, test_result in self.test_results.items():
                if test_result.get('status') == 'failed':
                    failed_tests.append(test_name)
                elif test_result.get('status') == 'warning':
                    warning_tests.append(test_name)
            
            # Build summary
            summary = {
                'tests_run': len(self.test_results),
                'boot_time': self.test_results['boot_time'],
                'responsiveness': self.test_results['responsiveness'],
                'io_performance': self.test_results['io_performance'],
                'network': self.test_results['network'],
                'memory': self.test_results['memory'],
            }
            
            # Determine overall status
            if failed_tests:
                status = TestStatus.FAILED
                message = f"Express tests failed: {', '.join(failed_tests)}"
                errors.extend([f"Test '{t}' failed" for t in failed_tests])
            elif warning_tests:
                status = TestStatus.WARNING
                message = f"Express tests completed with warnings: {', '.join(warning_tests)}"
                warnings.extend([f"Test '{t}' has issues" for t in warning_tests])
            else:
                status = TestStatus.PASSED
                message = "All express tests passed"
            
            return StepResult(
                step_name=self.name,
                status=status,
                message=message,
                details=summary,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            self.logger.exception(f"Express tests failed: {e}")
            return StepResult(
                step_name=self.name,
                status=TestStatus.ERROR,
                message=f"Express tests failed: {str(e)}",
                errors=[str(e)]
            )
