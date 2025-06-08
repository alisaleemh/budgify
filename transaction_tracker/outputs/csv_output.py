# transaction_tracker/outputs/csv_output.py
import os, csv
from datetime import datetime
from transaction_tracker.outputs.base import BaseOutput
from transaction_tracker.core.categorizer import categorize


class CSVOutput(BaseOutput):
    def __init__(self, config):
        self.config = config
        self.output_dir = config.get('output_dir', 'data')
        os.makedirs(self.output_dir, exist_ok=True)

    def append(self, transactions, month=None):
        month = month or datetime.now().strftime('%Y-%m')
        out = os.path.join(self.output_dir, f"{month}.csv")
        exists = os.path.isfile(out)
        with open(out, 'a', newline='') as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(['date','description','merchant','category','amount'])
            for tx in transactions:
                cat = categorize(tx, self.config['categories']) or ''
                w.writerow([tx.date, tx.description, tx.merchant, cat, tx.amount])