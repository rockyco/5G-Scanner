# 5G NR SSB Signal Scanner - Refactored Version

## Overview
A modular, configurable web-based application for scanning and detecting 5G NR Synchronization Signal Blocks (SSB) using the NI USRP X310 device. This refactored version provides improved efficiency, modularity, and user-configurable paths.

You must think carefully and only action the specific task I have given you with the most concise and elegant solution that changes as little code as possible.

## Key Improvements

### ✅ **Modular Architecture**
- **`config.py`**: Configuration management with JSON persistence
- **`gscn_calculator.py`**: GSCN frequency calculations (3GPP compliant)
- **`usrp_controller.py`**: USRP device communication and process management
- **`app.py`**: Main Flask application (significantly simplified)

### ✅ **Configurable Paths**
- **USRP Executable Path**: No more hardcoded paths
- **Data Directory**: User-configurable save location
- **USRP Arguments**: Customizable device parameters (IP address, type, etc.)
- **Scanning Parameters**: Adjustable frequency count and step size

### ✅ **Enhanced Efficiency**
- Thread-safe operations with proper locking
- Improved process management and cleanup
- Configurable retry attempts and timeouts
- Optimized frequency sampling (configurable step size)

## Quick Start

### 1. Installation
```bash
cd /home/amd/UTS/NR5G/AppUI
pip install -r requirements.txt
```

### 2. Configuration
Edit `config.json` or use the web interface:

```json
{
  "usrp": {
    "executable_path": "/path/to/your/init_ssb_block",
    "default_args": "type=x300,addr=192.168.40.2",
    "default_gain": 30,
    "default_rx_sig_length": 7680000
  },
  "paths": {
    "data_directory": "/your/data/directory"
  },
  "scanning": {
    "max_frequencies_per_band": 50,
    "gscn_step_size": 1
  }
}
```

### 3. Run Application
```bash
python app.py
# or
./run.sh
```

### 4. Access Web Interface
Open browser: `http://localhost:5000`

## Configuration Options

### USRP Settings
- **Executable Path**: Path to `init_ssb_block` binary
- **Default Arguments**: USRP connection string (e.g., `type=x300,addr=IP`)
- **Default Gain**: RF gain in dB (default: 30)
- **Default RX Signal Length**: Number of samples (default: 7,680,000)
- **Timeout**: Command timeout in seconds (default: 60)
- **Retry Attempts**: Max retries for failed scans (default: 2)

### Path Settings
- **Data Directory**: Where to save captured signal files
- **Log Directory**: Application log storage (future use)
- **Temp Directory**: Temporary file storage

### Scanning Settings
- **Max Frequencies per Band**: Limit frequencies scanned per band (default: 50)
- **GSCN Step Size**: Sample every Nth GSCN (1 = all, 2 = every 2nd, etc.)

## Web Interface Features

### Configuration Tab
- Set USRP executable path and arguments
- Configure scanning parameters
- Validate configuration
- Real-time path validation

### Scanning Tab
- Band selection with automatic GSCN calculation
- Customizable scan parameters
- Real-time progress monitoring
- Live log display with color coding

### Results Tab
- Detected SSB signals with technical details (GSCN, SCS, frequency)
- Export capabilities
- Historical scan data

## API Endpoints

### Configuration Management
- `GET /api/config` - Get current configuration
- `POST /api/config` - Update configuration
- `POST /api/validate` - Validate current settings

### Scanning Operations
- `GET /api/bands` - Get available 5G NR bands
- `GET /api/gscn/<band>` - Get GSCN frequencies for band
- `POST /api/scan` - Start band scan
- `POST /api/scan/stop` - Stop current scan
- `POST /api/scan/single` - Test single frequency
- `GET /api/status` - Get scan status

## Technical Features

### Accurate GSCN Calculations
- **3GPP TS 38.104 Compliant**: Exact frequency calculations matching MATLAB reference
- **Band-Specific GSCN Ranges**: Uses official 3GPP tables
- **Multiple SCS Support**: 15 kHz and 30 kHz subcarrier spacing

### Robust Process Management
- **Process Cleanup**: Automatic cleanup of stray USRP processes
- **Timeout Handling**: Configurable command timeouts
- **Overflow Detection**: Smart detection and handling of overflow conditions
- **Graceful Termination**: Proper signal handling for stuck processes

### Thread-Safe Operations
- **Concurrent Scanning**: Thread-safe status updates
- **Process Isolation**: Separate threads for UI and scanning
- **Resource Management**: Proper cleanup and resource release

## File Structure
```
/home/amd/UTS/NR5G/AppUI/
├── app.py                 # Main Flask application
├── config.py             # Configuration management
├── gscn_calculator.py    # GSCN frequency calculations
├── usrp_controller.py    # USRP device controller
├── config.json           # User configuration file
├── templates/
│   └── index.html        # Web interface
├── data/                 # Signal data storage
├── requirements.txt      # Python dependencies
├── run.sh               # Startup script
└── README.md            # This file
```

## Migration from Original Version

### Automatic Migration
The application automatically handles configuration migration. Existing users can:

1. **Keep existing workflows**: API endpoints remain compatible
2. **Update paths**: Use web interface or edit `config.json`
3. **Customize scanning**: Adjust frequency limits and step sizes

### Configuration Updates Needed
- Set correct path to `init_ssb_block` executable
- Update USRP arguments with your device IP address
- Verify data directory paths

## Troubleshooting

### Common Issues

1. **"USRP executable not found"**
   - Check path in Configuration tab
   - Verify file exists and is executable
   - Use "Validate Config" button

2. **"Cannot create data directory"**
   - Check directory permissions
   - Ensure parent directories exist
   - Try different path

3. **Connection timeouts**
   - Verify USRP IP address in arguments
   - Check network connectivity
   - Increase timeout in config

### Debug Mode
Run with debug logging:
```bash
python app.py  # Debug mode enabled by default
```

## Performance Optimization

### Reduce Scan Time
- Increase `gscn_step_size` (scan every 2nd or 3rd GSCN)
- Decrease `max_frequencies_per_band`
- Use specific bands instead of broad scans

### Improve Reliability
- Increase `retry_attempts` for unstable connections
- Adjust `timeout_seconds` based on your system
- Monitor logs for pattern identification

## Contributing

The modular architecture makes it easy to:
- Add new band definitions in `gscn_calculator.py`
- Extend USRP support in `usrp_controller.py`
- Add new configuration options in `config.py`
- Enhance the UI in `templates/index.html`

## License
GPL-3.0-or-later (same as original UHD/RFNoC components)