# transaction_tracker/recurring.py
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional

from transaction_tracker.core.models import Transaction


def _parse_date(value, field_name, entry):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    raise ValueError(f"Unrecognized {field_name} in recurring entry: {entry}")


def _add_months(original_date: date, months: int) -> date:
    month_index = original_date.month - 1 + months
    year = original_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(original_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _next_date(current_date: date, cadence: str) -> date:
    if cadence == "daily":
        return current_date + timedelta(days=1)
    if cadence == "weekly":
        return current_date + timedelta(weeks=1)
    if cadence == "monthly":
        return _add_months(current_date, 1)
    raise ValueError(f"Unsupported cadence '{cadence}'.")


def _expand_entry(entry) -> List[Transaction]:
    cadence = entry.get("cadence")
    if cadence is None:
        raise ValueError(f"Missing 'cadence' in recurring entry: {entry}")

    start_date = _parse_date(entry.get("start_date"), "start_date", entry)
    if start_date is None:
        raise ValueError(f"Missing 'start_date' in recurring entry: {entry}")

    end_date = _parse_date(entry.get("end_date"), "end_date", entry)
    count = entry.get("count")
    if end_date is None and count is None:
        raise ValueError(
            "Recurring entries require either 'end_date' or 'count'."
        )
    if count is not None:
        count = int(count)
        if count <= 0:
            raise ValueError(
                "Recurring entries require 'count' to be greater than 0."
            )

    description = entry.get("description", "")
    merchant = entry.get("merchant", "")
    amount = float(entry.get("amount", 0.0))

    transactions = []
    current = start_date
    generated = 0
    while True:
        if end_date is not None and current > end_date:
            break
        if count is not None and generated >= count:
            break
        transactions.append(
            Transaction(
                date=current,
                description=description,
                merchant=merchant,
                amount=amount,
            )
        )
        generated += 1
        if cadence == "monthly":
            current = _add_months(start_date, generated)
        else:
            current = _next_date(current, cadence)

    return transactions


def expand_recurring_transactions(
    entries: Optional[Iterable[dict]],
) -> List[Transaction]:
    if not entries:
        return []
    expanded = []
    for entry in entries:
        expanded.extend(_expand_entry(entry))
    return expanded
