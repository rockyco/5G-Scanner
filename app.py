#!/usr/bin/env python3
"""
5G NR SSB Signal Scanner Application - Refactored Version
Improved efficiency, modularity, and configurability
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import threading
import time
import os
from datetime import datetime
from pathlib import Path
from pathlib import Path

# Import our modular components
from config import config
from gscn_calculator import NR_BANDS, calculate_gscn_frequencies, get_band_info, get_all_bands
from usrp_controller import USRPController

app = Flask(__name__)
CORS(app)

class ScanManager:
    """Manages scanning operations and state"""
    
    def __init__(self):
        self.status = {
            'state': 'idle',
            'current_band': None,
            'scan_start_time': None,
            'progress': {
                'completed_count': 0,
                'total_count': 0,
                'current_frequency': None,
                'detections': 0
            },
            'results': [],
            'log': []
        }
        self.usrp = USRPController(config)
        self.scan_thread = None
        self.stop_requested = False
        self.lock = threading.Lock()
        self.scanned_frequencies = set() # Track scanned frequencies
        self.detected_frequencies = {} # Store detected frequencies by band
        self.capture_thread = None
        
        # Load persistent detected frequencies
        self.load_detected_frequencies()
    
    def load_detected_frequencies(self):
        """Load detected frequencies from persistent storage"""
        try:
            freq_file = Path(config.get('paths.data_directory')) / 'detected_frequencies.json'
            if freq_file.exists():
                import json
                with open(freq_file, 'r') as f:
                    self.detected_frequencies = json.load(f)
                self.add_log(f"Loaded {sum(len(freqs) for freqs in self.detected_frequencies.values())} persistent frequencies")
        except Exception as e:
            self.add_log(f"Failed to load persistent frequencies: {e}")
    
    def save_detected_frequencies(self):
        """Save detected frequencies to persistent storage"""
        try:
            data_dir = Path(config.get('paths.data_directory'))
            data_dir.mkdir(exist_ok=True)
            freq_file = data_dir / 'detected_frequencies.json'
            import json
            with open(freq_file, 'w') as f:
                json.dump(self.detected_frequencies, f, indent=2)
        except Exception as e:
            self.add_log(f"Failed to save persistent frequencies: {e}")
    
    def add_log(self, message, level='info'):
        """Add a log entry with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}"
        
        with self.lock:
            self.status['log'].append(log_entry)
            
            # Limit log size
            max_logs = config.get('ui.max_log_entries', 1000)
            if len(self.status['log']) > max_logs:
                self.status['log'] = self.status['log'][-max_logs:]
        
        # Also print to console for debugging
        print(log_entry, flush=True)
    
    def update_status(self, **kwargs):
        """Thread-safe status update"""
        with self.lock:
            self.status.update(kwargs)
    
    def get_status(self):
        """Get current status (thread-safe copy)"""
        with self.lock:
            return self.status.copy()
    
    def start_scan(self, band, rx_sig_length, gain, usrp_args=None, max_retries=None):
        """Start scanning a band"""
        if self.scan_thread and self.scan_thread.is_alive():
            return False, "Scan already in progress"
        
        if band not in NR_BANDS:
            return False, f"Invalid band: {band}"
        
        # Reset status
        with self.lock:
            self.scanned_frequencies.clear() # Clear previously scanned frequencies
            self.status.update({
                'state': 'starting',
                'current_band': band,
                'scan_start_time': datetime.now().isoformat(),
                'progress': {
                    'completed_count': 0,
                    'total_count': 0,
                    'current_frequency': None,
                    'detections': 0
                },
                'results': [],
                'log': []
            })
            # Initialize detected frequencies for this band
            if band not in self.detected_frequencies:
                self.detected_frequencies[band] = []
        
        self.stop_requested = False
        
        # Start scan thread
        self.scan_thread = threading.Thread(
            target=self._scan_band_worker,
            args=(band, rx_sig_length, gain, usrp_args, max_retries),
            daemon=True
        )
        self.scan_thread.start()
        
        return True, "Scan started"
    
    def stop_scan(self):
        """Stop current scan"""
        self.stop_requested = True
        self.usrp.stop_current_scan()
        
        self.update_status(state='stopping')
        self.add_log("Scan stop requested")
        
        return True, "Scan stopped"
    
    def _scan_band_worker(self, band, rx_sig_length, gain, usrp_args, max_retries):
        """Worker thread for band scanning"""
        try:
            self.update_status(state='scanning')
            self.add_log(f"Starting scan for band {band}")
            
            # Get frequencies to scan
            max_freq = config.get('scanning.max_frequencies_per_band', 50)
            step_size = config.get('scanning.gscn_step_size', 1)
            
            frequencies = calculate_gscn_frequencies(band, max_freq, step_size)
            total_frequencies = len(frequencies)
            
            with self.lock:
                self.status['progress']['total_count'] = total_frequencies

            if not frequencies:
                self.add_log(f"No frequencies found for band {band}")
                self.update_status(state='completed')
                return
            
            self.add_log(f"Scanning {total_frequencies} frequencies in band {band}")
            
            if max_retries is None:
                max_retries = config.get('usrp.retry_attempts', 2)
            
            # Scan each frequency
            for idx, freq_info in enumerate(frequencies):
                if self.stop_requested:
                    break
                
                self._scan_single_frequency(freq_info, rx_sig_length, gain, 
                                          usrp_args, max_retries)
                
                # Update progress
                with self.lock:
                    self.status['progress']['completed_count'] = idx + 1
                
            # Complete scan
            final_state = 'stopped' if self.stop_requested else 'completed'
            self.update_status(state=final_state)
            with self.lock:
                self.status['progress']['current_frequency'] = None

            detected_count = self.status['progress']['detections']
            self.add_log(f"Scan {final_state}. Found SSB signals at {detected_count} frequencies")
            
        except Exception as e:
            self.add_log(f"Scan error: {e}", 'error')
            self.update_status(state='error')
    
    def _scan_single_frequency(self, freq_info, rx_sig_length, gain, usrp_args, max_retries):
        """Scan a single frequency with specific retry logic."""
        frequency = freq_info['frequency']
        gscn = freq_info['gscn']
        scs = freq_info['scs']

        # Skip if this frequency has already been successfully scanned
        if frequency in self.scanned_frequencies:
            self.add_log(f"Skipping already scanned frequency: {frequency/1e9:.5f} GHz")
            return

        with self.lock:
            self.status['progress']['current_frequency'] = frequency
        
        self.add_log(f"Scanning GSCN {gscn} at {frequency/1e9:.5f} GHz (SCS: {scs} kHz)")
        
        for attempt in range(2):  # Max 2 attempts
            if self.stop_requested:
                break

            result = self.usrp.execute_scan(
                frequency=frequency,
                rx_sig_length=rx_sig_length,
                gain=gain,
                usrp_args=usrp_args,
                log_callback=self.add_log
            )
            
            # Add result to the main results list
            with self.lock:
                # Check if a result for this frequency already exists
                existing_result = next((r for r in self.status['results'] if r['freq_hz'] == frequency), None)
                
                if existing_result:
                    # Update existing result
                    existing_result['result_type'] = result['result_type']
                    existing_result['message'] = result.get('error', 'Success')
                else:
                    # Add new result
                    self.status['results'].append({
                        'gscn': gscn,
                        'freq_hz': frequency,
                        'result_type': result['result_type'],
                        'message': result.get('error', 'Success')
                    })

            # First attempt logic
            if attempt == 0:
                if result['result_type'] == 0:
                    # Success on first try
                    with self.lock:
                        self.status['progress']['detections'] += 1
                        self.scanned_frequencies.add(frequency) # Mark as successfully scanned
                        # Store detected frequency
                        self.detected_frequencies[self.status['current_band']].append({
                            'gscn': gscn,
                            'frequency': frequency,
                            'ssb_count': result['ssb_count'],
                            'scs': scs
                        })
                        # Save to persistent storage
                        self.save_detected_frequencies()
                    self.add_log(f"SUCCESS: Detected {result['ssb_count']} SSB blocks at {frequency/1e9:.5f} GHz")
                    break  # Done with this frequency

                elif result['result_type'] == 2:
                    # Overflow on first try, terminate
                    self.add_log(f"Overflow at {frequency/1e9:.5f} GHz on first attempt - skipping")
                    break  # Done with this frequency

                elif result['result_type'] == 1:
                    # Timeout on first try, retry once
                    self.add_log(f"Timeout at {frequency/1e9:.5f} GHz, retrying once...")
                    time.sleep(2)
                    continue  # Go to the second attempt

                else:
                    # Unknown error on first try
                    self.add_log(f"Unknown error at {frequency/1e9:.5f} GHz - skipping")
                    break # Done with this frequency
            
            # Second attempt logic (only happens after a type 1 failure)
            else:
                if result['result_type'] == 0:
                    # Success on second try
                    with self.lock:
                        self.status['progress']['detections'] += 1
                        self.scanned_frequencies.add(frequency) # Mark as successfully scanned
                        # Store detected frequency
                        self.detected_frequencies[self.status['current_band']].append({
                            'gscn': gscn,
                            'frequency': frequency,
                            'ssb_count': result['ssb_count'],
                            'scs': scs
                        })
                        # Save to persistent storage
                        self.save_detected_frequencies()
                    self.add_log(f"SUCCESS on second attempt: Detected {result['ssb_count']} SSB blocks at {frequency/1e9:.5f} GHz")
                
                else:
                    # Failure on second try
                    self.add_log(f"Scan failed on second attempt for {frequency/1e9:.5f} GHz (type {result['result_type']}) - skipping")
                
                break # Done with this frequency, regardless of outcome
    
    def scan_single_frequency(self, frequency, rx_sig_length, gain, usrp_args=None):
        """Scan a single frequency with retry logic (for testing)."""
        self.add_log(f"Starting single frequency test for {frequency/1e9:.5f} GHz")
        
        for attempt in range(2):  # Max 2 attempts
            if self.stop_requested:
                break

            result = self.usrp.execute_scan(
                frequency=frequency,
                rx_sig_length=rx_sig_length,
                gain=gain,
                usrp_args=usrp_args,
                log_callback=self.add_log
            )

            # First attempt logic
            if attempt == 0:
                if result['result_type'] == 0:
                    self.add_log(f"SUCCESS on first attempt: Detected {result['ssb_count']} SSB blocks.")
                    return result # Success

                elif result['result_type'] == 2:
                    self.add_log(f"Overflow on first attempt - terminating test.")
                    return result # Failure, but don't retry

                elif result['result_type'] == 1:
                    self.add_log(f"Timeout on first attempt, retrying once...")
                    time.sleep(2)
                    continue  # Go to the second attempt
                
                else:
                    self.add_log(f"Unknown error on first attempt - terminating test.")
                    return result

            # Second attempt logic
            else:
                if result['result_type'] == 0:
                    self.add_log(f"SUCCESS on second attempt: Detected {result['ssb_count']} SSB blocks.")
                else:
                    self.add_log(f"Scan failed on second attempt (type {result['result_type']}).")
                
                return result # Return result of second attempt

        # This part should not be reached if logic is correct, but as a fallback
        return {'result_type': -1, 'error': 'Exited scan loop unexpectedly'}

    def start_data_capture(self, gscn, frequency, duration_minutes, num_files, gain=30, usrp_args=None):
        """Start long-duration data capture for a specific frequency"""
        if self.capture_thread and self.capture_thread.is_alive():
            return False, "Data capture already in progress"
        
        # Calculate rx_sig_length based on duration (7680000 samples per second)
        rx_sig_length = int(7680000 * duration_minutes * 60)
        
        self.capture_thread = threading.Thread(
            target=self._data_capture_worker,
            args=(gscn, frequency, rx_sig_length, num_files, gain, usrp_args),
            daemon=True
        )
        self.capture_thread.start()
        
        return True, "Data capture started"
    
    def _data_capture_worker(self, gscn, frequency, rx_sig_length, num_files, gain, usrp_args):
        """Worker thread for data capture"""
        try:
            self.update_status(state='data_capture')
            self.add_log(f"Starting data capture for GSCN {gscn} at {frequency/1e9:.5f} GHz")
            self.add_log(f"Capturing {num_files} files, {rx_sig_length/7680000/60:.1f} minutes each")
            
            data_dir = Path(config.get('paths.data_directory'))
            data_dir.mkdir(exist_ok=True)
            
            for file_num in range(1, num_files + 1):
                if self.stop_requested:
                    break
                
                # Generate filename with timestamp and GSCN
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"gscn_{gscn}_{frequency/1e6:.1f}MHz_{timestamp}_file{file_num}.dat"
                output_file = data_dir / filename
                
                self.add_log(f"Capturing file {file_num}/{num_files}: {filename}")
                
                # Retry logic for data capture (similar to band scan)
                for attempt in range(2):  # Max 2 attempts
                    if self.stop_requested:
                        break
                    
                    result = self.usrp.execute_scan(
                        frequency=frequency,
                        rx_sig_length=rx_sig_length,
                        gain=gain,
                        usrp_args=usrp_args,
                        log_callback=self.add_log,
                        output_file=output_file
                    )
                    
                    if result['result_type'] == 0:
                        self.add_log(f"Successfully captured file {file_num}: {filename}")
                        break  # Success, move to next file
                    elif attempt == 0 and (result['result_type'] == 1 or 'Could not connect DDC to detectSSB' in result.get('error', '')):
                        # Retry on first timeout or connection error
                        self.add_log(f"Data capture failed for file {file_num} (attempt {attempt + 1}), retrying once...")
                        time.sleep(5)  # Longer wait for connection issues
                        continue
                    else:
                        # Failed on retry or other error
                        error_msg = result.get('error', 'Unknown error')
                        self.add_log(f"Failed to capture file {file_num} after retries: {error_msg}")
                        return  # Exit data capture on failure
                    
                if self.stop_requested:
                    break
            
            if not self.stop_requested:
                self.add_log("Data capture completed successfully")
            else:
                self.add_log("Data capture stopped by user")
            
            self.update_status(state='idle')
                
        except Exception as e:
            self.add_log(f"Data capture error: {e}", 'error')
            self.update_status(state='error')

