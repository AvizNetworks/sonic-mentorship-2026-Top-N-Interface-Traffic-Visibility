import pytest
from src.traffic_analysis import TrafficProcessor

def test_64_bit_integer_rollover_logic():
    """
    Validates that a 64-bit hardware integer overflowing across 
    the boundaries evaluates bandwidth mathematically perfectly and not into negatives.
    """
    t0_byte_value = (2**64) - 1000  # Right at the edge of overflowing
    t1_byte_value = 9000            # Overflowed + wrapped around + advanced 9000 bytes

    # The actual distance traveled was 1000 + 9000 = 10000 bytes
    expected_bits = 10000 * 8
    
    interval_time = 1.0  # 1 second
    calculated_bits_per_sec = TrafficProcessor.calc_rate_bps(t1_byte_value, t0_byte_value, interval_time)
    
    assert calculated_bits_per_sec == expected_bits, f"Expected {expected_bits} Mbps after rollover, got {calculated_bits_per_sec}"

def test_sorting_and_slicing_top_results():
    """Validates the fast Timsort functionality returning strictly Top 2 instances."""
    t0 = {
        "Ethernet0": {"SAI_PORT_STAT_IF_IN_OCTETS": 0, "SAI_PORT_STAT_IF_OUT_OCTETS": 0},
        "Ethernet4": {"SAI_PORT_STAT_IF_IN_OCTETS": 0, "SAI_PORT_STAT_IF_OUT_OCTETS": 0},
        "Ethernet8": {"SAI_PORT_STAT_IF_IN_OCTETS": 0, "SAI_PORT_STAT_IF_OUT_OCTETS": 0},
    }
    t1 = {
        "Ethernet0": {"SAI_PORT_STAT_IF_IN_OCTETS": 1000, "SAI_PORT_STAT_IF_OUT_OCTETS": 0}, # 1000 bytes
        "Ethernet4": {"SAI_PORT_STAT_IF_IN_OCTETS": 5000, "SAI_PORT_STAT_IF_OUT_OCTETS": 5000}, # 10000 bytes
        "Ethernet8": {"SAI_PORT_STAT_IF_IN_OCTETS": 9000, "SAI_PORT_STAT_IF_OUT_OCTETS": 0}, # 9000 bytes
    }
    
    results = TrafficProcessor.process_and_sort(t0, t1, 1.0, 2)
    
    assert len(results) == 2
    # Ensure descending Timsort functioned
    assert results[0]["interface"] == "Ethernet4"
    assert results[1]["interface"] == "Ethernet8"
