from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from transaction_tracker.database import _connect_db

_SENSITIVE_KEY_RE = re.compile(
    r"(password|pass|token|secret|api[_-]?key|auth|credential|session|cookie|"
    r"card|cvv|pin|ssn|account|routing|iban|bank)",
    re.IGNORECASE,
)
_DIGIT_BLOB_RE = re.compile(r"\b(?:\d[ -]*?){6,}\b")
_EMAIL_RE = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")
_WHITESPACE_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_SEARCH_EVENTS = {
    "search_submitted",
    "search_zero_results",
    "search_abandoned",
}

_FILTER_EVENTS = {"filter_changed", "settings_changed"}
_SORT_EVENTS = {"sort_changed"}


@dataclass(slots=True)
class AnalyticsEventRecord:
    event_id: str
    user_id: str
    session_id: str
    event_type: str
    page: str
    component: str | None
    metadata: dict[str, Any]
    ts: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect_analytics_db(db_path: str | Path) -> sqlite3.Connection:
    conn = _connect_db(db_path)
    _init_analytics_db(conn)
    return conn


def _init_analytics_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_events (
            event_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            page TEXT NOT NULL,
            component TEXT,
            metadata_json TEXT NOT NULL,
            ts TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_seconds REAL,
            event_count INTEGER NOT NULL,
            first_page TEXT,
            last_page TEXT,
            last_event_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_user_id ON analytics_events(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_session_id ON analytics_events(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_event_type ON analytics_events(event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_ts ON analytics_events(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_sessions_user_id ON analytics_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_sessions_last_event_at ON analytics_sessions(last_event_at)")
    conn.commit()


def _clean_text(value: str, limit: int = 120) -> str:
    cleaned = _CONTROL_RE.sub(" ", value)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:limit]


def _normalize_key(value: str) -> str:
    cleaned = _clean_text(value, limit=64).lower()
    cleaned = re.sub(r"[^a-z0-9_]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(key))


def _looks_sensitive_text(value: str) -> bool:
    return bool(_DIGIT_BLOB_RE.search(value) or _EMAIL_RE.search(value))


def _sanitize_search_term(value: str) -> str:
    term = _clean_text(value, limit=120)
    if len(term) > 2 and _looks_sensitive_text(term):
        return "[redacted]"
    return term


def _sanitize_scalar(key: str | None, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        cleaned = _clean_text(value)
        if not cleaned:
            return None
        if key and key in {"query", "term", "search", "search_term"}:
            return _sanitize_search_term(cleaned)
        if _is_sensitive_key(key or "") or _looks_sensitive_text(cleaned):
            return "[redacted]"
        return cleaned
    return _clean_text(str(value))


def _sanitize_metadata(value: Any, key: str | None = None, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for idx, (raw_key, raw_value) in enumerate(value.items()):
            if idx >= 16:
                break
            normalized_key = _normalize_key(str(raw_key))
            if not normalized_key:
                continue
            if _is_sensitive_key(normalized_key):
                cleaned[normalized_key] = "[redacted]"
                continue
            cleaned_value = _sanitize_metadata(raw_value, normalized_key, depth + 1)
            if cleaned_value is not None:
                cleaned[normalized_key] = cleaned_value
        return cleaned
    if isinstance(value, (list, tuple, set)):
        items = []
        for item in list(value)[:8]:
            cleaned_item = _sanitize_metadata(item, key, depth + 1)
            if cleaned_item is not None:
                items.append(cleaned_item)
        return items
    return _sanitize_scalar(key, value)


def _normalize_event(payload: Mapping[str, Any] | AnalyticsEventRecord) -> AnalyticsEventRecord:
    if isinstance(payload, AnalyticsEventRecord):
        data = asdict(payload)
    else:
        data = dict(payload)

    event_id = _clean_text(str(data.get("eventId") or data.get("event_id") or uuid.uuid4()), limit=64)
    user_id = _clean_text(str(data.get("userId") or data.get("user_id") or "anonymous"), limit=64) or "anonymous"
    session_id = _clean_text(str(data.get("sessionId") or data.get("session_id") or uuid.uuid4()), limit=64)
    event_type = _normalize_key(str(data.get("eventType") or data.get("event_type") or "interaction")) or "interaction"
    page = _clean_text(str(data.get("page") or "/"), limit=120) or "/"
    component_raw = data.get("component")
    component = _clean_text(str(component_raw), limit=80) if component_raw else None
    metadata = _sanitize_metadata(data.get("metadata") or {})
    if not isinstance(metadata, dict):
        metadata = {"value": metadata}
    ts = _clean_text(str(data.get("ts") or data.get("timestamp") or _utc_now_iso()), limit=64)
    if not ts:
        ts = _utc_now_iso()

    return AnalyticsEventRecord(
        event_id=event_id,
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        page=page,
        component=component,
        metadata=metadata,
        ts=ts,
    )


def append_analytics_events(db_path: str | Path, events: Iterable[Mapping[str, Any] | AnalyticsEventRecord]) -> None:
    records = [_normalize_event(event) for event in events]
    if not records:
        return

    conn = _connect_analytics_db(db_path)
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO analytics_events
            (event_id, user_id, session_id, event_type, page, component, metadata_json, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.event_id,
                    record.user_id,
                    record.session_id,
                    record.event_type,
                    record.page,
                    record.component,
                    json.dumps(record.metadata, separators=(",", ":"), sort_keys=True),
                    record.ts,
                )
                for record in records
            ],
        )
        session_ids = sorted({record.session_id for record in records})
        for session_id in session_ids:
            _refresh_session_summary(conn, session_id)
        conn.commit()
    finally:
        conn.close()


def _refresh_session_summary(conn: sqlite3.Connection, session_id: str) -> None:
    rows = conn.execute(
        """
        SELECT user_id, event_type, page, metadata_json, ts
        FROM analytics_events
        WHERE session_id = ?
        ORDER BY ts, event_id
        """,
        (session_id,),
    ).fetchall()
    if not rows:
        conn.execute("DELETE FROM analytics_sessions WHERE session_id = ?", (session_id,))
        return

    first_ts = rows[0][4]
    last_ts = rows[-1][4]
    user_id = rows[0][0]
    event_count = len(rows)
    first_page = next((row[2] for row in rows if row[2]), None)
    last_page = next((row[2] for row in reversed(rows) if row[2]), None)
    ended_at = next((row[4] for row in reversed(rows) if row[1] == "session_ended"), None)
    duration_seconds = _duration_seconds(first_ts, ended_at or last_ts)

    conn.execute(
        """
        INSERT INTO analytics_sessions
        (session_id, user_id, started_at, ended_at, duration_seconds, event_count, first_page, last_page, last_event_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            user_id=excluded.user_id,
            started_at=excluded.started_at,
            ended_at=excluded.ended_at,
            duration_seconds=excluded.duration_seconds,
            event_count=excluded.event_count,
            first_page=excluded.first_page,
            last_page=excluded.last_page,
            last_event_at=excluded.last_event_at
        """,
        (
            session_id,
            user_id,
            first_ts,
            ended_at,
            duration_seconds,
            event_count,
            first_page,
            last_page,
            last_ts,
        ),
    )


def _duration_seconds(start_ts: str, end_ts: str | None) -> float | None:
    if not end_ts:
        return None
    try:
        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max((end - start).total_seconds(), 0.0)


def _load_metadata(metadata_json: str) -> dict[str, Any]:
    try:
        data = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def analytics_top_events(
    db_path: str | Path,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    conn = _connect_analytics_db(db_path)
    try:
        rows = conn.execute(
            """
            SELECT event_type, component, COUNT(*) AS count
            FROM analytics_events
            GROUP BY event_type, component
            ORDER BY count DESC, event_type, component
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [
            {
                "eventType": row[0],
                "component": row[1],
                "count": int(row[2]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def analytics_feature_usage_counts(
    db_path: str | Path,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conn = _connect_analytics_db(db_path)
    try:
        rows = conn.execute(
            """
            SELECT page, component, event_type, COUNT(*) AS count
            FROM analytics_events
            WHERE event_type NOT IN ('session_started', 'session_ended', 'page_view')
            GROUP BY page, component, event_type
            ORDER BY count DESC, page, component, event_type
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [
            {
                "page": row[0],
                "component": row[1],
                "eventType": row[2],
                "count": int(row[3]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def analytics_common_filters_sorts(db_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    conn = _connect_analytics_db(db_path)
    try:
        filter_rows = conn.execute(
            """
            SELECT metadata_json
            FROM analytics_events
            WHERE event_type = 'filter_changed'
            """
        ).fetchall()
        sort_rows = conn.execute(
            """
            SELECT metadata_json
            FROM analytics_events
            WHERE event_type = 'sort_changed'
            """
        ).fetchall()
    finally:
        conn.close()

    filters: dict[tuple[str, str], int] = defaultdict(int)
    for (metadata_json,) in filter_rows:
        metadata = _load_metadata(metadata_json)
        name = _clean_text(str(metadata.get("filter") or metadata.get("field") or metadata.get("name") or ""), 64)
        value = _clean_text(str(metadata.get("value") or metadata.get("selected") or metadata.get("state") or ""), 80)
        if name and value:
            filters[(name, value)] += 1

    sorts: dict[tuple[str, str], int] = defaultdict(int)
    for (metadata_json,) in sort_rows:
        metadata = _load_metadata(metadata_json)
        sort_by = _clean_text(str(metadata.get("sort") or metadata.get("sortby") or metadata.get("sort_by") or ""), 64)
        sort_dir = _clean_text(str(metadata.get("direction") or metadata.get("sortdir") or metadata.get("sort_dir") or ""), 32)
        if sort_by:
            sorts[(sort_by, sort_dir or "asc")] += 1

    return {
        "filters": [
            {"filter": key[0], "value": key[1], "count": count}
            for key, count in sorted(filters.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
        ],
        "sorts": [
            {"sort": key[0], "direction": key[1], "count": count}
            for key, count in sorted(sorts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
        ],
    }


def analytics_search_trends(
    db_path: str | Path,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conn = _connect_analytics_db(db_path)
    try:
        rows = conn.execute(
            """
            SELECT session_id, event_type, metadata_json, ts
            FROM analytics_events
            WHERE event_type IN ('search_submitted', 'search_zero_results', 'search_abandoned')
            ORDER BY ts, event_id
            """
        ).fetchall()
    finally:
        conn.close()

    trends: dict[str, dict[str, Any]] = {}
    for session_id, event_type, metadata_json, ts in rows:
        metadata = _load_metadata(metadata_json)
        query = _clean_text(str(metadata.get("query") or metadata.get("term") or metadata.get("search") or ""), 120)
        if not query:
            continue
        bucket = trends.setdefault(
            query,
            {
                "query": query,
                "submitted": 0,
                "zeroResults": 0,
                "abandoned": 0,
                "lastSeen": ts,
                "_sessions": set(),
            },
        )
        bucket["lastSeen"] = max(bucket["lastSeen"], ts)
        bucket["_sessions"].add(session_id)
        if event_type == "search_submitted":
            bucket["submitted"] += 1
            result_count = metadata.get("resultcount")
            if result_count is None:
                result_count = metadata.get("result_count")
            try:
                is_zero_result = result_count is not None and int(result_count) == 0
            except (TypeError, ValueError):
                is_zero_result = False
            if is_zero_result:
                bucket["zeroResults"] += 1
        elif event_type == "search_zero_results":
            bucket["zeroResults"] += 1
        elif event_type == "search_abandoned":
            bucket["abandoned"] += 1

    rows_out = [
        {
            "query": item["query"],
            "submitted": item["submitted"],
            "zeroResults": item["zeroResults"],
            "abandoned": item["abandoned"],
            "zeroResultRate": round(item["zeroResults"] / item["submitted"], 3) if item["submitted"] else 0.0,
            "abandonmentRate": round(item["abandoned"] / item["submitted"], 3) if item["submitted"] else 0.0,
            "lastSeen": item["lastSeen"],
            "sessionCount": len(item["_sessions"]),
        }
        for item in trends.values()
    ]
    rows_out.sort(key=lambda row: (-row["submitted"], -row["zeroResults"], row["query"]))
    return rows_out[: max(1, min(int(limit), 100))]


def analytics_session_flows(
    db_path: str | Path,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conn = _connect_analytics_db(db_path)
    try:
        session_rows = conn.execute(
            """
            SELECT session_id, user_id, started_at, ended_at, duration_seconds, event_count, first_page, last_page, last_event_at
            FROM analytics_sessions
            ORDER BY last_event_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        sessions = []
        for row in session_rows:
            event_rows = conn.execute(
                """
                SELECT event_type, page, component, metadata_json, ts
                FROM analytics_events
                WHERE session_id = ?
                ORDER BY ts, event_id
                """,
                (row[0],),
            ).fetchall()
            flow = [event_row[0] for event_row in event_rows]
            pages = [event_row[1] for event_row in event_rows if event_row[1]]
            sessions.append(
                {
                    "sessionId": row[0],
                    "userId": row[1],
                    "startedAt": row[2],
                    "endedAt": row[3],
                    "durationSeconds": row[4],
                    "eventCount": row[5],
                    "firstPage": row[6],
                    "lastPage": row[7],
                    "flow": flow,
                    "pages": pages,
                }
            )
        return sessions
    finally:
        conn.close()
