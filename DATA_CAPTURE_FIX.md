# Fix for Data Capture Immediate Stop Issue

## Problem
When starting data capture, the operation immediately stopped with the message:
```
[05:05:12.591] Starting data capture for GSCN 7846 at 3.49968 GHz
[05:05:12.591] Capturing 2 files, 1.0 minutes each
[05:05:12.591] Data capture stopped by user - captured 0/2 files
```

## Root Cause
The `stop_requested` flag was shared between band scanning and data capture operations. When any previous scan operation was stopped, the flag remained `True`, causing data capture to immediately think it should stop.

## Fix Applied

### 1. Reset stop_requested flag in start_data_capture()
**File:** `app.py` - `start_data_capture()` method
```python
def start_data_capture(self, gscn, frequency, duration_minutes, num_files, gain=30, usrp_args=None):
    """Start long-duration data capture for a specific frequency"""
    if self.capture_thread and self.capture_thread.is_alive():
        return False, "Data capture already in progress"
    
    # Reset stop flag for new capture operation
    self.stop_requested = False  # <-- NEW LINE
    
    # Calculate rx_sig_length based on duration...
```

### 2. Added separate stop method for data capture
**File:** `app.py` - New method
```python
def stop_data_capture(self):
    """Stop current data capture"""
    self.stop_requested = True
    self.usrp.stop_current_scan()
    
    self.update_status(state='stopping')
    self.add_log("Data capture stop requested")
    
    return True, "Data capture stopped"
```

### 3. Added dedicated API endpoint for stopping data capture
**File:** `app.py` - New route
```python
@app.route('/api/capture/stop', methods=['POST'])
def stop_capture():
    """Stop the current data capture"""
    success, message = scan_manager.stop_data_capture()
    return jsonify({'message': message})
```

### 4. Updated front-end to use correct stop endpoint
**File:** `templates/index.html` - Modified `stopScan()` function
- Now checks current state and calls appropriate endpoint
- `/api/scan/stop` for scanning operations
- `/api/capture/stop` for data capture operations

### 5. Enhanced UI feedback
**File:** `templates/index.html` - Modified `updateUIForState()` function
- Stop button text changes based on operation:
  - "Stop Scanning" during band scans
  - "Stop Data Capture" during data capture

### 6. Added debug logging
**File:** `app.py` - Enhanced logging in `_data_capture_worker()`
- Logs the initial state of `stop_requested` flag for debugging

## Testing
1. Start any band scan, then stop it
2. Immediately try to start data capture
3. Data capture should now start properly instead of immediately stopping

## Files Modified
- `app.py`: Core logic fixes
- `templates/index.html`: UI improvements
- `test_stop_flag.py`: Test script (new)
- `DATA_CAPTURE_FIX.md`: This documentation (new)

## Verification
The fix ensures that:
1. Each operation type (scan vs data capture) properly manages its state
2. Previous operation states don't interfere with new operations
3. UI provides clear feedback about which operation is running
4. Correct stop endpoints are called for each operation type
