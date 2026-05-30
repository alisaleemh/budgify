from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

from transaction_tracker.ai.costs import build_session_cost
from transaction_tracker.ai.providers import ChatCompletionsProvider, get_chat_provider_from_env
from transaction_tracker.mcp_server import (
    _compare_periods_impl,
    _find_transactions_impl,
    _insight_context_impl,
    _profile_summary_impl,
    _recurring_impl,
    _spend_summary_impl,
)

BETA_SYSTEM_PROMPT = """You are Budgify AI Beta, a conservative personal CFO.
Use only the provided Budgify MCP context. Every money claim must be traceable
to provided transactions, aggregates, or recurring candidates. If data is
insufficient, say so directly. Do not promise outcomes, investment returns, or
autonomous money movement.

Return JSON only:
{
  "summary": "short direct answer",
  "insights": [
    {
      "title": "what changed or matters",
      "body": "grounded explanation",
      "why": "why the user is seeing this",
      "citationIds": ["transaction id"]
    }
  ],
  "recommendations": [
    {
      "title": "specific next step",
      "body": "what to do",
      "estimated": true,
      "citationIds": ["transaction id"]
    }
  ],
  "citations": ["transaction id"],
  "estimated": true
}

Rules:
- Keep copy calm, specific, and human.
- Prefer 2-4 insights and 1-3 recommendations.
- Use citationIds only from the provided transaction list.
- Mark estimated true when using incomplete history, projections, or heuristics.
- If there are no useful transactions, return a sparse response saying data is insufficient."""

_CACHE_LOCK = threading.Lock()
_CACHE_MAX_ITEMS = 64
_BETA_CACHE: dict[tuple[Any, ...], "BetaBriefing"] = {}


@dataclass
class BetaCitation:
    id: str
    date: str
    merchant: str
    amount: float
    amountCents: int
    category: str
    account: str | None = None


@dataclass
class BetaInsight:
    title: str
    body: str
    why: str = ""
    citationIds: list[str] = field(default_factory=list)


@dataclass
class BetaRecommendation:
    title: str
    body: str
    estimated: bool = True
    citationIds: list[str] = field(default_factory=list)
    state: str = "open"


@dataclass
class BetaBriefing:
    summary: str
    insights: list[BetaInsight]
    recommendations: list[BetaRecommendation]
    citations: list[BetaCitation]
    dataFreshness: dict[str, Any]
    context: dict[str, Any]
    sessionCost: dict[str, Any] | None = None
    requestId: str = ""
    cacheHit: bool = False
    estimated: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "insights": [item.__dict__ for item in self.insights],
            "recommendations": [item.__dict__ for item in self.recommendations],
            "citations": [item.__dict__ for item in self.citations],
            "dataFreshness": self.dataFreshness,
            "context": self.context,
            "sessionCost": self.sessionCost,
            "requestId": self.requestId,
            "cacheHit": self.cacheHit,
            "estimated": self.estimated,
        }


def generate_beta_briefing(
    db_path: str,
    provider: ChatCompletionsProvider | None = None,
    today: date | None = None,
) -> BetaBriefing:
    anchor = today or date.today()
    fingerprint = beta_transaction_fingerprint(db_path)
    cache_key = ("briefing", db_path, anchor.isoformat(), fingerprint)
    cached = _cache_get(cache_key)
    if cached is not None:
        return _mark_cached(cached)
    start = anchor - timedelta(days=30)
    prior_start = start - timedelta(days=30)
    prior_end = start - timedelta(days=1)
    context = _beta_context(db_path, start, anchor, prior_start, prior_end)
    prompt = (
        "Create today's Budgify money briefing with sections for what changed, "
        "what it means, and recommended actions."
    )
    result = _run_beta_ai(context, prompt, provider=provider)
    return _cache_set(cache_key, result)


