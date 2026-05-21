from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from transaction_tracker.ai.finance_tools import ToolValidationError, call_finance_tool, tool_schemas
from transaction_tracker.ai.providers import ChatCompletionsProvider, get_chat_provider_from_env

MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """You are Budgify's finance assistant.
Answer only questions about the user's transaction data and personal spending.
Use finance tools for all numeric claims. The final answer must be grounded only
in tool results already returned in this conversation. If the user asks about
anything unrelated to finance or their ledger, briefly steer them back to
Budgify finance questions. Prefer concise markdown with short sections, bullets,
and plain-language labels. Keep prose tight and scannable."""


@dataclass
class AssistantResult:
    answer: str
    data_used: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)


def query_finance_assistant(
    db_path: str,
    question: str,
    provider: ChatCompletionsProvider | None = None,
) -> AssistantResult:
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("question is required")
    provider = provider or get_chat_provider_from_env()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Today's date is {date.today().isoformat()}. Use it for relative date ranges."},
        {"role": "user", "content": cleaned},
    ]
    data_used: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ROUNDS):
        message = provider.complete(messages, tools=tool_schemas(), tool_choice="auto")
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            cards, tables = _build_structured_blocks(data_used)
            return AssistantResult(answer=_message_content(message), data_used=data_used, cards=cards, tables=tables)
        messages.append(_assistant_tool_message(message))
        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name")
            arguments = function.get("arguments")
            if not isinstance(name, str):
                raise ToolValidationError("Tool call missing function name")
            result = call_finance_tool(db_path, name, arguments)
            data_used.append({"tool": name, "arguments": _safe_arguments(arguments), "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id") or name),
                    "name": name,
                    "content": json.dumps(result, default=str),
                }
            )

    messages.append(
        {
            "role": "system",
            "content": "Tool limit reached. Give a concise final answer using only the tool results above.",
        }
    )
    message = provider.complete(messages)
    cards, tables = _build_structured_blocks(data_used)
    return AssistantResult(answer=_message_content(message), data_used=data_used, cards=cards, tables=tables)


