# transaction_tracker/cli.py
import os
import click
from dotenv import load_dotenv
from transaction_tracker.config import load_config
from transaction_tracker.loaders import get_loader
from transaction_tracker.outputs import get_output
from transaction_tracker.utils import dedupe_transactions
from transaction_tracker.manual import load_manual_transactions
from transaction_tracker.ai import generate_report
from transaction_tracker.database import append_transactions

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
    type=click.Choice(['csv', 'sheets', 'excel']),
    help='Output target: csv, sheets, or excel'
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
@click.option(
    '--env-file', 'env_file',
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help='Optional .env file containing API tokens for AI providers'
)
@click.option(
    '--db', 'db_path',
    default=None,
    type=click.Path(dir_okay=False),
    help='Optional SQLite database file to also store transactions'
)
@click.option(
    '--ai-report',
    is_flag=True,
    default=False,
    help='Send transactions to an LLM and display the generated report.'
)
def main(statements_dir, output_format, include_payments, config_path,
         manual_file, env_file, db_path, ai_report):
    """
    Scan a directory of mixed-bank statements, auto-detect bank by filename,
    parse each file, dedupe the full set, and output to CSV or a multi-tab
    Google Sheet with monthly tabs, AllData, and Summary.
    Optionally send the final transactions to an LLM to generate
    an insight report printed to the console.
    """
    if env_file:
        load_dotenv(env_file)

    cfg = load_config(config_path)
    loaders = cfg['bank_loaders']
    manual_cfg_path = manual_file or cfg.get('manual_transactions_file')
    db_path = db_path or cfg.get('db_path')

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

    if db_path:
        append_transactions(unique_txs, db_path, cfg.get('categories', {}))
        click.echo(f"Stored {len(unique_txs)} transaction(s) in {db_path}.")

    click.echo(
        f"Appended {len(unique_txs)} transaction(s) to {output_format.upper()}."
    )

    if ai_report:
        report = generate_report(unique_txs)
        click.echo("\nAI Report:\n" + report)
