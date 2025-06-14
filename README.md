# Budgify

A professional, extensible command-line tool for importing, categorizing, and exporting credit-card transactions into a unified monthly ledger.

## Overview

**Budgify** centralizes financial data across multiple banks and formats. It enables:

* **Seamless imports** from different banks (e.g., Amex, Canadian Tire).
* **Keyword-driven categorization** (restaurants, groceries, fun, fuel).
* **Flexible exports** (CSV by default; extendable to Excel, databases, etc.).
* **Plugin-based design** for easy addition of new banks and output formats.

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

* Implement one loader per bank in `transaction_tracker/loaders/`.
* Each loader handles header detection, parsing, payment filtering, and validation.

### Output Interface

`transaction_tracker/outputs/base.py`

```python
class BaseOutput(ABC):
    def append(self, transactions: List[Transaction], month: str) -> None:
        """
        Persist transactions for the specified YYYY-MM period.
        """
```

* Implement one output per format in `transaction_tracker/outputs/`.
* The default CSV output writes to `data/{YYYY-MM}.csv`, creating headers as needed.

## Configuration

Configure available loaders, outputs, and categories in `config.yaml`:

```yaml
bank_loaders:
  amex:       "transaction_tracker.loaders.amex.AmexLoader"
  canadiantire: "transaction_tracker.loaders.canadiantire.CanadianTireLoader"

output_modules:
  csv:        "transaction_tracker.outputs.csv_output.CSVOutput"

categories:
  restaurants: ["restaurant", "cafe"]
  groceries:   ["supermarket", "mart"]
  fun:         ["uber", "netflix"]
  fuel:        ["petro", "shell"]

data_dir:     "./data"  # default output directory
```

## Installation

```bash
git clone https://github.com/yourusername/transaction-cli.git
cd transaction-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install click pyyaml pandas openpyxl xlrd
pip freeze > requirements.txt
```

## Usage

```bash
# Process a directory of statements and exclude payments (default)
budgify --dir ~/Downloads/statements \
         --month 2025-05

# Include payments (must be negative amounts)
budgify --dir ~/Downloads/statements \
         --month 2025-05 \
         --include-payments
```

* `--dir`: directory containing statement files; filenames match bank keys (e.g., "amex" or "canadiantire").
* `--month`: target ledger in `YYYY-MM`.
* `--include-payments`: include payment transactions.

Outputs are saved under `data/{YYYY-MM}.csv` by default.

## Extending

**Add a new bank**

1. Create a subclass of `BaseLoader` in `transaction_tracker/loaders/`.
2. Register it in `config.yaml` under `bank_loaders`.

**Add a new output**

1. Create a subclass of `BaseOutput` in `transaction_tracker/outputs/`.
2. Register it in `config.yaml` under `output_modules`.

## Contributing

1. Fork the repository.
2. Implement feature/tests.
3. Update documentation and examples.
4. Submit a pull request.

## License

Released under the [MIT License](LICENSE).
