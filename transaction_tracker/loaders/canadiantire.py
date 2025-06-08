# transaction_tracker/loaders/canadiantire.py
import csv
import re
import pandas as pd
from transaction_tracker.loaders.base import BaseLoader
from transaction_tracker.core.models import Transaction

# Regex to remove all characters except digits, minus sign, and decimal point.
_CLEAN_AMOUNT = re.compile(r"[^\d\-\.]")

class CanadianTireLoader(BaseLoader):
    def load(self, file_path):
        # 1. Auto-detect header row by looking for fragments in each row
        header_row = None
        header = None
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for idx, row in enumerate(reader):
                vals = [cell.strip().lower() for cell in row if cell]
                has_date = any('date' in v for v in vals)
                has_desc = any('description' in v for v in vals)
                has_amt  = any('amount' in v for v in vals)
                if has_date and has_desc and has_amt:
                    header_row = idx
                    header = row
                    break

        if header_row is None:
            raise RuntimeError(f"Could not locate header row in {file_path}")

        # 2. Read the CSV from that header row onward
        df = pd.read_csv(
            file_path,
            skiprows=header_row,
            header=0,
            names=header,
            engine='python',
            skip_blank_lines=True
        )

        # 3. Normalize column lookup
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
                    f"Found columns: {df.columns.tolist()}"
                )

        # 4. Yield Transaction instances
        for _, row in df.iterrows():
            # parse date into datetime.date
            raw_d = row[date_col]
            d = pd.to_datetime(raw_d).date()

            # clean & parse amount
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