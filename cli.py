#!/usr/bin/env python3
"""
CLI Application simulating the integration into sonic-utilities.
Demonstrates extracting and sorting Top N heavily utilized datacenter interfaces natively.
"""
import click
import json
import time
from tabulate import tabulate

from src.redis_client import FastCounterDB
from src.traffic_analysis import TrafficProcessor

@click.group()
def cli():
    """SONiC Observability - Extracted top-n utility prototype."""
    pass

@cli.command('top-n')
@click.option('--top', '-n', default=5, type=int, help='Limit the scope to the top N interface talkers.')
@click.option('--interval', '-i', default=1.0, type=float, help='Wait time between reading hardware deltas (seconds).')
@click.option('--json-out', '-j', is_flag=True, help='Produce exact JSON payload for platforms like Aviz ONES.')
def fetch_top_talkers(top: int, interval: float, json_out: bool):
    """Real-time network traffic ranking via native ASIC telemetry."""
    
    # Emulates the SonicV2Connector
    db = FastCounterDB()
    
    if not json_out:
        click.echo("[*] Executing zero-blocking Redis Pipeline snapshot T0...")
    
    t0_data = db.bulk_pipeline_fetch(0, interval)
    
    if not json_out:
        click.echo(f"[*] Aggregating delta variables, sleeping {interval}s...")
    
    time.sleep(interval)
    
    if not json_out:
        click.echo("[*] Executing snapshot T1. Sorting results natively (O(N logN))...")
        
    t1_data = db.bulk_pipeline_fetch(1, interval)
    
    # Send it to the optimized mathematical core
    top_results = TrafficProcessor.process_and_sort(t0_data, t1_data, interval, top)
    
    if json_out:
        click.echo(json.dumps(top_results, indent=2))
        return
    
    # Process for terminal rendering
    render_table = []
    for rank, port in enumerate(top_results, start=1):
        render_table.append([
            rank,
            port["interface"],
            TrafficProcessor.humanize(port["rx_bps"]),
            TrafficProcessor.humanize(port["tx_bps"]),
            TrafficProcessor.humanize(port["total_bps"])
        ])
    
    click.echo("\n" + tabulate(
        render_table,
        headers=["Rank", "Interface (RoCEv2/LAG)", "RX BPS", "TX BPS", "Total Throughput"],
        tablefmt="grid"
    ))

if __name__ == '__main__':
    cli()
