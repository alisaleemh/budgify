from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from statistics import mean, pstdev
from typing import Any, Callable

from transaction_tracker.database import (
    query_transactions,
    summarize_by_category,
    summarize_by_merchant,
)

RAW_LIMIT = 50
AGGREGATE_LIMIT = 20


class ToolValidationError(ValueError):
    pass


def tool_schemas() -> list[dict[str, Any]]:
    common_filter_props = _common_filter_props()
    common_filter_schema = {
        "type": "object",
        "properties": common_filter_props,
        "additionalProperties": False,
    }
    return [
        _tool(
            "getTransactions",
            "Return matching transactions capped at 50 rows.",
            {
                **common_filter_schema,
                "properties": {
                    **common_filter_props,
                    "min_amount": {"type": "number"},
                    "max_amount": {"type": "number"},
                    "sort_by": {
                        "type": "string",
                        "enum": ["date", "amount", "merchant", "category", "description", "provider"],
                    },
                    "sort_dir": {"type": "string", "enum": ["asc", "desc"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": RAW_LIMIT},
                },
            },
        ),
        _tool("getSpendByCategory", "Aggregate spend by category capped at 20 rows.", common_filter_schema),
        _tool("getSpendByMerchant", "Aggregate spend by merchant capped at 20 rows.", common_filter_schema),
        _tool(
            "compareSpendPeriods",
            "Compare two date ranges by total, category, and merchant spend.",
            {
                "type": "object",
                "properties": {
                    "period_a": _period_schema("First period."),
                    "period_b": _period_schema("Second period."),
                    "category": {"type": "string"},
                    "categories": {"type": "array", "items": {"type": "string"}},
                    "merchant": {"type": "string"},
                    "provider": {"type": "string"},
                },
                "required": ["period_a", "period_b"],
                "additionalProperties": False,
            },
        ),
        _tool("getRecurringTransactions", "Find merchants with repeated monthly transactions.", common_filter_schema),
        _tool(
            "getTopMerchants",
            "Return top merchants by total spend.",
            {
                **common_filter_schema,
                "properties": {
                    **common_filter_props,
                    "limit": {"type": "integer", "minimum": 1, "maximum": AGGREGATE_LIMIT},
                },
            },
        ),
        _tool(
            "getUnusualSpending",
            "Return transactions unusually large for their merchant.",
            {
                **common_filter_schema,
                "properties": {
                    **common_filter_props,
                    "limit": {"type": "integer", "minimum": 1, "maximum": AGGREGATE_LIMIT},
                },
            },
        ),
    ]


def _common_filter_props() -> dict[str, Any]:
    return {
        "start_date": {"type": "string", "description": "Inclusive YYYY-MM-DD start date."},
        "end_date": {"type": "string", "description": "Inclusive YYYY-MM-DD end date."},
        "category": {"type": "string"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "merchant": {"type": "string"},
        "provider": {"type": "string"},
    }


def _tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
            "strict": True,
        },
    }


def _period_schema(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "description": description,
        "properties": {
            "start_date": {"type": "string"},
            "end_date": {"type": "string"},
            "label": {"type": "string"},
        },
        "required": ["start_date", "end_date"],
        "additionalProperties": False,
    }


def call_finance_tool(db_path: str, name: str, arguments: dict[str, Any] | str | None) -> dict[str, Any]:
    args = _parse_args(arguments)
    tools: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
        "getTransactions": _get_transactions,
        "getSpendByCategory": _get_spend_by_category,
        "getSpendByMerchant": _get_spend_by_merchant,
        "compareSpendPeriods": _compare_spend_periods,
        "getRecurringTransactions": _get_recurring_transactions,
        "getTopMerchants": _get_top_merchants,
        "getUnusualSpending": _get_unusual_spending,
    }
    tool = tools.get(name)
    if tool is None:
        raise ToolValidationError(f"Unknown finance tool: {name}")
    return tool(db_path, args)


