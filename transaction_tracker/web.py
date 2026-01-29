from __future__ import annotations

import argparse
import base64
import json
import os
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, unquote

import hmac

from transaction_tracker.database import (
    list_categories,
    list_unique_merchants,
    overview_metrics,
    query_transactions,
    summarize_by_category,
    summarize_by_merchant,
    summarize_by_period,
)

STATIC_DIR = Path(__file__).with_name("web_ui")
DEFAULT_PASSWORD_KEY = "Altaf Hussain"


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


def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class BudgifyWebHandler(BaseHTTPRequestHandler):
    db_path = "budgify.db"
    static_dir = STATIC_DIR
    password_file: str | None = None
    password_key: str = DEFAULT_PASSWORD_KEY

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

    def _handle_api(self, parsed) -> None:
        query = parse_qs(parsed.query)
        path = parsed.path

        try:
            if path == "/api/metadata":
                payload = {
                    "categories": list_categories(self.db_path),
                    "merchants": list_unique_merchants(self.db_path),
                }
                _json_response(self, payload)
                return

            if path == "/api/overview":
                payload = overview_metrics(
                    self.db_path,
                    start_date=_parse_date(_get_param(query, "start_date")),
                    end_date=_parse_date(_get_param(query, "end_date")),
                    category=_get_param(query, "category"),
                    exclude_category=_get_param(query, "exclude_category"),
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
                    exclude_category=_get_param(query, "exclude_category"),
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
                    exclude_category=_get_param(query, "exclude_category"),
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
                    exclude_category=_get_param(query, "exclude_category"),
                )
                _json_response(self, payload[:limit])
                return

            if path == "/api/transactions":
                payload = query_transactions(
                    self.db_path,
                    start_date=_parse_date(_get_param(query, "start_date")),
                    end_date=_parse_date(_get_param(query, "end_date")),
                    category=_get_param(query, "category"),
                    exclude_category=_get_param(query, "exclude_category"),
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

    def _handle_static(self, raw_path: str) -> None:
        static_root = Path(self.static_dir).resolve()
        path = raw_path or "/"
        if path == "/":
            path = "/index.html"
        resolved = (static_root / unquote(path.lstrip("/"))).resolve()
        if not resolved.exists() or not resolved.is_file():
            self.send_error(404)
            return

        content_type = _guess_content_type(resolved)
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
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
    if path.suffix == ".svg":
        return "image/svg+xml"
    if path.suffix == ".png":
        return "image/png"
    return "application/octet-stream"


def _get_param(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


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
    args = parser.parse_args()

    handler = type(
        "BudgifyWebHandler",
        (BudgifyWebHandler,),
        {
            "db_path": args.db_path,
            "static_dir": STATIC_DIR,
            "password_file": args.password_file,
            "password_key": args.password_key,
        },
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Budgify web UI running at http://{args.host}:{args.port} (db: {args.db_path})")
    server.serve_forever()


if __name__ == "__main__":
    main()
