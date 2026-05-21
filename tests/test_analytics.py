import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from transaction_tracker import web
from transaction_tracker.analytics import (
    analytics_common_filters_sorts,
    analytics_feature_usage_counts,
    analytics_search_trends,
    analytics_session_flows,
    analytics_top_events,
    append_analytics_events,
)


def _seed_events(db_path: Path) -> None:
    events = [
        {
            "eventId": "evt-1",
            "userId": "user-1",
            "sessionId": "sess-1",
            "eventType": "session_started",
            "page": "/transactions",
            "component": "Analytics",
            "metadata": {"startedAt": "2026-05-19T00:00:00+00:00"},
            "ts": "2026-05-19T00:00:00+00:00",
        },
        {
            "eventId": "evt-2",
            "userId": "user-1",
            "sessionId": "sess-1",
            "eventType": "search_submitted",
            "page": "/transactions",
            "component": "FiltersPanel",
            "metadata": {"query": "Coffee Beans", "queryLength": 12, "resultCount": 0},
            "ts": "2026-05-19T00:00:10+00:00",
        },
        {
            "eventId": "evt-3",
            "userId": "user-1",
            "sessionId": "sess-1",
            "eventType": "search_zero_results",
            "page": "/transactions",
            "component": "FiltersPanel",
            "metadata": {"query": "Coffee Beans"},
            "ts": "2026-05-19T00:00:11+00:00",
        },
        {
            "eventId": "evt-4",
            "userId": "user-1",
            "sessionId": "sess-1",
            "eventType": "filter_changed",
            "page": "/transactions",
            "component": "FiltersPanel",
            "metadata": {"filter": "provider", "value": "amex"},
            "ts": "2026-05-19T00:00:12+00:00",
        },
        {
            "eventId": "evt-5",
            "userId": "user-1",
            "sessionId": "sess-1",
            "eventType": "sort_changed",
            "page": "/transactions",
            "component": "TransactionTable",
            "metadata": {"sort": "amount", "direction": "desc", "apiKey": "secret-value"},
            "ts": "2026-05-19T00:00:13+00:00",
        },
        {
            "eventId": "evt-6",
            "userId": "user-1",
            "sessionId": "sess-1",
            "eventType": "button_clicked",
            "page": "/transactions",
            "component": "AppLayout",
            "metadata": {"action": "refresh_dashboard"},
            "ts": "2026-05-19T00:00:14+00:00",
        },
        {
            "eventId": "evt-7",
            "userId": "user-1",
            "sessionId": "sess-1",
            "eventType": "session_ended",
            "page": "/transactions",
            "component": "Analytics",
            "metadata": {"reason": "pagehide"},
            "ts": "2026-05-19T00:00:20+00:00",
        },
    ]
    append_analytics_events(db_path, events)


def test_append_analytics_events_sanitizes_and_summaries(tmp_path):
    db_path = tmp_path / "analytics.db"
    _seed_events(db_path)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT event_type, metadata_json FROM analytics_events ORDER BY ts").fetchall()
        assert len(rows) == 7
        assert rows[4][0] == "sort_changed"
        assert "secret-value" not in rows[4][1]
        assert "[redacted]" in rows[4][1]
    finally:
        conn.close()

    top_events = analytics_top_events(db_path, limit=3)
    assert top_events[0]["eventType"] in {"search_submitted", "search_zero_results", "button_clicked"}

    sessions = analytics_session_flows(db_path, limit=1)
    assert sessions[0]["sessionId"] == "sess-1"
    assert sessions[0]["flow"][:3] == ["session_started", "search_submitted", "search_zero_results"]
    assert sessions[0]["durationSeconds"] == 20.0

    trends = analytics_search_trends(db_path, limit=5)
    assert trends[0]["query"] == "Coffee Beans"
    assert trends[0]["submitted"] == 1
    assert trends[0]["zeroResults"] == 2

    filters = analytics_common_filters_sorts(db_path)
    assert filters["filters"][0]["filter"] == "provider"
    assert filters["sorts"][0]["sort"] == "amount"
    assert filters["sorts"][0]["direction"] == "desc"

    usage = analytics_feature_usage_counts(db_path, limit=10)
    assert any(row["eventType"] == "button_clicked" for row in usage)


def test_analytics_api_persists_events(tmp_path):
    db_path = tmp_path / "api.db"
    handler = type(
        "TestBudgifyWebHandler",
        (web.BudgifyWebHandler,),
        {
            "db_path": str(db_path),
            "static_dir": web.STATIC_DIR,
            "password_file": None,
            "password_key": web.DEFAULT_PASSWORD_KEY,
            "analytics_enabled": True,
            "analytics_sampling_rate": 1.0,
            "analytics_dev_logging": False,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        payload = {
            "events": [
                {
                    "eventId": "evt-api-1",
                    "userId": "user-api",
                    "sessionId": "sess-api",
                    "eventType": "page_view",
                    "page": "/",
                    "component": "Analytics",
                    "metadata": {"path": "/"},
                    "ts": "2026-05-19T00:01:00+00:00",
                }
            ]
        }
        req = Request(
            f"{base_url}/api/analytics/events",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            assert resp.status == 202

        with urlopen(f"{base_url}/api/analytics/top-events?limit=5") as resp:
            body = json.loads(resp.read().decode("utf-8"))
            assert body[0]["eventType"] == "page_view"
    finally:
        server.shutdown()
        server.server_close()
