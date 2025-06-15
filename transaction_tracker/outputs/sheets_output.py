# transaction_tracker/outputs/sheets_output.py

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
from dateutil import parser as date_parser
from transaction_tracker.outputs.base import BaseOutput
from transaction_tracker.core.categorizer import categorize


class SheetsOutput(BaseOutput):
    """
    Writes transactions into a single yearly Google Sheet named "Budget YYYY",
    with each month as its own tab (e.g., "May 2025").
    On each tab, raw data (columns A–E) is written, sorted by empty categories first,
    and a live pivot table is injected on the same sheet (starting in column G)
    that sums amounts by category.
    """
    def __init__(self, config):
        self.config      = config
        google_cfg       = config.get('google', {})
        cred_path        = google_cfg.get('service_account_file')
        scopes           = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds            = Credentials.from_service_account_file(cred_path, scopes=scopes)
        self.gc          = gspread.authorize(creds)
        self.sheets_srv  = build('sheets', 'v4', credentials=creds)
        self.drive_srv   = build('drive', 'v3', credentials=creds)
        self.folder_id   = google_cfg.get('sheet_folder_id')
        self.owner_email = google_cfg.get('owner_email')

    def append(self, transactions, month=None):
        # Determine year and human-readable month name
        month_str = month or datetime.now().strftime('%Y-%m')
        dt        = datetime.strptime(month_str, '%Y-%m')
        year      = dt.strftime('%Y')
        tab_title = dt.strftime('%B %Y')  # e.g., "May 2025"
        ss_title  = f"Budget {year}"

        # 1) Open or create the yearly spreadsheet
        try:
            sh = self.gc.open(ss_title)
            created_ss = False
        except gspread.exceptions.SpreadsheetNotFound:
            sh = self.gc.create(ss_title)
            created_ss = True

        # 2) Move into Drive folder (and out of SA root)
        if self.folder_id:
            meta    = self.drive_srv.files().get(
                fileId=sh.id,
                fields='parents'
            ).execute()
            parents = set(meta.get('parents', []))
            to_add    = [] if self.folder_id in parents else [self.folder_id]
            to_remove = ['root'] if 'root' in parents else []
            if to_add or to_remove:
                self.drive_srv.files().update(
                    fileId        = sh.id,
                    addParents    = ",".join(to_add),
                    removeParents = ",".join(to_remove),
                    fields        = 'id, parents'
                ).execute()

        # 3) Share with personal account for visibility
        if self.owner_email:
            sh.share(self.owner_email, perm_type='user', role='writer')

        # 4) Find or create the month tab
        try:
            ws_raw = sh.worksheet(tab_title)
        except gspread.exceptions.WorksheetNotFound:
            if created_ss and sh.sheet1.title == 'Sheet1':
                ws_raw = sh.sheet1
                ws_raw.update_title(tab_title)
            else:
                ws_raw = sh.add_worksheet(title=tab_title, rows="1000", cols="7")

        # 5) Build raw rows for columns A–E
        rows = [['date','description','merchant','category','amount']]
        for tx in transactions:
            date_s   = tx.date.isoformat() if hasattr(tx.date, 'isoformat') else str(tx.date)
            cat      = categorize(tx, self.config['categories']) or ''
            amt_s    = f"{tx.amount:.2f}" if isinstance(tx.amount, float) else str(tx.amount)
            rows.append([date_s, tx.description, tx.merchant, cat, amt_s])

        # Clear and write with USER_ENTERED so amounts are numeric
        ws_raw.clear()
        ws_raw.update('A1', rows, value_input_option='USER_ENTERED')

        # 6) Sort the range A2:E by Category (column D, index 3) -- blanks first
        # Fetch sheetId for the tab
        meta      = self.sheets_srv.spreadsheets().get(
            spreadsheetId=sh.id,
            fields='sheets.properties'
        ).execute()
        props     = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}
        raw_id    = props[tab_title]
        sort_req  = {
            'sortRange': {
                'range': {
                    'sheetId': raw_id,
                    'startRowIndex': 1,
                    'endRowIndex': len(rows),
                    'startColumnIndex': 0,
                    'endColumnIndex': 5
                },
                'sortSpecs': [{
                    'dimensionIndex': 3,
                    'sortOrder': 'ASCENDING'
                }]
            }
        }

        # 7) Inject pivot table in column G on same tab
        pivot_req = {
            'updateCells': {
                'rows': [{
                    'values': [{
                        'pivotTable': {
                            'source': {
                                'sheetId': raw_id,
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
                'start': {'sheetId': raw_id, 'rowIndex': 0, 'columnIndex': 6},
                'fields': 'pivotTable'
            }
        }

        # Batch update: sort then pivot
        self.sheets_srv.spreadsheets().batchUpdate(
            spreadsheetId=sh.id,
            body={'requests': [sort_req, pivot_req]}
        ).execute()

        print(
            f"Wrote {len(rows)-1} rows to '{tab_title}' tab in '{ss_title}', "
            f"sorted by category (blanks first) and updated pivot at G1."
        )
