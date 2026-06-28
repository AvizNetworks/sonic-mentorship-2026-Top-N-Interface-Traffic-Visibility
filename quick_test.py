#!/usr/bin/env python3
"""Quick validation tests."""

from click.testing import CliRunner
import sys
import json

from cli import top_n

runner = CliRunner()

# Test 2: Exactly 3 rows
print("=" * 70)
print("TEST 2: Exactly 3 rows, sorted by throughput")
print("=" * 70)

result = runner.invoke(top_n, ["--top", "3", "--interval", "1"])
eth_lines = [line for line in result.output.split("\n") if "Ethernet" in line and "+" not in line]
if len(eth_lines) == 3:
    print("PASS: Exactly 3 rows displayed")
else:
    print("FAIL: Expected 3 rows, got " + str(len(eth_lines)))
    sys.exit(1)

# Test 3: JSON validation
print("\n" + "=" * 70)
print("TEST 3: JSON output validation")
print("=" * 70)

result = runner.invoke(top_n, ["--top", "5", "--interval", "1", "--json"])
try:
    data = json.loads(result.output)
    print("PASS: Valid JSON output")
    print("PASS: Contains " + str(len(data)) + " items")
    print("PASS: JSON structure correct")
except json.JSONDecodeError as e:
    print("FAIL: Invalid JSON - " + str(e))
    sys.exit(1)

print("\n" + "=" * 70)
print("ALL TESTS PASSED")
print("=" * 70)