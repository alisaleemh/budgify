from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from transaction_tracker.core.models import Transaction
from transaction_tracker.loaders.base import BaseLoader

_RAW_FILENAME_RX = re.compile(r"^credit-card-statement-transactions-(\d{4})-(\d{2})-(\d{2})\.csv$", re.I)
_NORMALIZED_FILENAME_RX = re.compile(r"^ws-(\d{2})-(\d{4})\.csv$", re.I)


def normalize_statement_filename(source: str | Path) -> str:
    """
    Convert a Wealthsimple export name into the repository's normalized form.

    Examples:
      credit-card-statement-transactions-2026-05-01.csv -> ws-05-2026.csv
      ws-05-2026.csv -> ws-05-2026.csv
    """
    name = Path(source).name
    normalized = _NORMALIZED_FILENAME_RX.match(name)
    if normalized:
        return name.lower()

    raw = _RAW_FILENAME_RX.match(name)
    if not raw:
        raise ValueError(f"Unrecognized Wealthsimple statement filename: {name}")

    year, month, _day = raw.groups()
    return f"ws-{month}-{year}.csv"


class WealthsimpleLoader(BaseLoader):
    """
    Loader for Wealthsimple credit card CSV statements.

    Expected headers:
      - transaction_date
      - post_date
      - type
      - details
      - amount
      - currency

    The loader is intentionally compact: it preserves the statement type as the
    description, uses the statement details as the merchant, and keeps the raw
    signed amount from the CSV.
    """

    REQUIRED_COLUMNS = {
        "transaction_date",
        "type",
        "details",
        "amount",
    }

    PAYMENT_TYPES = {
        "payment",
        "payment settled",
        "payment received",
    }

    def load(self, file_path, include_payments=False):
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise RuntimeError(f"Missing header row in {file_path}")

            cols = {str(name).strip().lower() for name in reader.fieldnames}
            missing = sorted(self.REQUIRED_COLUMNS - cols)
            if missing:
                raise RuntimeError(
                    f"Missing required column(s) {', '.join(missing)} in {file_path}"
                )

            for row in reader:
                raw_date = str(row.get("transaction_date", "")).strip()
                if not raw_date:
                    continue
                try:
                    tx_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                except ValueError as exc:
                    raise ValueError(
                        f"Could not parse transaction_date '{raw_date}' in {file_path}: {exc}"
                    ) from exc

                tx_type = str(row.get("type", "")).strip()
                details = str(row.get("details", "")).strip()
                amt_raw = str(row.get("amount", "")).strip()
                if not amt_raw:
                    continue
                try:
                    amount = float(amt_raw)
                except ValueError as exc:
                    raise ValueError(
                        f"Could not parse amount '{amt_raw}' in {file_path}"
                    ) from exc

                description = tx_type or details
                merchant = details or tx_type or description
                tx = Transaction(
                    date=tx_date,
                    description=description,
                    merchant=merchant,
                    amount=amount,
                )

                is_payment = description.lower() in self.PAYMENT_TYPES
                if not include_payments and is_payment:
                    continue
                if include_payments and is_payment and tx.amount >= 0:
                    raise RuntimeError(f"Wealthsimple payment not negative: {tx}")

                yield tx
