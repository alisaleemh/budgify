# transaction_tracker/cli.py
import os
import click
from transaction_tracker.config import load_config
from transaction_tracker.loaders import get_loader
from transaction_tracker.outputs import get_output
from transaction_tracker.utils import dedupe_transactions
from transaction_tracker.manual import load_manual_transactions

@click.command()
@click.option(
    '--dir', 'statements_dir',
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help='Directory containing all statement files. Files matched to bank by filename.'
)
@click.option(
    '--output', 'output_format',
    default='csv',
    type=click.Choice(['csv', 'sheets']),
    help='Output target: csv or sheets'
)
@click.option(
    '--include-payments',
    is_flag=True,
    default=False,
    help='Include payment transactions (default: exclude them)'
)
@click.option(
    '--config', 'config_path',
    default='config.yaml',
    type=click.Path(exists=True),
    help='Path to config.yaml'
)
@click.option(
    '--manual-file', 'manual_file',
    default=None,
    type=click.Path(exists=True),
    help='YAML file of manual transactions (overrides config if provided)'
)
def main(statements_dir, output_format, include_payments, config_path, manual_file):
    """
    Scan a directory of mixed-bank statements, auto-detect bank by filename,
    parse each file, dedupe the full set, and output to CSV or a multi-tab
    Google Sheet with monthly tabs, AllData, and Summary.
    """
    cfg = load_config(config_path)
    loaders = cfg['bank_loaders']
    manual_cfg_path = manual_file or cfg.get('manual_transactions_file')

    # Collect all transactions across all files
    all_txs = []
    for fname in os.listdir(statements_dir):
        path = os.path.join(statements_dir, fname)
        if not os.path.isfile(path):
            continue
        low = fname.lower()
        match = next((bank for bank in loaders if bank.lower() in low), None)
        if not match:
            click.echo(f"⚠️  Skipping unknown bank file: {fname}", err=True)
            continue
        loader = get_loader(match, cfg)
        all_txs.extend(loader.load(path, include_payments=include_payments))

    # Manual transactions
    if manual_cfg_path:
        try:
            all_txs.extend(load_manual_transactions(manual_cfg_path))
        except Exception as e:
            click.echo(f"Error loading manual transactions: {e}", err=True)

    # Deduplicate globally
    unique_txs = dedupe_transactions(all_txs)

    # Output
    outputter = get_output(output_format, cfg)
    outputter.append(unique_txs)

    click.echo(
        f"Appended {len(unique_txs)} transaction(s) to {output_format.upper()}."
    )
