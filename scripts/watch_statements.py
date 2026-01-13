import hashlib
import os
import subprocess
import sys
import time


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_config_path() -> str:
    explicit = os.environ.get("CONFIG_PATH")
    if explicit:
        return explicit
    for candidate in ("/app/config.yaml", "/app/examples/config.example.yaml"):
        if os.path.exists(candidate):
            return candidate
    return "/app/config.yaml"


def _statement_signature(statements_dir: str) -> str:
    entries: list[str] = []
    for root, _, files in os.walk(statements_dir):
        for name in files:
            if name.startswith("."):
                continue
            path = os.path.join(root, name)
            if not os.path.isfile(path):
                continue
            try:
                st = os.stat(path)
            except FileNotFoundError:
                continue
            rel = os.path.relpath(path, statements_dir)
            entries.append(f"{rel}:{st.st_mtime_ns}:{st.st_size}")
    entries.sort()
    digest = hashlib.sha1("\n".join(entries).encode("utf-8")).hexdigest()
    return digest


def _run_sync(statements_dir: str, db_path: str, output_format: str) -> None:
    cmd = [
        "budgify",
        "--dir",
        statements_dir,
        "--output",
        output_format,
        "--db",
        db_path,
        "--config",
        _resolve_config_path(),
    ]
    if _env_bool("INCLUDE_PAYMENTS"):
        cmd.append("--include-payments")

    manual_file = os.environ.get("MANUAL_FILE")
    if manual_file:
        cmd.extend(["--manual-file", manual_file])

    env_file = os.environ.get("ENV_FILE")
    if env_file:
        cmd.extend(["--env-file", env_file])

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"budgify sync failed with exit code {result.returncode}")


def main() -> int:
    statements_dir = os.environ.get("STATEMENTS_DIR", "/statements")
    db_path = os.environ.get("DB_PATH", "/data/budgify.db")
    output_format = os.environ.get("OUTPUT_FORMAT", "csv")
    poll_seconds = float(os.environ.get("POLL_SECONDS", "10"))

    if not os.path.isdir(statements_dir):
        print(f"Statements directory not found: {statements_dir}", file=sys.stderr)
        return 1

    last_sig = None
    while True:
        try:
            sig = _statement_signature(statements_dir)
            if sig != last_sig:
                print("Detected statement changes. Syncing...", flush=True)
                _run_sync(statements_dir, db_path, output_format)
                last_sig = sig
                print("Sync complete.", flush=True)
        except Exception as exc:
            print(f"Sync error: {exc}", file=sys.stderr)
        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
