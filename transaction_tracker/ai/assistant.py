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
Budgify finance questions."""


@dataclass
class AssistantResult:
    answer: str
    data_used: list[dict[str, Any]] = field(default_factory=list)


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
            return AssistantResult(answer=_message_content(message), data_used=data_used)
        messages.append(_assistant_tool_message(message))
        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name")
            arguments = function.get("arguments")
            if not isinstance(name, str):
                raise ToolValidationError("Tool call missing function name")
            result = call_finance_tool(db_path, name, arguments)
            data_used.append({"tool": name, "arguments": _safe_arguments(arguments), "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": str(call.get("id") or name),
                "name": name,
                "content": json.dumps(result, default=str),
            })

    messages.append({
        "role": "system",
        "content": "Tool limit reached. Give a concise final answer using only the tool results above.",
    })
    message = provider.complete(messages)
    return AssistantResult(answer=_message_content(message), data_used=data_used)


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
