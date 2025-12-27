# transaction_tracker/outputs/sheets_output.py

import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
from calendar import month_name
from transaction_tracker.outputs.base import BaseOutput
from transaction_tracker.core.categorizer import categorize


class SheetsOutput(BaseOutput):
    """
    Yearly budget spreadsheet with:
      - One tab per month ("May 2025" etc.) with its own pivot
      - An "AllData" tab deduping month tabs, prepended with a "month" column
      - A "Summary" tab containing a single pivot grouped by month & category
      - Tabs reordered: Summary, AllData, then months Jan–Dec
    """
    MONTH_FMT = "%B %Y"
    ALL_DATA  = "AllData"
    SUMMARY   = "Summary"
    CHARTS    = "Charts"

    def __init__(self, config):
        google_cfg  = config.get('google', {})
        scopes      = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds       = Credentials.from_service_account_file(
            google_cfg['service_account_file'], scopes=scopes
        )
        self.gc         = gspread.authorize(creds)
        self.sheets_srv = build('sheets', 'v4', credentials=creds)
        self.drive_srv  = build('drive', 'v3', credentials=creds)
        self.folder_id  = google_cfg.get('sheet_folder_id')
        self.spreadsheet_id = google_cfg.get('spreadsheet_id')
        self.owner      = google_cfg.get('owner_email')
        self.config     = config

    def append(self, transactions):
        # Determine year
        months = sorted({tx.date.strftime('%Y-%m') for tx in transactions})
        if not months:
            return
        first_dt = datetime.strptime(months[0], '%Y-%m')
        year = first_dt.year
        ss_title = ""
        if self.spreadsheet_id:
            sh = self.gc.open_by_key(self.spreadsheet_id)
            created = False
            ss_title = sh.title
        else:
            ss_title = f"Budget {year}"

        # Open or create spreadsheet
        try:
            sh = self.gc.open(ss_title)
            created = False
        except gspread.exceptions.SpreadsheetNotFound:
            sh = self.gc.create(ss_title)
            created = True

        # Move/share
        if self.folder_id:
            meta    = self.drive_srv.files().get(fileId=sh.id, fields='parents').execute()
            parents = set(meta.get('parents', []))
            add     = [] if self.folder_id in parents else [self.folder_id]
            rem     = ['root'] if 'root' in parents else []
            if add or rem:
                self.drive_srv.files().update(
                    fileId        = sh.id,
                    addParents    = ','.join(add),
                    removeParents = ','.join(rem),
                    fields        = 'id,parents'
                ).execute()
        if self.owner:
            try:
                perms = sh.list_permissions()
            except Exception:
                perms = []
            emails = {p.get('emailAddress') for p in perms}
            if self.owner not in emails:
                sh.share(self.owner, perm_type='user', role='writer')

        value_updates = []
        clear_ranges = []
        batch_requests = []
        month_rows = {}

        # 1) Monthly tabs
        for month_str in months:
            dt = datetime.strptime(month_str, '%Y-%m')
            tab_title = dt.strftime(self.MONTH_FMT)
            txs = [tx for tx in transactions if tx.date.strftime('%Y-%m') == month_str]
            ws = self._get_tab(sh, tab_title, created)
            rows = [['date','description','merchant','category','amount']]
            for tx in txs:
                rows.append([
                    tx.date.isoformat(),
                    tx.description,
                    tx.merchant,
                    categorize(tx, self.config['categories']) or '',
                    tx.amount
                ])
            month_rows[tab_title] = rows
            clear_ranges.append(f"'{tab_title}'!A:Z")
            end_cell = rowcol_to_a1(len(rows), len(rows[0]))
            value_updates.append({
                'range': f"'{tab_title}'!A1:{end_cell}",
                'values': rows
            })

        # Ensure aggregate tabs exist before fetching metadata
        self._get_tab(sh, self.ALL_DATA, created, cols='6')
        self._get_tab(sh, self.SUMMARY, created, cols='10')
        self._get_tab(sh, self.CHARTS, created, cols='10')

        # 2) AllData tab: combine & dedupe
        monthly_data = {}
        for title, rows in month_rows.items():
            monthly_data[title] = [r[:5] for r in rows[1:]]

        for ws in sh.worksheets():
            title = ws.title
            if title in (self.ALL_DATA, self.SUMMARY) or title in monthly_data:
                continue
            monthly_data[title] = [row[:5] for row in ws.get_all_values()[1:]]

        all_rows = [['month','date','description','merchant','category','amount']]
        seen = set()
        for title, data_rows in monthly_data.items():
            for r in data_rows:
                key = (title,) + tuple(r)
                if key not in seen:
                    seen.add(key)
                    val = r[4] if len(r) > 4 else 0
                    try:
                        amount = float(
                            val if isinstance(val, (int, float))
                            else str(val).replace("$", "").replace(",", "")
                        )
                    except Exception:
                        amount = 0.0
                    all_rows.append([title] + r[:4] + [amount])

        clear_ranges.append(f"'{self.ALL_DATA}'!A:Z")
        end_cell = rowcol_to_a1(len(all_rows), len(all_rows[0]))
        value_updates.append({
            'range': f"'{self.ALL_DATA}'!A1:{end_cell}",
            'values': all_rows
        })

        # Fetch metadata once for sheet ids
        meta = self.sheets_srv.spreadsheets().get(
            spreadsheetId=sh.id,
            fields='sheets.properties'
        ).execute()['sheets']
        id_map = {s['properties']['title']: s['properties']['sheetId'] for s in meta}

        # Build requests for monthly tabs
        for title, rows in month_rows.items():
            sheet_id = id_map[title]
            batch_requests.extend(
                self._table_and_sort_requests(sheet_id, len(rows), len(rows[0]), amount_col_index=4)
            )
            batch_requests.append(
                self._month_pivot_request(sheet_id, len(rows))
            )
            batch_requests.extend(
                self._formatting_requests(sheet_id, len(rows[0]), amount_col_index=4, tab_rgb=(0.6,0.8,1.0))
            )

        # Requests for AllData tab
        all_sheet_id = id_map[self.ALL_DATA]
        batch_requests.extend(
            self._table_and_sort_requests(all_sheet_id, len(all_rows), len(all_rows[0]), amount_col_index=5)
        )
        batch_requests.extend(
            self._formatting_requests(all_sheet_id, len(all_rows[0]), amount_col_index=5, tab_rgb=(0.9,0.9,0.9))
        )

        # 3) Summary tab: single pivot grouping month & category
        clear_ranges.append(f"'{self.SUMMARY}'!A:Z")
        clear_ranges.append(f"'{self.CHARTS}'!A:Z")
        summary_sheet_id = id_map[self.SUMMARY]
        batch_requests.append(
            self._summary_pivot_request(
                summary_sheet_id,
                all_sheet_id,
                len(all_rows)
            )
        )
        batch_requests.extend(
            self._formatting_requests(summary_sheet_id, 10, amount_col_index=4, tab_rgb=(0.7,0.7,0.7))
        )

        # 4) Charts tab with aggregated tables + visuals
        chart_sheet_id = id_map[self.CHARTS]
        chart_tables = self._build_chart_tables(all_rows)
        chart_layout = {}
        start_row = 0
        for key in ('monthly', 'restaurants', 'groceries', 'categories'):
            table = chart_tables[key]
            chart_layout[key] = {
                'start_row': start_row,
                'row_count': len(table)
            }
            end_cell = rowcol_to_a1(start_row + len(table), 2)
            value_updates.append({
                'range': f"'{self.CHARTS}'!A{start_row + 1}:{end_cell}",
                'values': table
            })
            start_row += len(table) + 2
        batch_requests.extend(
            self._charts_tab_requests(
                chart_sheet_id,
                chart_layout
            )
        )

        # 5) Reorder tabs
        ordered = [self.SUMMARY, self.CHARTS, self.ALL_DATA]
        for m in range(1,13):
            t = f"{month_name[m]} {year}"
            if t in id_map:
                ordered.append(t)
        for idx, title in enumerate(ordered):
            sid = id_map[title]
            batch_requests.append({
                'updateSheetProperties': {
                    'properties': {'sheetId': sid, 'index': idx},
                    'fields': 'index'
                }
            })

        # Execute batched operations to minimise API calls
        if clear_ranges:
            self.sheets_srv.spreadsheets().values().batchClear(
                spreadsheetId=sh.id,
                body={'ranges': clear_ranges}
            ).execute()

        if value_updates:
            self.sheets_srv.spreadsheets().values().batchUpdate(
                spreadsheetId=sh.id,
                body={
                    'valueInputOption': 'USER_ENTERED',
                    'data': value_updates
                }
            ).execute()

        if batch_requests:
            self.sheets_srv.spreadsheets().batchUpdate(
                spreadsheetId=sh.id,
                body={'requests': batch_requests}
            ).execute()

        print(f"Built tabs for {len(months)} months, AllData, Summary, and reordered tabs in '{ss_title}'.")

    def _table_and_sort_requests(self, sheet_id, row_count, column_count, amount_col_index):
        if row_count <= 1 or column_count == 0:
            return []
        return [
            {
                'setBasicFilter': {
                    'filter': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': row_count,
                            'startColumnIndex': 0,
                            'endColumnIndex': column_count
                        }
                    }
                }
            },
            {
                'sortRange': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 1,
                        'endRowIndex': row_count,
                        'startColumnIndex': 0,
                        'endColumnIndex': column_count
                    },
                    'sortSpecs': [{
                        'dimensionIndex': amount_col_index,
                        'sortOrder': 'DESCENDING'
                    }]
                }
            }
        ]

    def _get_tab(self, sh, title, created_ss, rows='100', cols='10'):
        try:
            return sh.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            if created_ss and sh.sheet1.title == 'Sheet1':
                ws = sh.sheet1
                ws.update_title(title)
                return ws
            return sh.add_worksheet(title=title, rows=rows, cols=cols)

    def _month_pivot_request(self, sheet_id, row_count):
        return {
            'updateCells': {
                'rows': [{
                    'values': [{
                        'pivotTable': {
                            'source': {
                                'sheetId': sheet_id,
                                'startRowIndex': 0,
                                'endRowIndex': row_count,
                                'startColumnIndex': 0,
                                'endColumnIndex': 5
                            },
                            'rows': [{
                                'sourceColumnOffset': 3,
                                'showTotals': True,
                                'sortOrder': 'ASCENDING'
                            }],
                            'values': [{
                                'summarizeFunction': 'SUM',
                                'sourceColumnOffset': 4
                            }]
                        }
                    }]
                }],
                'start': {
                    'sheetId': sheet_id,
                    'rowIndex': 0,
                    'columnIndex': 6
                },
                'fields': 'pivotTable'
            }
        }

    def _summary_pivot_request(self, summary_sheet_id, all_sheet_id, all_row_count):
        return {
            'updateCells': {
                'rows': [{
                    'values': [{
                        'pivotTable': {
                            'source': {
                                'sheetId': all_sheet_id,
                                'startRowIndex': 0,
                                'endRowIndex': all_row_count,
                                'startColumnIndex': 0,
                                'endColumnIndex': 6
                            },
                            'rows': [
                                {
                                    'sourceColumnOffset': 0,
                                    'showTotals': True,
                                    'sortOrder': 'ASCENDING'
                                },
                                {
                                    'sourceColumnOffset': 4,
                                    'showTotals': True,
                                    'sortOrder': 'ASCENDING'
                                }
                            ],
                            'values': [{
                                'summarizeFunction': 'SUM',
                                'sourceColumnOffset': 5
                            }]
                        }
                    }]
                }],
                'start': {
                    'sheetId': summary_sheet_id,
                    'rowIndex': 0,
                    'columnIndex': 0
                },
                'fields': 'pivotTable'
            }
        }

    def _formatting_requests(self, sheet_id, column_count, amount_col_index, tab_rgb=(0.8,0.9,1.0)):
        header_fmt = {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': column_count
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {
                            'red': 0.9,
                            'green': 0.9,
                            'blue': 0.9
                        },
                        'textFormat': {'bold': True}
                    }
                },
                'fields': 'userEnteredFormat(backgroundColor,textFormat)'
            }
        }

        amount_fmt = {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 1,
                    'startColumnIndex': amount_col_index,
                    'endColumnIndex': amount_col_index + 1
                },
                'cell': {
                    'userEnteredFormat': {
                        'numberFormat': {
                            'type': 'CURRENCY',
                            'pattern': '"$"#,##0.00'
                        }
                    }
                },
                'fields': 'userEnteredFormat.numberFormat'
            }
        }

        freeze_req = {
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'gridProperties': {'frozenRowCount': 1},
                    'tabColor': {
                        'red': tab_rgb[0],
                        'green': tab_rgb[1],
                        'blue': tab_rgb[2]
                    }
                },
                'fields': 'gridProperties.frozenRowCount,tabColor'
            }
        }

        return [header_fmt, amount_fmt, freeze_req]

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
            category = (row[4] or '').strip()
            amount = row[5] or 0

            if month:
                month_totals[month] = month_totals.get(month, 0) + amount
                if month not in month_sort:
                    try:
                        month_sort[month] = datetime.strptime(month, self.MONTH_FMT)
                    except ValueError:
                        month_sort[month] = month

            category_norm = category.lower()
            if category_norm == 'restaurants':
                restaurant_totals[month] = restaurant_totals.get(month, 0) + amount
            if category_norm == 'groceries':
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
            'monthly': [['Month', 'Total']] + monthly_rows,
            'restaurants': [['Month', 'Total']] + restaurant_rows,
            'groceries': [['Month', 'Total']] + grocery_rows,
            'categories': [['Category', 'Total']] + category_rows
        }

    def _charts_tab_requests(self, chart_sheet_id, chart_layout):
        requests = []

        def pivot_range(start_row, row_count, start_col=0, col_count=2):
            return {
                'sources': [{
                    'sheetId': chart_sheet_id,
                    'startRowIndex': start_row,
                    'endRowIndex': start_row + row_count,
                    'startColumnIndex': start_col,
                    'endColumnIndex': start_col + col_count
                }]
            }

        def add_basic_chart(title, anchor_row, anchor_col, data_start_row, data_row_count):
            if data_row_count <= 1:
                return None
            return {
                'addChart': {
                    'chart': {
                        'spec': {
                            'title': title,
                            'basicChart': {
                                'chartType': 'COLUMN',
                                'legendPosition': 'BOTTOM_LEGEND',
                                'headerCount': 1,
                                'domains': [{
                                    'domain': {
                                        'sourceRange': pivot_range(data_start_row, data_row_count, start_col=0, col_count=1)
                                    }
                                }],
                                'series': [{
                                    'series': {
                                        'sourceRange': pivot_range(data_start_row, data_row_count, start_col=1, col_count=1)
                                    }
                                }]
                            }
                        },
                        'position': {
                            'overlayPosition': {
                                'anchorCell': {
                                    'sheetId': chart_sheet_id,
                                    'rowIndex': anchor_row,
                                    'columnIndex': anchor_col
                                },
                                'offsetXPixels': 0,
                                'offsetYPixels': 0,
                                'widthPixels': 600,
                                'heightPixels': 300
                            }
                        }
                    }
                }
            }

        monthly = chart_layout['monthly']
        restaurant = chart_layout['restaurants']
        grocery = chart_layout['groceries']
        categories = chart_layout['categories']

        for chart_request in (
            add_basic_chart('Monthly spending', 0, 6, monthly['start_row'], monthly['row_count']),
            add_basic_chart('Restaurant spending by month', 18, 6, restaurant['start_row'], restaurant['row_count']),
            add_basic_chart('Grocery spending by month', 36, 6, grocery['start_row'], grocery['row_count'])
        ):
            if chart_request:
                requests.append(chart_request)

        if categories['row_count'] > 1:
            requests.append({
                'addChart': {
                    'chart': {
                        'spec': {
                            'title': 'YTD spending by category',
                            'pieChart': {
                                'legendPosition': 'RIGHT_LEGEND',
                                'domain': {
                                    'sourceRange': pivot_range(categories['start_row'] + 1, categories['row_count'] - 1, start_col=0, col_count=1)
                                },
                                'series': {
                                    'sourceRange': pivot_range(categories['start_row'] + 1, categories['row_count'] - 1, start_col=1, col_count=1)
                                }
                            }
                        },
                        'position': {
                            'overlayPosition': {
                                'anchorCell': {
                                    'sheetId': chart_sheet_id,
                                    'rowIndex': 0,
                                    'columnIndex': 8
                                },
                                'offsetXPixels': 0,
                                'offsetYPixels': 0,
                                'widthPixels': 600,
                                'heightPixels': 300
                            }
                        }
                    }
                }
            })

        return requests
