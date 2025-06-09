# transaction_tracker/cli.py
import click
from transaction_tracker.config import load_config
from transaction_tracker.loaders import get_loader
from transaction_tracker.outputs import get_output
from transaction_tracker.utils import filter_transactions_by_month, dedupe_transactions

@click.command()
@click.option('--bank', required=True,
              help='Which bank plugin to use (amex, canadiantire)')
@click.option('--file', 'file_paths', required=True, multiple=True,
              type=click.Path(exists=True),
              help='One or more transaction files for the given bank')
@click.option('--output-format', default='csv',
              help='Output format (csv)')
@click.option('--month', required=True,
              help='Ledger month to use (YYYY-MM), e.g. 2025-05')
@click.option('--include-payments', is_flag=True, default=False,
              help='Include payment transactions (default: exclude them)')
@click.option('--config', 'config_path', default='config.yaml',
              type=click.Path(exists=True),
              help='Path to config.yaml')
def main(bank, file_paths, output_format, month, include_payments, config_path):
    """
    Load transactions from one or more files, filter to the specified month,
    dedupe, then append to the chosen output.
    """
    cfg       = load_config(config_path)
    loader    = get_loader(bank, cfg)
    outputter = get_output(output_format, cfg)

    all_txs = []
    for path in file_paths:
        # pass include_payments flag into each loader
        all_txs.extend(loader.load(path, include_payments=include_payments))

    filtered   = filter_transactions_by_month(all_txs, month)
    unique_txs = dedupe_transactions(filtered)

    outputter.append(unique_txs, month=month)
    click.echo(
        f"Appended {len(unique_txs)} transaction(s) for {month} "
        f"({'including' if include_payments else 'excluding'} payments)."
    )

if __name__ == '__main__':
    main()