"""Local elapsed timing measures only matched phases from one observer lifetime."""

import sqlite3

from gflow_cli.selfhost.captcha import CaptchaStats
from gflow_cli.selfhost.captcha_events import query_events


def test_solver_and_ack_elapsed_samples_are_monotonic_and_provider_scoped(tmp_path, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr("gflow_cli.selfhost.captcha.time.monotonic", lambda: clock[0])
    stats = CaptchaStats(tmp_path)
    stats.record("CapSolver", "solveStarted")
    clock[0] += 1.25
    stats.record("CapSolver", "solved")
    stats.record("CapSolver", "submitted")
    clock[0] += 0.5
    stats.record("CapSolver", "rejected")
    stats.record("2Captcha", "solved")
    value = query_events(tmp_path, limit=10, provider="CapSolver")
    measured = {row["phase"]: row["durationMs"] for row in value["data"] if "durationMs" in row}
    assert measured == {"solved": 1250, "rejected": 500}
    assert value["summary"]["latency"]["solver"]["sampleCount"] == 1
    assert value["summary"]["latency"]["solver"]["averageMs"] == 1250
    assert value["summary"]["latency"]["googleAcknowledgment"]["averageMs"] == 500
    assert value["summary"]["acceptanceRate"] == 0
    assert "durationMs" not in query_events(tmp_path, limit=1, provider="2Captcha")["data"][0]


def test_observers_never_correlate_elapsed_across_instances_or_repeat_terminal(
    tmp_path, monkeypatch
):
    clock = [10.0]
    monkeypatch.setattr("gflow_cli.selfhost.captcha.time.monotonic", lambda: clock[0])
    one = CaptchaStats(tmp_path)
    one.record("CapSolver", "submitted")
    clock[0] += 1
    CaptchaStats(tmp_path).record("CapSolver", "accepted")
    one.record("CapSolver", "unknown")
    one.record("CapSolver", "unknown")
    data = query_events(tmp_path, limit=10)["data"]
    assert "durationMs" not in data[1]
    assert data[2]["durationMs"] == 1000
    assert "durationMs" not in data[3]


def test_legacy_events_migrate_without_inventing_elapsed_samples(tmp_path):
    path = tmp_path / "captcha-stats.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE events(id INTEGER PRIMARY KEY,timestamp TEXT NOT NULL,"
            "provider TEXT NOT NULL,phase TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO events VALUES(1,'2026-10-01T10:00:00.000Z','CapSolver','solved')")
    CaptchaStats(tmp_path)
    result = query_events(tmp_path, limit=10)
    assert "durationMs" not in result["data"][0]
    assert result["summary"]["latency"]["solver"] == {"averageMs": None, "sampleCount": 0}
    assert path.stat().st_mode & 0o077 == 0
