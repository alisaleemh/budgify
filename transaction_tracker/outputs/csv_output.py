# transaction_tracker/outputs/csv_output.py

import os
import csv
from datetime import datetime
from decimal import Decimal
from transaction_tracker.outputs.base import BaseOutput
from transaction_tracker.core.categorizer import categorize


class CSVOutput(BaseOutput):
    def __init__(self, config):
        self.config = config
        self.output_dir = config.get('output_dir', 'data')
        os.makedirs(self.output_dir, exist_ok=True)

    def append(self, transactions, month=None):
        month = month or datetime.now().strftime('%Y-%m')
        out_path = os.path.join(self.output_dir, f"{month}.csv")

        # 1) Load existing records
        records = {}
        if os.path.isfile(out_path):
            with open(out_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    date_s   = row['date'].strip()
                    desc     = row['description'].strip()
                    merchant = row['merchant'].strip()
                    amount   = f"{Decimal(row['amount'].strip()):.2f}"
                    key = (date_s, desc, merchant, amount)
                    records[key] = {
                        'date':        date_s,
                        'description': desc,
                        'merchant':    merchant,
                        'category':    row.get('category', '').strip(),
                        'amount':      amount
                    }
        original_count = len(records)

        # 2) Merge new transactions
        for tx in transactions:
            # normalize date to ISO string
            if hasattr(tx.date, 'isoformat'):
                date_s = tx.date.isoformat()
            else:
                date_s = str(tx.date)
            # then strip any stray whitespace
            date_s = date_s.strip()

            # ensure description and merchant are strings
            desc     = str(tx.description).strip()
            merchant = str(tx.merchant).strip()
            amount   = f"{Decimal(tx.amount):.2f}"

            key = (date_s, desc, merchant, amount)
            cat = categorize(tx, self.config['categories']) or ''
            records[key] = {
                'date':        date_s,
                'description': desc,
                'merchant':    merchant,
                'category':    cat,
                'amount':      amount
            }

        # 3) Write back the full de-duped list
        with open(out_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['date','description','merchant','category','amount'])
            for row in records.values():
                writer.writerow([
                    row['date'],
                    row['description'],
                    row['merchant'],
                    row['category'],
                    row['amount'],
                ])

        new_count = len(records) - original_count
        print(f"Written {len(records)} unique transactions to {out_path}")
        print(f"Appended {new_count} new transaction(s) for {month}")