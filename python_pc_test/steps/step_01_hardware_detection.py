"""
Step 01: Hardware Detection
Detects and catalogs all hardware components in the system.
"""

import subprocess
import re
from typing import Dict, Any, List
from .base import BaseStep, StepResult, StepStatus


class HardwareDetectionStep(BaseStep):
    """Detects hardware components."""
    
    def execute(self) -> StepResult:
        """Execute hardware detection."""
        self.logger.info("Starting hardware detection...")
        
        hardware_info = {
            "cpu": self._detect_cpu(),
            "memory": self._detect_memory(),
            "disks": self._detect_disks(),
            "network": self._detect_network(),
            "graphics": self._detect_graphics(),
            "audio": self._detect_audio(),
            "usb": self._detect_usb(),
            "numa": self._detect_numa(),
        }
        
        # Check if critical components are detected
        errors = []
        if not hardware_info["cpu"].get("model"):
            errors.append("CPU not detected")
        if not hardware_info["memory"].get("total_gb", 0) > 0:
            errors.append("Memory not detected")
        
        if errors:
            return StepResult(
                step_name=self.name,
                status=StepStatus.FAILED,
                message="Hardware detection completed with errors",
                details=hardware_info,
                errors=errors
            )
        
        return StepResult(
            step_name=self.name,
            status=StepStatus.PASSED,
            message="Hardware detection completed successfully",
            details=hardware_info
        )
    
    def _detect_cpu(self) -> Dict[str, Any]:
        """Detect CPU information."""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
            
            models = re.findall(r'model name\s+:\s+(.+)', cpuinfo)
            cores = len(re.findall(r'processor\s+:\s+\d+', cpuinfo))
            sockets = len(set(re.findall(r'physical id\s+:\s+(\d+)', cpuinfo))) or 1
            
            return {
                "model": models[0] if models else "Unknown",
                "cores": cores,
                "sockets": sockets,
                "threads_per_core": cores // (sockets * len(set(re.findall(r'core id\s+:\s+(\d+)', cpuinfo)) or 1))
            }
        except Exception as e:
            self.logger.error(f"CPU detection failed: {e}")
            return {"error": str(e)}
    
    def _detect_memory(self) -> Dict[str, Any]:
        """Detect memory information."""
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            total_kb = int(re.search(r'MemTotal:\s+(\d+)', meminfo).group(1))
            free_kb = int(re.search(r'MemFree:\s+(\d+)', meminfo).group(1))
            available_kb = int(re.search(r'MemAvailable:\s+(\d+)', meminfo).group(1))
            
            return {
                "total_gb": round(total_kb / 1024 / 1024, 2),
                "free_gb": round(free_kb / 1024 / 1024, 2),
                "available_gb": round(available_kb / 1024 / 1024, 2)
            }
        except Exception as e:
            self.logger.error(f"Memory detection failed: {e}")
            return {"error": str(e)}
    
    def _detect_disks(self) -> List[Dict[str, Any]]:
        """Detect disk drives."""
        disks = []
        try:
            result = subprocess.run(
                ['lsblk', '-bdo', 'NAME,SIZE,TYPE,MOUNTPOINT,MODEL'],
                capture_output=True, text=True, timeout=30
            )
            
            for line in result.stdout.strip().split('\n')[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 3:
                    disks.append({
                        "name": parts[0],
                        "size_bytes": int(parts[1]) if parts[1].isdigit() else 0,
                        "type": parts[2],
                        "mountpoint": parts[3] if len(parts) > 3 else "",
                        "model": " ".join(parts[4:]) if len(parts) > 4 else ""
                    })
        except Exception as e:
            self.logger.error(f"Disk detection failed: {e}")
        
        return disks
    
    def _detect_network(self) -> List[Dict[str, Any]]:
        """Detect network interfaces."""
        interfaces = []
        try:
            result = subprocess.run(
                ['ip', '-o', 'link', 'show'],
                capture_output=True, text=True, timeout=30
            )
            
            for line in result.stdout.strip().split('\n'):
                match = re.search(r'\d+:\s+(\S+):\s+<([^>]+)>', line)
                if match:
                    name = match.group(1)
                    flags = match.group(2)
                    is_up = "UP" in flags
                    
                    # Get MAC address
                    mac_match = re.search(r'link/ether\s+(\S+)', line)
                    mac = mac_match.group(1) if mac_match else ""
                    
                    interfaces.append({
                        "name": name,
                        "state": "up" if is_up else "down",
                        "mac": mac
                    })
        except Exception as e:
            self.logger.error(f"Network detection failed: {e}")
        
        return interfaces
    
    def _detect_graphics(self) -> List[Dict[str, Any]]:
        """Detect graphics adapters."""
        gpus = []
        try:
            result = subprocess.run(
                ['lspci', '-nn'],
                capture_output=True, text=True, timeout=30
            )
            
            for line in result.stdout.split('\n'):
                if 'VGA compatible controller' in line or '3D controller' in line:
                    match = re.search(r'(\S+):\s+(.+?)\s+\[(\S+)\]', line)
                    if match:
                        gpus.append({
                            "bus": match.group(1),
                            "model": match.group(2),
                            "device_id": match.group(3)
                        })
        except Exception as e:
            self.logger.error(f"Graphics detection failed: {e}")
        
        return gpus
    
    def _detect_audio(self) -> List[Dict[str, Any]]:
        """Detect audio devices."""
        audio_devices = []
        try:
            result = subprocess.run(
                ['lspci', '-nn'],
                capture_output=True, text=True, timeout=30
            )
            
            for line in result.stdout.split('\n'):
                if 'Audio device' in line or 'Multimedia audio controller' in line:
                    match = re.search(r'(\S+):\s+(.+?)\s+\[(\S+)\]', line)
                    if match:
                        audio_devices.append({
                            "bus": match.group(1),
                            "model": match.group(2),
                            "device_id": match.group(3)
                        })
        except Exception as e:
            self.logger.error(f"Audio detection failed: {e}")
        
        return audio_devices
    
    def _detect_usb(self) -> List[Dict[str, Any]]:
        """Detect USB devices."""
        usb_devices = []
        try:
            result = subprocess.run(
                ['lsusb'],
                capture_output=True, text=True, timeout=30
            )
            
            for line in result.stdout.split('\n'):
                if line.strip():
                    match = re.search(r'Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+(\S+)\s+(.+)', line)
                    if match:
                        usb_devices.append({
                            "bus": int(match.group(1)),
                            "device": int(match.group(2)),
                            "vendor_product": match.group(3),
                            "description": match.group(4)
                        })
        except Exception as e:
            self.logger.error(f"USB detection failed: {e}")
        
        return usb_devices
    
    def _detect_numa(self) -> Dict[str, Any]:
        """Detect NUMA topology."""
        numa_info = {"nodes": 0, "topology": []}
        try:
            if subprocess.run(['numactl', '--hardware'], 
                            capture_output=True, timeout=30).returncode == 0:
                result = subprocess.run(
                    ['numactl', '--hardware'],
                    capture_output=True, text=True, timeout=30
                )
                
                nodes_match = re.search(r'available:\s+(\d+)\s+nodes', result.stdout)
                if nodes_match:
                    numa_info["nodes"] = int(nodes_match.group(1))
                    
                # Parse node details
                for line in result.stdout.split('\n'):
                    if line.startswith('node'):
                        numa_info["topology"].append(line.strip())
        except Exception as e:
            self.logger.error(f"NUMA detection failed: {e}")
        
        return numa_info
