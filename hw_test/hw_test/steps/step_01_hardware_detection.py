"""Step 1: Hardware Detection."""

import subprocess
import re
from typing import List, Dict, Any, Optional

from hw_test.types import StepResult, TestStatus, HardwareInfo, TestConfig
from hw_test.steps.base import BaseHWStep


class HardwareDetectionStep(BaseHWStep):
    """Detect and catalog all hardware components."""
    
    name = "Hardware Detection"
    description = "Detect CPU, memory, storage, network, GPU, audio, USB devices, and other hardware"
    required_privileges = True
    
    def __init__(self, config: TestConfig, hardware_info: Optional[HardwareInfo] = None):
        super().__init__(config, hardware_info)
        self.detected_hardware = HardwareInfo()
    
    def _run_command(self, cmd: List[str], timeout: int = 30) -> tuple[str, str]:
        """Run a command and return (stdout, stderr)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Command timed out: {' '.join(cmd)}")
            return "", "Timeout"
        except Exception as e:
            self.logger.debug(f"Command failed: {' '.join(cmd)} - {e}")
            return "", str(e)
    
    def _detect_cpu(self) -> None:
        """Detect CPU information."""
        try:
            import cpuinfo
            info = cpuinfo.get_cpu_info()
            self.detected_hardware.cpu_model = info.get('brand_raw', 'Unknown')
            self.detected_hardware.cpu_cores = info.get('count', 0)
            
            # Get frequency
            stdout, _ = self._run_command(['lscpu'])
            for line in stdout.split('\n'):
                if 'CPU MHz' in line or 'MHz' in line:
                    match = re.search(r'([\d.]+)', line)
                    if match:
                        self.detected_hardware.cpu_freq_mhz = float(match.group(1))
                        break
            
            # Threads
            stdout, _ = self._run_command(['nproc', '--all'])
            if stdout.strip().isdigit():
                self.detected_hardware.cpu_threads = int(stdout.strip())
                
        except Exception as e:
            self.logger.warning(f"CPU detection failed: {e}")
            self.detected_hardware.cpu_model = "Unknown"
    
    def _detect_memory(self) -> None:
        """Detect memory information."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            self.detected_hardware.total_memory_mb = int(mem.total / (1024 * 1024))
            self.detected_hardware.available_memory_mb = int(mem.available / (1024 * 1024))
        except Exception as e:
            self.logger.warning(f"Memory detection failed: {e}")
    
    def _detect_disks(self) -> None:
        """Detect disk information."""
        try:
            import psutil
            disks = []
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append({
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total_gb': round(usage.total / (1024**3), 2),
                        'used_gb': round(usage.used / (1024**3), 2),
                        'free_gb': round(usage.free / (1024**3), 2),
                        'percent_used': usage.percent
                    })
                except PermissionError:
                    continue
            self.detected_hardware.disk_info = disks
        except Exception as e:
            self.logger.warning(f"Disk detection failed: {e}")
    
    def _detect_network(self) -> None:
        """Detect network interfaces."""
        try:
            import psutil
            interfaces = []
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            
            for iface_name, addrs_list in addrs.items():
                if iface_name.startswith('lo'):
                    continue
                    
                iface_info = {
                    'name': iface_name,
                    'is_up': stats.get(iface_name, {}).isup if iface_name in stats else False,
                    'speed': stats.get(iface_name, {}).speed if iface_name in stats else 0,
                    'addresses': []
                }
                
                for addr in addrs_list:
                    addr_info = {
                        'family': str(addr.family),
                        'address': addr.address
                    }
                    if addr.netmask:
                        addr_info['netmask'] = addr.netmask
                    iface_info['addresses'].append(addr_info)
                
                interfaces.append(iface_info)
            
            self.detected_hardware.network_interfaces = interfaces
        except Exception as e:
            self.logger.warning(f"Network detection failed: {e}")
    
    def _detect_gpu(self) -> None:
        """Detect GPU information."""
        gpus = []
        
        # Try lspci for VGA controllers
        stdout, _ = self._run_command(['lspci', '-nn'])
        for line in stdout.split('\n'):
            if 'VGA' in line or '3D' in line or 'Display' in line:
                gpus.append({'description': line.strip(), 'source': 'lspci'})
        
        # Try nvidia-smi if available
        stdout, _ = self._run_command(['nvidia-smi', '-L'])
        if stdout:
            for line in stdout.split('\n'):
                if line.strip():
                    gpus.append({'description': line.strip(), 'source': 'nvidia-smi'})
        
        self.detected_hardware.gpu_info = gpus
    
    def _detect_audio(self) -> None:
        """Detect audio devices."""
        audio = []
        stdout, _ = self._run_command(['aplay', '-l'])
        
        if stdout:
            current_card = {}
            for line in stdout.split('\n'):
                if line.startswith('card '):
                    if current_card:
                        audio.append(current_card)
                    match = re.match(r'card (\d+): (.+)', line)
                    if match:
                        current_card = {'card': match.group(1), 'name': match.group(2), 'devices': []}
                elif line.strip() and current_card:
                    current_card.setdefault('devices', []).append(line.strip())
            
            if current_card:
                audio.append(current_card)
        
        self.detected_hardware.audio_devices = audio
    
    def _detect_usb(self) -> None:
        """Detect USB devices."""
        usb = []
        stdout, _ = self._run_command(['lsusb'])
        
        for line in stdout.split('\n'):
            if line.strip() and 'Bus' in line:
                usb.append({'description': line.strip()})
        
        self.detected_hardware.usb_devices = usb
    
    def _detect_system_info(self) -> None:
        """Detect system information from DMI/SMBIOS."""
        # Manufacturer and product
        for file_path, attr in [
            ('/sys/class/dmi/id/sys_vendor', 'system_manufacturer'),
            ('/sys/class/dmi/id/product_name', 'system_product'),
            ('/sys/class/dmi/id/bios_vendor', 'bios_vendor'),
            ('/sys/class/dmi/id/bios_version', 'bios_version'),
        ]:
            try:
                with open(file_path, 'r') as f:
                    value = f.read().strip()
                    setattr(self.detected_hardware, attr, value)
            except (FileNotFoundError, PermissionError):
                pass
        
        # NUMA nodes
        try:
            numa_nodes = 0
            for entry in subprocess.run(['ls', '-d', '/sys/devices/system/node/node*'], 
                                       capture_output=True, text=True).stdout.split():
                if 'node' in entry:
                    numa_nodes += 1
            self.detected_hardware.numa_nodes = max(1, numa_nodes)
        except Exception:
            self.detected_hardware.numa_nodes = 1
        
        # IPMI detection
        stdout, _ = self._run_command(['ipmitool', 'mc', 'info'])
        self.detected_hardware.ipmi_detected = 'Manufacturer' in stdout
    
    def _detect_webcams(self) -> None:
        """Detect webcams."""
        webcams = []
        stdout, _ = self._run_command(['v4l2-ctl', '--list-devices'])
        
        if stdout:
            current_device = {}
            for line in stdout.split('\n'):
                if line.strip() and not line.startswith(' '):
                    if current_device:
                        webcams.append(current_device)
                    current_device = {'name': line.strip(), 'paths': []}
                elif line.strip():
                    current_device.setdefault('paths', []).append(line.strip())
            
            if current_device:
                webcams.append(current_device)
        
        # Also check via lsusb
        if not webcams:
            stdout, _ = self._run_command(['lsusb'])
            for line in stdout.split('\n'):
                if 'Camera' in line or 'Webcam' in line:
                    webcams.append({'name': line.strip(), 'source': 'lsusb'})
        
        self.detected_hardware.webcams = webcams
    
    def _detect_fingerprint_readers(self) -> None:
        """Detect fingerprint readers."""
        readers = []
        stdout, _ = self._run_command(['lsusb'])
        
        for line in stdout.split('\n'):
            if any(keyword in line.lower() for keyword in ['fingerprint', 'goodix', 'validity', 'synaptics']):
                readers.append({'description': line.strip()})
        
        self.detected_hardware.fingerprint_readers = readers
    
    def execute(self) -> StepResult:
        """Execute hardware detection."""
        errors = []
        warnings = []
        
        self.logger.info("Starting hardware detection...")
        
        try:
            self._detect_cpu()
            self._detect_memory()
            self._detect_disks()
            self._detect_network()
            self._detect_gpu()
            self._detect_audio()
            self._detect_usb()
            self._detect_system_info()
            self._detect_webcams()
            self._detect_fingerprint_readers()
            
            # Update hardware info for subsequent steps
            self.hardware_info = self.detected_hardware
            
            # Build summary
            summary = {
                'cpu': f"{self.detected_hardware.cpu_model} ({self.detected_hardware.cpu_cores} cores)",
                'memory_mb': self.detected_hardware.total_memory_mb,
                'disks_count': len(self.detected_hardware.disk_info),
                'network_interfaces': len(self.detected_hardware.network_interfaces),
                'gpus': len(self.detected_hardware.gpu_info),
                'audio_devices': len(self.detected_hardware.audio_devices),
                'usb_devices': len(self.detected_hardware.usb_devices),
                'numa_nodes': self.detected_hardware.numa_nodes,
                'system': f"{self.detected_hardware.system_manufacturer} {self.detected_hardware.system_product}",
                'bios': f"{self.detected_hardware.bios_vendor} {self.detected_hardware.bios_version}",
                'ipmi': self.detected_hardware.ipmi_detected,
                'webcams': len(self.detected_hardware.webcams),
                'fingerprint_readers': len(self.detected_hardware.fingerprint_readers),
            }
            
            # Check for potential issues
            if not self.detected_hardware.cpu_model or self.detected_hardware.cpu_model == "Unknown":
                warnings.append("CPU model could not be detected")
            
            if self.detected_hardware.total_memory_mb == 0:
                warnings.append("Memory size could not be detected")
            
            if len(self.detected_hardware.network_interfaces) == 0:
                warnings.append("No network interfaces detected")
            
            status = TestStatus.WARNING if warnings else TestStatus.PASSED
            message = "Hardware detection completed successfully"
            
            return StepResult(
                step_name=self.name,
                status=status,
                message=message,
                details=summary,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            self.logger.exception(f"Hardware detection failed: {e}")
            return StepResult(
                step_name=self.name,
                status=TestStatus.ERROR,
                message=f"Hardware detection failed: {str(e)}",
                errors=[str(e)]
            )
