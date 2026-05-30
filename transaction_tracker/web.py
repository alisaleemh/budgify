from __future__ import annotations

import argparse
import base64
import html
import json
import os
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, unquote

import hmac

from transaction_tracker.ai.beta import ask_beta_question, generate_beta_briefing
from transaction_tracker.ai.assistant import query_finance_assistant
from transaction_tracker.ai.config import ai_status
from transaction_tracker.ai.finance_tools import ToolValidationError
from transaction_tracker.analytics import (
    analytics_common_filters_sorts,
    analytics_feature_usage_counts,
    analytics_search_trends,
    analytics_session_flows,
    analytics_top_events,
    append_analytics_events,
)
from transaction_tracker.database import (
    list_categories,
    list_providers,
    list_unique_merchants,
    overview_metrics,
    query_transactions,
    summarize_by_category,
    summarize_by_merchant,
    summarize_by_period,
)

STATIC_DIR = Path(__file__).with_name("web_ui")
DEFAULT_PASSWORD_KEY = "Altaf Hussain"
DEFAULT_UI_HOME_NAME = "Ali's Home"



def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(byte ^ key[idx % len(key)] for idx, byte in enumerate(data))


def _encode_password(password: str, key: str) -> str:
    encoded = _xor_bytes(password.encode("utf-8"), key.encode("utf-8"))
    return f"enc:{base64.urlsafe_b64encode(encoded).decode('utf-8')}"


def _decode_password(payload: str, key: str) -> str:
    text = payload.strip()
    if text.startswith("plain:"):
        return text.split("plain:", 1)[1]
    if text.startswith("enc:"):
        text = text[4:]
    decoded = base64.urlsafe_b64decode(text.encode("utf-8"))
    return _xor_bytes(decoded, key.encode("utf-8")).decode("utf-8")


def _extract_auth_password(header_value: str | None) -> str | None:
    if not header_value:
        return None
    if header_value.startswith("Basic "):
        token = header_value[6:].strip()
        try:
            decoded = base64.b64decode(token).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
        if ":" not in decoded:
            return None
        return decoded.split(":", 1)[1]
    if header_value.startswith("Bearer "):
        return header_value[7:].strip()
    return None


