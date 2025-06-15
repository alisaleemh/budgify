# transaction_tracker/loaders/tdvisa.py

import csv
import re
from datetime import datetime
from transaction_tracker.loaders.base import BaseLoader
from transaction_tracker.core.models import Transaction

# Regex to strip out any character that's not digit, minus, or dot
_CLEAN_AMOUNT = re.compile(r"[^\d\-\.]" )
_PAYMENT_DESC = "payment - thank you"

class TDVisaLoader(BaseLoader):
    """
    Loader for TD Visa CSV statements without headers.
    Expected columns:
      0: Date in MM/DD/YYYY
      1: Transaction description
      2: Amount (cleanable to float)
      3: empty / reserved
      4: balance (ignored)

    Filters out payments unless include_payments=True.
    """
    def load(self, file_path, include_payments=False):
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 3:
                    continue  # skip empty or malformed lines

                # Parse date
                try:
                    d = datetime.strptime(row[0].strip(), '%m/%d/%Y').date()
                except Exception as e:
                    raise ValueError(f"Could not parse date '{row[0]}' in {file_path}: {e}")

                # Description
                desc = row[1].strip()
                desc_lower = desc.lower()

                # Parse amount
                amt_raw = row[2].strip()
                cleaned = _CLEAN_AMOUNT.sub('', amt_raw)
                try:
                    amount = float(cleaned)
                except ValueError:
                    raise ValueError(f"Could not parse amount '{amt_raw}' in {file_path}")

                # Build Transaction
                tx = Transaction(date=d, description=desc, merchant=desc, amount=amount)

                # Identify payments
                is_payment = (desc_lower == _PAYMENT_DESC)
                if not include_payments and is_payment:
                    continue
                if include_payments and is_payment and amount >= 0:
                    # payments should be negative on Visa
                    raise RuntimeError(f"TD Visa payment not negative: {tx}")

                yield tx