def _parse_args(arguments: dict[str, Any] | str | None) -> dict[str, Any]:
    if arguments is None:
        return {}
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ToolValidationError("Tool arguments must be valid JSON") from exc
    else:
        parsed = arguments
    if not isinstance(parsed, dict):
        raise ToolValidationError("Tool arguments must be an object")
    return parsed


def _filters(args: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "start_date",
        "end_date",
        "category",
        "categories",
        "provider",
        "merchant",
        "min_amount",
        "max_amount",
        "sort_by",
        "sort_dir",
        "limit",
    }
    unknown = set(args) - allowed
    if unknown:
        raise ToolValidationError(f"Unsupported argument: {sorted(unknown)[0]}")
    return {
        "start_date": _parse_date(args.get("start_date")),
        "end_date": _parse_date(args.get("end_date")),
        "category": _optional_string(args.get("category")),
        "categories": _string_list(args.get("categories")),
        "provider": _optional_string(args.get("provider")),
        "merchant": _optional_string(args.get("merchant")),
    }


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ToolValidationError("Dates must be YYYY-MM-DD strings")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ToolValidationError("Dates must be valid YYYY-MM-DD strings") from exc


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ToolValidationError("String arguments must be strings")
    return value.strip() or None


def _string_list(value: Any) -> list[str] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, list):
        raise ToolValidationError("categories must be an array")
    values = []
    for item in value:
        if not isinstance(item, str):
            raise ToolValidationError("categories must contain only strings")
        cleaned = item.strip()
        if cleaned:
            values.append(cleaned)
    return values or None


def _limit(args: dict[str, Any], default: int, maximum: int) -> int:
    raw = args.get("limit", default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("limit must be an integer") from exc
    return max(1, min(value, maximum))


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("Amount filters must be numbers") from exc


def _aggregate_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in filters.items() if key != "merchant"}


