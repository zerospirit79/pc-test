"""Step 4: Performance Benchmarks."""

import time
import subprocess
import os
import tempfile
from typing import List, Dict, Any, Optional
import multiprocessing

from hw_test.types import StepResult, TestStatus, HardwareInfo, TestConfig
from hw_test.steps.base import BaseHWStep


class PerformanceStep(BaseHWStep):
    """Run performance benchmarks for CPU, memory, disk, and context switching."""
    
    name = "Performance Benchmarks"
    description = "Measure CPU, memory, disk I/O, and context switching performance"
    required_privileges = False
    
    def __init__(self, config: TestConfig, hardware_info: Optional[HardwareInfo] = None):
        super().__init__(config, hardware_info)
        self.benchmark_results: Dict[str, Any] = {}
    
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
    
    def _benchmark_cpu(self) -> Dict[str, Any]:
        """Simple CPU benchmark using prime calculation."""
        result = {'status': 'passed', 'scores': []}
        
        try:
            # Simple CPU-bound task: calculate primes
            def find_primes(n: int) -> int:
                count = 0
                for num in range(2, n):
                    is_prime = True
                    for i in range(2, int(num ** 0.5) + 1):
                        if num % i == 0:
                            is_prime = False
                            break
                    if is_prime:
                        count += 1
                return count
            
            scores = []
            iterations = 3
            
            for i in range(iterations):
                start = time.perf_counter()
                primes_found = find_primes(5000)  # Find primes up to 5000
                elapsed = time.perf_counter() - start
                score = primes_found / elapsed if elapsed > 0 else 0
                scores.append({
                    'iteration': i + 1,
                    'primes_found': primes_found,
                    'time_seconds': round(elapsed, 4),
                    'score': round(score, 2)
                })
            
            if scores:
                avg_score = sum(s['score'] for s in scores) / len(scores)
                avg_time = sum(s['time_seconds'] for s in scores) / len(scores)
                
                result['iterations'] = scores
                result['avg_score'] = round(avg_score, 2)
                result['avg_time_seconds'] = round(avg_time, 4)
                result['cpu_cores_used'] = 1
                
                # Multi-core test if available
                cpu_count = multiprocessing.cpu_count()
                if cpu_count > 1:
                    result['multi_core_available'] = True
                    result['cpu_count'] = cpu_count
                    
                    # Run parallel test
                    start = time.perf_counter()
                    with multiprocessing.Pool(cpu_count) as pool:
                        results = pool.map(find_primes, [5000] * cpu_count)
                    multi_elapsed = time.perf_counter() - start
                    
                    result['multi_core_time_seconds'] = round(multi_elapsed, 4)
                    result['multi_core_score'] = round(sum(results) / multi_elapsed, 2)
                    
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
        
        return result
    
    def _benchmark_memory(self) -> Dict[str, Any]:
        """Memory bandwidth benchmark."""
        result = {'status': 'passed', 'read_speed_mbs': 0, 'write_speed_mbs': 0}
        
        try:
            import psutil
            
            # Get available memory
            mem = psutil.virtual_memory()
            test_size_mb = min(256, mem.available // (1024 * 1024) // 4)
            test_size_bytes = test_size_mb * 1024 * 1024
            
            if test_size_bytes < 1024 * 1024:  # At least 1MB
                test_size_bytes = 1024 * 1024
            
            # Write test
            data = bytearray(test_size_bytes)
            for i in range(0, len(data), 4096):
                data[i:i+4] = b'\x00\x01\x02\x03'
            
            start = time.perf_counter()
            _ = bytes(data)  # Force copy
            write_elapsed = time.perf_counter() - start
            write_speed = (test_size_bytes / (1024 * 1024)) / write_elapsed if write_elapsed > 0 else 0
            
            # Read test (simulate)
            start = time.perf_counter()
            checksum = sum(data)
            read_elapsed = time.perf_counter() - start
            read_speed = (test_size_bytes / (1024 * 1024)) / read_elapsed if read_elapsed > 0 else 0
            
            result['test_size_mb'] = test_size_mb
            result['write_speed_mbs'] = round(write_speed, 2)
            result['read_speed_mbs'] = round(read_speed, 2)
            result['checksum'] = checksum
            
            # Check against thresholds
            if write_speed < 1000:  # Less than 1GB/s is concerning for modern RAM
                result['status'] = 'warning'
                
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
        
        return result
    
    def _benchmark_disk(self) -> Dict[str, Any]:
        """Disk I/O benchmark."""
        result = {'status': 'passed', 'results': []}
        
        try:
            # Find a suitable location for testing
            test_locations = ['/tmp', '/var/tmp']
            test_path = None
            
            for loc in test_locations:
                if os.path.exists(loc) and os.access(loc, os.W_OK):
                    test_path = loc
                    break
            
            if not test_path:
                result['status'] = 'skipped'
                result['error'] = 'No writable test location found'
                return result
            
            # Create test file
            test_file = os.path.join(test_path, f'hw_test_benchmark_{os.getpid()}.dat')
            test_size_mb = 64
            test_size_bytes = test_size_mb * 1024 * 1024
            
            # Sequential write
            chunk_size = 1024 * 1024  # 1MB chunks
            data = b'x' * chunk_size
            
            start = time.perf_counter()
            with open(test_file, 'wb') as f:
                for _ in range(test_size_mb):
                    f.write(data)
            write_elapsed = time.perf_counter() - start
            write_speed = test_size_mb / write_elapsed if write_elapsed > 0 else 0
            
            # Flush caches
            try:
                subprocess.run(['sync'], capture_output=True, timeout=10)
            except Exception:
                pass
            
            # Sequential read
            start = time.perf_counter()
            with open(test_file, 'rb') as f:
                total_read = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    total_read += len(chunk)
            read_elapsed = time.perf_counter() - start
            read_speed = (total_read / (1024 * 1024)) / read_elapsed if read_elapsed > 0 else 0
            
            # Cleanup
            try:
                os.unlink(test_file)
            except Exception:
                pass
            
            result['test_file'] = test_file
            result['test_size_mb'] = test_size_mb
            result['sequential_write_mbs'] = round(write_speed, 2)
            result['sequential_read_mbs'] = round(read_speed, 2)
            result['write_time_seconds'] = round(write_elapsed, 3)
            result['read_time_seconds'] = round(read_elapsed, 3)
            
            # Check thresholds
            if write_speed < 10:  # Less than 10 MB/s is very slow
                result['status'] = 'warning'
            elif write_speed < 1:
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
    
    def _benchmark_context_switch(self) -> Dict[str, Any]:
        """Context switching benchmark."""
        result = {'status': 'passed'}
        
        try:
            # Use simple process creation as proxy for context switch cost
            iterations = 100
            
            start = time.perf_counter()
            for _ in range(iterations):
                proc = subprocess.run(['true'], capture_output=True, timeout=5)
                if proc.returncode != 0:
                    break
            elapsed = time.perf_counter() - start
            
            avg_time_ms = (elapsed / iterations) * 1000 if iterations > 0 else 0
            
            result['iterations'] = iterations
            result['total_time_seconds'] = round(elapsed, 4)
            result['avg_time_per_switch_ms'] = round(avg_time_ms, 4)
            result['switches_per_second'] = round(iterations / elapsed, 2) if elapsed > 0 else 0
            
            # Thresholds
            if avg_time_ms > 10:  # More than 10ms per switch is slow
                result['status'] = 'warning'
            elif avg_time_ms > 50:
                result['status'] = 'failed'
                
        except Exception as e:
            result['status'] = 'warning'
            result['error'] = str(e)
        
        return result
    
    def execute(self) -> StepResult:
        """Execute performance benchmarks."""
        errors = []
        warnings = []
        
        self.logger.info("Starting performance benchmarks...")
        
        try:
            # Run all benchmarks
            self.benchmark_results['cpu'] = self._benchmark_cpu()
            self.benchmark_results['memory'] = self._benchmark_memory()
            self.benchmark_results['disk'] = self._benchmark_disk()
            self.benchmark_results['context_switch'] = self._benchmark_context_switch()
            
            # Aggregate results
            failed_benchmarks = []
            warning_benchmarks = []
            
            for bench_name, bench_result in self.benchmark_results.items():
                if bench_result.get('status') == 'failed':
                    failed_benchmarks.append(bench_name)
                elif bench_result.get('status') == 'warning':
                    warning_benchmarks.append(bench_name)
            
            # Build summary
            summary = {
                'cpu': self.benchmark_results['cpu'],
                'memory': self.benchmark_results['memory'],
                'disk': self.benchmark_results['disk'],
                'context_switch': self.benchmark_results['context_switch'],
            }
            
            # Determine overall status
            if failed_benchmarks:
                status = TestStatus.FAILED
                message = f"Performance benchmarks failed: {', '.join(failed_benchmarks)}"
                errors.extend([f"Benchmark '{b}' failed" for b in failed_benchmarks])
            elif warning_benchmarks:
                status = TestStatus.WARNING
                message = f"Performance benchmarks completed with warnings: {', '.join(warning_benchmarks)}"
                warnings.extend([f"Benchmark '{b}' shows poor performance" for b in warning_benchmarks])
            else:
                status = TestStatus.PASSED
                message = "All performance benchmarks passed"
            
            return StepResult(
                step_name=self.name,
                status=status,
                message=message,
                details=summary,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            self.logger.exception(f"Performance benchmarks failed: {e}")
            return StepResult(
                step_name=self.name,
                status=TestStatus.ERROR,
                message=f"Performance benchmarks failed: {str(e)}",
                errors=[str(e)]
            )
