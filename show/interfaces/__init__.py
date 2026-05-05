"""
show/interfaces/__init__.py
===========================
Native sonic-utilities integration for `show interfaces top-traffic`.

This file is based on PR #4 (AbHash-RixE) with one focused addition:
  - format_bps() helper for human-readable rate display in table output

All other sonic-utilities interface commands are preserved as comments
(matching PR #4's approach) to show where this command fits in the
full __init__.py without requiring the full SONiC build environment.

Changes from PR #4:
  1. Added format_bps() function above the top_traffic command
  2. Updated table_data block to use format_bps() for RX/TX/Total columns
  3. Updated table headers from "RX bps / TX bps / Total bps"
     to "RX Rate / TX Rate / Total Rate"
  4. JSON output (-j flag) left unchanged — raw integers suit automation

BEFORE (PR #4 table output):
  Interface     RX bps        TX bps        Total bps
  Ethernet48    1240000000    987000000     2227000000

AFTER (this patch):
  Interface       RX Rate        TX Rate        Total Rate
  Ethernet48      1.24 Gb/s      987.00 Mb/s    2.23 Gb/s
"""

import json
import time

import click
from tabulate import tabulate
import utilities_common.cli as clicommon

# NOTE: The full sonic-utilities imports below are commented out
# following PR #4's approach, to allow standalone testing without
# the full SONiC build environment.

# import os
# import subprocess
# from utilities_common import constants
# import utilities_common.multi_asic as multi_asic_util
# from natsort import natsorted
# from sonic_py_common import multi_asic
# from sonic_py_common import device_info
# from swsscommon.swsscommon import ConfigDBConnector, SonicV2Connector
# from portconfig import get_child_ports
# import sonic_platform_base.sonic_sfp.sfputilhelper
# from . import portchannel
# from collections import OrderedDict
# from datetime import datetime
# HWSKU_JSON = 'hwsku.json'
# REDIS_HOSTIP = "127.0.0.1"

# ---------------------------------------------------------------------------
# All existing interface subcommands (alias, description, status, counters,
# transceiver, autoneg, fec, switchport, etc.) are preserved as comments
# below — identical to PR #4. Omitted here for brevity but present in the
# full sonic-utilities __init__.py.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 'top-traffic' subcommand ("show interfaces top-traffic")
# ---------------------------------------------------------------------------

MAX_64BIT = 2 ** 64


def calculate_delta(t0, t1):
    """
    Compute true byte delta between two counter snapshots.
    Handles 64-bit hardware counter rollover safely.

    When a counter wraps past UINT64_MAX back to zero,
    naive subtraction (t1 - t0) produces a massive negative-equivalent
    value. This function detects the wrap and computes the correct delta.

    Args:
        t0: Counter value at snapshot A (older)
        t1: Counter value at snapshot B (newer)

    Returns:
        True byte delta as a positive integer
    """
    if t1 >= t0:
        return t1 - t0
    return (MAX_64BIT - t0) + t1


def format_bps(bps: float) -> str:
    """
    Convert a raw bits-per-second value to a human-readable string.

    Auto-scales across Gb/s, Mb/s, Kb/s, and b/s thresholds.
    Applied to table output only — JSON output intentionally uses
    raw integers for automation compatibility.

    Args:
        bps: Rate in bits per second (float or int)

    Returns:
        Formatted string, e.g. "1.24 Gb/s", "987.00 Mb/s", "0 b/s"

    Examples:
        >>> format_bps(1_240_000_000)
        '1.24 Gb/s'
        >>> format_bps(987_000_000)
        '987.00 Mb/s'
        >>> format_bps(500_000)
        '500.00 Kb/s'
        >>> format_bps(800)
        '800 b/s'
        >>> format_bps(0)
        '0 b/s'
    """
    if bps >= 1e9:
        return f"{bps / 1e9:.2f} Gb/s"
    elif bps >= 1e6:
        return f"{bps / 1e6:.2f} Mb/s"
    elif bps >= 1e3:
        return f"{bps / 1e3:.2f} Kb/s"
    else:
        return f"{int(bps)} b/s"