# Global scan manager
scan_manager = ScanManager()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    return jsonify({
        'usrp_executable': config.get('usrp.executable_path'),
        'data_directory': config.get('paths.data_directory'),
        'default_args': config.get('usrp.default_args'),
        'default_gain': config.get('usrp.default_gain'),
        'default_rx_sig_length': config.get('usrp.default_rx_sig_length'),
        'scanning': {
            'max_frequencies_per_band': config.get('scanning.max_frequencies_per_band'),
            'gscn_step_size': config.get('scanning.gscn_step_size')
        }
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration"""
    try:
        data = request.json
        
        # Update configuration
        if 'usrp_executable' in data:
            config.set('usrp.executable_path', data['usrp_executable'])
        
        if 'data_directory' in data:
            config.set('paths.data_directory', data['data_directory'])
        
        if 'default_args' in data:
            config.set('usrp.default_args', data['default_args'])
        
        if 'scanning' in data:
            for key, value in data['scanning'].items():
                config.set(f'scanning.{key}', value)
        
        # Save configuration
        if config.save_config():
            return jsonify({'status': 'success', 'message': 'Configuration updated'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to save configuration'}), 500
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/bands', methods=['GET'])
def get_bands():
    """Return all available bands with their details."""
    return jsonify(get_all_bands())

@app.route('/api/gscn/<band>')
def get_gscn_frequencies(band):
    if band not in NR_BANDS:
        return jsonify({'error': 'Invalid band'}), 400
    
    max_freq = config.get('scanning.max_frequencies_per_band', 50)
    step_size = config.get('scanning.gscn_step_size', 1)
    
    frequencies = calculate_gscn_frequencies(band, max_freq, step_size)
    band_info = get_band_info(band)
    
    return jsonify({
        'band': band,
        'band_info': band_info,
        'frequencies': frequencies,
        'count': len(frequencies)
    })

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    """Start a new scan"""
    data = request.get_json()
    band = data.get('band')
    rx_sig_length = int(data.get('rx_sig_length', 7680000))
    gain = int(data.get('gain', 30))
    
    if not band:
        return jsonify({'message': 'Band is a required parameter'}), 400
        
    success, message = scan_manager.start_scan(band, rx_sig_length, gain)
    
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'message': message}), 400

@app.route('/api/scan/stop', methods=['POST'])
def stop_scan():
    """Stop the current scan"""
    success, message = scan_manager.stop_scan()
    return jsonify({'message': message})

@app.route('/api/scan/single_freq', methods=['POST'])
def scan_single_freq():
    """Scan a single frequency for testing"""
    data = request.get_json()
    frequency = data.get('frequency')
    gain = data.get('gain')
    
    if not frequency or not gain:
        return jsonify({'message': 'Frequency and gain are required'}), 400
        
    result = scan_manager.scan_single_frequency(
        frequency=float(frequency),
        rx_sig_length=7680000, # Use a default length for now
        gain=int(gain)
    )
    
    return jsonify(result)

@app.route('/api/status')
def status():
    """Get current scan status"""
    status_data = scan_manager.get_status()
    # Add detected frequencies to status
    status_data['detected_frequencies'] = scan_manager.detected_frequencies
    return jsonify(status_data)

@app.route('/api/capture/start', methods=['POST'])
def start_data_capture():
    """Start data capture for a specific frequency"""
    data = request.get_json()
    gscn = data.get('gscn')
    frequency = float(data.get('frequency'))
    duration_minutes = float(data.get('duration_minutes'))
    num_files = int(data.get('num_files'))
    gain = int(data.get('gain', 30))
    
    if not all([gscn, frequency, duration_minutes, num_files]):
        return jsonify({'message': 'Missing required parameters'}), 400
    
    success, message = scan_manager.start_data_capture(
        gscn, frequency, duration_minutes, num_files, gain
    )
    
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'message': message}), 400

@app.route('/api/validate', methods=['POST'])
def validate_config():
    """Validate USRP executable path"""
    data = request.get_json()
    usrp_executable = data.get('usrp_executable')
    
    if not usrp_executable:
        return jsonify({'is_valid': False, 'message': 'Executable path is required.'}), 400
        
    is_valid = Path(usrp_executable).is_file()
    
    if is_valid:
        message = "USRP executable found and is valid."
    else:
        message = f"Executable not found at: {usrp_executable}"
        
    return jsonify({'is_valid': is_valid, 'message': message})

if __name__ == '__main__':
    # Validate configuration on startup
    if not config.validate_paths():
        print("Warning: Configuration validation failed. Please check settings.")
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)