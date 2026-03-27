"""
Step 04: Performance Testing
Runs performance benchmarks for CPU, memory, and disk.
"""

import subprocess
import time
import os
from typing import Dict, Any, List
from .base import BaseStep, StepResult, StepStatus


class PerformanceTestStep(BaseStep):
    """Runs performance benchmarks."""
    
    def execute(self) -> StepResult:
        """Execute performance tests."""
        self.logger.info("Starting performance testing...")
        
        results = {
            "cpu_benchmark": self._run_cpu_benchmark(),
            "memory_bandwidth": self._run_memory_test(),
            "disk_performance": self._run_disk_benchmark(),
            "context_switching": self._test_context_switching(),
        }
        
        errors = []
        warnings = []
        
        # Analyze results
        if results["cpu_benchmark"].get("score", 0) < 1000:
            warnings.append("Low CPU benchmark score")
        
        if results["disk_performance"].get("sequential_read_mb_s", 0) < 50:
            warnings.append("Low disk sequential read speed")
        
        status = StepStatus.FAILED if errors else (StepStatus.WARNING if warnings else StepStatus.PASSED)
        
        return StepResult(
            step_name=self.name,
            status=status,
            message="Performance testing completed",
            details=results,
            errors=errors,
            warnings=warnings
        )
    
    def _run_cpu_benchmark(self) -> Dict[str, Any]:
        """Run CPU benchmark using simple calculations."""
        try:
            import math
            
            start_time = time.time()
            iterations = 10000000
            
            # Simple calculation benchmark
            result = 0.0
            for i in range(iterations):
                result += math.sin(i) * math.cos(i)
            
            elapsed = time.time() - start_time
            
            # Calculate a simple score (iterations per second)
            score = int(iterations / elapsed)
            
            return {
                "elapsed_seconds": round(elapsed, 2),
                "iterations": iterations,
                "score": score,
                "result": round(result, 6)
            }
        except Exception as e:
            self.logger.error(f"CPU benchmark failed: {e}")
            return {"error": str(e)}
    
    def _run_memory_test(self) -> Dict[str, Any]:
        """Test memory bandwidth."""
        try:
            import tempfile
            
            # Allocate and test memory
            size_mb = 256
            size_bytes = size_mb * 1024 * 1024
            
            # Write test
            start_time = time.time()
            data = bytearray(size_bytes)
            for i in range(0, size_bytes, 4096):
                data[i] = 0xFF
            write_time = time.time() - start_time
            
            # Read test
            start_time = time.time()
            checksum = 0
            for i in range(0, size_bytes, 4096):
                checksum += data[i]
            read_time = time.time() - start_time
            
            write_speed = size_mb / write_time  # MB/s
            read_speed = size_mb / read_time  # MB/s
            
            return {
                "test_size_mb": size_mb,
                "write_speed_mb_s": round(write_speed, 2),
                "read_speed_mb_s": round(read_speed, 2),
                "write_time_s": round(write_time, 3),
                "read_time_s": round(read_time, 3),
                "checksum": checksum
            }
        except Exception as e:
            self.logger.error(f"Memory test failed: {e}")
            return {"error": str(e)}
    
    def _run_disk_benchmark(self) -> Dict[str, Any]:
        """Run disk performance benchmark."""
        try:
            import tempfile
            
            # Create a temporary file for testing
            with tempfile.NamedTemporaryFile(delete=False) as f:
                temp_path = f.name
                
                # Sequential write test (100MB)
                write_size = 100 * 1024 * 1024  # 100MB
                chunk_size = 1024 * 1024  # 1MB chunks
                
                write_start = time.time()
                test_data = b'x' * chunk_size
                written = 0
                while written < write_size:
                    f.write(test_data)
                    written += chunk_size
                f.flush()
                os.fsync(f.fileno())
                write_time = time.time() - write_start
                
                # Sequential read test
                f.seek(0)
                read_start = time.time()
                read_bytes = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    read_bytes += len(chunk)
                read_time = time.time() - read_start
                
                # Random I/O test (small writes)
                f.seek(0)
                random_start = time.time()
                random_ops = 1000
                for i in range(random_ops):
                    pos = (i * 4096) % (write_size - 4096)
                    f.seek(pos)
                    f.write(b'y' * 4096)
                f.flush()
                os.fsync(f.fileno())
                random_time = time.time() - random_start
                
                # Cleanup
                os.unlink(temp_path)
                
                seq_write_speed = (write_size / 1024 / 1024) / write_time  # MB/s
                seq_read_speed = (read_bytes / 1024 / 1024) / read_time  # MB/s
                random_iops = random_ops / random_time  # IOPS
                
                return {
                    "sequential_write_mb_s": round(seq_write_speed, 2),
                    "sequential_read_mb_s": round(seq_read_speed, 2),
                    "random_iops": round(random_iops, 0),
                    "write_time_s": round(write_time, 2),
                    "read_time_s": round(read_time, 2),
                    "random_time_s": round(random_time, 2),
                    "test_size_mb": write_size / 1024 / 1024
                }
        except Exception as e:
            self.logger.error(f"Disk benchmark failed: {e}")
            return {"error": str(e)}
    
    def _test_context_switching(self) -> Dict[str, Any]:
        """Test context switching performance."""
        try:
            import multiprocessing
            
            # Create multiple processes to trigger context switches
            num_processes = min(multiprocessing.cpu_count(), 8)
            
            def worker(n):
                result = 0
                for i in range(100000):
                    result += i
                return result
            
            start_time = time.time()
            with multiprocessing.Pool(num_processes) as pool:
                results = pool.map(worker, range(num_processes))
            elapsed = time.time() - start_time
            
            return {
                "processes": num_processes,
                "elapsed_seconds": round(elapsed, 3),
                "total_operations": num_processes * 100000,
                "ops_per_second": int((num_processes * 100000) / elapsed) if elapsed > 0 else 0
            }
        except Exception as e:
            self.logger.error(f"Context switching test failed: {e}")
            return {"error": str(e)}
