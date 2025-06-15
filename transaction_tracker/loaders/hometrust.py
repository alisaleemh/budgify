# transaction_tracker/loaders/hometrust.py

import csv
import re
from datetime import datetime
from transaction_tracker.loaders.base import BaseLoader
from transaction_tracker.core.models import Transaction

# Regex to strip everything except digits and dot
_CLEAN_AMOUNT = re.compile(r"[^\d\.]" )

class HomeTrustLoader(BaseLoader):
    """
    Loader for Home Trust credit card CSV statements.

    Expected CSV headers (case-sensitive):
      - Account Number
      - Cardholder Name
      - Trans Date       (MM/DD/YYYY)
      - Posting Date     (ignored)
      - Type             (Credit/Debit)
      - Category         (ignored)
      - Merchant Name
      - Merchant City    (ignored)
      - Merchant State   (ignored)
      - Amount           (e.g. "$1.23" or "($45.67)")
      - ...              (other columns ignored)

    Payments are rows where Merchant Name is "SCOTIABANK PAYMENT" or exactly "PAYMENT".
    Such rows are excluded unless include_payments=True.
    """
    PAYMENT_KEYWORDS = ('scotiabank payment', 'payment')

    def load(self, file_path, include_payments=False):
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # Verify required columns
            required = ['Trans Date', 'Merchant Name', 'Amount']
            for col in required:
                if col not in reader.fieldnames:
                    raise RuntimeError(f"Missing required column '{col}' in {file_path}")

            for row in reader:
                # Parse transaction date
                raw_date = row['Trans Date'].strip()
                try:
                    d = datetime.strptime(raw_date, '%m/%d/%Y').date()
                except Exception as e:
                    raise ValueError(f"Could not parse Trans Date '{raw_date}' in {file_path}: {e}")

                # Description and merchant
                desc = row['Merchant Name'].strip()
                desc_lower = desc.lower()

                # Parse amount (handle parentheses for negatives)
                amt_raw = row['Amount'].strip()
                is_negative = '(' in amt_raw and ')' in amt_raw
                cleaned = _CLEAN_AMOUNT.sub('', amt_raw)
                try:
                    val = float(cleaned)
                    amount = -val if is_negative else val
                except ValueError:
                    raise ValueError(f"Could not parse Amount '{amt_raw}' in {file_path}")

                # Build Transaction
                tx = Transaction(date=d, description=desc, merchant=desc, amount=amount)

                # Filter payments
                is_payment = any(desc_lower == kw for kw in self.PAYMENT_KEYWORDS)
                if not include_payments and is_payment:
                    continue
                if include_payments and is_payment and tx.amount >= 0:
                    raise RuntimeError(f"HomeTrust payment not negative: {tx}")

                yield tx
