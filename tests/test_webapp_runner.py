from pathlib import Path
from types import SimpleNamespace

import pytest

from webapp.runner import Runner


def test_runner_invokes_budgify(tmp_path, monkeypatch):
    calls = {}

    def fake_run(cmd, cwd, capture_output, text):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("webapp.runner.subprocess.run", fake_run)

    runner = Runner(config_path=tmp_path / "config.yaml", state_dir=tmp_path)
    result = runner.run_budgify()

    assert calls["cmd"][:3] == ["budgify", "--dir", "/statements"]
    assert calls["cwd"] == Path("/app")
    assert result.status == "success"
    assert (tmp_path / "last_run.json").exists()
    assert (tmp_path / "last_run.log").exists()

    persisted_runner = Runner(config_path=tmp_path / "config.yaml", state_dir=tmp_path)
    assert persisted_runner.last_result is not None
    assert persisted_runner.last_result.status == "success"


def test_runner_rejects_parallel_runs(tmp_path, monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr("webapp.runner.subprocess.run", fake_run)
    runner = Runner(config_path=tmp_path / "config.yaml", state_dir=tmp_path)

    runner._lock.acquire()
    with pytest.raises(RuntimeError):
        runner.run_budgify()
    runner._lock.release()
