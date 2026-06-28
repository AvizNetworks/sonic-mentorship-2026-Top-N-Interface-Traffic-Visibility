# SONiC Top-N Interface Traffic Visibility

A prototype implementation for displaying top N interfaces by traffic in SONiC network operating system.

## Overview

This project implements a CLI command to show the top N interfaces carrying the highest traffic in SONiC deployments. It addresses the problem statement from the LFX Sonic Mentorship program where operators lack a simple mechanism to quickly identify high-traffic interfaces.

## Problem Statement

SONiC currently exposes per-interface traffic counters, but operators lack a simple mechanism to quickly identify which interfaces are carrying the highest traffic at any given time. In large-scale deployments, manually scanning counters is inefficient and error-prone.

## Solution

A new CLI command `show interfaces counters top-n` that:
- Displays top 5 interfaces by traffic (RX + TX combined)
- Supports configurable sampling interval
- Provides JSON output for automation
- Reads from COUNTERS_DB with proper OID resolution
- Handles 64-bit counter rollovers correctly

### Setup

```bash
# Navigate to project directory
cd sonic-mentorship-2026-Top-N-Interface-Traffic-Visibility

# Activate virtual environment (if using)
source venv/bin/activate

# Verify dependencies
pip list | grep -E 'click|tabulate|natsort'
```

## Usage

### Basic Usage

```bash
# Show top 5 interfaces by traffic
python cli.py top-n --top 5 --interval 1

# Show top 3 interfaces
python cli.py top-n --top 3 --interval 1

# Use 2-second sampling interval
python cli.py top-n --top 5 --interval 2
```

### JSON Output

```bash
# Get JSON output for automation
python cli.py top-n --top 5 --interval 1 --json
```

Output:
```json
[
  {
    "interface": "Ethernet0",
    "rx_bytes": 1234567,
    "tx_bytes": 9876543,
    "rx_packets": 12345,
    "tx_packets": 98765,
    "rx_rate_bps": 1234567.0,
    "tx_rate_bps": 9876543.0,
    "total_throughput_bps": 11111110.0,
    ...
  },
  ...
]
```

## Architecture

### Core Modules

1. **data_generator.py** - Mock data generator
   - Generates realistic SONiC interface counter data
   - Interface naming: Ethernet0, Ethernet4, Ethernet8, ...
   - Supports counter rollover scenarios

2. **db_connector.py** - COUNTERS_DB connector
   - Two-stage OID resolution
   - Mock and Real modes
   - Graceful fallback when swsscommon unavailable

3. **traffic_processor.py** - Traffic analysis engine
   - Delta calculation with rollover handling
   - Rate computation (bytes/sec, packets/sec)
   - Sorting by total throughput

4. **cli.py** - Click CLI command
   - `top-n` command with options: --top, --interval, --json, --mode

### OID Resolution Flow

```
1. Query COUNTERS_PORT_NAME_MAP
   → Ethernet0 → oid:0x1000000000001
   
2. Query COUNTERS:oid:0x1000000000001
   → SAI_PORT_STAT_IF_IN_OCTETS: 123456
   → SAI_PORT_STAT_IF_OUT_OCTETS: 789012
```

## Counter Rollover Handling

64-bit hardware counters can wrap from `2**64 - 1` back to `0`. The implementation handles this:

```python
def calculate_delta(current, previous):
    if current >= previous:
        delta = current - previous
    else:
        # Rollover case
        delta = (2**64 - previous) + current
    return delta
```

Unit tests in `traffic_processor.py` prove this logic works correctly.

## Tests

### Run All Tests

```bash
python final_validation.py
```

### Acceptance Criteria (All 8 Must Pass)

1. ✅ End-to-end CLI run without exceptions
2. ✅ Exactly N rows with --top N
3. ✅ Valid JSON output with --json
4. ✅ Graceful clamping when N > available interfaces
5. ✅ Counter rollover handling unit tests
6. ✅ Correct SONiC interface naming (Ethernet0, Ethernet4...)
7. ✅ natsort for proper interface ordering
8. ✅ Mock and Real mode handling

### Verify JSON Output

```bash
python cli.py top-n --top 5 --json | python -m json.tool
```

## Integration with sonic-utilities

See `integration_notes.md` for detailed integration steps.

### Command Path

The command integrates as:
```bash
show interfaces counters top-n [OPTIONS]
```

### Files to Create

1. `show/interfaces/top_n.py` - CLI command module
2. Register in `show/interfaces/__init__.py`

## Project Structure

```
sonic/
├── venv/                    # Python virtual environment
├── data_generator.py        # Mock data generation
├── db_connector.py          # COUNTERS_DB connector
├── traffic_processor.py     # Traffic analysis
├── cli.py                   # Click CLI command
├── test_sonic.py           # End-to-end tests
├── quick_test.py           # Quick validation tests
├── integration_notes.md     # Integration guide
└── README.md               # This file
```

## Example Output

```
+------------+----------+----------+---------+---------+---------------+---------------+------------------------+
| Interface  | RX Bytes | TX Bytes | RX Pkts | TX Pkts | RX Rate (B/s) | TX Rate (B/s) | Total Throughput (B/s) |
+------------+----------+----------+---------+---------+---------------+---------------+------------------------+
| Ethernet0  | 956,802  | 785,720  |   138   |   670   |   956802.00   |   785720.00   |       1742522.00       |
| Ethernet16 | 839,985  | 791,808  |   495   |   661   |   839985.00   |   791808.00   |       1631793.00       |
| Ethernet12 | 838,437  | 713,284  |   412   |   596   |   838437.00   |   713284.00   |       1551721.00       |
| Ethernet24 | 539,177  | 918,704  |   933   |   957   |   539177.00   |   918704.00   |       1457881.00       |
| Ethernet32 | 877,038  | 559,337  |   760   |   429   |   877038.00   |   559337.00   |       1436375.00       |
+------------+----------+----------+---------+---------+---------------+---------------+------------------------+
```

## LFX Mentorship Details

- **Project:** Top-N Interface Traffic Visibility
- **Mentors:** Nikhil Moray (nikhil@aviznetworks.com), Madhu Paluru (madhuapa@aviznetworks.com)
- **Organization:** SONiC
- **Timeline:** April 10, 2026 deadline