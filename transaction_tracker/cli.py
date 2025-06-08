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
@click.option('--config', 'config_path', default='config.yaml',
              type=click.Path(exists=True),
              help='Path to config.yaml')
def main(bank, file_paths, output_format, month, config_path):
    """
    Load transactions from one or more files, filter to the specified month,
    dedupe, then append to the chosen output.
    """
    # 1. Load config & instantiate plugins
    cfg = load_config(config_path)
    loader = get_loader(bank, cfg)
    outputter = get_output(output_format, cfg)

    # 2. Aggregate from multiple files
    all_txs = []
    for path in file_paths:
        all_txs.extend(loader.load(path))

    # 3. Filter and dedupe
    filtered = filter_transactions_by_month(all_txs, month)
    unique_txs = dedupe_transactions(filtered)

    # 4. Append to output
    outputter.append(unique_txs, month=month)
    click.echo(f"Appended {len(unique_txs)} unique transactions for {month}.")

if __name__ == '__main__':
    main()