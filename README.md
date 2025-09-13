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

Create your own `config.yaml` (ignored by Git) based on `examples/config.example.yaml`.
This file configures loaders, outputs, categories, and Google credentials:

```yaml
bank_loaders:
  amex:       "transaction_tracker.loaders.amex.AmexLoader"
  canadiantire: "transaction_tracker.loaders.canadiantire.CanadianTireLoader"
  tdvisa:     "transaction_tracker.loaders.tdvisa.TDVisaLoader"
  hometrust:  "transaction_tracker.loaders.hometrust.HomeTrustLoader"

output_modules:
  csv:    "transaction_tracker.outputs.csv_output.CSVOutput"
  sheets: "transaction_tracker.outputs.sheets_output.SheetsOutput"
  excel:  "transaction_tracker.outputs.excel_output.ExcelOutput"

# Optional YAML listing any cash or other manual transactions
manual_transactions_file: manual.yaml

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

`config.yaml` and your personal `manual.yaml` are listed in `.gitignore` so they remain local. Copy the templates from `examples/` and modify them as needed.

## Installation

```bash
git clone https://github.com/yourusername/budgify.git
cd budgify
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# Or use the task runner:
task install
# Optional: if you use SheetsOutput, also:
pip install gspread google-auth google-api-python-client
```

### Packaging

Build a wheel for distribution using the `task` runner:

```bash
task build
```

Install the cross-platform [`task`](https://taskfile.dev) binary if you don't already have it.
The wheel will be placed in `dist/`. Copy it to another machine and install via:

```bash
pip install dist/budgify-<version>-py3-none-any.whl
```

## Usage

### CSV Export

```bash
# Process all statements in a directory, exclude payments:
budgify --dir ~/Downloads/statements --output csv
# You can optionally specify a different YAML of manual transactions
# budgify --dir ~/Downloads/statements --manual-file my_manual.yaml --output csv
# Save transactions to SQLite as well
# budgify --dir ~/Downloads/statements --output csv --db mydata.db
```

Results:  `data/Budget2025.csv` (for year 2025), deduped and sorted by date.

### Excel Export

```bash
budgify --dir ~/Downloads/statements --output excel
# or combine with a database:
# budgify --dir ~/Downloads/statements --output excel --db mydata.db
```

Generates a local `Budget2025.xlsx` workbook with monthly tabs (sorted from
largest to smallest transaction), an `AllData` tab, and a manually generated
`Summary` sheet that aggregates totals by month and category without using Excel
PivotTables.

### Manual Transactions

Any cash purchases or other expenses not present in bank statements can be
listed in a small YAML file. Set `manual_transactions_file` in `config.yaml` or
provide `--manual-file` on the command line. See
`examples/manual.example.yaml` for a template.

Example `manual.yaml`:

```yaml
- date: 2025-05-05
  description: Farmers Market
  merchant: CASH
  amount: 23.50
```

These entries are loaded alongside statement data and deduplicated.

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

### AI Report

Pass `--ai-report` when running Budgify to send the final list of
transactions to an LLM for analysis.  `transaction_tracker.ai` exposes an
`LLMClient` capable of using multiple providers (Hugging Face or OpenAI
via environment variables) and composable output layers.  The default
`InsightsReport` class is used by the CLI.  Configure your provider with
`HF_API_TOKEN` or `OPENAI_API_KEY` (and `BUDGIFY_LLM_PROVIDER=openai`).
These variables can be stored in a `.env` file and loaded with
`--env-file path/to/.env`.

To use a local LLM such as [Ollama](https://github.com/ollama/ollama), set
`BUDGIFY_LLM_PROVIDER=ollama` and optionally `OLLAMA_URL` if your server is not
running on `http://localhost:11434`.

### MCP Server

Budgify can be exposed as an MCP server so tools like a locally running LLM can
invoke it directly. Install the optional `mcp` dependency and run:

```bash
budgify-mcp
```

This starts a FastMCP server exposing a single `run_budgify` tool.

### Go MCP Server

A lightweight HTTP server written in Go also exposes the transactions
database via an MCP-friendly endpoint. Run it with:

```bash
go run transaction_tracker/go_mcp_server/main.go
```

Set the `BUDGIFY_DB` environment variable to point at your SQLite
database (defaults to `budget.db`). The server listens on `:8080` and
provides `/get_spend_by_category_month`, returning monthly totals by
category in JSON.

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

## Testing

Budgify's tests require `pytest` and `PyYAML`. Install dependencies from `requirements.txt` and run:

```bash
pip install -r requirements.txt
pytest -q
```

Alternatively use the task runner which installs dependencies first:

```bash
task test
```

Google Sheets APIs are mocked, so the test suite runs offline.

## License

Released under the [MIT License](LICENSE).

