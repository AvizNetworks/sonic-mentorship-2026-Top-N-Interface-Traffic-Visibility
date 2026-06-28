"""Traffic Processor Module for SONiC Top-N Interface Traffic.

Processes counter samples, calculates deltas and rates, handles counter rollovers.
"""

from typing import Dict, List


class TrafficProcessor:
    COUNTER_MAX = 2**64 - 1

    def calculate_delta(self, current: int, previous: int) -> int:
        if current >= previous:
            return current - previous
        return (self.COUNTER_MAX - previous) + current

    def process_counters(self, sample1: Dict[str, Dict[str, int]],
                         sample2: Dict[str, Dict[str, int]],
                         interval_seconds: float = 1.0) -> List[Dict]:
        results = []
        for interface in sample2.keys():
            if interface not in sample1:
                continue
            prev, curr = sample1[interface], sample2[interface]

            rx_delta = self.calculate_delta(curr['rx_bytes'], prev['rx_bytes'])
            tx_delta = self.calculate_delta(curr['tx_bytes'], prev['tx_bytes'])
            rx_pkt_delta = self.calculate_delta(curr['rx_packets'], prev['rx_packets'])
            tx_pkt_delta = self.calculate_delta(curr['tx_packets'], prev['tx_packets'])

            rx_rate = rx_delta / interval_seconds
            tx_rate = tx_delta / interval_seconds
            total = rx_rate + tx_rate

            results.append({
                'interface': interface,
                'rx_bytes': rx_delta,
                'tx_bytes': tx_delta,
                'rx_packets': rx_pkt_delta,
                'tx_packets': tx_pkt_delta,
                'rx_rate_bps': rx_rate,
                'tx_rate_bps': tx_rate,
                'total_throughput_bps': total
            })
        results.sort(key=lambda x: x['total_throughput_bps'], reverse=True)
        return results

    def filter_top_n(self, results: List[Dict], n: int) -> List[Dict]:
        return results[:n] if len(results) >= n else results[:]

    def format_table_output(self, results: List[Dict], n: int) -> str:
        from tabulate import tabulate
        headers = ['Interface', 'RX Bytes', 'TX Bytes', 'RX Pkts', 'TX Pkts',
                   'RX Rate (B/s)', 'TX Rate (B/s)', 'Total Throughput (B/s)']
        rows = [[
            stat['interface'],
            f"{stat['rx_bytes']:,}",
            f"{stat['tx_bytes']:,}",
            f"{stat['rx_packets']:,}",
            f"{stat['tx_packets']:,}",
            f"{stat['rx_rate_bps']:.2f}",
            f"{stat['tx_rate_bps']:.2f}",
            f"{stat['total_throughput_bps']:.2f}"
        ] for stat in results]
        return tabulate(rows, headers=headers, tablefmt='pretty')

    def format_json_output(self, results: List[Dict]) -> str:
        from json import dumps
        return dumps(results, indent=2)


def test_rollover():
    processor = TrafficProcessor()

    # Normal case: no rollover
    assert processor.calculate_delta(1500000, 1000000) == 500000

    # Rollover case: counter wrapped from 2^64-1 to small value
    delta = processor.calculate_delta(1000000, 18446744073709051615)
    expected = (processor.COUNTER_MAX - 18446744073709051615) + 1000000
    assert delta == expected, f"Rollover incorrect: {delta} != {expected}"

    # Partial rollover: counter wraps after adding 1M bytes
    prev = processor.COUNTER_MAX - 500000  # 500K before wrap
    curr = 499500                            # After wrap (500K - 500)
    delta = processor.calculate_delta(curr, prev)
    expected = (processor.COUNTER_MAX - prev) + curr
    assert delta == expected, f"Partial rollover incorrect: {delta} != {expected}"

    # Full wrap: from max to 0
    assert processor.calculate_delta(0, processor.COUNTER_MAX) == 0

    return True


if __name__ == '__main__':
    assert test_rollover(), "Rollover tests failed"
    print("All tests passed")