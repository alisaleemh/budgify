from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


@dataclass
class RunResult:
    status: str
    timestamp: str
    stdout: str
    stderr: str
    returncode: int

    @property
    def combined_output(self) -> str:
        return f"{self.stdout}\n{self.stderr}".strip()


class Runner:
    def __init__(
        self,
        config_path: Path = Path("/app/config.yaml"),
        statements_path: Path = Path("/statements"),
        state_dir: Path = Path("/appdata"),
    ) -> None:
        self.config_path = config_path
        self.statements_path = statements_path
        self.state_dir = state_dir
        self.state_file = self.state_dir / "last_run.json"
        self.log_file = self.state_dir / "last_run.log"
        self._lock = threading.Lock()
        self._last_result: Optional[RunResult] = None
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._load_last_result()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    @property
    def last_result(self) -> Optional[RunResult]:
        return self._last_result

    def _load_last_result(self) -> None:
        if not self.state_file.exists():
            return
        try:
            with self.state_file.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            self._last_result = RunResult(**data)
        except (json.JSONDecodeError, OSError, TypeError):
            self._last_result = None

    def _persist_result(self, result: RunResult) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w", encoding="utf-8") as fp:
            json.dump(result.__dict__, fp, indent=2)
        with self.log_file.open("w", encoding="utf-8") as fp:
            fp.write(result.combined_output)

    def run_budgify(self) -> RunResult:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Budgify run already in progress")

        try:
            command = [
                "budgify",
                "--dir",
                str(self.statements_path),
                "--output",
                "sheets",
                "--config",
                str(self.config_path),
            ]

            completed = subprocess.run(
                command,
                cwd=Path("/app"),
                capture_output=True,
                text=True,
            )
            status = "success" if completed.returncode == 0 else "failure"
            timestamp = datetime.utcnow().isoformat() + "Z"
            result = RunResult(
                status=status,
                timestamp=timestamp,
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
            )
            self._last_result = result
            self._persist_result(result)
            return result
        finally:
            self._lock.release()

    def status_payload(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "running": self.is_running,
            "last_result": self._last_result.__dict__ if self._last_result else None,
            "log_path": str(self.log_file),
        }
        return payload