def get_top_traffic_data(db, interval):
    """
    Fetch interface counters from COUNTERS_DB using Redis pipelining,
    compute per-interface traffic rates over the sampling interval.

    Uses two pipeline bulk-fetches (snapshot A, sleep, snapshot B)
    to avoid the N+1 query bottleneck of per-port HGET calls.

    Args:
        db:       SonicV2Connector database object
        interval: Sampling interval in seconds (int)

    Returns:
        List of dicts with keys:
            interface (str), rx_bps (int), tx_bps (int), total_bps (int)
        Returns [] if COUNTERS_PORT_NAME_MAP is empty or unavailable.
    """
    port_name_map = db.db.get_all(db.db.COUNTERS_DB, 'COUNTERS_PORT_NAME_MAP')
    if not port_name_map:
        return []

    client = db.db.get_redis_client(db.db.COUNTERS_DB)

    # ── Snapshot A ──────────────────────────────────────────────────────────
    pipe_a = client.pipeline()
    ports = list(port_name_map.keys())

    for port in ports:
        pipe_a.hgetall(f'COUNTERS:{port_name_map[port]}')

    raw_results_a = pipe_a.execute()

    sample_a = {}
    for i, raw_hash in enumerate(raw_results_a):
        if not raw_hash:
            continue
        sample_a[ports[i]] = {
            "rx": int(raw_hash.get(b'SAI_PORT_STAT_IF_IN_OCTETS',  b'0')),
            "tx": int(raw_hash.get(b'SAI_PORT_STAT_IF_OUT_OCTETS', b'0')),
        }

    time.sleep(interval)

    # ── Snapshot B ──────────────────────────────────────────────────────────
    pipe_b = client.pipeline()
    valid_ports = []

    for port in ports:
        if port in sample_a:
            pipe_b.hgetall(f'COUNTERS:{port_name_map[port]}')
            valid_ports.append(port)

    if not valid_ports:
        return []

    raw_results_b = pipe_b.execute()
    port_traffic = []

    for i, raw_hash in enumerate(raw_results_b):
        if not raw_hash:
            continue

        port   = valid_ports[i]
        data_a = sample_a[port]

        current_rx = int(raw_hash.get(b'SAI_PORT_STAT_IF_IN_OCTETS',  b'0'))
        current_tx = int(raw_hash.get(b'SAI_PORT_STAT_IF_OUT_OCTETS', b'0'))

        # Bytes → bits, divided by interval → bps
        rx_bps    = (calculate_delta(data_a["rx"], current_rx) * 8) // interval
        tx_bps    = (calculate_delta(data_a["tx"], current_tx) * 8) // interval
        total_bps = rx_bps + tx_bps

        port_traffic.append({
            "interface": port,
            "rx_bps":    rx_bps,
            "tx_bps":    tx_bps,
            "total_bps": total_bps,
        })

    return port_traffic


@interfaces.command('top-traffic')
@click.option('-n', '--num',      default=5, type=int,  help="Number of top interfaces to show")
@click.option('-i', '--interval', default=1, type=int,  help="Polling interval in seconds")
@click.option('-j', '--json', 'as_json', is_flag=True,  help="Output results in JSON format")
@clicommon.pass_db
def top_traffic(db, num, interval, as_json):
    """Show the top interfaces by real-time traffic volume."""

    if interval <= 0:
        interval = 1

    port_traffic = get_top_traffic_data(db, interval)

    if not port_traffic:
        click.echo("No counters available or no active traffic data found.")
        return

    port_traffic.sort(key=lambda x: x["total_bps"], reverse=True)
    top_ports = port_traffic[:num]

    # ── JSON output — raw integers for automation ────────────────────────
    if as_json:
        click.echo(json.dumps(top_ports, indent=4))
        return

    # ── Table output — human-readable rates ─────────────────────────────
    # format_bps() auto-scales to Gb/s, Mb/s, Kb/s, or b/s.
    # Raw bps integers are preserved in the data dict for JSON consumers.
    table_data = []
    for p in top_ports:
        table_data.append([
            p["interface"],
            format_bps(p["rx_bps"]),     # e.g. "1.24 Gb/s"
            format_bps(p["tx_bps"]),     # e.g. "987.00 Mb/s"
            format_bps(p["total_bps"]),  # e.g. "2.23 Gb/s"
        ])

    headers = ["Interface", "RX Rate", "TX Rate", "Total Rate"]
    click.echo(tabulate(table_data, headers=headers, stralign="right"))