def _load_password_file(path: str, key: str) -> str | None:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None
    return _decode_password(payload, key)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    return int(value)


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    text = value.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_float_env(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_ui_text() -> dict[str, str]:
    app_name = os.environ.get("BUDGIFY_UI_APP_NAME", "Budgify").strip() or "Budgify"
    home_name = os.environ.get("BUDGIFY_UI_HOME_NAME", DEFAULT_UI_HOME_NAME).strip() or DEFAULT_UI_HOME_NAME

    app_title = os.environ.get("BUDGIFY_UI_TITLE_TEMPLATE", "{app} · {home}").format(
        app=app_name,
        home=home_name,
    )
    app_eyebrow = os.environ.get("BUDGIFY_UI_EYEBROW_TEMPLATE", "{app} Home").format(
        app=app_name,
        home=home_name,
    )
    app_headline = os.environ.get(
        "BUDGIFY_UI_HEADLINE_TEMPLATE",
        "{home} spending, powered by {app}.",
    ).format(app=app_name, home=home_name)
    app_lede = os.environ.get(
        "BUDGIFY_UI_LEDE_TEMPLATE",
        "Explore monthly trends, category mix, and top merchants for your home ledger.",
    ).format(app=app_name, home=home_name)

    return {
        "{{APP_TITLE}}": html.escape(app_title),
        "{{APP_EYEBROW}}": html.escape(app_eyebrow),
        "{{APP_HEADLINE}}": html.escape(app_headline),
        "{{APP_LEDE}}": html.escape(app_lede),
    }


def _get_analytics_text(handler: "BudgifyWebHandler" | None = None) -> dict[str, str]:
    enabled = handler.analytics_enabled if handler is not None else _parse_bool(os.environ.get("BUDGIFY_ANALYTICS_ENABLED"), True)
    sampling_rate = handler.analytics_sampling_rate if handler is not None else _parse_float_env(os.environ.get("BUDGIFY_ANALYTICS_SAMPLING_RATE"), 1.0)
    dev_logging = handler.analytics_dev_logging if handler is not None else _parse_bool(os.environ.get("BUDGIFY_ANALYTICS_DEV_LOGGING"), False)
    return {
        "{{ANALYTICS_ENABLED}}": "true" if enabled else "false",
        "{{ANALYTICS_SAMPLING_RATE}}": str(max(0.0, min(float(sampling_rate), 1.0))),
        "{{ANALYTICS_DEV_LOGGING}}": "true" if dev_logging else "false",
    }


def _render_index_html(html_text: str, handler: "BudgifyWebHandler" | None = None) -> str:
    rendered = html_text
    for token, value in {**_get_ui_text(), **_get_analytics_text(handler)}.items():
        rendered = rendered.replace(token, value)
    return rendered


def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length_value = handler.headers.get("Content-Length", "0")
    try:
        length = int(length_value)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


class BudgifyWebHandler(BaseHTTPRequestHandler):
    db_path = "budgify.db"
    static_dir = STATIC_DIR
    password_file: str | None = None
    password_key: str = DEFAULT_PASSWORD_KEY
    analytics_enabled = True
    analytics_sampling_rate = 1.0
    analytics_dev_logging = False

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if not self._authorize_request():
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return
        self._handle_static(parsed.path)

    def do_POST(self) -> None:
        if not self._authorize_request():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/assistant/query":
            self._handle_assistant_query()
            return
        if parsed.path == "/api/beta/ask":
            self._handle_beta_ask()
            return
        if parsed.path.startswith("/api/"):
            self._handle_post_api(parsed)
            return
        _json_response(self, {"error": "not found"}, status=404)

    def _handle_api(self, parsed) -> None:
        query = parse_qs(parsed.query)
        categories = _get_categories(query)
        path = parsed.path

        try:
            if path == "/api/assistant/status":
                _json_response(self, ai_status())
                return

            if path == "/api/beta/briefing":
                _json_response(self, generate_beta_briefing(self.db_path).as_dict())
                return

            if path == "/api/metadata":
                payload = {
                    "categories": list_categories(self.db_path),
                    "providers": list_providers(self.db_path),
                    "merchants": list_unique_merchants(self.db_path),
                }
                _json_response(self, payload)
                return

            if path == "/api/analytics/top-events":
                limit = _parse_int(_get_param(query, "limit"), default=10) or 10
                _json_response(self, analytics_top_events(self.db_path, limit=limit))
                return

            if path == "/api/analytics/session-flows":
                limit = _parse_int(_get_param(query, "limit"), default=20) or 20
                _json_response(self, analytics_session_flows(self.db_path, limit=limit))
                return

            if path == "/api/analytics/search-trends":
                limit = _parse_int(_get_param(query, "limit"), default=20) or 20
                _json_response(self, analytics_search_trends(self.db_path, limit=limit))
                return

            if path == "/api/analytics/feature-usage":
                limit = _parse_int(_get_param(query, "limit"), default=20) or 20
                _json_response(self, analytics_feature_usage_counts(self.db_path, limit=limit))
                return

            if path == "/api/analytics/filters-sorts":
                _json_response(self, analytics_common_filters_sorts(self.db_path))
                return

            if path == "/api/overview":
                payload = overview_metrics(
                    self.db_path,
                    start_date=_parse_date(_get_param(query, "start_date")),
                    end_date=_parse_date(_get_param(query, "end_date")),
                    category=_get_param(query, "category"),
                    categories=categories,
                    exclude_category=_get_param(query, "exclude_category"),
                    provider=_get_param(query, "provider"),
                    merchant=_get_param(query, "merchant"),
                    min_amount=_parse_float(_get_param(query, "min_amount")),
                    max_amount=_parse_float(_get_param(query, "max_amount")),
                    merchant_regex=_get_param(query, "merchant_regex"),
                )
                _json_response(self, payload)
                return

            if path == "/api/summary/category":
                payload = summarize_by_category(
                    self.db_path,
                    start_date=_parse_date(_get_param(query, "start_date")),
                    end_date=_parse_date(_get_param(query, "end_date")),
                    category=_get_param(query, "category"),
                    categories=categories,
                    exclude_category=_get_param(query, "exclude_category"),
                    provider=_get_param(query, "provider"),
                )
                _json_response(self, payload)
                return

            if path == "/api/summary/period":
                period = _get_param(query, "period")
                if period not in ("month", "quarter", "year"):
                    _json_response(self, {"error": "period must be month, quarter, or year"}, status=400)
                    return
                payload = summarize_by_period(
                    self.db_path,
                    period=period,
                    start_date=_parse_date(_get_param(query, "start_date")),
                    end_date=_parse_date(_get_param(query, "end_date")),
                    category=_get_param(query, "category"),
                    categories=categories,
                    exclude_category=_get_param(query, "exclude_category"),
                    provider=_get_param(query, "provider"),
                )
                _json_response(self, payload)
                return

            if path == "/api/summary/merchant":
                limit = _parse_int(_get_param(query, "limit"), default=15) or 15
                payload = summarize_by_merchant(
                    self.db_path,
                    start_date=_parse_date(_get_param(query, "start_date")),
                    end_date=_parse_date(_get_param(query, "end_date")),
                    category=_get_param(query, "category"),
                    categories=categories,
                    exclude_category=_get_param(query, "exclude_category"),
                    provider=_get_param(query, "provider"),
                )
                _json_response(self, payload[:limit])
                return

            if path == "/api/transactions":
                payload = query_transactions(
                    self.db_path,
                    start_date=_parse_date(_get_param(query, "start_date")),
                    end_date=_parse_date(_get_param(query, "end_date")),
                    category=_get_param(query, "category"),
                    categories=categories,
                    exclude_category=_get_param(query, "exclude_category"),
                    provider=_get_param(query, "provider"),
                    merchant=_get_param(query, "merchant"),
                    merchant_regex=_get_param(query, "merchant_regex"),
                    min_amount=_parse_float(_get_param(query, "min_amount")),
                    max_amount=_parse_float(_get_param(query, "max_amount")),
                    sort_by=_get_param(query, "sort_by") or "date",
                    sort_dir=_get_param(query, "sort_dir") or "asc",
                    group_by=_get_param(query, "group_by"),
                    limit=_parse_int(_get_param(query, "limit"), default=200) or 200,
                    offset=_parse_int(_get_param(query, "offset"), default=0) or 0,
                )
                _json_response(self, payload)
                return
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, status=500)
            return

        _json_response(self, {"error": "not found"}, status=404)

    def _handle_assistant_query(self) -> None:
        try:
            payload = _read_json_body(self)
            question = payload.get("question")
            if not isinstance(question, str) or not question.strip():
                _json_response(self, {"error": "question is required"}, status=400)
                return
            result = query_finance_assistant(self.db_path, question)
            _json_response(
                self,
                {
                    "answer": result.answer,
                    "summary": result.summary,
                    "bullets": result.bullets,
                    "followup": result.followup,
                    "cards": result.cards,
                    "tables": result.tables,
                    "dataUsed": result.data_used,
                    "sessionCost": result.sessionCost,
                },
            )
        except ToolValidationError as exc:
            _json_response(self, {"error": str(exc)}, status=400)
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, status=400)
        except RuntimeError as exc:
            _json_response(self, {"error": str(exc)}, status=503)
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, status=500)

    def _handle_beta_ask(self) -> None:
        try:
            payload = _read_json_body(self)
            question = payload.get("question")
            if not isinstance(question, str) or not question.strip():
                _json_response(self, {"error": "question is required"}, status=400)
                return
            _json_response(self, ask_beta_question(self.db_path, question).as_dict())
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, status=400)
        except RuntimeError as exc:
            _json_response(self, {"error": str(exc)}, status=503)
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, status=500)

    def _handle_post_api(self, parsed) -> None:
        if parsed.path == "/api/analytics/events":
            if not self.analytics_enabled:
                _json_response(self, {"accepted": 0}, status=202)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                _json_response(self, {"error": "invalid json"}, status=400)
                return
            events = payload.get("events", payload)
            if not isinstance(events, list):
                _json_response(self, {"error": "events must be a list"}, status=400)
                return
            append_analytics_events(self.db_path, events)
            if self.analytics_dev_logging:
                print(f"[analytics] stored {len(events)} event(s)")
            _json_response(self, {"accepted": len(events)}, status=202)
            return
        _json_response(self, {"error": "not found"}, status=404)
    def _handle_static(self, raw_path: str) -> None:
        static_root = Path(self.static_dir).resolve()
        path = raw_path or "/"
        if path == "/":
            path = "/index.html"
        resolved = (static_root / unquote(path.lstrip("/"))).resolve()
        if not resolved.exists() and "." not in Path(path).name:
            resolved = (static_root / "index.html").resolve()
        if static_root not in resolved.parents and resolved != static_root:
            self.send_error(404)
            return
        if not resolved.exists() or not resolved.is_file():
            self.send_error(404)
            return

        content_type = _guess_content_type(resolved)
        if resolved.name == "index.html":
            body = _render_index_html(resolved.read_text(encoding="utf-8"), self).encode("utf-8")
        else:
            body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if resolved.name == "index.html":
            self.send_header("Cache-Control", "no-store")
        elif "/assets/" in resolved.as_posix():
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorize_request(self) -> bool:
        if not self.password_file:
            return True
        expected = _load_password_file(self.password_file, self.password_key)
        if expected is None:
            self.send_error(500, "Password file not found")
            return False
        provided = _extract_auth_password(self.headers.get("Authorization"))
        if provided is None or not hmac.compare_digest(provided, expected):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Budgify"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return False
        return True


