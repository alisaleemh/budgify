# transaction_tracker/outputs/excel_output.py

"""Excel output module backed by XlsxWriter.

This module writes transactions to an Excel workbook. Each month's
worksheet optionally includes a native PivotTable showing the total
amount per category for that month. A separate ``Summary`` worksheet is
generated manually (no Excel PivotTable) to aggregate spending by
category for each month and overall.
"""

from __future__ import annotations

from datetime import datetime
import os
import xlsxwriter

from transaction_tracker.outputs.base import BaseOutput
from transaction_tracker.core.categorizer import categorize


class ExcelOutput(BaseOutput):
    """Generate a local Excel workbook with optional PivotTables."""

    MONTH_FMT = "%B %Y"
    ALL_DATA = "AllData"
    SUMMARY = "Summary"

    def __init__(self, config: dict):
        self.config = config
        self.output_dir = config.get("output_dir", "data")
        os.makedirs(self.output_dir, exist_ok=True)

    def append(self, transactions):
        if not transactions:
            print("No transactions to write.")
            return

        months = sorted({tx.date.strftime("%Y-%m") for tx in transactions})
        first_dt = datetime.strptime(months[0], "%Y-%m")
        year = first_dt.year
        out_path = os.path.join(self.output_dir, f"Budget{year}.xlsx")

        workbook = xlsxwriter.Workbook(out_path)
        amount_fmt = workbook.add_format({"num_format": "$#,##0.00"})
        supports_pivot = hasattr(workbook, "add_pivot_table")

        all_rows = []
        monthly_totals = {}
        summary_data = {}
        for month_str in months:
            dt = datetime.strptime(month_str, "%Y-%m")
            sheet_name = dt.strftime(self.MONTH_FMT)
            ws = workbook.add_worksheet(sheet_name)
            ws.freeze_panes(1, 0)

            headers = ["date", "description", "merchant", "category", "amount"]
            ws.write_row(0, 0, headers)

            month_rows = []
            for tx in transactions:
                if tx.date.strftime("%Y-%m") != month_str:
                    continue
                cat = categorize(tx, self.config["categories"]) or ""
                row = [
                    tx.date.isoformat(),
                    tx.description,
                    tx.merchant,
                    cat,
                    float(tx.amount),
                ]
                month_rows.append(row)
                all_rows.append([sheet_name] + row)
                summary_data.setdefault(sheet_name, {}).setdefault(cat, 0.0)
                summary_data[sheet_name][cat] += row[4]

            # Sort transactions by absolute amount, largest first
            month_rows.sort(key=lambda r: abs(r[4]), reverse=True)

            row_idx = 1
            for row in month_rows:
                ws.write_row(row_idx, 0, row[:4])
                ws.write_number(row_idx, 4, row[4], amount_fmt)
                row_idx += 1

            monthly_totals[sheet_name] = sum(r[4] for r in month_rows)

            ws.set_column(4, 4, None, amount_fmt)
            ws.add_table(0, 0, len(month_rows), 4, {
                "columns": [{"header": h} for h in headers]
            })

            if month_rows and supports_pivot:
                data_range = f"A1:E{len(month_rows) + 1}"
                workbook.add_pivot_table({
                    "name": f"Pivot_{sheet_name.replace(' ', '_')}",
                    "source": f"'{sheet_name}'!{data_range}",
                    "dest": f"'{sheet_name}'!G3",
                    "fields": {"category": "row", "amount": "sum"},
                })

        # AllData worksheet consolidating all transactions
        all_ws = workbook.add_worksheet(self.ALL_DATA)
        all_ws.freeze_panes(1, 0)
        all_headers = ["month", "date", "description", "merchant", "category", "amount"]
        all_ws.write_row(0, 0, all_headers)
        for idx, row in enumerate(all_rows, start=1):
            all_ws.write_row(idx, 0, row[:5])
            all_ws.write_number(idx, 5, row[5], amount_fmt)
        all_ws.set_column(5, 5, None, amount_fmt)
        all_ws.add_table(0, 0, len(all_rows), 5, {
            "columns": [{"header": h} for h in all_headers]
        })

        # Summary worksheet manually aggregating by month & category
        summary_ws = workbook.add_worksheet(self.SUMMARY)
        summary_ws.freeze_panes(1, 0)
        summary_ws.set_column(2, 2, None, amount_fmt)
        row_idx = 0
        grand_total = 0.0
        for month_str in months:
            sheet_name = datetime.strptime(month_str, "%Y-%m").strftime(self.MONTH_FMT)
            cats = summary_data.get(sheet_name, {})
            for i, cat in enumerate(sorted(cats)):
                amount = cats[cat]
                if i == 0:
                    summary_ws.write(row_idx, 0, sheet_name)
                summary_ws.write(row_idx, 1, cat)
                summary_ws.write_number(row_idx, 2, amount, amount_fmt)
                row_idx += 1
            month_total = monthly_totals.get(sheet_name, 0.0)
            summary_ws.write(row_idx, 0, f"{sheet_name} Total")
            summary_ws.write_number(row_idx, 2, month_total, amount_fmt)
            grand_total += month_total
            row_idx += 1
        summary_ws.write(row_idx, 0, "Grand Total")
        summary_ws.write_number(row_idx, 2, grand_total, amount_fmt)

        workbook.close()
        print(f"Written Excel workbook {out_path}")

