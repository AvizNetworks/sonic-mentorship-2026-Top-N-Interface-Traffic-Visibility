"""SONiC COUNTERS_DB Connector Module."""

import random
import json
import sys
from typing import Dict, List
from data_generator import generate_sample_series, generate_with_rollover


class COUNTERSConnector:
    SAI_COUNTERS = {
        'rx_bytes': 'SAI_PORT_STAT_IF_IN_OCTETS',
        'tx_bytes': 'SAI_PORT_STAT_IF_OUT_OCTETS',
        'rx_packets': 'SAI_PORT_STAT_IF_IN_PACKETS',
        'tx_packets': 'SAI_PORT_STAT_IF_OUT_PACKETS'
    }

    def __init__(self, mode: str = 'MOCK', quiet: bool = False):
        self.mode = mode.upper()
        self.connector = None
        self.mock_data = None
        self.interfaces = None
        self.quiet = quiet

        if self.mode == 'MOCK':
            self._setup_mock_data()
        elif self.mode == 'REAL':
            self._setup_real_mode(quiet)
        else:
            raise ValueError(f"Invalid mode: {mode}")

    def _setup_mock_data(self):
        interfaces = [f"Ethernet{i}" for i in range(0, 10 * 4, 4)]
        self.interfaces = interfaces
        self.mock_data = generate_sample_series(interfaces, num_samples=3)

    def _setup_real_mode(self, quiet: bool = False):
        try:
            from swsscommon.swsscommon import SonicV2Connector
            self.connector = SonicV2Connector()
        except ImportError:
            self.mode = 'MOCK'
            self._setup_mock_data()
            return
        try:
            self.connector.connect()
        except Exception:
            self.mode = 'MOCK'
            self._setup_mock_data()

    def _get_interface_to_oid_mapping(self) -> Dict[str, str]:
        if self.mode == 'MOCK':
            return {
                f"Ethernet{i}": f"oid:{0x1000000000001 + i}"
                for i in range(len(self.interfaces))
            }
        return {}

    def _get_counters_for_oid(self, oid: str) -> Dict[str, int]:
        if self.mode == 'MOCK':
            base = random.randint(1_000_000, 100_000_000)
            return {
                self.SAI_COUNTERS['rx_bytes']: base + random.randint(0, 1_000_000),
                self.SAI_COUNTERS['tx_bytes']: base + random.randint(0, 1_000_000),
                self.SAI_COUNTERS['rx_packets']: base // 1500 + random.randint(0, 100),
                self.SAI_COUNTERS['tx_packets']: base // 1500 + random.randint(0, 100)
            }
        return {}

    def get_counters(self, sample_idx: int = 0) -> Dict[str, Dict[str, int]]:
        if self.mode == 'MOCK':
            return self.mock_data[sample_idx]
        result = {}
        interface_to_oid = self._get_interface_to_oid_mapping()
        for interface_name, oid in interface_to_oid.items():
            counters = self._get_counters_for_oid(oid)
            result[interface_name] = {}
            for sai_key, value in counters.items():
                for counter_name, skey in self.SAI_COUNTERS.items():
                    if sai_key == skey:
                        result[interface_name][counter_name] = value
        return result

    def get_counters_raw(self, sample_idx: int = 0) -> Dict[str, Dict[str, int]]:
        if self.mode == 'MOCK':
            result = {}
            for interface, counters in self.mock_data[sample_idx].items():
                result[interface] = {self.SAI_COUNTERS[k]: v for k, v in counters.items()}
            return result
        return self.get_counters(sample_idx)

    def close(self):
        if self.connector:
            try:
                self.connector.close()
            except Exception:
                pass


def get_counters_from_mock() -> Dict[str, Dict[str, int]]:
    return COUNTERSConnector(mode='MOCK').get_counters()


def get_counters_from_real() -> Dict[str, Dict[str, int]]:
    return COUNTERSConnector(mode='REAL').get_counters()