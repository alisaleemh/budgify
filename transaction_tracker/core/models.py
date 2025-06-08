# transaction_tracker/core/models.py
from dataclasses import dataclass
from datetime import date

@dataclass
class Transaction:
    date: date
    description: str
    merchant: str
    amount: float
    category: str = None