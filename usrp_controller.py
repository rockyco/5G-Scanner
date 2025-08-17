#!/usr/bin/env python3
"""
USRP device controller module
Handles all USRP communication and process management
"""

import subprocess
import threading
import time
import os
import re
import signal
import psutil
from datetime import datetime
from pathlib import Path

class USRPController:
    """Controller for USRP device operations"""
    
    def __init__(self, config):
        self.config = config
        self.current_process = None
        self.process_lock = threading.Lock()
    
    def cleanup_processes(self):
        """Clean up any stray USRP processes"""
        try:
            executable_name = Path(self.config.get('usrp.executable_path')).name
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if (proc.info['name'] == executable_name or 
                        any(executable_name in str(cmd) for cmd in proc.info['cmdline'] or [])):
                        
                        process = psutil.Process(proc.info['pid'])
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            process.kill()
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            print(f"Warning: Error cleaning up processes: {e}")
    
    def build_command(self, frequency, rx_sig_length, gain, ddc_rate, usrp_args=None, output_file=None):
        """Build USRP command with given parameters"""
        template = self.config.get_usrp_command_template()
        
        if not template or not template[0]:
            raise ValueError("USRP executable path not configured")
        
        if not os.path.exists(template[0]):
            raise FileNotFoundError(f"USRP executable not found: {template[0]}")
        
        # Format command with actual values
        args = usrp_args or self.config.get('usrp.default_args')
        
        command = []
        for part in template:
            if isinstance(part, str):
                formatted_part = part.format(
                    args=args,
                    frequency=str(frequency),
                    gain=str(gain),
                    ddc_rate=str(ddc_rate),
                    rx_sig_length=str(rx_sig_length)
                )
                command.append(formatted_part)
            else:
                command.append(str(part))
        
        command.append('--setup')
        command.append('3')
        # Add setup delay and null output if not already present
        if '--setup' not in command:
            command.extend(['--setup', '3'])
        
        if '--null' not in command and not output_file:
            command.append('--null')
        elif output_file:
            command.extend(['--file', str(output_file)])
            
        return command
    
    def parse_output(self, output):
        """Parse USRP output to determine result type and SSB count"""
        # Type 0: Successful - "ap_done signal is high" and SSB blocks detected
        if "Number of SSB blocks detected" in output:
            match = re.search(r"Number of SSB blocks detected: (\d+)", output)
            if match:
                ssb_count = int(match.group(1))
                if ssb_count > 0:
                    return 0, ssb_count # Success
        
        # Type 1: Timeout or connection error - need to retry
        timeout_indicators = [
            "Timeout while streaming",
            "Operation timed out", 
            "Could not connect DDC to detectSSB",
            "timed out during flush"
        ]
        if any(indicator in output for indicator in timeout_indicators):
            return 1, 0
        
        # Type 2: Overflow - need to change frequency
        overflow_indicators = [
            "Got an overflow indication",
            "Your write medium must sustain a rate",
            "Dropped samples will not be written"
        ]
        
        # Enhanced overflow detection
        has_overflow = any(indicator in output for indicator in overflow_indicators)
        has_zero_samples = "Number of samples received: 0" in output
        
        if has_overflow or (has_zero_samples and "overflow" in output.lower()):
            return 2, 0
        
        # Check for successful completion but no SSB detected
        if "Tests completed successfully!" in output:
            match = re.search(r"Number of SSB blocks detected: (\d+)", output)
            if match:
                ssb_count = int(match.group(1))
                return (0 if ssb_count > 0 else 1), ssb_count
        
        # Default: No SSB detected, treat as a timeout for retry purposes
        return 1, 0
    
    def execute_scan(self, frequency, rx_sig_length, gain, usrp_args=None, log_callback=None, output_file=None):
        """Execute a single frequency scan"""
        try:
            # Get ddc_rate from config
            ddc_rate = self.config.get('usrp.default_ddc_rate', 7680000)
            
            # Build command
            command = self.build_command(frequency, rx_sig_length, gain, ddc_rate, usrp_args, output_file)
            
            if log_callback:
                log_callback(f"Executing: {' '.join(command)}")
            
            # Start process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                preexec_fn=os.setsid  # Create new process group
            )
            
            self.current_process = process
            process_id = process.pid
            
            # Note: Removed PID logging as requested for cleaner output
            
            # Calculate timeout based on capture duration
            base_timeout = self.config.get('usrp.timeout_seconds', 60)
            if output_file:
                # For data capture, calculate timeout based on rx_sig_length
                # rx_sig_length samples at 7.68 MHz = duration in seconds
                capture_duration = (rx_sig_length / 7680000) + 60  # Add 60s buffer
                timeout = max(base_timeout, capture_duration)
            else:
                timeout = base_timeout
            
            try:
                # Read output line by line in real-time
                output_lines = []
                start_time = time.time()
                
                while True:
                    # Check if process has finished
                    if process.poll() is not None:
                        # Process finished, read any remaining output
                        remaining = process.stdout.read()
                        if remaining:
                            for line in remaining.strip().split('\n'):
                                if line.strip():
                                    if log_callback:
                                        log_callback(line.strip())
                                    output_lines.append(line.strip())
                        break
                    
                    # Check for timeout
                    if time.time() - start_time > timeout:
                        raise subprocess.TimeoutExpired(command, timeout)
                    
                    # Read a line (with timeout)
                    line = process.stdout.readline()
                    if line:
                        line = line.strip()
                        if line:
                            if log_callback:
                                log_callback(line)
                            output_lines.append(line)
                            
                            # Check for overflow indication and terminate process immediately
                            if "Got an overflow indication" in line:
                                if log_callback:
                                    log_callback("Overflow detected, terminating process")
                                # Kill the process group
                                try:
                                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                                    time.sleep(1)
                                    if process.poll() is None:
                                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                                except:
                                    pass
                                self.current_process = None
                                output = '\n'.join(output_lines)
                                return {'result_type': 2, 'error': 'Overflow'}
                    
                    # Small sleep to prevent busy waiting
                    time.sleep(0.01)
                
                self.current_process = None
                output = '\n'.join(output_lines)
                
                if log_callback:
                    log_callback(f"USRP process finished with code {process.returncode}")
                
                return self._parse_result(output, process.returncode)
                
            except subprocess.TimeoutExpired:
                if log_callback:
                    log_callback(f"Timeout expired for process {process_id}")
                
                # Kill the process group
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    time.sleep(2)
                    if process.poll() is None:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except:
                    pass
                
                self.current_process = None
                return {'result_type': 1, 'error': 'Timeout'}
                
        except Exception as e:
            self.current_process = None
            if log_callback:
                log_callback(f"Error executing scan: {e}")
            return {'result_type': -1, 'error': str(e)}
    
    def _terminate_process(self, process):
        """Gracefully terminate a process"""
        try:
            process.send_signal(signal.SIGINT)
            time.sleep(1)
            
            if process.poll() is None:
                process.terminate()
                time.sleep(1)
            
            if process.poll() is None:
                process.kill()
                time.sleep(1)
            
            if process.poll() is None:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                
        except Exception as e:
            print(f"Error terminating process: {e}")
    
    def _force_kill_process(self, process):
        """Force kill a process and its group"""
        try:
            process.kill()
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except:
            pass
    
    def _parse_result(self, output, return_code):
        """Parse USRP process output and return standardized result"""
        result_type, ssb_count = self.parse_output(output)
        
        if result_type == 0:
            return {'result_type': result_type, 'ssb_count': ssb_count}
        elif result_type == 1:
            return {'result_type': result_type, 'error': 'Timeout or connection error'}
        elif result_type == 2:
            return {'result_type': result_type, 'error': 'Overflow'}
        else:
            return {'result_type': return_code, 'error': f'Process exited with code {return_code}'}
    
    def stop_current_scan(self):
        """Stop the currently running scan"""
        with self.process_lock:
            if self.current_process:
                self._terminate_process(self.current_process)
                self.current_process = None
        
        # Also cleanup any stray processes
        self.cleanup_processes()
    
    def is_scanning(self):
        """Check if a scan is currently running"""
        with self.process_lock:
            return self.current_process is not None and self.current_process.poll() is None