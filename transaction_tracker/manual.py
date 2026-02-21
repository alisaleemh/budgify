# transaction_tracker/manual.py
from datetime import datetime, date
import yaml
from transaction_tracker.core.models import Transaction


def load_manual_transactions(path):
    """Load manual transactions from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f) or []

    txs = []
    for entry in data:
        date_val = entry.get('date')
        if not date_val:
            raise ValueError(f"Missing 'date' in manual entry: {entry}")
        if isinstance(date_val, date):
            d = date_val
        elif isinstance(date_val, str):
            d = datetime.fromisoformat(date_val).date()
        else:
            raise ValueError(f"Unrecognized date format in manual entry: {entry}")
        tx = Transaction(
            date=d,
            description=entry.get('description', ''),
            merchant=entry.get('merchant', ''),
            amount=float(entry.get('amount', 0.0)),
            provider="manual",
        )
        txs.append(tx)
    return txs
