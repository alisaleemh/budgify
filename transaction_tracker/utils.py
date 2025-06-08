# transaction_tracker/utils.py
from datetime import datetime

def filter_transactions_by_month(transactions, month_str):
    """
    Return only those transactions whose date falls in the given YYYY-MM.
    """
    year, month = map(int, month_str.split('-'))
    return [tx for tx in transactions if tx.date.year == year and tx.date.month == month]

def dedupe_transactions(transactions):
    """
    Remove duplicates based on (date, description, merchant, amount).
    """
    seen = set()
    unique = []
    for tx in transactions:
        key = (tx.date, tx.description, tx.merchant, tx.amount)
        if key not in seen:
            seen.add(key)
            unique.append(tx)
    return unique