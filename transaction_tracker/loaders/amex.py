# transaction_tracker/loaders/amex.py
import re
import pandas as pd
from transaction_tracker.loaders.base import BaseLoader
from transaction_tracker.core.models import Transaction

_PAYMENT_RX    = re.compile(r"payment received", re.I)
_CLEAN_AMOUNT  = re.compile(r"[^\d\-\.]")

class AmexLoader(BaseLoader):
    def load(self, file_path, include_payments=False):
        # 1. Detect header row
        raw = pd.read_excel(file_path, header=None, engine='xlrd')
        header_row = None
        for idx, row in raw.iterrows():
            vals = [str(v).lower() for v in row.values if pd.notna(v)]
            if 'date' in vals and 'description' in vals and 'amount' in vals:
                header_row = idx
                break
        if header_row is None:
            raise RuntimeError(f"Could not locate header row in {file_path}")

        # 2. Read with that header
        df = pd.read_excel(
            file_path,
            header=header_row,
            engine='xlrd',
            parse_dates=False
        )

        # 3. Column lookup
        cols = {c.lower(): c for c in df.columns}
        def find(frag):
            frag = frag.lower()
            if frag in cols:
                return cols[frag]
            return next((orig for low, orig in cols.items() if frag in low), None)

        date_col     = find('date')
        desc_col     = find('description')
        amt_col      = find('amount')
        merchant_col = find('merchant') or desc_col

        for name, col in (('date', date_col), ('description', desc_col), ('amount', amt_col)):
            if col is None:
                raise RuntimeError(f"Missing required column '{name}' in {file_path}")

        # 4. Parse & yield, with payment filtering/validation
        for _, row in df.iterrows():
            d_raw = row[date_col]
            d = pd.to_datetime(d_raw).date()

            amt_raw = str(row[amt_col])
            cleaned = _CLEAN_AMOUNT.sub("", amt_raw)

            # Some Amex exports include rows without an amount (e.g. NaN or empty
            # strings).  Previously these rows raised ValueError and stopped the
            # entire import.  Treat them as non-transactions and skip them.
            if not cleaned:
                continue

            try:
                amount = float(cleaned)
            except ValueError:
                raise ValueError(f"Could not parse amount '{amt_raw}' in {file_path}")

            desc = str(row[desc_col]).strip()

            merch_val = row[merchant_col]
            merch = desc if pd.isna(merch_val) else str(merch_val).strip()
            if not merch:
                merch = desc
            tx = Transaction(date=d, description=desc, merchant=merch, amount=amount)

            is_payment = bool(_PAYMENT_RX.search(desc))
            if not include_payments and is_payment:
                continue
            if include_payments and is_payment and tx.amount >= 0:
                raise RuntimeError(f"Amex payment not negative: {tx}")

            yield tx