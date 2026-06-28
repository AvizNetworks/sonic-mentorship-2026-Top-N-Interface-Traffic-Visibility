#!/usr/bin/env python3
"""Test JSON output with REAL mode."""

import sys
import json

from cli import counters
from click.testing import CliRunner

runner = CliRunner()
result = runner.invoke(counters, ["--top", "5", "--interval", "1", "--json", "--mode", "REAL"])

try:
    data = json.loads(result.output)
    print("JSON output test")
    print("=" * 70)
    assert isinstance(data, list), "JSON should be a list"
    assert len(data) == 5, f"Expected 5 items, got {len(data)}"
    assert all("interface" in item for item in data), "Missing interface field"
    print("PASS: JSON output test passed")
except (json.JSONDecodeError, AssertionError) as e:
    print("FAIL: " + str(e))
    sys.exit(1)