def _get_transactions(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    filters = _filters(args)
    rows = query_transactions(
        db_path,
        **filters,
        min_amount=_number(args.get("min_amount")),
        max_amount=_number(args.get("max_amount")),
        sort_by=args.get("sort_by") or "date",
        sort_dir=args.get("sort_dir") or "asc",
        limit=_limit(args, RAW_LIMIT, RAW_LIMIT),
    )
    return {"transactions": rows, "truncated": len(rows) >= RAW_LIMIT, "limit": RAW_LIMIT}


def _get_spend_by_category(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    filters = _filters(args)
    if filters.get("merchant"):
        rows = _group_transactions(query_transactions(db_path, **filters, limit=1000), "category")
    else:
        rows = summarize_by_category(db_path, **_aggregate_filters(filters))
    return {"categories": rows[:AGGREGATE_LIMIT], "truncated": len(rows) > AGGREGATE_LIMIT}


def _get_spend_by_merchant(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    filters = _filters(args)
    if filters.get("merchant"):
        rows = _group_transactions(query_transactions(db_path, **filters, limit=1000), "merchant")
    else:
        rows = summarize_by_merchant(db_path, **_aggregate_filters(filters))
    return {"merchants": rows[:AGGREGATE_LIMIT], "truncated": len(rows) > AGGREGATE_LIMIT}


def _group_transactions(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    output_key = "transactions" if key == "merchant" else "transactions"
    for row in rows:
        label = row.get(key) or "uncategorized"
        item = grouped.setdefault(str(label), {key: label, "total": 0.0, output_key: 0})
        item["total"] += float(row["amount"])
        item[output_key] += 1
    return sorted(grouped.values(), key=lambda item: item["total"], reverse=True)


def _compare_spend_periods(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    unknown = set(args) - {"period_a", "period_b", "category", "categories", "merchant", "provider"}
    if unknown:
        raise ToolValidationError(f"Unsupported argument: {sorted(unknown)[0]}")
    period_a = _period_args(args.get("period_a"), "period_a")
    period_b = _period_args(args.get("period_b"), "period_b")
    shared = _filters({
        "category": args.get("category"),
        "categories": args.get("categories"),
        "merchant": args.get("merchant"),
        "provider": args.get("provider"),
    })
    return {"period_a": _period_result(db_path, period_a, shared), "period_b": _period_result(db_path, period_b, shared)}


def _period_args(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ToolValidationError(f"{name} must be an object")
    return {
        "label": _optional_string(value.get("label")) or name,
        "start_date": _parse_date(value.get("start_date")),
        "end_date": _parse_date(value.get("end_date")),
    }


def _period_result(db_path: str, period: dict[str, Any], shared: dict[str, Any]) -> dict[str, Any]:
    filters = {**shared, "start_date": period["start_date"], "end_date": period["end_date"]}
    txs = query_transactions(db_path, **filters, limit=1000)
    categories = summarize_by_category(db_path, **_aggregate_filters(filters))[:AGGREGATE_LIMIT]
    merchants = summarize_by_merchant(db_path, **_aggregate_filters(filters))[:AGGREGATE_LIMIT]
    total = sum(float(tx["amount"]) for tx in txs)
    return {
        "label": period["label"],
        "start_date": period["start_date"].isoformat() if period["start_date"] else None,
        "end_date": period["end_date"].isoformat() if period["end_date"] else None,
        "total": total,
        "transactions": len(txs),
        "categories": categories,
        "merchants": merchants,
    }


def _get_recurring_transactions(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    filters = _filters(args)
    rows = query_transactions(db_path, **filters, sort_by="date", sort_dir="asc", limit=1000)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["merchant"] or "unknown"].append(row)
    recurring = []
    for merchant, merchant_rows in grouped.items():
        months = {row["date"][:7] for row in merchant_rows}
        if len(months) < 2 or len(merchant_rows) < 2:
            continue
        amounts = [float(row["amount"]) for row in merchant_rows]
        recurring.append({
            "merchant": merchant,
            "transactions": len(merchant_rows),
            "months": sorted(months),
            "average": mean(amounts),
            "total": sum(amounts),
            "latest_date": merchant_rows[-1]["date"],
        })
    recurring.sort(key=lambda item: (len(item["months"]), item["total"]), reverse=True)
    return {"recurring": recurring[:AGGREGATE_LIMIT], "truncated": len(recurring) > AGGREGATE_LIMIT}


def _get_top_merchants(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    filters = _filters(args)
    limit = _limit(args, AGGREGATE_LIMIT, AGGREGATE_LIMIT)
    if filters.get("merchant"):
        rows = _group_transactions(query_transactions(db_path, **filters, limit=1000), "merchant")
    else:
        rows = summarize_by_merchant(db_path, **_aggregate_filters(filters))
    return {"merchants": rows[:limit], "truncated": len(rows) > limit}


def _get_unusual_spending(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    filters = _filters(args)
    rows = query_transactions(db_path, **filters, sort_by="date", sort_dir="asc", limit=1000)
    by_merchant: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_merchant[row["merchant"] or "unknown"].append(float(row["amount"]))
    unusual = []
    for row in rows:
        merchant = row["merchant"] or "unknown"
        amounts = by_merchant[merchant]
        if len(amounts) < 2:
            continue
        baseline = mean(amounts)
        spread = pstdev(amounts) if len(amounts) > 1 else 0.0
        amount = float(row["amount"])
        threshold = baseline + max(spread * 1.5, baseline * 0.5, 25)
        if amount > threshold:
            item = dict(row)
            item["merchant_average"] = baseline
            item["difference"] = amount - baseline
            unusual.append(item)
    unusual.sort(key=lambda item: item["difference"], reverse=True)
    limit = _limit(args, AGGREGATE_LIMIT, AGGREGATE_LIMIT)
    return {"transactions": unusual[:limit], "truncated": len(unusual) > limit}
