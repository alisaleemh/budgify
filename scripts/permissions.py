import sys
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from gspread.exceptions import APIError

# === CONFIGURE THESE ===
SERVICE_ACCOUNT_FILE = "/Users/asaleemh/git/budgify/personal-462917-96895ffc2fc9.json"
SPREADSHEET_ID = "1VzmoIc69vnCsKWd5rQ4ZSPthLV_3smtF"
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def main():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)

    print(f"🔍 Using service account: {creds.service_account_email}")

    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.sheet1
        print(f"📄 Accessed sheet: {sh.title}")
        print(f"🔢 Worksheet rows: {ws.row_count}, cols: {ws.col_count}")

        # Test write
        ws.update("A1", [["Permission", "Status"], ["Read", "✅"], ["Write", "✅"]],
                  value_input_option='USER_ENTERED')
        print("✍️  Successfully wrote to the sheet")

        # Test read
        data = ws.get("A1:B3")
        print("📖 Read data:")
        for row in data:
            print("  ", row)

        # Test clear
        ws.clear()
        print("🧹 Successfully cleared the sheet")

    except APIError as e:
        print(f"❌ API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        sys.exit(1)

    print("✅ All permission checks passed.")

if __name__ == "__main__":
    main()