def _build_structured_blocks(data_used: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cards: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    for item in data_used:
        tool = item.get("tool")
        result = item.get("result") or {}
        if not isinstance(tool, str) or not isinstance(result, dict):
            continue
        tool_cards, tool_tables = _blocks_for_tool(tool, result)
        cards.extend(tool_cards)
        tables.extend(tool_tables)
    return cards, tables


def _blocks_for_tool(tool: str, result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if tool == "getTransactions":
        rows = result.get("transactions") or []
        table = _transactions_table("Matching transactions", rows, note="Sorted by the tool request")
        return [], [table] if table else []

    if tool in {"getSpendByCategory", "getTopMerchants"}:
        rows = result.get("categories") or result.get("merchants") or []
        cards = []
        tables = []
        if rows:
            top = rows[0]
            label = str(top.get("category") or top.get("merchant") or "Top result")
            cards.append(
                _metric_card(
                    label=label,
                    value=_currency(top.get("total")),
                    detail=_count_detail(top),
                )
            )
            tables.append(_summary_table("Category breakdown" if tool == "getSpendByCategory" else "Top merchants", rows))
        return cards, tables

    if tool == "getSpendByMerchant":
        rows = result.get("merchants") or []
        cards = []
        tables = []
        if rows:
            top = rows[0]
            cards.append(
                _metric_card(
                    label=str(top.get("merchant") or "Top merchant"),
                    value=_currency(top.get("total")),
                    detail=_count_detail(top),
                )
            )
            tables.append(_summary_table("Merchant breakdown", rows))
        return cards, tables

    if tool == "compareSpendPeriods":
        period_a = result.get("period_a") or {}
        period_b = result.get("period_b") or {}
        cards = [_comparison_card(period_a, period_b)]
        tables: list[dict[str, Any]] = []
        for period in (period_a, period_b):
            label = str(period.get("label") or "Period")
            categories = period.get("categories") or []
            merchants = period.get("merchants") or []
            if categories:
                tables.append(_summary_table(f"{label} categories", categories))
            if merchants:
                tables.append(_summary_table(f"{label} merchants", merchants))
        return cards, tables

    if tool == "getRecurringTransactions":
        rows = result.get("recurring") or []
        cards = []
        tables: list[dict[str, Any]] = []
        if rows:
            cards.append(
                {
                    "kind": "list",
                    "title": "Recurring merchants",
                    "detail": f"{len(rows)} repeated merchants",
                    "items": [
                        {
                            "label": str(row.get("merchant") or "Unknown"),
                            "value": _currency(row.get("total")),
                            "detail": f"{row.get('transactions', 0)} txns · {len(row.get('months') or [])} months",
                        }
                        for row in rows[:5]
                    ],
                }
            )
            tables.append(_recurring_table(rows))
        return cards, tables

    if tool == "getUnusualSpending":
        rows = result.get("transactions") or []
        cards = []
        tables = []
        if rows:
            top = rows[0]
            cards.append(
                _metric_card(
                    label=str(top.get("merchant") or "Unusual spend"),
                    value=_currency(top.get("amount")),
                    detail=f"{_currency(top.get('difference'))} above merchant average",
                    tone="warning",
                )
            )
            tables.append(_unusual_table(rows))
        return cards, tables

    return [], []


def _comparison_card(period_a: dict[str, Any], period_b: dict[str, Any]) -> dict[str, Any]:
    total_a = float(period_a.get("total") or 0)
    total_b = float(period_b.get("total") or 0)
    delta = total_b - total_a
    baseline = total_a or 1.0
    pct = (abs(delta) / baseline) * 100 if total_a else 0.0
    if delta > 0:
        trend = "up"
        delta_label = "Increase"
    elif delta < 0:
        trend = "down"
        delta_label = "Decrease"
    else:
        trend = "flat"
        delta_label = "No change"
    return {
        "kind": "comparison",
        "title": "Period comparison",
        "detail": f"{period_a.get('label') or 'Period A'} vs {period_b.get('label') or 'Period B'}",
        "leftLabel": str(period_a.get("label") or "Period A"),
        "leftValue": _currency(total_a),
        "leftDetail": f"{period_a.get('transactions', 0)} transactions",
        "rightLabel": str(period_b.get("label") or "Period B"),
        "rightValue": _currency(total_b),
        "rightDetail": f"{period_b.get('transactions', 0)} transactions",
        "deltaLabel": delta_label,
        "deltaValue": f"{'+' if delta > 0 else '-' if delta < 0 else ''}{_currency(abs(delta))} ({pct:.1f}%)",
        "trend": trend,
    }


def _metric_card(label: str, value: str, detail: str, tone: str = "default") -> dict[str, Any]:
    return {"kind": "metric", "label": label, "value": value, "detail": detail, "tone": tone}


def _summary_table(title: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    mapped_rows = []
    for row in rows[:8]:
        label = str(row.get("category") or row.get("merchant") or row.get("label") or "Unknown")
        mapped_rows.append(
            {
                "label": label,
                "total": _currency(row.get("total")),
                "transactions": str(row.get("transactions", "")),
            }
        )
    return {
        "title": title,
        "columns": ["Label", "Total", "Transactions"],
        "rows": mapped_rows,
        "note": f"Top {min(len(rows), 8)} rows",
    }


def _transactions_table(title: str, rows: list[dict[str, Any]], note: str | None = None) -> dict[str, Any] | None:
    if not rows:
        return None
    mapped_rows = []
    for row in rows[:10]:
        mapped_rows.append(
            {
                "date": str(row.get("date") or ""),
                "merchant": str(row.get("merchant") or "Unknown"),
                "category": str(row.get("category") or "uncategorized"),
                "amount": _currency(row.get("amount")),
                "description": str(row.get("description") or ""),
            }
        )
    return {
        "title": title,
        "columns": ["Date", "Merchant", "Category", "Amount", "Description"],
        "rows": mapped_rows,
        "note": note or ("Top 10 rows" if len(rows) > 10 else None),
    }


def _recurring_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mapped_rows = []
    for row in rows[:8]:
        mapped_rows.append(
            {
                "merchant": str(row.get("merchant") or "Unknown"),
                "total": _currency(row.get("total")),
                "average": _currency(row.get("average")),
                "transactions": str(row.get("transactions", "")),
                "months": ", ".join(str(month) for month in row.get("months") or []),
            }
        )
    return {
        "title": "Recurring patterns",
        "columns": ["Merchant", "Total", "Average", "Transactions", "Months"],
        "rows": mapped_rows,
        "note": f"{len(rows)} recurring merchants",
    }


def _unusual_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mapped_rows = []
    for row in rows[:8]:
        mapped_rows.append(
            {
                "date": str(row.get("date") or ""),
                "merchant": str(row.get("merchant") or "Unknown"),
                "amount": _currency(row.get("amount")),
                "average": _currency(row.get("merchant_average")),
                "difference": _currency(row.get("difference")),
            }
        )
    return {
        "title": "Unusual transactions",
        "columns": ["Date", "Merchant", "Amount", "Average", "Difference"],
        "rows": mapped_rows,
        "note": f"{len(rows)} unusual transactions",
    }


def _count_detail(row: dict[str, Any]) -> str:
    count = row.get("transactions")
    if count is None:
        return "Summary result"
    return f"{count} transactions"


def _currency(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"${amount:,.2f}"


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content") or ""
    if not isinstance(content, str):
        return ""
    return content.strip()


def _assistant_tool_message(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    return {
        "role": "assistant",
        "content": content if isinstance(content, str) else "",
        "tool_calls": message.get("tool_calls") or [],
    }


def _safe_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
