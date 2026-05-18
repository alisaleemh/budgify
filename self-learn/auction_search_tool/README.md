# Auction Search Tool

A local Flask app that searches a local SQLite index of current/open lots from `hibid.com` and `403auction.com`.

## Features

- Server-rendered search page at `GET /`
- JSON API at `GET /api/search?q=...`
- Local SQLite-backed search index
- Built-in nightly index scheduler
- Manual index rebuild command
- Case-insensitive token matching across lot title, condition, and details
- Indexed scope limited to open lots ending within the next 7 days
- Generic schema with provider raw payload retention

## Setup

Create and activate a virtual environment, then install the local requirements:

```bash
cd self-learn/auction_search_tool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
cd self-learn/auction_search_tool
source .venv/bin/activate
python app.py serve
```

Open `http://127.0.0.1:5001`.

## Build The Index

```bash
cd self-learn/auction_search_tool
source .venv/bin/activate
python app.py index
```

The local app reads only from the SQLite index. Run `python app.py index` once before your first search. The `serve` command also starts a built-in nightly scheduler that refreshes the index automatically.

## Test

```bash
cd self-learn/auction_search_tool
source .venv/bin/activate
pytest -q
```

## Notes

- The tool is read-only.
- HiBid search is fixed to `zip=L9T 8N6` and `miles=25` in v1.
- Search requests do not fetch live upstream data.
- Results are limited to lots ending within the next 7 days.
