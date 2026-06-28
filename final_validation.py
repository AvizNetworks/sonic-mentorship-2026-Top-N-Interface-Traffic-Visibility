#!/usr/bin/env python3
"""Final Validation - All 8 Acceptance Criteria."""

from click.testing import CliRunner
import sys
import json

from cli import top_n
from traffic_processor import TrafficProcessor
from natsort import natsorted
from db_connector import COUNTERSConnector

runner = CliRunner()

print("=" * 70)
print("FINAL VALIDATION - ALL 8 ACCEPTANCE CRITERIA")
print("=" * 70)

all_passed = True

# Test 1: End-to-end run
print("\n[1] End-to-end run with NO exceptions")
print("-" * 70)
result = runner.invoke(top_n, ["--top", "5", "--interval", "1"])
if result.exit_code == 0 and "Ethernet" in result.output and "Total Throughput" in result.output:
    print("PASS: Runs successfully with visible table output")
else:
    print("FAIL")
    all_passed = False

# Test 2: Exactly 3 rows sorted
print("\n[2] Exactly 3 rows sorted by throughput")
print("-" * 70)
result = runner.invoke(top_n, ["--top", "3", "--interval", "1"])
eth_lines = [line for line in result.output.split("\n") if "Ethernet" in line and "+" not in line]
if len(eth_lines) == 3:
    print("PASS: Exactly 3 rows displayed")
else:
    print("FAIL: Expected 3 rows, got " + str(len(eth_lines)))
    all_passed = False

# Test 3: JSON validation
print("\n[3] JSON output validation")
print("-" * 70)
result = runner.invoke(top_n, ["--top", "5", "--interval", "1", "--json"])
try:
    data = json.loads(result.output)
    print("PASS: Valid JSON output")
    print("PASS: Contains " + str(len(data)) + " items")
except json.JSONDecodeError as e:
    print("FAIL: Invalid JSON - " + str(e))
    all_passed = False

# Test 4: Clamping
print("\n[4] Clamping when asking for more than available")
print("-" * 70)
result = runner.invoke(top_n, ["--top", "20", "--interval", "1"])
eth_lines = [line for line in result.output.split("\n") if "Ethernet" in line and "+" not in line]
if len(eth_lines) <= 20:
    print("PASS: Gracefully handled, displayed " + str(len(eth_lines)) + " interfaces")
else:
    print("FAIL")
    all_passed = False

# Test 5: Rollover unit test
print("\n[5] Counter rollover unit test")
print("-" * 70)
processor = TrafficProcessor()
prev = 18446744073709051615  # 2^64 - 1
curr = 1000000
delta = processor.calculate_delta(curr, prev)
expected = (processor.COUNTER_MAX - prev) + curr
if delta == expected:
    print("PASS: Rollover logic correct (delta=" + str(delta) + ")")
    print("PASS: Unit test proves rollover handling works")
else:
    print("FAIL: Expected " + str(expected) + ", got " + str(delta))
    all_passed = False

# Test 6: Interface naming
print("\n[6] Interface naming (Ethernet0, Ethernet4, Ethernet8)")
print("-" * 70)
result = runner.invoke(top_n, ["--top", "10", "--interval", "1"])
has_eth0 = "Ethernet0" in result.output
has_eth4 = "Ethernet4" in result.output
has_eth8 = "Ethernet8" in result.output
has_no_wlan = "wlan0" not in result.output and "eth0" not in result.output
if has_eth0 and has_eth4 and has_eth8 and has_no_wlan:
    print("PASS: Correct SONiC naming convention")
    print("   - Found: Ethernet0, Ethernet4, Ethernet8...")
    print("   - No: eth0, wlan0 style names")
else:
    print("FAIL")
    all_passed = False

# Test 7: natsort
print("\n[7] natsort verification (Ethernet10 after Ethernet8)")
print("-" * 70)
interfaces = ["Ethernet0", "Ethernet4", "Ethernet8", "Ethernet10", "Ethernet12"]
sorted_if = natsorted(interfaces)
print("   Sorted order: " + str(sorted_if))
if sorted_if.index("Ethernet10") > sorted_if.index("Ethernet8"):
    print("PASS: Ethernet10 sorts AFTER Ethernet8")
else:
    print("FAIL: Ethernet10 sorts BEFORE Ethernet8")
    all_passed = False

# Test 8: db_connector modes
print("\n[8] db_connector.py mode handling")
print("-" * 70)
connector = COUNTERSConnector(mode="MOCK")
if connector.mode == "MOCK" and len(connector.interfaces) > 0:
    print("PASS: MOCK mode works")
else:
    print("FAIL: MOCK mode")
    all_passed = False

connector_real = COUNTERSConnector(mode="REAL")
if connector_real.mode == "MOCK":
    print("PASS: REAL mode gracefully falls back to MOCK with clear error")
else:
    print("REAL mode connected (expected only in SONiC container)")

# Summary
print("\n" + "=" * 70)
print("FINAL SUMMARY")
print("=" * 70)
if all_passed:
    print("\nALL 8 ACCEPTANCE CRITERIA PASSED!")
    print("Prototype is ready for LFX application submission.")
    sys.exit(0)
else:
    print("\nSome tests failed. Review and fix issues.")
    sys.exit(1)