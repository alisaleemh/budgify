from __future__ import annotations

import logging
import os
import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Literal
from urllib.parse import urlparse

import anyio
from mcp.server.fastmcp import FastMCP

from transaction_tracker.database import (
    category_insights,
    list_categories,
    list_providers,
    list_unique_merchants,
    overview_metrics,
    query_transactions,
    summarize_by_category,
    summarize_by_merchant,
    summarize_by_period,
)

MAX_GROUPS = 50
MAX_ROWS = 100
DEFAULT_LIMIT = 20
DEFAULT_TX_LIMIT = 25
MAX_BUNDLE_QUERIES = 5
DEFAULT_FIELDS = ["id", "date", "amountCents", "merchant", "category"]
FIELD_ALLOWLIST = {
    "id",
    "date",
    "amountCents",
    "merchant",
    "category",
    "account",
    "description",
    "notes",
}
SAFE_BUNDLE_TOOLS = {
    "spend_summary",
    "merchant_summary",
    "category_summary",
    "compare_periods",
    "top_drivers",
    "recurring_transactions",
    "anomalies",
    "search_dimensions",
}

server = FastMCP(
    name="Budgify",
    instructions=(
        "Expose Budgify finance data through compact read-only MCP tools. "
        "Use aggregates first. Avoid raw rows unless find_transactions needed."
    ),
    log_level=os.environ.get("LOG_LEVEL", "info").upper(),
    host="127.0.0.1",
    port=int(os.environ.get("MCP_PORT", "8002")),
)

logger = logging.getLogger(__name__)

try:
    BUDGIFY_VERSION = version("budgify")
except PackageNotFoundError:
    BUDGIFY_VERSION = "0.1.0"

CATEGORIES = [
    "subscription",
    "car",
    "misc",
    "restaurants",
    "groceries",
    "communications",
    "charity",
    "learning",
    "commute",
    "insurance",
    "medical",
    "fun",
]


class McpInputError(ValueError):
    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def as_dict(self) -> dict[str, str]:
        payload = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        return payload


def _err(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, McpInputError):
        return {"error": exc.as_dict()}
    logger.exception("MCP tool failed")
    return {"error": {"code": "SERVER_ERROR", "message": "tool failed"}}


def _db_path(dbPath: str | None = None) -> str:
    value = dbPath or os.environ.get("DATABASE_URL") or os.environ.get("BUDGIFY_DB_PATH") or "budgify.db"
    if value.startswith("sqlite:///"):
        return urlparse(value).path
    if "://" in value and value != ":memory:":
        raise McpInputError("INVALID_DB", "only sqlite DATABASE_URL supported")
    return value


