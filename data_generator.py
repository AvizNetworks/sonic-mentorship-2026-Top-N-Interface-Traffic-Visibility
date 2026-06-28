"""Mock Data Generator for SONiC Top-N."""

import random
from typing import Dict, List


def generate_sonic_interfaces(count: int = 10) -> List[str]:
    return [f"Ethernet{i}" for i in range(0, count * 4, 4)]


def generate_sample_series(interfaces: List[str], num_samples: int = 3) -> Dict[int, Dict[str, Dict[str, int]]]:
    series = {}
    prev = {iface: {'rx_bytes': 0, 'tx_bytes': 0, 'rx_packets': 0, 'tx_packets': 0} for iface in interfaces}
    
    for idx in range(num_samples):
        sample = {}
        for iface in interfaces:
            inc = {
                'rx_bytes': random.randint(100_000, 1_000_000),
                'tx_bytes': random.randint(100_000, 1_000_000),
                'rx_packets': random.randint(100, 1000),
                'tx_packets': random.randint(100, 1000)
            }
            sample[iface] = {
                'rx_bytes': prev[iface]['rx_bytes'] + inc['rx_bytes'],
                'tx_bytes': prev[iface]['tx_bytes'] + inc['tx_bytes'],
                'rx_packets': prev[iface]['rx_packets'] + inc['rx_packets'],
                'tx_packets': prev[iface]['tx_packets'] + inc['tx_packets']
            }
        prev = sample
        series[idx] = sample
    return series


def generate_with_rollover(interfaces: List[str], rollover_interface: str = 'Ethernet4') -> Dict[int, Dict[str, Dict[str, int]]]:
    """Generate counter data with simulated rollover for Ethernet4."""
    series = {}
    prev = {iface: {'rx_bytes': 0, 'tx_bytes': 0, 'rx_packets': 0, 'tx_packets': 0} for iface in interfaces}
    rollover_value = 2**64 - 1
    
    for idx in range(3):
        sample = {}
        for iface in interfaces:
            inc = {
                'rx_bytes': random.randint(100_000, 1_000_000),
                'tx_bytes': random.randint(100_000, 1_000_000),
                'rx_packets': random.randint(100, 1000),
                'tx_packets': random.randint(100, 1000)
            }
            
            if iface == rollover_interface and idx == 1:
                sample[iface] = {
                    'rx_bytes': rollover_value - 500_000,
                    'tx_bytes': rollover_value - 500_000,
                    'rx_packets': 100_000,
                    'tx_packets': 100_000
                }
            elif iface == rollover_interface and idx == 2:
                sample[iface] = {
                    'rx_bytes': 1_000_000,
                    'tx_bytes': 1_000_000,
                    'rx_packets': 10_000,
                    'tx_packets': 10_000
                }
            else:
                sample[iface] = {
                    'rx_bytes': prev[iface]['rx_bytes'] + inc['rx_bytes'],
                    'tx_bytes': prev[iface]['tx_bytes'] + inc['tx_bytes'],
                    'rx_packets': prev[iface]['rx_packets'] + inc['rx_packets'],
                    'tx_packets': prev[iface]['tx_packets'] + inc['tx_packets']
                }
        
        prev = sample
        series[idx] = sample
    return series