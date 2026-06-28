"""SONiC Top-N CLI Command."""

import sys
import click
from tabulate import tabulate
from json import dumps

from data_generator import generate_sample_series
from db_connector import COUNTERSConnector
from traffic_processor import TrafficProcessor


@click.group()
def counters():
    """Show interface counters."""
    pass


@counters.command()
@click.option('--top', '-t', default=5, help='Number of interfaces')
@click.option('--interval', '-i', default=1.0, type=float, help='Sampling interval')
@click.option('--json', '-j', is_flag=True, default=False, help='Output as JSON')
@click.option('--mode', '-m', default='MOCK', type=click.Choice(['MOCK', 'REAL']))
def top_n(top: int, interval: float, json: bool, mode: str):
    """Display top N interfaces by traffic."""
    mode = mode.upper()
    
    if top <= 0 or interval <= 0:
        click.echo("Error: Invalid parameters", err=True)
        sys.exit(1)
    
    try:
        if mode == 'MOCK':
            interfaces = [f"Ethernet{i}" for i in range(0, 10 * 4, 4)]
            mock_data = generate_sample_series(interfaces, num_samples=3)
            sample1, sample2 = mock_data[0], mock_data[1]
        else:
            connector = COUNTERSConnector(mode='REAL', quiet=json)
            if connector.mode == 'REAL':
                sample1, sample2 = connector.get_counters(0), connector.get_counters(1)
            else:
                interfaces = [f"Ethernet{i}" for i in range(0, 10 * 4, 4)]
                mock_data = generate_sample_series(interfaces, num_samples=3)
                sample1, sample2 = mock_data[0], mock_data[1]
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    
    processor = TrafficProcessor()
    results = processor.process_counters(sample1, sample2, interval)
    top_results = processor.filter_top_n(results, top)
    
    if json:
        click.echo(processor.format_json_output(top_results))
    else:
        click.echo(processor.format_table_output(top_results, len(top_results)))


if __name__ == '__main__':
    counters()