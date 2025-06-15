# transaction_tracker/outputs/csv_output.py

import os
import csv
from datetime import datetime
from decimal import Decimal
from transaction_tracker.outputs.base import BaseOutput
from transaction_tracker.core.categorizer import categorize


class CSVOutput(BaseOutput):
    """
    Writes all transactions to a single master CSV file named Budget<Year>.csv,
    de-duplicated and sorted by date (oldest to latest).
    """
    def __init__(self, config):
        self.config      = config
        self.output_dir  = config.get('output_dir', 'data')
        os.makedirs(self.output_dir, exist_ok=True)

    def append(self, transactions):
        if not transactions:
            print("No transactions to write.")
            return

        # Deduplicate and map
        records = {}
        for tx in transactions:
            date_s   = tx.date.isoformat() if hasattr(tx.date, 'isoformat') else str(tx.date)
            desc     = str(tx.description).strip()
            merchant = str(tx.merchant).strip()
            amount   = f"{Decimal(tx.amount):.2f}"
            key      = (date_s, desc, merchant, amount)
            cat      = categorize(tx, self.config['categories']) or ''
            records[key] = {
                'date':        date_s,
                'description': desc,
                'merchant':    merchant,
                'category':    cat,
                'amount':      amount
            }

        # Sort records by date ascending and extract year
        sorted_records = sorted(
            records.values(),
            key=lambda r: datetime.fromisoformat(r['date'])
        )
        year = datetime.fromisoformat(sorted_records[0]['date']).year

        # Determine master filename
        filename = f"Budget{year}.csv"
        out_path = os.path.join(self.output_dir, filename)

        # Write back to master CSV
        with open(out_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['date','description','merchant','category','amount'])
            for row in sorted_records:
                writer.writerow([
                    row['date'],
                    row['description'],
                    row['merchant'],
                    row['category'],
                    row['amount'],
                ])

        new_count = len(sorted_records)
        print(f"Written {new_count} unique transactions to {out_path}")
