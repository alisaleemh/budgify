# transaction_tracker/outputs/excel_output.py

"""Excel output module backed by XlsxWriter.

This module writes transactions to an Excel workbook and adds native
PivotTables summarizing spending by category. Each month's worksheet
contains a PivotTable showing the total amount per category for that
month. A "Summary" worksheet contains a PivotTable aggregating all
months with categories as rows and months as columns.
"""

from __future__ import annotations

from datetime import datetime
import os
import xlsxwriter

from transaction_tracker.outputs.base import BaseOutput
from transaction_tracker.core.categorizer import categorize


class ExcelOutput(BaseOutput):
    """Generate a local Excel workbook with PivotTables."""

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
        for month_str in months:
            dt = datetime.strptime(month_str, "%Y-%m")
            sheet_name = dt.strftime(self.MONTH_FMT)
            ws = workbook.add_worksheet(sheet_name)
            ws.freeze_panes(1, 0)

            headers = ["date", "description", "merchant", "category", "amount"]
            ws.write_row(0, 0, headers)

            month_rows = []
            row_idx = 1
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
                ws.write_row(row_idx, 0, row[:4])
                ws.write_number(row_idx, 4, row[4], amount_fmt)
                month_rows.append(row)
                all_rows.append([sheet_name] + row)
                row_idx += 1

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

        # Summary worksheet with cross-month PivotTable
        workbook.add_worksheet(self.SUMMARY)
        if all_rows and supports_pivot:
            data_range = f"A1:F{len(all_rows) + 1}"
            workbook.add_pivot_table({
                "name": "Pivot_Summary",
                "source": f"'{self.ALL_DATA}'!{data_range}",
                "dest": f"'{self.SUMMARY}'!A3",
                "fields": {
                    "category": "row",
                    "month": "column",
                    "amount": "sum",
                },
            })

        workbook.close()
        print(f"Written Excel workbook {out_path}")

