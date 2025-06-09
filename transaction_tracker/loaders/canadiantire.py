# transaction_tracker/loaders/canadiantire.py
import csv
import re
import pandas as pd
from transaction_tracker.loaders.base import BaseLoader
from transaction_tracker.core.models import Transaction

_PAYMENT_STR   = "payment"
_CLEAN_AMOUNT  = re.compile(r"[^\d\-\.]")

class CanadianTireLoader(BaseLoader):
    def load(self, file_path, include_payments=False):
        # 1. Auto-detect header row
        header_row = None
        header     = None
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for idx, row in enumerate(reader):
                vals     = [c.strip().lower() for c in row if c]
                has_date = any('date' in v for v in vals)
                has_desc = any('description' in v for v in vals)
                has_amt  = any('amount' in v for v in vals)
                if has_date and has_desc and has_amt:
                    header_row = idx
                    header     = row
                    break
        if header_row is None:
            raise RuntimeError(f"Could not locate header row in {file_path}")

        # 2. Read CSV from that row onward
        df = pd.read_csv(
            file_path,
            skiprows=header_row,
            header=0,
            names=header,
            engine='python',
            skip_blank_lines=True
        )

        # 3. Column lookup
        cols = {c.strip().lower(): c for c in df.columns}
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
                raise RuntimeError(
                    f"Missing required column '{name}' in {file_path}. "
                    f"Found: {list(df.columns)}"
                )

        # 4. Parse & yield, with payment filtering/validation
        for _, row in df.iterrows():
            d = pd.to_datetime(row[date_col]).date()

            amt_raw = str(row[amt_col])
            cleaned = _CLEAN_AMOUNT.sub("", amt_raw)
            try:
                amount = float(cleaned)
            except ValueError:
                raise ValueError(f"Could not parse amount '{amt_raw}' in {file_path}")

            desc = str(row[desc_col]).strip()
            merch= str(row[merchant_col]).strip()
            tx = Transaction(date=d, description=desc, merchant=merch, amount=amount)

            is_payment = (desc.lower() == _PAYMENT_STR)
            if not include_payments and is_payment:
                continue
            if include_payments and is_payment and tx.amount >= 0:
                raise RuntimeError(f"CT payment not negative: {tx}")

            yield tx