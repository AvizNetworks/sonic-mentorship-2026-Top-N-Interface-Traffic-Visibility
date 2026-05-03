# Sonic-Mentorship-2026-Top-N-Interface-Traffic-Visibility

## Project Overview

This repository contains a prototype implementation of the `show interfaces top-traffic` CLI command, designed to integrate with the SONiC `sonic-utilities` framework.

Instead of functioning as a standalone script, this code is structured to integrate directly into the `sonic-utilities` framework and follows its conventions, utilizing SONiC's official database connectors and testing standards.

This tool provides network administrators with real-time visibility into which network ports are transmitting and receiving the highest volume of data.

## Usage

```bash
show interfaces top-traffic [OPTIONS]
```

**Options:**

- `-n <int>`: Number of top interfaces to display.

- `-i <int>`: Polling interval (in seconds) between data snapshots.

- `-j`: Output results in raw JSON format.

### Examples:

```bash
# Show the top 2 ports with a 1-second polling interval
show interfaces top-traffic -n 2 -i 1

# Output the default top 5 ports in JSON format for automation
show interfaces top-traffic -j
```

----

## Files Modified/Added

The implementation is integrated into the existing `sonic-utilities` codebase. The following files were modified/added:

```bash
sonic-buildimage/src/sonic-utilities/show/interfaces/__init__.py
```

```bash
sonic-buildimage/src/sonic-utilities/tests/test_top_traffic.py
```

- `__init__.py` → Contains the CLI command (`top-traffic`) and core logic for data collection, processing, and output
- `test_top_traffic.py` → Contains unit tests validating CLI behavior and rollover-safe traffic calculations

---

## How the Code Works

This tool performs three core operations to calculate network speeds efficiently while minimizing load on the switch's control plane.

### 1. Data Snapshots (Redis Pipelining)

Inside the `get_top_traffic_data()` function, the tool first retrieves the `COUNTERS_PORT_NAME_MAP` to identify all active interfaces.

- To avoid the latency of iterating through hundreds of ports individually, the code utilizes **Redis Pipelining** (`client.pipeline()`).

- It queues up `pipe_a.hgetall()` commands for every port and executes them in a single batched request using `pipe_a.execute()` to capture the initial byte counts (`sample_a`).

- It then sleeps for the user-defined `interval` and repeats the pipelining process (`pipe_b.execute()`) to capture the second snapshot.

### 2. Traffic Calculation (64-bit Rollover Protection)

The raw ASIC hardware counters track bytes using the `SAI_PORT_STAT_IF_IN_OCTETS` (RX) and `SAI_PORT_STAT_IF_OUT_OCTETS` (TX) keys.

- These hardware counters have a physical maximum limit (a 64-bit integer). Once they reach maximum capacity, they reset back to zero.

- To safely calculate the network speed, the code passes the initial (`t0`) and current (`t1`) byte counts to the `calculate_delta()` helper function.

- If a reset occurred (`t1 < t0`), `calculate_delta()` detects this and applies the `MAX_64BIT` constant (`2**64`) to calculate the true forward progress. This ensures the resulting `rx_bps` and `tx_bps` metrics are always mathematically accurate and never evaluate to negative numbers.

### 3. Sorting & Displaying

Once the true byte delta is calculated:

1. It is multiplied by 8 and divided by the polling `interval` to convert it into Bits Per Second (`rx_bps` and `tx_bps`).

2. These are added together to calculate the `total_bps`.

3. The data is returned to the main `@interfaces.command('top-traffic')` CLI function, where the list is sorted in descending order (`port_traffic.sort(key=lambda x: x["total_bps"], reverse=True)`).

4. The list is sliced to the user's requested limit (`top_ports = port_traffic[:num]`).

5. The data is presented as a cleanly formatted terminal Table, or, if the `-j` flag is active, it outputs a raw JSON object via `json.dumps()` for external automation ingestion.

---

## Testing Methodology

A critical requirement of this project is proving the code operates safely. Inside `test_top_traffic.py`, the test suite performs the following:

- It sets `os.environ['UTILITIES_UNIT_TESTING'] = "1"`. This acts as a flag to enable test mode, allowing the code to use controlled mock data instead of connecting to a live Redis database.

- It uses `Click.CliRunner` to simulate a user executing the command in the terminal. It then automatically verifies that both the table headers and the JSON structure print accurately without crashing.

- It explicitly tests the 64-bit rollover logic to guarantee the mathematics hold up under hardware edge-cases.