def _guess_content_type(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".mjs":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".json":
        return "application/json"
    if path.suffix == ".map":
        return "application/json"
    if path.suffix == ".svg":
        return "image/svg+xml"
    if path.suffix == ".png":
        return "image/png"
    if path.suffix == ".ico":
        return "image/x-icon"
    if path.suffix == ".woff2":
        return "font/woff2"
    if path.suffix == ".woff":
        return "font/woff"
    return "application/octet-stream"


def _get_param(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _get_categories(query: dict[str, list[str]]) -> list[str] | None:
    raw_values = query.get("categories") or query.get("category")
    if not raw_values:
        return None

    categories: list[str] = []
    for raw in raw_values:
        for part in raw.split(","):
            cleaned = part.strip()
            if cleaned:
                categories.append(cleaned)

    if not categories:
        return None
    return list(dict.fromkeys(categories))


def main() -> None:
    parser = argparse.ArgumentParser(description="Budgify web dashboard")
    parser.add_argument("--db", dest="db_path", default="budgify.db", help="Path to SQLite database")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument(
        "--password-file",
        default=os.environ.get("BUDGIFY_PASSWORD_FILE"),
        help="Path to encrypted password file",
    )
    parser.add_argument(
        "--password-key",
        default=os.environ.get("BUDGIFY_PASSWORD_KEY", DEFAULT_PASSWORD_KEY),
        help="Encryption key for password file",
    )
    parser.add_argument(
        "--analytics-enabled",
        action=argparse.BooleanOptionalAction,
        default=_parse_bool(os.environ.get("BUDGIFY_ANALYTICS_ENABLED"), True),
        help="Enable analytics persistence and API endpoints",
    )
    parser.add_argument(
        "--analytics-sampling-rate",
        type=float,
        default=_parse_float_env(os.environ.get("BUDGIFY_ANALYTICS_SAMPLING_RATE"), 1.0),
        help="Fraction of sessions to sample (0.0 to 1.0)",
    )
    parser.add_argument(
        "--analytics-dev-logging",
        action=argparse.BooleanOptionalAction,
        default=_parse_bool(os.environ.get("BUDGIFY_ANALYTICS_DEV_LOGGING"), False),
        help="Print analytics event ingestion logs",
    )
    args = parser.parse_args()

    handler = type(
        "BudgifyWebHandler",
        (BudgifyWebHandler,),
        {
            "db_path": args.db_path,
            "static_dir": STATIC_DIR,
            "password_file": args.password_file,
            "password_key": args.password_key,
            "analytics_enabled": args.analytics_enabled,
            "analytics_sampling_rate": max(0.0, min(float(args.analytics_sampling_rate), 1.0)),
            "analytics_dev_logging": args.analytics_dev_logging,
        },
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Budgify web UI running at http://{args.host}:{args.port} (db: {args.db_path})")
    server.serve_forever()


if __name__ == "__main__":
    main()