def ask_beta_question(
    db_path: str,
    question: str,
    provider: ChatCompletionsProvider | None = None,
    today: date | None = None,
) -> BetaBriefing:
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("question is required")
    anchor = today or date.today()
    fingerprint = beta_transaction_fingerprint(db_path)
    cache_key = ("ask", db_path, anchor.isoformat(), cleaned, fingerprint)
    cached = _cache_get(cache_key)
    if cached is not None:
        return _mark_cached(cached)
    start = anchor - timedelta(days=120)
    prior_start = start - timedelta(days=120)
    prior_end = start - timedelta(days=1)
    context = _beta_context(db_path, start, anchor, prior_start, prior_end)
    result = _run_beta_ai(context, cleaned, provider=provider)
    return _cache_set(cache_key, result)


def beta_transaction_fingerprint(db_path: str) -> str:
    """Return a cheap MCP-derived cache key for the current transaction dataset."""
    profile = _profile_summary_impl(db_path)
    totals = _spend_summary_impl(db_path, groupBy="month", limit=50)
    payload = {
        "dateRange": profile.get("dateRange"),
        "transactionCount": profile.get("transactionCount", 0),
        "totalCents": totals.get("totalCents", 0),
        "groupCount": len(totals.get("groups") or []),
        "groups": [
            {
                "key": item.get("key"),
                "totalCents": item.get("totalCents"),
                "count": item.get("count"),
            }
            for item in totals.get("groups", [])
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def clear_beta_cache() -> None:
    with _CACHE_LOCK:
        _BETA_CACHE.clear()


def parse_beta_response(raw: str | dict[str, Any], citation_lookup: dict[str, BetaCitation]) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else _json_object(raw)
    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object")

    allowed_ids = set(citation_lookup)
    insights = [
        BetaInsight(
            title=_text(item.get("title"), "Insight"),
            body=_text(item.get("body"), ""),
            why=_text(item.get("why"), ""),
            citationIds=_valid_ids(item.get("citationIds"), allowed_ids),
        )
        for item in _items(payload.get("insights"))
    ]
    recommendations = [
        BetaRecommendation(
            title=_text(item.get("title"), "Recommended action"),
            body=_text(item.get("body"), ""),
            estimated=bool(item.get("estimated", payload.get("estimated", True))),
            citationIds=_valid_ids(item.get("citationIds"), allowed_ids),
        )
        for item in _items(payload.get("recommendations"))
    ]

    cited_ids = _valid_ids(payload.get("citations"), allowed_ids)
    for item in insights + recommendations:
        cited_ids.extend([tx_id for tx_id in item.citationIds if tx_id not in cited_ids])

    return {
        "summary": _text(payload.get("summary"), "Budgify needs more transaction history to brief you well."),
        "insights": insights,
        "recommendations": recommendations,
        "citationIds": cited_ids,
        "estimated": bool(payload.get("estimated", True)),
    }


def _run_beta_ai(
    context: dict[str, Any],
    user_prompt: str,
    provider: ChatCompletionsProvider | None,
) -> BetaBriefing:
    citation_lookup = _citation_lookup(context.get("transactions", []))
    ai_provider = provider or get_chat_provider_from_env()
    response = _complete_response(
        ai_provider,
        [
            {"role": "system", "content": BETA_SYSTEM_PROMPT},
            {"role": "system", "content": f"Budgify MCP context:\n{json.dumps(context, default=str)}"},
            {"role": "user", "content": user_prompt},
        ],
    )
    message = response.get("message") or {}
    content = str(message.get("content") or "")
    try:
        parsed = parse_beta_response(content, citation_lookup)
    except ValueError:
        parsed = {
            "summary": "Budgify could not format a grounded briefing from the model output.",
            "insights": [],
            "recommendations": [],
            "citationIds": [],
            "estimated": True,
        }
    usage = _usage_payload(response)
    model_id = getattr(getattr(ai_provider, "config", None), "model", "")
    request_id = str(uuid.uuid4())
    return BetaBriefing(
        summary=parsed["summary"],
        insights=parsed["insights"],
        recommendations=parsed["recommendations"],
        citations=[citation_lookup[tx_id] for tx_id in parsed["citationIds"]],
        dataFreshness=context["dataFreshness"],
        context={
            "range": context["range"],
            "transactionCount": context["profile"].get("transactionCount", 0),
            "tools": context["tools"],
        },
        sessionCost=build_session_cost(
            request_id=request_id,
            source="beta",
            model_id=model_id,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cached=False,
            cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
        ),
        requestId=request_id,
        estimated=parsed["estimated"],
    )


def _cache_get(key: tuple[Any, ...]) -> BetaBriefing | None:
    with _CACHE_LOCK:
        return _BETA_CACHE.get(key)


def _cache_set(key: tuple[Any, ...], value: BetaBriefing) -> BetaBriefing:
    with _CACHE_LOCK:
        if len(_BETA_CACHE) >= _CACHE_MAX_ITEMS:
            _BETA_CACHE.pop(next(iter(_BETA_CACHE)))
        _BETA_CACHE[key] = value
    return value


def _mark_cached(value: BetaBriefing) -> BetaBriefing:
    session_cost = dict(value.sessionCost or {})
    if session_cost:
        session_cost["cached"] = True
    return replace(value, cacheHit=True, sessionCost=session_cost or value.sessionCost)


def _complete_response(provider: ChatCompletionsProvider, messages: list[dict[str, Any]]) -> dict[str, Any]:
    if hasattr(provider, "complete_response"):
        return provider.complete_response(messages)
    message = provider.complete(messages)
    return {"message": message, "usage": {}}


def _usage_payload(response: dict[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    return usage if isinstance(usage, dict) else {}


def _beta_context(db_path: str, start: date, end: date, prior_start: date, prior_end: date) -> dict[str, Any]:
    start_text = start.isoformat()
    end_text = end.isoformat()
    profile = _profile_summary_impl(db_path)
    current = {"startDate": start_text, "endDate": end_text}
    prior = {"startDate": prior_start.isoformat(), "endDate": prior_end.isoformat()}
    insight_context = _insight_context_impl(
        db_path,
        start_text,
        end_text,
        "previous_period",
        ["totals", "top_categories", "top_merchants", "drivers", "anomalies", "recurring"],
        {"topCategories": 6, "topMerchants": 6, "drivers": 6, "anomalies": 5},
    )
    transactions = _find_transactions_impl(
        db_path,
        start_text,
        end_text,
        None,
        None,
        None,
        20,
        None,
        ["id", "date", "amountCents", "merchant", "category", "account", "description"],
    )
    return {
        "profile": profile,
        "range": current,
        "comparisonRange": prior,
        "dataFreshness": {
            "asOf": date.today().isoformat(),
            "rangeStart": start_text,
            "rangeEnd": end_text,
            "ledgerStart": profile.get("dateRange", {}).get("startDate"),
            "ledgerEnd": profile.get("dateRange", {}).get("endDate"),
        },
        "insightContext": insight_context,
        "comparison": _compare_periods_impl(db_path, current, prior, "category", 8),
        "cashflow": _spend_summary_impl(db_path, start_text, end_text, "month", limit=12),
        "recurring": _recurring_impl(db_path, start_text, end_text, 2, False),
        "transactions": transactions.get("items", []),
        "tools": [
            "budgify.profile_summary",
            "budgify.insight_context",
            "budgify.compare_periods",
            "budgify.spend_summary",
            "budgify.recurring_transactions",
            "budgify.find_transactions",
        ],
    }


def _citation_lookup(rows: list[dict[str, Any]]) -> dict[str, BetaCitation]:
    lookup: dict[str, BetaCitation] = {}
    for row in rows:
        tx_id = str(row.get("id") or "")
        if not tx_id:
            continue
        amount_cents = int(row.get("amountCents") or 0)
        lookup[tx_id] = BetaCitation(
            id=tx_id,
            date=str(row.get("date") or ""),
            merchant=str(row.get("merchant") or "Unknown"),
            amount=round(amount_cents / 100, 2),
            amountCents=amount_cents,
            category=str(row.get("category") or "uncategorized"),
            account=str(row.get("account") or "") or None,
        )
    return lookup


def _json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("AI response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("AI response must be a JSON object")
    return parsed


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    return value.strip() or default


def _valid_ids(value: Any, allowed_ids: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        tx_id = str(item)
        if tx_id in allowed_ids and tx_id not in out:
            out.append(tx_id)
    return out
