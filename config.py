#!/usr/bin/env python3
"""
Configuration management for 5G NR SSB Signal Scanner
"""

import os
import json
from pathlib import Path

class Config:
    """Configuration class for managing application settings"""
    
    def __init__(self, config_file=None):
        self.config_file = config_file or os.path.join(os.path.dirname(__file__), 'config.json')
        self.settings = self._load_default_config()
        self._load_config_file()
    
    def _load_default_config(self):
        """Load default configuration values"""
        return {
            'usrp': {
                'executable_path': '/home/user/Projects/NR5G/rfnoc_detectSSB/build/apps/init_ssb_block',
                'default_args': 'type=x300',
                'default_gain': 30,
                'default_ddc_rate': 7.68e6,
                'default_rx_sig_length': 7680000,
                'timeout_seconds': 60,
                'retry_attempts': 2
            },
            'paths': {
                'data_directory': '/home/user/Projects/NR5G/AppUI/data',
                'log_directory': '/home/user/Projects/NR5G/AppUI/logs',
                'temp_directory': '/tmp/ssb_scanner'
            },
            'scanning': {
                'gscn_step_size': 1,  # Sample every Nth GSCN
                'max_frequencies_per_band': 50,
                'parallel_scans': False
            },
            'ui': {
                'default_band': 'n78',
                'refresh_interval_ms': 1000,
                'max_log_entries': 1000
            }
        }
    
    def _load_config_file(self):
        """Load configuration from file if it exists"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    file_config = json.load(f)
                    self._deep_update(self.settings, file_config)
        except Exception as e:
            print(f"Warning: Could not load config file {self.config_file}: {e}")
    
    def _deep_update(self, base_dict, update_dict):
        """Recursively update nested dictionaries"""
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get(self, key_path, default=None):
        """Get configuration value using dot notation (e.g., 'usrp.executable_path')"""
        keys = key_path.split('.')
        value = self.settings
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key_path, value):
        """Set configuration value using dot notation"""
        keys = key_path.split('.')
        config = self.settings
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
    
    def validate_paths(self):
        """Validate and create necessary directories"""
        paths_to_check = [
            self.get('paths.data_directory'),
            self.get('paths.log_directory'),
            self.get('paths.temp_directory')
        ]
        
        for path in paths_to_check:
            if path:
                try:
                    os.makedirs(path, exist_ok=True)
                except Exception as e:
                    print(f"Warning: Could not create directory {path}: {e}")
        
        # Check if USRP executable exists
        usrp_path = self.get('usrp.executable_path')
        if usrp_path and not os.path.exists(usrp_path):
            print(f"Warning: USRP executable not found at {usrp_path}")
            return False
        
        return True
    
    def get_usrp_command_template(self):
        """Get USRP command template with placeholders"""
        executable = self.get('usrp.executable_path')
        args = self.get('usrp.default_args')
        
        return [
            executable,
            '--args', '{args}',
            '--freq', '{frequency}',
            '--gain', '{gain}',
            '--ddc-rate', '{ddc_rate}',
            '--rx-sig-length', '{rx_sig_length}'
        ]

# Global configuration instance
config = Config()