def _connect(dbPath: str | None = None) -> sqlite3.Connection:
    path = _db_path(dbPath)
    if path != ":memory:" and not path.startswith("file:"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_date(value: str | None, field: str = "date") -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise McpInputError("INVALID_DATE", f"{field} must be YYYY-MM-DD", "Use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise McpInputError("INVALID_DATE", f"{field} must be YYYY-MM-DD", "Use YYYY-MM-DD") from exc


def _require_range(startDate: str | None, endDate: str | None) -> tuple[date, date]:
    start = _parse_date(startDate, "startDate")
    end = _parse_date(endDate, "endDate")
    if not start or not end:
        raise McpInputError("INVALID_DATE_RANGE", "startDate/endDate required", "Use YYYY-MM-DD")
    if start > end:
        raise McpInputError("INVALID_DATE_RANGE", "startDate must be before endDate")
    return start, end


def _optional_range(startDate: str | None, endDate: str | None) -> tuple[date | None, date | None]:
    start = _parse_date(startDate, "startDate")
    end = _parse_date(endDate, "endDate")
    if start and end and start > end:
        raise McpInputError("INVALID_DATE_RANGE", "startDate must be before endDate")
    return start, end


def _limit(value: int | None, default: int = DEFAULT_LIMIT, max_value: int = MAX_GROUPS) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise McpInputError("INVALID_LIMIT", "limit must be integer") from exc
    if parsed < 1:
        raise McpInputError("INVALID_LIMIT", "limit must be positive")
    return min(parsed, max_value)


def _id(label: str | None) -> str:
    text = (label or "uncategorized").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "uncategorized"


def _cents(amount: Any) -> int:
    return int(round(float(amount or 0) * 100))


def _money(cents: int) -> float:
    return round(cents / 100.0, 2)


def _clean(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: _clean(v) for k, v in payload.items() if v not in (None, [], {})}
    if isinstance(payload, list):
        return [_clean(item) for item in payload]
    return payload


def _filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise McpInputError("INVALID_FILTERS", "filters must be object")
    allowed = {"categoryIds", "merchantIds", "accountIds", "search"}
    unknown = set(filters) - allowed
    if unknown:
        raise McpInputError("INVALID_FILTERS", f"unsupported filter {sorted(unknown)[0]}")
    return filters


def _list(value: Any, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise McpInputError("INVALID_FILTERS", f"{field} must be list")
    return [str(item).strip() for item in value if str(item).strip()]


def _rows(
    dbPath: str | None,
    start: date | None = None,
    end: date | None = None,
    filters: dict[str, Any] | None = None,
    min_cents: int | None = None,
    max_cents: int | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict[str, Any]]:
    f = _filters(filters)
    category_ids = set(_list(f.get("categoryIds"), "categoryIds"))
    merchant_ids = set(_list(f.get("merchantIds"), "merchantIds"))
    account_ids = set(_list(f.get("accountIds"), "accountIds"))
    search = str(f.get("search") or "").strip().lower()
    rows = query_transactions(
        _db_path(dbPath),
        start_date=start,
        end_date=end,
        min_amount=_money(min_cents) if min_cents is not None else None,
        max_amount=_money(max_cents) if max_cents is not None else None,
        sort_by="date",
        sort_dir="asc",
        limit=limit,
        offset=offset,
    )
    out = []
    for row in rows:
        category = row.get("category") or "uncategorized"
        merchant = row.get("merchant") or ""
        account = row.get("provider") or ""
        haystack = " ".join(str(row.get(key) or "") for key in ("merchant", "description", "category", "provider")).lower()
        if category_ids and _id(category) not in category_ids and category not in category_ids:
            continue
        if merchant_ids and _id(merchant) not in merchant_ids and merchant not in merchant_ids:
            continue
        if account_ids and _id(account) not in account_ids and account not in account_ids:
            continue
        if search and search not in haystack:
            continue
        item = dict(row)
        item["id"] = _tx_id(row)
        item["amountCents"] = _cents(row.get("amount"))
        item["account"] = account
        item["category"] = category
        out.append(item)
    return out


def _tx_id(row: dict[str, Any]) -> str:
    raw = f"{row.get('date')}|{row.get('merchant')}|{row.get('amount')}|{row.get('description')}"
    return _id(raw)[:64]


def _group_rows(rows: list[dict[str, Any]], group_by: str, limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key, label = _group_key(row, group_by)
        item = grouped.setdefault(key, {"key": key, "label": label, "totalCents": 0, "count": 0})
        item["totalCents"] += int(row["amountCents"])
        item["count"] += 1
    total = sum(row["amountCents"] for row in rows)
    out = sorted(grouped.values(), key=lambda item: item["totalCents"], reverse=True)
    for item in out:
        item["sharePct"] = round((item["totalCents"] / total) * 100, 1) if total else 0.0
    return out[:limit]


def _group_key(row: dict[str, Any], group_by: str) -> tuple[str, str]:
    if group_by == "month":
        label = str(row["date"])[:7]
        return label, label
    if group_by == "week":
        d = date.fromisoformat(str(row["date"]))
        label = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        return label, label
    if group_by == "account":
        label = row.get("account") or "unknown"
        return _id(label), label
    if group_by == "merchant":
        label = row.get("merchant") or "unknown"
        return _id(label), label
    label = row.get("category") or "uncategorized"
    return _id(label), label


def _comparison_range(start: date, end: date, mode: str | None) -> tuple[date, date] | None:
    if not mode:
        return None
    days = (end - start).days + 1
    if mode == "previous_period":
        prev_end = start - timedelta(days=1)
        return prev_end - timedelta(days=days - 1), prev_end
    if mode == "same_period_last_year":
        return date(start.year - 1, start.month, start.day), date(end.year - 1, end.month, end.day)
    raise McpInputError("INVALID_COMPARISON", "invalid comparison mode")


def _spend_summary_impl(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    groupBy: Literal["category", "merchant", "month", "week", "account"] = "category",
    filters: dict[str, Any] | None = None,
    includeComparison: dict[str, Any] | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> dict[str, Any]:
    start, end = _optional_range(startDate, endDate)
    lim = _limit(limit)
    if groupBy not in {"category", "merchant", "month", "week", "account"}:
        raise McpInputError("INVALID_GROUP_BY", "invalid groupBy")
    rows = _rows(dbPath, start, end, filters, limit=1000)
    total = sum(row["amountCents"] for row in rows)
    groups = _group_rows(rows, groupBy, lim)
    mode = (includeComparison or {}).get("mode") if isinstance(includeComparison, dict) else None
    if mode and start and end:
        comp = _comparison_range(start, end, mode)
        if comp:
            base_rows = _rows(dbPath, comp[0], comp[1], filters, limit=1000)
            base_groups = {item["key"]: item for item in _group_rows(base_rows, groupBy, MAX_GROUPS)}
            for item in groups:
                item["deltaCents"] = item["totalCents"] - int(base_groups.get(item["key"], {}).get("totalCents", 0))
    return _clean({
        "range": {"startDate": start.isoformat() if start else None, "endDate": end.isoformat() if end else None},
        "totalCents": total,
        "count": len(rows),
        "groups": groups,
    })


def _find_transactions_impl(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    filters: dict[str, Any] | None = None,
    minAmountCents: int | None = None,
    maxAmountCents: int | None = None,
    limit: int | None = DEFAULT_TX_LIMIT,
    cursor: str | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    start, end = _require_range(startDate, endDate)
    lim = _limit(limit, DEFAULT_TX_LIMIT, MAX_ROWS)
    offset = int(cursor or 0)
    selected = fields or DEFAULT_FIELDS
    bad = [field for field in selected if field not in FIELD_ALLOWLIST]
    if bad:
        raise McpInputError("INVALID_FIELDS", f"unsupported field {bad[0]}")
    rows = _rows(dbPath, start, end, filters, minAmountCents, maxAmountCents, limit=lim + 1, offset=offset)
    page = rows[:lim]
    next_cursor = str(offset + lim) if len(rows) > lim else None
    items = []
    for row in page:
        item = {}
        for field in selected:
            if field == "notes":
                continue
            item[field] = row.get(field)
        items.append(_clean(item))
    return _clean({"items": items, "nextCursor": next_cursor, "totalApprox": offset + len(page) + (1 if next_cursor else 0)})


def _merchant_summary_impl(
    dbPath: str | None = None,
    merchantSearch: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    includeTransactions: bool = False,
    transactionLimit: int = 10,
) -> dict[str, Any]:
    if not merchantSearch:
        raise McpInputError("INVALID_SEARCH", "merchantSearch required")
    start, end = _optional_range(startDate, endDate)
    rows = _rows(dbPath, start, end, {"search": merchantSearch}, limit=1000)
    by_merchant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if merchantSearch.lower() in str(row.get("merchant") or "").lower():
            by_merchant[row["merchant"]].append(row)
    merchants = []
    for merchant, items in by_merchant.items():
        total = sum(row["amountCents"] for row in items)
        dates = [row["date"] for row in items]
        payload = {
            "id": _id(merchant),
            "label": merchant,
            "totalCents": total,
            "count": len(items),
            "avgCents": int(total / len(items)) if items else 0,
            "firstDate": min(dates) if dates else None,
            "lastDate": max(dates) if dates else None,
        }
        if includeTransactions:
            payload["transactions"] = _find_transactions_impl(
                dbPath, startDate, endDate, {"merchantIds": [_id(merchant)]}, limit=transactionLimit
            )["items"]
        merchants.append(_clean(payload))
    merchants.sort(key=lambda item: item["totalCents"], reverse=True)
    return {"merchants": merchants[:_limit(transactionLimit, 10, 20)]}


def _category_summary_impl(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    categoryIds: list[str] | None = None,
    includeComparison: dict[str, Any] | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> dict[str, Any]:
    filters = {"categoryIds": categoryIds or []}
    result = _spend_summary_impl(dbPath, startDate, endDate, "category", filters, includeComparison, limit)
    result["budgetAvailable"] = False
    return result


def _compare_periods_impl(
    dbPath: str | None,
    periodA: dict[str, str],
    periodB: dict[str, str],
    groupBy: Literal["category", "merchant", "account", "none"] = "category",
    limit: int | None = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if groupBy not in {"category", "merchant", "account", "none"}:
        raise McpInputError("INVALID_GROUP_BY", "invalid groupBy")
    a_start, a_end = _require_range(periodA.get("startDate"), periodA.get("endDate"))
    b_start, b_end = _require_range(periodB.get("startDate"), periodB.get("endDate"))
    a_rows = _rows(dbPath, a_start, a_end, limit=1000)
    b_rows = _rows(dbPath, b_start, b_end, limit=1000)
    a_total = sum(row["amountCents"] for row in a_rows)
    b_total = sum(row["amountCents"] for row in b_rows)
    drivers = []
    if groupBy != "none":
        a_groups = {item["key"]: item for item in _group_rows(a_rows, groupBy, MAX_GROUPS)}
        b_groups = {item["key"]: item for item in _group_rows(b_rows, groupBy, MAX_GROUPS)}
        for key in set(a_groups) | set(b_groups):
            cur = a_groups.get(key, {"totalCents": 0, "label": b_groups.get(key, {}).get("label", key)})
            base = b_groups.get(key, {"totalCents": 0})
            drivers.append({
                "key": key,
                "label": cur["label"],
                "currentCents": cur["totalCents"],
                "baselineCents": base["totalCents"],
                "deltaCents": cur["totalCents"] - base["totalCents"],
            })
        drivers.sort(key=lambda item: abs(item["deltaCents"]), reverse=True)
    return _clean({
        "periodA": {"startDate": a_start.isoformat(), "endDate": a_end.isoformat(), "totalCents": a_total, "count": len(a_rows)},
        "periodB": {"startDate": b_start.isoformat(), "endDate": b_end.isoformat(), "totalCents": b_total, "count": len(b_rows)},
        "deltaCents": a_total - b_total,
        "topDrivers": drivers[:_limit(limit)],
    })


def _top_drivers_impl(
    dbPath: str | None,
    current: dict[str, str],
    baseline: dict[str, str],
    dimension: Literal["category", "merchant"] = "category",
    limit: int | None = 10,
) -> list[dict[str, Any]]:
    compared = _compare_periods_impl(dbPath, current, baseline, dimension, limit)
    out = []
    for item in compared.get("topDrivers", []):
        delta = item["deltaCents"]
        reason = "new" if item["baselineCents"] == 0 and item["currentCents"] > 0 else "increase"
        if delta < 0:
            reason = "decrease"
        out.append({**item, "reasonCode": reason})
    return out


def _recurring_impl(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    minOccurrences: int = 3,
    includeInactive: bool = False,
) -> dict[str, Any]:
    start, end = _optional_range(startDate, endDate)
    rows = _rows(dbPath, start, end, limit=1000)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["merchant"]].append(row)
    out = []
    for merchant, items in grouped.items():
        if len(items) < minOccurrences:
            continue
        dates = sorted(date.fromisoformat(str(item["date"])) for item in items)
        gaps = [(dates[idx] - dates[idx - 1]).days for idx in range(1, len(dates))]
        avg_gap = int(mean(gaps)) if gaps else 0
        cadence = "monthly" if 25 <= avg_gap <= 35 else "weekly" if 5 <= avg_gap <= 9 else "irregular"
        if not includeInactive and end and (end - dates[-1]).days > max(avg_gap * 2, 45):
            continue
        amounts = [item["amountCents"] for item in items]
        out.append({
            "merchant": merchant,
            "cadence": cadence,
            "avgAmountCents": int(mean(amounts)),
            "lastAmountCents": amounts[-1],
            "lastDate": dates[-1].isoformat(),
            "confidence": round(min(0.95, len(items) / max(minOccurrences, 1) * 0.3), 2),
            "category": items[-1].get("category"),
        })
    out.sort(key=lambda item: (item["confidence"], item["avgAmountCents"]), reverse=True)
    return {"items": out[:MAX_GROUPS]}


def _anomalies_impl(
    dbPath: str | None,
    startDate: str,
    endDate: str,
    dimension: Literal["category", "merchant", "transaction"] = "transaction",
    sensitivity: Literal["low", "medium", "high"] = "medium",
    limit: int | None = 10,
) -> dict[str, Any]:
    start, end = _require_range(startDate, endDate)
    rows = _rows(dbPath, start, end, limit=1000)
    factor = {"low": 2.0, "medium": 1.5, "high": 1.0}.get(sensitivity, 1.5)
    lim = _limit(limit, 10, 20)
    items = []
    if dimension == "transaction":
        buckets: dict[str, list[int]] = defaultdict(list)
        for row in rows:
            buckets[row["merchant"]].append(row["amountCents"])
        for row in rows:
            values = buckets[row["merchant"]]
            if len(values) < 2:
                continue
            expected = int(mean(values))
            threshold = expected + int(max(pstdev(values) * factor, 2500))
            if row["amountCents"] > threshold:
                items.append({
                    "id": row["id"],
                    "label": row["merchant"],
                    "expectedCents": expected,
                    "actualCents": row["amountCents"],
                    "deltaCents": row["amountCents"] - expected,
                    "confidence": 0.7,
                    "explanationCode": "transaction_spike",
                })
    else:
        grouped = _group_rows(rows, dimension, MAX_GROUPS)
        values = [item["totalCents"] for item in grouped]
        expected = int(mean(values)) if values else 0
        spread = pstdev(values) if len(values) > 1 else 0
        for item in grouped:
            if item["totalCents"] > expected + max(spread * factor, 2500):
                items.append({
                    "label": item["label"],
                    "expectedCents": expected,
                    "actualCents": item["totalCents"],
                    "deltaCents": item["totalCents"] - expected,
                    "confidence": 0.65,
                    "explanationCode": f"{dimension}_spike",
                })
    items.sort(key=lambda item: item["deltaCents"], reverse=True)
    return {"items": items[:lim]}


def _search_dimensions_impl(
    dbPath: str | None,
    query: str,
    types: list[str] | None = None,
    limit: int | None = 10,
) -> list[dict[str, Any]]:
    if not query:
        raise McpInputError("INVALID_SEARCH", "query required")
    wanted = set(types or ["merchant", "category", "account"])
    lim = _limit(limit, 10, 50)
    q = query.lower()
    matches = []
    if "merchant" in wanted:
        for item in list_unique_merchants(_db_path(dbPath)):
            label = item["merchant"]
            if q in label.lower():
                matches.append({"type": "merchant", "id": _id(label), "label": label, "aliases": item.get("categories", [])[:3]})
    if "category" in wanted:
        for label in list_categories(_db_path(dbPath)):
            if q in label.lower():
                matches.append({"type": "category", "id": _id(label), "label": label})
    if "account" in wanted:
        for label in list_providers(_db_path(dbPath)):
            if q in label.lower():
                matches.append({"type": "account", "id": _id(label), "label": label})
    return matches[:lim]


def _insight_context_impl(
    dbPath: str | None,
    startDate: str,
    endDate: str,
    comparisonMode: Literal["previous_period", "same_period_last_year", None] = "previous_period",
    include: list[str] | None = None,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    wanted = set(include or ["totals", "top_categories", "top_merchants", "drivers", "anomalies", "recurring"])
    lim = limits or {}
    start, end = _require_range(startDate, endDate)
    payload: dict[str, Any] = {"range": {"startDate": start.isoformat(), "endDate": end.isoformat()}}
    if "totals" in wanted:
        payload["totals"] = _spend_summary_impl(dbPath, startDate, endDate, "month", limit=12)
    if "top_categories" in wanted:
        payload["topCategories"] = _spend_summary_impl(dbPath, startDate, endDate, "category", limit=lim.get("topCategories", 8))["groups"]
    if "top_merchants" in wanted:
        payload["topMerchants"] = _spend_summary_impl(dbPath, startDate, endDate, "merchant", limit=lim.get("topMerchants", 8))["groups"]
    comp = _comparison_range(start, end, comparisonMode)
    if comp and "drivers" in wanted:
        payload["drivers"] = _top_drivers_impl(
            dbPath,
            {"startDate": start.isoformat(), "endDate": end.isoformat()},
            {"startDate": comp[0].isoformat(), "endDate": comp[1].isoformat()},
            "category",
            lim.get("drivers", 8),
        )
    if "anomalies" in wanted:
        payload["anomalies"] = _anomalies_impl(dbPath, startDate, endDate, "transaction", "medium", lim.get("anomalies", 5))["items"]
    if "recurring" in wanted:
        payload["recurring"] = _recurring_impl(dbPath, startDate, endDate, 3, False)["items"][:8]
    return _clean(payload)


@server.tool(name="budgify.health", description="Check MCP/server/db readiness")
async def budgify_health(dbPath: str | None = None) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            with _connect(dbPath) as conn:
                conn.execute("SELECT 1").fetchone()
            return {"ok": True, "db": "ok", "version": BUDGIFY_VERSION, "capabilities": sorted(SAFE_BUNDLE_TOOLS | {"find_transactions", "profile_summary"})}
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.profile_summary", description="Return compact app/account summary")
async def budgify_profile_summary(dbPath: str | None = None) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            overview = overview_metrics(_db_path(dbPath))
            return _clean({
                "dateRange": {"startDate": overview.get("first_date"), "endDate": overview.get("last_date")},
                "transactionCount": overview.get("transactions", 0),
                "categoryCount": len(list_categories(_db_path(dbPath))),
                "merchantCount": len(list_unique_merchants(_db_path(dbPath))),
                "accountCount": len(list_providers(_db_path(dbPath))),
                "budgetCount": _budget_count(dbPath),
                "currency": "USD",
            })
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


def _budget_count(dbPath: str | None) -> int:
    with _connect(dbPath) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        budget_tables = [name for name in tables if "budget" in name.lower()]
        total = 0
        for table in budget_tables:
            try:
                total += int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.Error:
                continue
        return total


@server.tool(name="budgify.spend_summary", description="Compact aggregate spending summary")
async def budgify_spend_summary(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    groupBy: Literal["category", "merchant", "month", "week", "account"] = "category",
    filters: dict[str, Any] | None = None,
    includeComparison: dict[str, Any] | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return _spend_summary_impl(dbPath, startDate, endDate, groupBy, filters, includeComparison, limit)
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.find_transactions", description="Filtered paged transaction lookup")
async def budgify_find_transactions(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    filters: dict[str, Any] | None = None,
    minAmountCents: int | None = None,
    maxAmountCents: int | None = None,
    limit: int | None = DEFAULT_TX_LIMIT,
    cursor: str | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return _find_transactions_impl(dbPath, startDate, endDate, filters, minAmountCents, maxAmountCents, limit, cursor, fields)
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.merchant_summary", description="Merchant compact lookup")
async def budgify_merchant_summary(
    dbPath: str | None = None,
    merchantSearch: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    includeTransactions: bool = False,
    transactionLimit: int = 10,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return _merchant_summary_impl(dbPath, merchantSearch, startDate, endDate, includeTransactions, transactionLimit)
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.category_summary", description="Category compact lookup")
async def budgify_category_summary(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    categoryIds: list[str] | None = None,
    includeComparison: dict[str, Any] | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return _category_summary_impl(dbPath, startDate, endDate, categoryIds, includeComparison, limit)
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.compare_periods", description="Compare two periods")
async def budgify_compare_periods(
    dbPath: str | None = None,
    periodA: dict[str, str] | None = None,
    periodB: dict[str, str] | None = None,
    groupBy: Literal["category", "merchant", "account", "none"] = "category",
    limit: int | None = DEFAULT_LIMIT,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return _compare_periods_impl(dbPath, periodA or {}, periodB or {}, groupBy, limit)
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.top_drivers", description="Explain spend change")
async def budgify_top_drivers(
    dbPath: str | None = None,
    current: dict[str, str] | None = None,
    baseline: dict[str, str] | None = None,
    dimension: Literal["category", "merchant"] = "category",
    limit: int | None = 10,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return {"items": _top_drivers_impl(dbPath, current or {}, baseline or {}, dimension, limit)}
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.recurring_transactions", description="Recurring/subscription candidates")
async def budgify_recurring_transactions(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    minOccurrences: int = 3,
    includeInactive: bool = False,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return _recurring_impl(dbPath, startDate, endDate, minOccurrences, includeInactive)
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.anomalies", description="Detect unusual spend compactly")
async def budgify_anomalies(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    dimension: Literal["category", "merchant", "transaction"] = "transaction",
    sensitivity: Literal["low", "medium", "high"] = "medium",
    limit: int | None = 10,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return _anomalies_impl(dbPath, startDate or "", endDate or "", dimension, sensitivity, limit)
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.search_dimensions", description="Resolve names to stable IDs")
async def budgify_search_dimensions(
    dbPath: str | None = None,
    query: str = "",
    types: list[str] | None = None,
    limit: int | None = 10,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return {"matches": _search_dimensions_impl(dbPath, query, types, limit)}
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="budgify.query_bundle", description="Run up to 5 safe read subqueries")
async def budgify_query_bundle(dbPath: str | None = None, queries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            if not isinstance(queries, list):
                raise McpInputError("INVALID_BUNDLE", "queries must be list")
            if len(queries) > MAX_BUNDLE_QUERIES:
                raise McpInputError("TOO_MANY_QUERIES", "max 5 subqueries")
            results = {}
            for item in queries:
                qid = str(item.get("id") or item.get("tool") or len(results))
                tool = str(item.get("tool") or "")
                args = dict(item.get("args") or {})
                args.setdefault("dbPath", dbPath)
                if tool not in SAFE_BUNDLE_TOOLS:
                    raise McpInputError("UNSAFE_TOOL", f"{tool} not allowed in query_bundle")
                results[qid] = _dispatch_safe(tool, args)
            return {"results": results}
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


def _dispatch_safe(tool: str, args: dict[str, Any]) -> Any:
    if tool == "spend_summary":
        return _spend_summary_impl(**args)
    if tool == "merchant_summary":
        return _merchant_summary_impl(**args)
    if tool == "category_summary":
        return _category_summary_impl(**args)
    if tool == "compare_periods":
        return _compare_periods_impl(args.get("dbPath"), args.get("periodA", {}), args.get("periodB", {}), args.get("groupBy", "category"), args.get("limit"))
    if tool == "top_drivers":
        return {"items": _top_drivers_impl(args.get("dbPath"), args.get("current", {}), args.get("baseline", {}), args.get("dimension", "category"), args.get("limit", 10))}
    if tool == "recurring_transactions":
        return _recurring_impl(**args)
    if tool == "anomalies":
        return _anomalies_impl(**args)
    if tool == "search_dimensions":
        return {"matches": _search_dimensions_impl(**args)}
    raise McpInputError("UNSAFE_TOOL", f"{tool} not allowed")


@server.tool(name="budgify.insight_context", description="Compact context pack for LLM explanation")
async def budgify_insight_context(
    dbPath: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    comparisonMode: Literal["previous_period", "same_period_last_year", None] = "previous_period",
    include: list[str] | None = None,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        try:
            return _insight_context_impl(dbPath, startDate or "", endDate or "", comparisonMode, include, limits)
        except Exception as exc:
            return _err(exc)

    return await anyio.to_thread.run_sync(_run)


@server.resource("budgify://schema", mime_type="application/json")
async def schema_resource() -> dict[str, Any]:
    return {"transaction": {"id": "string", "date": "YYYY-MM-DD", "amountCents": "int", "merchant": "string", "category": "string", "account": "string"}}


@server.resource("budgify://capabilities", mime_type="application/json")
async def capabilities_resource() -> dict[str, Any]:
    return {"tools": sorted([f"budgify.{name}" for name in SAFE_BUNDLE_TOOLS] + ["budgify.find_transactions", "budgify.profile_summary"])}


@server.resource("budgify://examples", mime_type="application/json")
async def examples_resource() -> dict[str, Any]:
    return {
        "examples": [
            {"tool": "budgify.spend_summary", "args": {"startDate": "2025-04-01", "endDate": "2025-04-30", "groupBy": "category"}},
            {"tool": "budgify.insight_context", "args": {"startDate": "2025-04-01", "endDate": "2025-04-30", "comparisonMode": "previous_period"}},
        ]
    }


def _prompt_text(task: str) -> str:
    return (
        f"{task}. Use Budgify aggregate tools first. Avoid budgify.find_transactions unless raw rows needed. "
        "Keep answer concise. Cite tool result ids when query_bundle/insight_context returns them."
    )


@server.prompt(name="explain_month")
async def prompt_explain_month(month: str) -> str:
    return _prompt_text(f"Explain spending for {month}")


@server.prompt(name="compare_months")
async def prompt_compare_months(month_a: str, month_b: str) -> str:
    return _prompt_text(f"Compare {month_a} against {month_b}")


@server.prompt(name="find_unusual_spending")
async def prompt_find_unusual_spending(range_label: str) -> str:
    return _prompt_text(f"Find unusual spending for {range_label}")


@server.prompt(name="merchant_deep_dive")
async def prompt_merchant_deep_dive(merchant: str) -> str:
    return _prompt_text(f"Analyze merchant {merchant}")


@server.prompt(name="budget_review")
async def prompt_budget_review(range_label: str) -> str:
    return _prompt_text(f"Review budget and category spend for {range_label}")


# Legacy tools preserved.
@server.tool(name="get_categories", description="List available transaction categories")
async def get_categories() -> list[str]:
    return CATEGORIES


@server.tool(name="summarize_spend_by_category", description="Total spending grouped by category")
async def summarize_spend_by_category(db_path: str, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    def _run() -> list[dict]:
        return summarize_by_category(db_path, start_date=_parse_date(start_date), end_date=_parse_date(end_date))

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="summarize_spend_by_period", description="Total spending grouped by month, quarter, or year")
async def summarize_spend_by_period(
    db_path: str,
    period: Literal["month", "quarter", "year"],
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
) -> list[dict]:
    def _run() -> list[dict]:
        return summarize_by_period(db_path, period=period, start_date=_parse_date(start_date), end_date=_parse_date(end_date), category=category)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="summarize_spend_by_merchant", description="Total spending grouped by merchant")
async def summarize_spend_by_merchant(db_path: str, start_date: str | None = None, end_date: str | None = None, category: str | None = None) -> list[dict]:
    def _run() -> list[dict]:
        return summarize_by_merchant(db_path, start_date=_parse_date(start_date), end_date=_parse_date(end_date), category=category)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="list_unique_merchants", description="List merchants and categories")
async def list_unique_merchants_tool(db_path: str) -> list[dict]:
    def _run() -> list[dict]:
        return list_unique_merchants(db_path)

    return await anyio.to_thread.run_sync(_run)


@server.tool(name="analyze_category_spend", description="Detailed category analysis")
async def analyze_category_spend(
    db_path: str,
    category: str,
    start_date: str | None = None,
    end_date: str | None = None,
    top_merchants: int = 5,
    top_transactions: int = 5,
) -> dict:
    def _run() -> dict:
        return category_insights(
            db_path,
            category=category,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            top_merchants=top_merchants,
            top_transactions=top_transactions,
        )

    return await anyio.to_thread.run_sync(_run)


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "info").upper())
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        transport = "streamable-http"
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise SystemExit("MCP_TRANSPORT must be stdio, http, or sse")
    if os.environ.get("MCP_AUTH_TOKEN") and transport == "stdio":
        logger.info("MCP_AUTH_TOKEN ignored for stdio transport")
    server.run(transport=transport)


if __name__ == "__main__":
    main()
