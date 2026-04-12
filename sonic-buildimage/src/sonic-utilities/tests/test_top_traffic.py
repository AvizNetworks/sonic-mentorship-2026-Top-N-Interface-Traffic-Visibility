import os
import pytest
from unittest import mock
from click.testing import CliRunner

import show.main as show
import show.interfaces as interfaces

class TestTopTraffic:
    
    @classmethod
    def setup_class(cls):
        os.environ['UTILITIES_UNIT_TESTING'] = "1"

    @classmethod
    def teardown_class(cls):
        os.environ['UTILITIES_UNIT_TESTING'] = "0"

    def test_calculate_delta_normal(self):
        assert interfaces.calculate_delta(100, 500) == 400

    def test_calculate_delta_rollover(self):
        """Test the 64-bit hardware counter rollover safety."""
        t0 = (2**64) - 100
        t1 = 50
        assert interfaces.calculate_delta(t0, t1) == 150

    @mock.patch('time.sleep', return_value=None) 
    def test_top_traffic_cli(self, mock_sleep):
        """Test CLI pipeline formats."""
        runner = CliRunner()
        result = runner.invoke(show.cli, ['interfaces', 'top-traffic', '-n', '2', '-i', '1'])

        print(result.output)
        
        assert result.exit_code == 0, f"Command failed: {result.exception}"
        assert "RX bps" in result.output
        assert "Ethernet4" in result.output

    @mock.patch('time.sleep', return_value=None)
    def test_top_traffic_json(self, mock_sleep):
        """Test -j flag outputs JSON."""
        runner = CliRunner()
        result = runner.invoke(show.cli, ['interfaces', 'top-traffic', '-j'])

        print(result.output)
        
        assert result.exit_code == 0, f"Command failed: {result.exception}"
        assert '"interface": "Ethernet0"' in result.output
        assert '"rx_bps": 0' in result.output
