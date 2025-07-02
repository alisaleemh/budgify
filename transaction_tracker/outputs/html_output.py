# transaction_tracker/outputs/html_output.py

import os
from datetime import datetime
from transaction_tracker.core.categorizer import categorize
from transaction_tracker.outputs.base import BaseOutput


class HTMLOutput(BaseOutput):
    """Generate a static HTML report similar to the Google Sheets output."""

    def __init__(self, config):
        self.config = config
        self.output_dir = config.get('output_dir', 'data')
        os.makedirs(self.output_dir, exist_ok=True)
        self.categories = config.get('categories', {})

    def append(self, transactions):
        if not transactions:
            print("No transactions to write.")
            return

        txs = sorted(transactions, key=lambda t: t.date)
        year = txs[0].date.year

        # Organize by month
        months = {}
        for tx in txs:
            key = tx.date.strftime('%Y-%m')
            months.setdefault(key, []).append(tx)

        # Build summary pivot by month & category
        summary = {}
        for key, tx_list in months.items():
            month_title = datetime.strptime(key, '%Y-%m').strftime('%B %Y')
            for tx in tx_list:
                cat = categorize(tx, self.categories) or ''
                summary.setdefault(month_title, {}).setdefault(cat, 0.0)
                summary[month_title][cat] += tx.amount

        def tx_row(tx, cat):
            return f"<tr><td>{tx.date}</td><td>{tx.description}</td><td>{tx.merchant}</td><td>{cat}</td><td>{tx.amount:.2f}</td></tr>"

        html_parts = [
            "<html><head><meta charset='UTF-8'>",
            "<style>body{font-family:sans-serif;}table{border-collapse:collapse;margin-bottom:20px;}th,td{border:1px solid #ccc;padding:4px 8px;}th{background:#eee;}</style>",
            "</head><body>",
            f"<h1>Budget {year}</h1>",
        ]

        # Monthly tables
        for key in sorted(months):
            title = datetime.strptime(key, '%Y-%m').strftime('%B %Y')
            html_parts.append(f"<h2>{title}</h2>")
            html_parts.append("<table><tr><th>Date</th><th>Description</th><th>Merchant</th><th>Category</th><th>Amount</th></tr>")
            for tx in months[key]:
                cat = categorize(tx, self.categories) or ''
                html_parts.append(tx_row(tx, cat))
            html_parts.append("</table>")

        # AllData table
        html_parts.append("<h2>AllData</h2>")
        html_parts.append("<table><tr><th>Month</th><th>Date</th><th>Description</th><th>Merchant</th><th>Category</th><th>Amount</th></tr>")
        for key in sorted(months):
            title = datetime.strptime(key, '%Y-%m').strftime('%B %Y')
            for tx in months[key]:
                cat = categorize(tx, self.categories) or ''
                html_parts.append(f"<tr><td>{title}</td><td>{tx.date}</td><td>{tx.description}</td><td>{tx.merchant}</td><td>{cat}</td><td>{tx.amount:.2f}</td></tr>")
        html_parts.append("</table>")

        # Summary table
        html_parts.append("<h2>Summary</h2>")
        html_parts.append("<table><tr><th>Month</th><th>Category</th><th>Total</th></tr>")
        def month_sort(m):
            return datetime.strptime(m, '%B %Y')
        for m in sorted(summary.keys(), key=month_sort):
            cats = summary[m]
            for cat in sorted(cats):
                html_parts.append(f"<tr><td>{m}</td><td>{cat}</td><td>{cats[cat]:.2f}</td></tr>")
        html_parts.append("</table>")

        html_parts.append("</body></html>")

        out_path = os.path.join(self.output_dir, f"Budget{year}.html")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(html_parts))

        print(f"Written {len(txs)} transactions to {out_path}")
