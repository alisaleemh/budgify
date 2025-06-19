# transaction_tracker/manual.py
from datetime import datetime
import yaml
from transaction_tracker.core.models import Transaction


def load_manual_transactions(path):
    """Load manual transactions from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f) or []

    txs = []
    for entry in data:
        date_str = entry.get('date')
        if not date_str:
            raise ValueError(f"Missing 'date' in manual entry: {entry}")
        tx = Transaction(
            date=datetime.fromisoformat(date_str).date(),
            description=entry.get('description', ''),
            merchant=entry.get('merchant', ''),
            amount=float(entry.get('amount', 0.0)),
        )
        txs.append(tx)
    return txs
