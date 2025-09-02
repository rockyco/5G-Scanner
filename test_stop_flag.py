#!/usr/bin/env python3
"""
Quick test to verify the stop_requested flag is properly managed
"""

import sys
import os
sys.path.append('/home/user/Projects/5G-Scanner')

from app import ScanManager

def test_stop_flag():
    print("Testing stop_requested flag management...")
    
    # Create scan manager
    scan_manager = ScanManager()
    
    print(f"Initial stop_requested: {scan_manager.stop_requested}")
    
    # Simulate stopping a scan
    scan_manager.stop_scan()
    print(f"After stop_scan(): {scan_manager.stop_requested}")
    
    # Now try starting data capture - this should reset the flag
    print("Starting data capture...")
    success, message = scan_manager.start_data_capture(
        gscn=7846, 
        frequency=3499680000, 
        duration_minutes=0.1,  # Very short for testing
        num_files=1, 
        gain=30
    )
    
    print(f"Data capture start result: {success}, {message}")
    print(f"stop_requested after start_data_capture: {scan_manager.stop_requested}")
    
    # Wait a moment and check status
    import time
    time.sleep(2)
    
    status = scan_manager.get_status()
    print(f"Current status: {status['state']}")
    
    # Stop the capture
    scan_manager.stop_data_capture()
    print(f"After stop_data_capture(): {scan_manager.stop_requested}")

if __name__ == "__main__":
    test_stop_flag()
