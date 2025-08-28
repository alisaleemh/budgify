# transaction_tracker/outputs/sheets_output.py

import gspread
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

        # 1) Monthly tabs
        for month_str in months:
            dt = datetime.strptime(month_str, '%Y-%m')
            tab_title = dt.strftime(self.MONTH_FMT)
            # filter transactions for this month
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
            ws.clear()
            ws.update('A1', rows, value_input_option='USER_ENTERED')
            self._ensure_pivot(ws, rows, ws.title)
            self._apply_formatting(ws, tab_rgb=(0.6,0.8,1.0))

        # 2) AllData tab: combine & dedupe
        all_rows = [['month','date','description','merchant','category','amount']]
        seen = set()
        for ws in sh.worksheets():
            title = ws.title
            if title in (self.ALL_DATA, self.SUMMARY):
                continue
            # Only consider the first five columns (transaction data) to avoid
            # picking up pivot-table output appended to the worksheet.
            data = [row[:5] for row in ws.get_all_values()[1:]]
            for r in data:
                key = (title,) + tuple(r)
                if key not in seen:
                    seen.add(key)
                    # Try parsing the amount column if it looks like a currency
                    val = r[4]
                    try:
                        amount = float(
                            val if isinstance(val, (int, float))
                            else val.replace("$", "").replace(",", "")
                        )
                    except Exception:
                        amount = 0.0
                    all_rows.append([title] + r[:4] + [amount])
        all_ws = self._get_tab(sh, self.ALL_DATA, created, cols='6')
        all_ws.clear()
        all_ws.update('A1', all_rows, value_input_option='USER_ENTERED')
        self._apply_formatting(all_ws, tab_rgb=(0.9,0.9,0.9))

        # 3) Summary tab: single pivot grouping month & category
        sum_ws = self._get_tab(sh, self.SUMMARY, created, cols='10')
        sum_ws.clear()
        meta = self.sheets_srv.spreadsheets().get(
            spreadsheetId=sh.id,
            fields='sheets.properties'
        ).execute()['sheets']
        id_map = {s['properties']['title']: s['properties']['sheetId'] for s in meta}
        pivot_req = {
            'updateCells': {
                'rows': [{
                    'values': [{
                        'pivotTable': {
                            'source': {
                                'sheetId': id_map[self.ALL_DATA],
                                'startRowIndex': 0,
                                'endRowIndex': len(all_rows),
                                'startColumnIndex': 0,
                                'endColumnIndex': 6
                            },
                            'rows': [
                                {'sourceColumnOffset': 0, 'showTotals': True, 'sortOrder': 'ASCENDING'},
                                {'sourceColumnOffset': 4, 'showTotals': True, 'sortOrder': 'ASCENDING'}
                            ],
                            'values': [{
                                'summarizeFunction': 'SUM',
                                'sourceColumnOffset': 5
                            }]
                        }
                    }]
                }],
                'start': {'sheetId': id_map[self.SUMMARY], 'rowIndex': 0, 'columnIndex': 0},
                'fields': 'pivotTable'
            }
        }
        self.sheets_srv.spreadsheets().batchUpdate(
            spreadsheetId=sh.id,
            body={'requests': [pivot_req]}
        ).execute()
        self._apply_formatting(sum_ws, tab_rgb=(0.7,0.7,0.7))

        # 4) Reorder tabs
        meta = self.sheets_srv.spreadsheets().get(
            spreadsheetId=sh.id,
            fields='sheets.properties'
        ).execute()['sheets']
        id_map = {s['properties']['title']: s['properties']['sheetId'] for s in meta}
        ordered = [self.SUMMARY, self.ALL_DATA]
        for m in range(1,13):
            t = f"{month_name[m]} {year}"
            if t in id_map:
                ordered.append(t)
        reqs = []
        for idx, title in enumerate(ordered):
            sid = id_map[title]
            reqs.append({
                'updateSheetProperties': {
                    'properties': {'sheetId': sid, 'index': idx},
                    'fields': 'index'
                }
            })
        if reqs:
            self.sheets_srv.spreadsheets().batchUpdate(
                spreadsheetId=sh.id,
                body={'requests': reqs}
            ).execute()

        print(f"Built tabs for {len(months)} months, AllData, Summary, and reordered tabs in '{ss_title}'.")

    def _get_tab(self, sh, title, created_ss, rows='100', cols='10'):
        try:
            return sh.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            if created_ss and sh.sheet1.title == 'Sheet1':
                ws = sh.sheet1
                ws.update_title(title)
                return ws
            return sh.add_worksheet(title=title, rows=rows, cols=cols)

    def _ensure_pivot(self, ws, rows, title):
        ss       = ws.spreadsheet.id
        meta     = self.sheets_srv.spreadsheets().get(
            spreadsheetId=ss,
            fields='sheets.properties'
        ).execute()['sheets']
        sheet_id = next(
            s['properties']['sheetId']
            for s in meta if s['properties']['title']==title
        )
        pivot_req = {
            'updateCells': {
                'rows': [{
                    'values': [{
                        'pivotTable': {
                            'source': {
                                'sheetId': sheet_id,
                                'startRowIndex': 0,
                                'endRowIndex': len(rows),
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
                'start': {'sheetId': sheet_id, 'rowIndex': 0, 'columnIndex': 6},
                'fields': 'pivotTable'
            }
        }
        self.sheets_srv.spreadsheets().batchUpdate(
            spreadsheetId=ss,
            body={'requests':[pivot_req]}
        ).execute()

    def _apply_formatting(self, ws, tab_rgb=(0.8,0.9,1.0)):
        """Apply basic formatting to the worksheet for better readability."""
        ss       = ws.spreadsheet.id
        meta     = self.sheets_srv.spreadsheets().get(
            spreadsheetId=ss,
            fields='sheets.properties'
        ).execute()['sheets']
        sheet_id = next(
            s['properties']['sheetId']
            for s in meta if s['properties']['title'] == ws.title
        )

        header_fmt = {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': 1
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
                    'startColumnIndex': 4,
                    'endColumnIndex': 5
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

        self.sheets_srv.spreadsheets().batchUpdate(
            spreadsheetId=ss,
            body={'requests': [header_fmt, amount_fmt, freeze_req]}
        ).execute()
