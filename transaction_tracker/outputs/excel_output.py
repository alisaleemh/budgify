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
    CHARTS = "Charts"

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

        # Charts worksheet with aggregates and visuals
        charts_ws = workbook.add_worksheet(self.CHARTS)
        charts_ws.freeze_panes(1, 0)
        charts_ws.set_column(1, 1, None, amount_fmt)
        chart_tables = self._build_chart_tables(all_rows)
        chart_layout = {}
        start_row = 0
        for key in ("monthly", "restaurants", "groceries", "categories"):
            table = chart_tables[key]
            chart_layout[key] = {"start_row": start_row, "row_count": len(table)}
            for offset, row in enumerate(table):
                charts_ws.write_row(start_row + offset, 0, row)
            start_row += len(table) + 2

        self._insert_charts(workbook, charts_ws, chart_layout)

        workbook.close()
        print(f"Written Excel workbook {out_path}")

    def _build_chart_tables(self, all_rows):
        data_rows = all_rows[1:]
        month_totals = {}
        restaurant_totals = {}
        grocery_totals = {}
        category_totals = {}
        month_sort = {}

        for row in data_rows:
            if len(row) < 6:
                continue
            month = row[0]
            category = (row[4] or "").strip()
            amount = row[5] or 0

            if month:
                month_totals[month] = month_totals.get(month, 0) + amount
                if month not in month_sort:
                    try:
                        month_sort[month] = datetime.strptime(month, self.MONTH_FMT)
                    except ValueError:
                        month_sort[month] = month

            category_norm = category.lower()
            if category_norm == "restaurants":
                restaurant_totals[month] = restaurant_totals.get(month, 0) + amount
            if category_norm == "groceries":
                grocery_totals[month] = grocery_totals.get(month, 0) + amount

            if category:
                category_totals[category] = category_totals.get(category, 0) + amount

        def month_sort_key(value):
            return month_sort.get(value, value)

        monthly_rows = [
            [month, month_totals[month]]
            for month in sorted(month_totals, key=month_sort_key)
        ]
        restaurant_rows = [
            [month, restaurant_totals.get(month, 0)]
            for month in sorted(month_totals, key=month_sort_key)
        ]
        grocery_rows = [
            [month, grocery_totals.get(month, 0)]
            for month in sorted(month_totals, key=month_sort_key)
        ]
        category_rows = [
            [category, total]
            for category, total in sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
        ]

        return {
            "monthly": [["Month", "Total"]] + monthly_rows,
            "restaurants": [["Month", "Total"]] + restaurant_rows,
            "groceries": [["Month", "Total"]] + grocery_rows,
            "categories": [["Category", "Total"]] + category_rows,
        }

    def _insert_charts(self, workbook, charts_ws, chart_layout):
        def table_range(table_key):
            layout = chart_layout[table_key]
            start_row = layout["start_row"]
            row_count = layout["row_count"]
            return start_row, row_count

        def add_column_chart(title, anchor_row, anchor_col, table_key):
            start_row, row_count = table_range(table_key)
            if row_count <= 1:
                return
            chart = workbook.add_chart({"type": "column"})
            chart.add_series({
                "categories": [charts_ws.name, start_row + 1, 0, start_row + row_count - 1, 0],
                "values": [charts_ws.name, start_row + 1, 1, start_row + row_count - 1, 1],
                "name": title,
            })
            chart.set_title({"name": title})
            chart.set_legend({"position": "bottom"})
            charts_ws.insert_chart(anchor_row, anchor_col, chart, {"x_offset": 0, "y_offset": 0})

        add_column_chart("Monthly spending", 0, 6, "monthly")
        add_column_chart("Restaurant spending by month", 18, 6, "restaurants")
        add_column_chart("Grocery spending by month", 36, 6, "groceries")

        categories_start, categories_rows = table_range("categories")
        if categories_rows > 1:
            chart = workbook.add_chart({"type": "pie"})
            chart.add_series({
                "categories": [charts_ws.name, categories_start + 1, 0, categories_start + categories_rows - 1, 0],
                "values": [charts_ws.name, categories_start + 1, 1, categories_start + categories_rows - 1, 1],
                "name": "YTD spending by category",
            })
            chart.set_title({"name": "YTD spending by category"})
            chart.set_legend({"position": "right"})
            chart.set_size({"width": 480, "height": 300})
            charts_ws.insert_chart(0, 14, chart, {"x_offset": 0, "y_offset": 0})
