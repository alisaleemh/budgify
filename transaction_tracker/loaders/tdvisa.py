# transaction_tracker/loaders/tdvisa.py

import csv
import re
from datetime import datetime
from transaction_tracker.loaders.base import BaseLoader
from transaction_tracker.core.models import Transaction

# Regex to strip out any character that's not digit, minus, or dot
_CLEAN_AMOUNT = re.compile(r"[^\d\-.]")
_PAYMENT_DESC = "payment - thank you"

class TDVisaLoader(BaseLoader):
    """
    Loader for TD Visa CSV statements without headers.
    Expected columns:
      0: Date in MM/DD/YYYY
      1: Transaction description
      2: Amount (cleanable to float)
      3: fallback for payments if col 2 is empty
      4: balance (ignored)

    Payments (description == "PAYMENT - THANK YOU") are excluded by default
    (include_payments=False), and will only be yielded if include_payments=True.
    """
    def load(self, file_path, include_payments=False):
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 3:
                    continue  # skip empty or malformed lines

                # 1) Parse the transaction date
                try:
                    d = datetime.strptime(row[0].strip(), '%m/%d/%Y').date()
                except Exception as e:
                    raise ValueError(f"Could not parse date '{row[0]}' in {file_path}: {e}")

                # 2) Get the description (and merchant)
                desc = row[1].strip()
                desc_lower = desc.lower()

                # 3) Parse the amount; fall back to column 3 for payment rows
                amt_raw = row[2].strip()
                fallback = False
                if amt_raw == '' and len(row) >= 4 and row[3].strip():
                    amt_raw = row[3].strip()
                    fallback = True

                cleaned = _CLEAN_AMOUNT.sub('', amt_raw)
                if not cleaned:
                    raise ValueError(f"Could not parse amount '{amt_raw}' in {file_path}")

                try:
                    amount = float(cleaned)
                except ValueError:
                    raise ValueError(f"Could not parse cleaned amount '{cleaned}' in {file_path}")

                # If we used the fallback column, treat it as a negative payment
                if fallback:
                    amount = -abs(amount)

                # 4) Build the Transaction
                tx = Transaction(date=d, description=desc, merchant=desc, amount=amount)

                # 5) Filter out payments by default
                is_payment = (desc_lower == _PAYMENT_DESC)
                if not include_payments and is_payment:
                    continue
                if include_payments and is_payment and tx.amount >= 0:
                    # payments should be negative
                    raise RuntimeError(f"TD Visa payment not negative: {tx}")

                yield tx