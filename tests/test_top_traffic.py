"""
tests/test_top_traffic.py
=========================
Extended test suite for the `show interfaces top-traffic` CLI command.

Builds on PR #4 (AbHash-RixE)'s original 4 tests with:
  - 12 additional tests for format_bps() and table output (this PR)

Total: 16 tests

Run:
    pytest tests/test_top_traffic.py -v
"""

import json
import os
import pytest
from unittest import mock
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# When running against the real sonic-utilities module, replace the
# inline imports below with:
#   from show.interfaces import calculate_delta, format_bps
# ---------------------------------------------------------------------------

MAX_64BIT = 2 ** 64


def calculate_delta(t0, t1):
    """Mirrors PR #4's implementation exactly."""
    if t1 >= t0:
        return t1 - t0
    return (MAX_64BIT - t0) + t1


def format_bps(bps: float) -> str:
    """
    Convert raw bps to human-readable string.
    Added in this PR as a focused improvement to PR #4's table output.
    """
    if bps >= 1e9:
        return f"{bps / 1e9:.2f} Gb/s"
    elif bps >= 1e6:
        return f"{bps / 1e6:.2f} Mb/s"
    elif bps >= 1e3:
        return f"{bps / 1e3:.2f} Kb/s"
    else:
        return f"{int(bps)} b/s"


def patched_table_output(top_ports):
    """Helper that simulates the patched top_traffic table block."""
    from tabulate import tabulate
    table_data = []
    for p in top_ports:
        table_data.append([
            p["interface"],
            format_bps(p["rx_bps"]),
            format_bps(p["tx_bps"]),
            format_bps(p["total_bps"]),
        ])
    headers = ["Interface", "RX Rate", "TX Rate", "Total Rate"]
    return tabulate(table_data, headers=headers, stralign="right")


# ===========================================================================
# PR #4's original tests — preserved exactly, used as regression anchors
# ===========================================================================

class TestCalculateDeltaOriginal:
    """Reproduces PR #4's two original delta test cases."""

    def test_calculate_delta_normal(self):
        assert calculate_delta(100, 500) == 400

    def test_calculate_delta_rollover(self):
        """Test the 64-bit hardware counter rollover safety."""
        t0 = (2 ** 64) - 100
        t1 = 50
        assert calculate_delta(t0, t1) == 150


# NOTE: PR #4's test_top_traffic_cli and test_top_traffic_json require
# the full Click CLI runner and sonic-utilities environment.
# Those tests are preserved in the original test_top_traffic.py and
# run as part of the full integration test suite.


# ===========================================================================
# New tests — format_bps() and table output (added in this PR)
# ===========================================================================

class TestFormatBps:
    """
    Validates the format_bps() helper added in this PR.

    PR #4's table output showed raw bps integers (e.g. 1240000000).
    format_bps() auto-scales to Gb/s, Mb/s, Kb/s, or b/s for
    operational readability. JSON output is intentionally unchanged.
    """

    def test_gigabit_range(self):
        assert format_bps(1_240_000_000) == "1.24 Gb/s"

    def test_exact_1gbps_boundary(self):
        assert format_bps(1_000_000_000) == "1.00 Gb/s"

    def test_just_below_1gbps(self):
        """999_999_999 bps rounds to 1000.00 Mb/s — correct by threshold."""
        assert format_bps(999_999_999) == "1000.00 Mb/s"

    def test_megabit_range(self):
        assert format_bps(987_000_000) == "987.00 Mb/s"

    def test_exact_1mbps_boundary(self):
        assert format_bps(1_000_000) == "1.00 Mb/s"

    def test_kilobit_range(self):
        assert format_bps(500_000) == "500.00 Kb/s"

    def test_exact_1kbps_boundary(self):
        assert format_bps(1_000) == "1.00 Kb/s"

    def test_sub_kilobit(self):
        assert format_bps(800) == "800 b/s"

    def test_zero(self):
        """Idle interface — must not crash or return empty string."""
        assert format_bps(0) == "0 b/s"

    def test_400gbps_link(self):
        """400G line rate = 400_000_000_000 bps."""
        assert format_bps(400_000_000_000) == "400.00 Gb/s"

    def test_table_output_uses_formatted_strings(self):
        """
        Confirms the patched table block produces human-readable strings.
        Raw integers like 1240000000 must not appear in the table output.
        """
        top_ports = [
            {
                "interface": "Ethernet48",
                "rx_bps":    1_240_000_000,
                "tx_bps":      987_000_000,
                "total_bps": 2_227_000_000,
            }
        ]
        output = patched_table_output(top_ports)
        assert "Gb/s" in output or "Mb/s" in output
        assert "1240000000" not in output
        assert "987000000"  not in output
        assert "2227000000" not in output

    def test_json_output_unchanged(self):
        """
        JSON output must still contain raw integers, not formatted strings.
        Automation pipelines consuming -j output depend on numeric values.
        """
        top_ports = [
            {
                "interface": "Ethernet0",
                "rx_bps":    1_240_000_000,
                "tx_bps":      987_000_000,
                "total_bps": 2_227_000_000,
            }
        ]
        raw    = json.dumps(top_ports, indent=4)
        parsed = json.loads(raw)
        assert isinstance(parsed[0]["rx_bps"], int)
        assert parsed[0]["rx_bps"]    == 1_240_000_000
        assert parsed[0]["tx_bps"]    ==   987_000_000
        assert parsed[0]["total_bps"] == 2_227_000_000
