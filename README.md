# Budgify

A professional, extensible command-line tool for importing, categorizing, and exporting credit-card transactions into a unified monthly ledger or Google Sheets workbook.

## Overview

**Budgify** centralizes financial data across multiple banks and formats. It enables:

- **Seamless imports** from different banks (e.g., Amex, Canadian Tire, TD Visa, Home Trust).
- **Keyword-driven categorization** (restaurants, groceries, fun, fuel, etc.).
- **Flexible exports**:
  - **CSV** by default (one master `Budget<Year>.csv`, sorted oldest→newest).
  - **Google Sheets**: a single yearly workbook with per‑month tabs, an `AllData` tab, and a `Summary` pivot.
- **Plugin-based design** for easy addition of new banks and output formats.

## Architecture

### Loader Interface

`transaction_tracker/loaders/base.py`

```python
class BaseLoader(ABC):
    def load(self, file_path: str, include_payments: bool = False) -> Iterator[Transaction]:
        """
        Parse a statement file and yield Transaction objects.
        By default, payment transactions are excluded.
        """
```

- Implement one loader per bank in `transaction_tracker/loaders/`.
- Existing loaders: `AmexLoader`, `CanadianTireLoader`, new: `TDVisaLoader`, `HomeTrustLoader`.
- Each loader handles parsing, cleaning, payment filtering, and validation.

### Output Interface

`transaction_tracker/outputs/base.py`

```python
class BaseOutput(ABC):
    def append(self, transactions: List[Transaction], **kwargs) -> None:
        """
        Persist a list of Transaction objects according to the output's logic.
        """
```

- **CSVOutput** (`csv`): writes to `data/Budget<Year>.csv`, deduped & sorted.
- **SheetsOutput** (`sheets`): writes to a Google Sheets workbook (yearly), with:
  - Monthly tabs (e.g. "May 2025") containing raw data + live pivot.
  - An `AllData` tab de-duplicating all month-tabs with a `month` column.
  - A `Summary` tab aggregating by month & category.
  - Tabs auto‑reordered: Summary, AllData, Jan→Dec.

## Configuration

`config.yaml` configures loaders, outputs, categories, and Google credentials:

```yaml
bank_loaders:
  amex:       "transaction_tracker.loaders.amex.AmexLoader"
  canadiantire: "transaction_tracker.loaders.canadiantire.CanadianTireLoader"
  tdvisa:     "transaction_tracker.loaders.tdvisa.TDVisaLoader"
  hometrust:  "transaction_tracker.loaders.hometrust.HomeTrustLoader"

output_modules:
  csv:    "transaction_tracker.outputs.csv_output.CSVOutput"
  sheets: "transaction_tracker.outputs.sheets_output.SheetsOutput"

categories:
  restaurants: [...]
  groceries:   [...]
  fun:         []
  fuel:        []
  # etc.

data_dir:     "./data"   # default local output dir for CSV

google:
  service_account_file: "/path/to/service-account.json"
  sheet_folder_id:      "GOOGLE_DRIVE_FOLDER_ID"  # optional
  owner_email:          "your.email@example.com" # for sharing new sheets

```

## Installation

```bash
git clone https://github.com/yourusername/transaction-cli.git
cd transaction-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# Optional: if you use SheetsOutput, also:
pip install gspread google-auth google-api-python-client
```

## Usage

### CSV Export

```bash
# Process all statements in a directory, exclude payments:
budgify --dir ~/Downloads/statements --output csv
```

Results:  `data/Budget2025.csv` (for year 2025), deduped and sorted by date.

### Google Sheets Export

1. Ensure **Sheets API** and **Drive API** are enabled in Google Cloud.
2. Create a **Service Account**, download JSON key, share your Drive folder with it.
3. Add credentials to `config.yaml` under `google:`.

```bash
budgify --dir ~/Downloads/statements --output sheets
```

This will create (or update) a **"Budget 2025"** workbook in your Drive folder, with:

- Monthly tabs ("Jan 2025", ...), each with raw data + pivot.
- An `AllData` tab.
- A `Summary` tab aggregating by month & category.

## Extending

### Add a new bank loader

1. Create a subclass of `BaseLoader` in `transaction_tracker/loaders/YourBank.py`.
2. Implement `load(self, file_path, include_payments=False)` to yield `Transaction`.
3. Register it in `config.yaml` under `bank_loaders`.

### Add a new output format

1. Create a subclass of `BaseOutput` in `transaction_tracker/outputs/your_output.py`.
2. Implement `append(self, transactions, **kwargs)`.
3. Register it under `output_modules` in `config.yaml`.

## Contributing

1. Fork the repository.
2. Write your code and tests.
3. Update documentation.
4. Submit a pull request.

## License

Released under the [MIT License](LICENSE).

