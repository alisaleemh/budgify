# transaction_tracker/outputs/sheets_output.py

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from transaction_tracker.outputs.base import BaseOutput
from transaction_tracker.core.categorizer import categorize


class SheetsOutput(BaseOutput):
    PIVOT_SHEET = "Pivot"

    def __init__(self, config):
        self.config     = config
        google_cfg      = config.get('google', {})
        cred_path       = google_cfg.get('service_account_file')
        scopes          = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds           = Credentials.from_service_account_file(cred_path, scopes=scopes)
        self.gc         = gspread.authorize(creds)
        self.sheets_srv = build('sheets', 'v4', credentials=creds)
        self.drive_srv  = build('drive', 'v3', credentials=creds)

        self.folder_id   = google_cfg.get('sheet_folder_id')
        self.owner_email = google_cfg.get('owner_email')

    def append(self, transactions, month=None):
        # 0) Determine spreadsheet & sheet names
        month      = month or __import__('datetime').datetime.now().strftime('%Y-%m')
        ss_title   = f"Budget {month}"
        raw_title  = month
        pivot_title= self.PIVOT_SHEET

        # 1) Open or create the spreadsheet
        try:
            sh = self.gc.open(ss_title)
            created_spreadsheet = False
        except gspread.exceptions.SpreadsheetNotFound:
            sh = self.gc.create(ss_title)
            created_spreadsheet = True

        # 2) Move the spreadsheet into your Drive folder once
        if self.folder_id:
            meta    = self.drive_srv.files().get(fileId=sh.id, fields='parents').execute()
            parents = set(meta.get('parents', []))
            to_add    = [] if self.folder_id in parents else [self.folder_id]
            to_remove = ['root'] if 'root' in parents else []
            if to_add or to_remove:
                self.drive_srv.files().update(
                    fileId       = sh.id,
                    addParents    = ",".join(to_add),
                    removeParents = ",".join(to_remove),
                    fields        = 'id, parents'
                ).execute()

        # 3) Share with your personal account so it surfaces in your Drive UI
        if self.owner_email:
            sh.share(self.owner_email, perm_type='user', role='writer')

        # 4) Find or create the raw‐data sheet (named after month)
        try:
            ws_raw = sh.worksheet(raw_title)
        except gspread.exceptions.WorksheetNotFound:
            # if it's the very first sheet (“Sheet1”), rename it
            if created_spreadsheet and sh.sheet1.title == 'Sheet1':
                ws_raw = sh.sheet1
                ws_raw.update_title(raw_title)
            else:
                ws_raw = sh.add_worksheet(title=raw_title, rows="100", cols="5")

        # 5) Write raw data into that sheet
        rows = [['date','description','merchant','category','amount']]
        for tx in transactions:
            date_s   = tx.date.isoformat() if hasattr(tx.date, 'isoformat') else str(tx.date)
            cat      = categorize(tx, self.config['categories']) or ''
            amt_s    = f"{tx.amount:.2f}" if isinstance(tx.amount, float) else str(tx.amount)
            rows.append([date_s, tx.description, tx.merchant, cat, amt_s])

        ws_raw.clear()
        # ensure numeric amounts so pivot works
        ws_raw.update('A1', rows, value_input_option='USER_ENTERED')

        # 6) Find or create the pivot sheet
        try:
            ws_pivot = sh.worksheet(pivot_title)
            created_pivot = False
        except gspread.exceptions.WorksheetNotFound:
            ws_pivot = sh.add_worksheet(title=pivot_title, rows="20", cols="10")
            created_pivot = True

        # 7) On first creation of pivot sheet (or new spreadsheet), inject the pivot definition
        if created_pivot or created_spreadsheet:
            # fetch sheet IDs
            meta     = self.sheets_srv.spreadsheets().get(
                spreadsheetId=sh.id, fields='sheets.properties'
            ).execute()
            props    = {s['properties']['title']: s['properties']['sheetId']
                        for s in meta['sheets']}
            raw_id   = props[raw_title]
            pivot_id = props[pivot_title]

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
                    'start': {'sheetId': pivot_id, 'rowIndex': 0, 'columnIndex': 0},
                    'fields': 'pivotTable'
                }
            }
            self.sheets_srv.spreadsheets().batchUpdate(
                spreadsheetId=sh.id,
                body={'requests': [pivot_req]}
            ).execute()

        print(f"Wrote {len(rows)-1} rows to '{raw_title}', pivot sheet is '{pivot_title}'.")