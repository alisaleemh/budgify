# transaction_tracker/loaders/amex.py
import re
import pandas as pd
from transaction_tracker.loaders.base import BaseLoader
from transaction_tracker.core.models import Transaction

# Regex to remove all characters except digits, minus sign, and decimal point.
_CLEAN_AMOUNT = re.compile(r"[^\d\-\.]")

class AmexLoader(BaseLoader):
    def load(self, file_path):
        # 1. Read without header to detect the real header row
        raw = pd.read_excel(file_path, header=None, engine='xlrd')
        header_row = None
        for idx, row in raw.iterrows():
            vals = [str(v).lower() for v in row.values if pd.notna(v)]
            if 'date' in vals and 'description' in vals and 'amount' in vals:
                header_row = idx
                break
        if header_row is None:
            raise RuntimeError(f"Could not locate header row in {file_path}")

        # 2. Read again using that row as header
        df = pd.read_excel(
            file_path,
            header=header_row,
            engine='xlrd',
            parse_dates=False
        )

        # 3. Normalize column names for lookup
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

        # 4. Ensure required columns exist
        for name, col in (('date', date_col), ('description', desc_col), ('amount', amt_col)):
            if col is None:
                raise RuntimeError(f"Missing required column '{name}' in {file_path}")

        # 5. Yield Transaction objects
        for _, row in df.iterrows():
            # Coerce date to datetime.date
            raw_d = row[date_col]
            d = pd.to_datetime(raw_d).date()

            # Clean and parse amount (strip $, commas, etc.)
            raw_amt = str(row[amt_col])
            cleaned = _CLEAN_AMOUNT.sub("", raw_amt)
            try:
                amount = float(cleaned)
            except ValueError:
                raise ValueError(f"Could not parse amount '{raw_amt}' in {file_path}")

            yield Transaction(
                date=d,
                description=str(row[desc_col]).strip(),
                merchant=str(row[merchant_col]).strip(),
                amount=amount
            )