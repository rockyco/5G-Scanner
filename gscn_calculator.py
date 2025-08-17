#!/usr/bin/env python3
"""
GSCN frequency calculation module
Separated from main app for better organization
"""

def gscn_to_frequency(gscn):
    """
    Convert GSCN to frequency using correct 3GPP TS 38.104 formula.
    Based on MATLAB hSynchronizationRasterInfo.gscn2frequency implementation.
    """
    if 1 < gscn < 7499:
        # For GSCN in range 2-7498 (frequencies < 3000 MHz)
        gscn_mod = gscn % 3
        if gscn_mod == 2:
            m = 1
        elif gscn_mod == 1:
            m = 5
        else:  # gscn_mod == 0
            m = 3
        
        n = (gscn - (m - 3) / 2) / 3
        frequency = n * 1200e3 + m * 50e3  # frequency in Hz
        return frequency
        
    elif 7498 < gscn < 22256:
        # For GSCN in range 7499-22255 (frequencies 3000 MHz - 24.25 GHz)
        n = gscn - 7499
        frequency = n * 1.44e6 + 3000e6  # frequency in Hz
        return frequency
        
    elif 22255 < gscn < 26640:
        # For GSCN in range 22256-26639 (frequencies > 24.25 GHz, FR2)
        n = gscn - 22256
        frequency = n * 17.28e6 + 24250.08e6  # frequency in Hz
        return frequency
        
    else:
        raise ValueError(f"Invalid GSCN value: {gscn}. Valid ranges: 2-7498, 7499-22255, 22256-26639")

# 5G NR Band information for Australia based on 3GPP TS 38.101-1 V18.2 and local allocations
NR_BANDS = {
    'n1': {
        'name': 'n1 (2100 MHz)',
        'freq_range_mhz': '2110-2170',
        'gscn_ranges': [{'gscn': list(range(5279, 5420)), 'scs': 15}]
    },
    'n3': {
        'name': 'n3 (1800 MHz)',
        'freq_range_mhz': '1805-1880',
        'gscn_ranges': [{'gscn': list(range(4517, 4694)), 'scs': 15}]
    },
    'n5': {
        'name': 'n5 (850 MHz)',
        'freq_range_mhz': '869-894',
        'gscn_ranges': [
            {'gscn': list(range(2177, 2231)), 'scs': 15},
            {'gscn': list(range(2183, 2225)), 'scs': 30}
        ]
    },
    'n7': {
        'name': 'n7 (2600 MHz)',
        'freq_range_mhz': '2620-2690',
        'gscn_ranges': [{'gscn': list(range(6554, 6719)), 'scs': 15}]
    },
    'n8': {
        'name': 'n8 (900 MHz)',
        'freq_range_mhz': '925-960',
        'gscn_ranges': [{'gscn': list(range(2318, 2396)), 'scs': 15}]
    },
    'n26': {
        'name': 'n26 (850 MHz)',
        'freq_range_mhz': '859-894',
        'gscn_ranges': [] # GSCN range not explicitly defined
    },
    'n28': {
        'name': 'n28 (700 MHz)',
        'freq_range_mhz': '758-803',
        'gscn_ranges': [{'gscn': list(range(1901, 2003)), 'scs': 15}]
    },
    'n40': {
        'name': 'n40 (2300 MHz)',
        'freq_range_mhz': '2300-2400',
        'gscn_ranges': [{'gscn': list(range(5762, 5990)), 'scs': 30}]
    },
    'n78': {
        'name': 'n78 (3500 MHz)',
        'freq_range_mhz': '3300-3800',
        'gscn_ranges': [{'gscn': list(range(7711, 8052)), 'scs': 30}]
    },
}

def calculate_gscn_frequencies(band, max_frequencies=50, step_size=1):
    """
    Calculate GSCN frequencies for a given band using band-specific GSCN ranges.
    """
    if band not in NR_BANDS:
        return []
    
    band_info = NR_BANDS[band]
    frequencies = []
    
    for gscn_range in band_info.get('gscn_ranges', []):
        gscn_list = gscn_range['gscn']
        scs = gscn_range['scs']
        
        sampled_gscns = gscn_list[::step_size]
        
        if len(frequencies) + len(sampled_gscns) > max_frequencies:
            remaining = max_frequencies - len(frequencies)
            sampled_gscns = sampled_gscns[:remaining]
        
        for gscn in sampled_gscns:
            try:
                freq = gscn_to_frequency(gscn)
                frequencies.append({'gscn': gscn, 'frequency': freq, 'scs': scs})
            except ValueError:
                continue
            
            if len(frequencies) >= max_frequencies:
                break
        
        if len(frequencies) >= max_frequencies:
            break
            
    frequencies.sort(key=lambda x: x['frequency'])
    return frequencies

def get_band_info(band):
    """Get detailed information about a specific band"""
    if band not in NR_BANDS:
        return None
    
    band_data = NR_BANDS[band].copy()
    total_gscns = sum(len(gr.get('gscn', [])) for gr in band_data.get('gscn_ranges', []))
    band_data['max_frequencies'] = total_gscns
    
    # For compatibility with the frontend, add scs_khz from the first range
    if band_data.get('gscn_ranges'):
        band_data['scs_khz'] = band_data['gscn_ranges'][0]['scs']
    else:
        band_data['scs_khz'] = 'N/A'

    return band_data

def get_all_bands():
    """Return all available bands with their details including max frequencies."""
    bands_with_details = {}
    for name in NR_BANDS:
        details = get_band_info(name)
        if details:
            bands_with_details[name] = details
    return bands_with_details

def validate_gscn(gscn):
    """Validate if a GSCN value is valid"""
    try:
        gscn_to_frequency(gscn)
        return True
    except ValueError:
        return False

def frequency_to_band(frequency_hz):
    """Find which band(s) a frequency belongs to"""
    frequency_mhz = frequency_hz / 1e6
    matching_bands = []
    
    for band_id, band_info in NR_BANDS.items():
        try:
            min_freq, max_freq = map(float, band_info['freq_range_mhz'].split('-'))
            if min_freq <= frequency_mhz <= max_freq:
                matching_bands.append(band_id)
        except (ValueError, KeyError):
            continue # Skip bands with malformed frequency range
    
    return matching_bands