"""
Redis Data Generator / Connection Simulator.
Proves the capacity to handle zero-blocking architecture by utilizing Redis pipelines.
"""
import random
from typing import Dict

class FastCounterDB:
    """Mock implementation of the SONiC swsscommon Redis datastore."""
    
    def __init__(self, interface_count=128):
        self.interfaces = [f"Ethernet{i*4}" for i in range(interface_count - 8)]
        # Mix in LAG for LAG awareness mapping
        self.interfaces.extend([f"PortChannel{i}" for i in range(8)])
        self._rollover_test_port = "Ethernet64"

    def bulk_pipeline_fetch(self, simulated_pass: int, interval: float = 1.0) -> Dict[str, Dict[str, int]]:
        """
        Simulates executing a single Redis execute() yielding massive data quickly.
        simulated_pass=0 implies T0, simulated_pass=1 implies T1
        """
        data = {}
        rollover_val = (2**64) - 1

        for iface in self.interfaces:
            # Baseline deterministic generation
            base_in = (abs(hash(iface)) % 1000000) * 10
            base_out = (abs(hash(iface + "_tx")) % 1000000) * 10
            
            if iface == self._rollover_test_port and simulated_pass == 0:
                # Sitting on the exact edge of overflowing for T0 snapshot
                rx = rollover_val - 1000
                tx = rollover_val - 1000
            elif iface == self._rollover_test_port and simulated_pass == 1:
                # OVF happened, hardware rolls back past zero for T1 snapshot
                rx = 999000  # Added 1 million bytes during delta, crossing boundary
                tx = 999000
            elif iface == "Ethernet8":
                # Create one massive baseline talker to ensure it hits Top 1
                rx = base_in + (simulated_pass * int(1e9)) # 1 Gigabyte injected
                tx = base_out + (simulated_pass * int(1e9))
            else:
                rx = base_in + (simulated_pass * random.randint(1000, 100000))
                tx = base_out + (simulated_pass * random.randint(1000, 100000))

            data[iface] = {
                "SAI_PORT_STAT_IF_IN_OCTETS": rx,
                "SAI_PORT_STAT_IF_OUT_OCTETS": tx
            }
        
        return data
