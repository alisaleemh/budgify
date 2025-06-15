# transaction_tracker/cli.py
import os
import click
from transaction_tracker.config import load_config
from transaction_tracker.loaders import get_loader
from transaction_tracker.outputs import get_output
from transaction_tracker.utils import filter_transactions_by_month, dedupe_transactions

@click.command()
@click.option(
    '--dir', 'statements_dir',
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help='Directory containing all statement files. Files matched to bank by filename.'
)
@click.option(
    '--month',
    required=True,
    help='Ledger month to use (YYYY-MM), e.g. 2025-05'
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
def main(statements_dir, month, output_format, include_payments, config_path):
    """
    Scan a directory of mixed-bank statements, auto-detect bank by filename,
    parse & filter each file, then append all to the chosen output.
    """
    # Load configuration and initialize
    cfg       = load_config(config_path)
    loaders   = cfg['bank_loaders']  # dict: bank_key -> loader path
    outputter = get_output(output_format, cfg)

    # Collect and parse transactions
    all_txs = []
    for fname in os.listdir(statements_dir):
        path = os.path.join(statements_dir, fname)
        if not os.path.isfile(path):
            continue

        # Determine bank by filename
        match = None
        low = fname.lower()
        for bank in loaders:
            if bank.lower() in low:
                match = bank
                break
        if not match:
            click.echo(f"⚠️  Skipping unknown bank file: {fname}", err=True)
            continue

        loader = get_loader(match, cfg)
        all_txs.extend(loader.load(path, include_payments=include_payments))

    # Filter by month and remove duplicates
    filtered   = filter_transactions_by_month(all_txs, month)
    unique_txs = dedupe_transactions(filtered)

    # Write to the selected output
    outputter.append(unique_txs, month=month)
    click.echo(
        f"Appended {len(unique_txs)} transaction(s) for {month} "
        f"({'including' if include_payments else 'excluding'} payments) to {output_format.upper()}."
    )
