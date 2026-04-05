"""
Traffic Analysis Engine for SONiC Top-N.
Handles calculating deltas efficiently and doing the heavy CPU sorting outside of Redis.
"""

class TrafficProcessor:
    # Handles 64-bit bounds commonly found in high-scale datacenter ASICs
    MAX_COUNTER_64 = (2**64) - 1

    @staticmethod
    def calc_rate_bps(t1_bytes: int, t0_bytes: int, interval: float) -> float:
        """
        Safely computes the Bits Per Second (bps). 
        Includes strict checks to handle hardware register overflow/rollovers.
        """
        if t1_bytes >= t0_bytes:
            diff = t1_bytes - t0_bytes
        else:
            # 64-bit wraps around to 0
            diff = (TrafficProcessor.MAX_COUNTER_64 - t0_bytes) + t1_bytes
        
        return (diff * 8) / interval

    @staticmethod
    def process_and_sort(t0_data: dict, t1_data: dict, interval: float, top_n: int) -> list:
        """
        Parses two dictionaries of raw counters, computes total BPS (RX+TX),
        and applies an O(N log N) Timsort.
        """
        stats_list = []
        for iface in t0_data.keys():
            if iface not in t1_data:
                continue
            
            try:
                rx = TrafficProcessor.calc_rate_bps(
                    t1_data[iface]["SAI_PORT_STAT_IF_IN_OCTETS"],
                    t0_data[iface]["SAI_PORT_STAT_IF_IN_OCTETS"],
                    interval
                )
                tx = TrafficProcessor.calc_rate_bps(
                    t1_data[iface]["SAI_PORT_STAT_IF_OUT_OCTETS"],
                    t0_data[iface]["SAI_PORT_STAT_IF_OUT_OCTETS"],
                    interval
                )
            except KeyError:
                continue

            total = rx + tx
            stats_list.append({
                "interface": iface,
                "rx_bps": rx,
                "tx_bps": tx,
                "total_bps": total
            })
            
        # O(N log N) sorting using Python's highly optimized engine
        stats_list.sort(key=lambda item: item["total_bps"], reverse=True)
        return stats_list[:top_n]

    @staticmethod
    def humanize(bps: float) -> str:
        """Format extremely large integers into Gbps/Mbps denominations."""
        units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps']
        u_idx = 0
        while bps >= 1000.0 and u_idx < len(units) - 1:
            bps /= 1000.0
            u_idx += 1
        return f"{bps:.2f} {units[u_idx]}"
